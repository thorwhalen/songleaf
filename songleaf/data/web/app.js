// songleaf page: search the corpus, read a song with its chords, transpose it, print it.
//
// The URL is the state: `?q=..&lyrics=..` is the search view, `?group=<id>` (or
// `?ungrouped=1`) the library narrowed to a group; `?song=<key>` opens a song, with
// `t=<semitones>` (transposition), `view=print` (the PDF) and `layout=<spec>` (a print layout
// chosen by hand; without it the sheet follows the reader's settings).
// Opening a song and choosing a group push a history entry (Back returns to the list, at the
// place it was left); everything done on the song (transpose, layout, view) replaces it. The
// reader's look (size, colours, opacity) is per viewer, kept through `prefs`, the one place
// that touches browser storage.
//
// No music logic lives here: the server sends each key's chord table (`/song`), and the
// page only looks chords up in it.
(function () {
  "use strict";

  const CONFIG = window.SONGLEAF || { api: "", base: "", title: "songleaf" };
  const SEARCH_DEBOUNCE_MS = 300;
  const SLOW_MS = 3000; // past this, say why the wait is long
  const READ_SIZES = { min: 12, max: 56, step: 2 }; // reader lyric size, px
  const PRINT_SCALES = { min: 0.5, max: 2, step: 0.1 }; // PDF size, x the size that fills the page
  const GROUPS_WAIT_MS = 2500; // the library waits this long for the groups before drawing without them
  const PILL_IDLE_MS = 4000; // a paused auto-scroll pill folds back to ▶ after this
  const UNGROUPED = "\u0000ungrouped"; // the library filter "songs in no group" (`?ungrouped=1`)
  // The reader's defaults. The printed sheet's colours and chord size come from the server
  // (/layouts), and the PDF gets only what the viewer changed, so it keeps its own tuning.
  const DEFAULT_LOOK = {
    readSize: 20,
    printScale: 1,
    lyricAlpha: 1,
    chordAlpha: 1,
    chordScale: 0.8, // the reader's chords sit on their own line: larger than the sheet's
    lineHeight: 1.25,
    font: "sans",
    paper: "auto", // "auto" follows the phone's light or dark mode
    chordMode: "above",
    columns: 1,
    shade: false,
  };
  // Papers to read on. Light is the printed sheet's own paper, so its inks are the server's.
  const PAPERS = {
    light: { label: "Light", paper: "#fbfaf7", theme: "light" },
    sepia: { label: "Sepia", paper: "#f4ecd8", ink: "#3b2f1e", chord: "#9a4f12", theme: "light", chorusBand: "#e9d9b4", bridgeBand: "#e0e1d3" },
    dark: { label: "Dark", paper: "#161615", ink: "#e8e6e1", chord: "#7aa7f0", theme: "dark" },
    black: { label: "Black", paper: "#000000", ink: "#f2f2f2", chord: "#8fb8ff", theme: "dark" },
  };
  const FONTS = {
    sans: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
    mono: 'ui-monospace, "SF Mono", Menlo, monospace',
  };
  const percent = (v) => `${Math.round(v * 100)}%`;
  // The reader's look, declared once: the Aa sheet is generated from this table by
  // renderLookSheet (essentials first, the rest under "Fine tuning"), so moving to a settings
  // library (zodal-dials) is a change to these two places only.
  //   widget:   "choice" (one of `choices`), "switch", "color" or "slider" (min, max, step, format)
  //   surfaces: where it applies: "read" (the reader), "print" (the PDF)
  //   ink:      kept per paper (colours read differently on light and dark paper)
  //   redraw:   changing it redraws the song, not only its colours
  const LOOK_SCHEMA = [
    { key: "paper", label: "Paper", widget: "choice", essential: true, surfaces: ["read"], swatches: true,
      choices: () => ({ auto: "Auto", ...Object.fromEntries(Object.entries(PAPERS).map(([k, v]) => [k, v.label])) }) },
    { key: "chordMode", label: "Chords", widget: "choice", essential: true, surfaces: ["read"], redraw: true,
      choices: { above: "Above", inline: "In the line", off: "Off" } },
    { key: "columns", label: "Columns", widget: "choice", essential: true, surfaces: ["read"], redraw: true,
      choices: { 1: "One", 2: "Two" }, parse: Number },
    { key: "shade", label: "Shade choruses", widget: "switch", essential: true, surfaces: ["read"], redraw: true },
    { key: "lyricColor", label: "Lyrics colour", widget: "color", ink: true, surfaces: ["read", "print"] },
    { key: "lyricAlpha", label: "Lyrics opacity", widget: "slider", min: 0.1, max: 1, step: 0.05, format: percent, surfaces: ["read", "print"] },
    { key: "chordColor", label: "Chords colour", widget: "color", ink: true, surfaces: ["read", "print"] },
    { key: "chordAlpha", label: "Chords opacity", widget: "slider", min: 0.1, max: 1, step: 0.05, format: percent, surfaces: ["read", "print"] },
    { key: "chordScale", label: "Chord size", widget: "slider", min: 0.4, max: 1.3, step: 0.05, format: percent, surfaces: ["read"] },
    { key: "printChordScale", label: "Chord size", widget: "slider", min: 0.4, max: 1.3, step: 0.05, format: percent, surfaces: ["print"] },
    { key: "lineHeight", label: "Line spacing", widget: "slider", min: 1, max: 2, step: 0.05, format: (v) => v.toFixed(2), surfaces: ["read"] },
    { key: "font", label: "Font", widget: "choice", surfaces: ["read"], fontPreview: true,
      choices: { sans: "Sans", serif: "Serif", mono: "Mono" } },
  ];
  const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const app = document.getElementById("app");
  let generation = 0; // bumps on every render: a late response from an older view is dropped
  let searchTimer = null; // the pending debounced search; a view change cancels it
  let options = null; // /layouts: {options: [{name, sets}], style, limits}, fetched once
  let openPanel = null; // the toolbar panel that is open ("key", "look"), kept across re-renders
  const songCache = new Map(); // key -> /song response, for this page's lifetime

  // --- prefs: per-viewer settings. The only browser storage on the page. ---------------

  const prefs = (function () {
    const STORAGE_KEY = "songleaf:prefs";
    let values = {};
    try {
      values = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (_) { /* private mode or blocked storage: defaults it is */ }
    const isObject = (x) => x && typeof x === "object" && !Array.isArray(x);
    if (!isObject(values)) values = {};
    if (!isObject(values.look)) delete values.look;
    const look = values.look || {};
    if (look.lyricColor || look.chordColor) { // before papers, colours were for light paper
      look.inks = { ...(look.inks || {}), light: { lyricColor: look.lyricColor, chordColor: look.chordColor } };
      delete look.lyricColor;
      delete look.chordColor;
    }
    function save() {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(values)); } catch (_) { /* not kept */ }
    }
    return {
      // Everything the page draws with, resolved: the paper in use and its inks included.
      look(paper) {
        const saved = values.look || {};
        const auto = darkQuery && darkQuery.matches ? "dark" : "light";
        const paperName = PAPERS[paper] ? paper : PAPERS[saved.paper] ? saved.paper : auto;
        const palette = PAPERS[paperName];
        const server = (options && options.style) || {};
        const inks = (saved.inks || {})[paperName] || {};
        return {
          ...DEFAULT_LOOK,
          printChordScale: server.chord_scale || 0.62, // the sheet's own, until the viewer changes it
          ...saved,
          paperName,
          palette,
          lyricColor: inks.lyricColor || palette.ink || server.lyric_color || "#000000",
          chordColor: inks.chordColor || palette.chord || server.chord_color || "#3b73c4",
        };
      },
      setLook(changes) { values.look = { ...(values.look || {}), ...changes }; save(); },
      setInk(paperName, changes) {
        const saved = { ...(values.look || {}) };
        saved.inks = { ...(saved.inks || {}), [paperName]: { ...((saved.inks || {})[paperName] || {}), ...changes } };
        values.look = saved;
        save();
      },
      // Back to the defaults for `keys` (what "Fine tuning" shows): one paper's inks among
      // them. The paper and the essentials stay.
      resetLook(paperName, keys) {
        const saved = { ...(values.look || {}) };
        for (const name of keys) delete saved[name];
        if (saved.inks && saved.inks[paperName]) {
          const inks = { ...saved.inks[paperName] };
          for (const name of keys) delete inks[name];
          saved.inks = { ...saved.inks, [paperName]: inks };
        }
        values.look = saved;
        save();
      },
      // The /sheet parameters the viewer's settings give: only what they changed, and the
      // inks chosen for light paper (a PDF is printed on white).
      printParams() {
        const saved = values.look || {};
        const light = (saved.inks || {}).light || {};
        const out = {};
        if (light.lyricColor) out.lyric_color = light.lyricColor;
        if (light.chordColor) out.chord_color = light.chordColor;
        const numeric = { lyricAlpha: "lyric_alpha", chordAlpha: "chord_alpha", printChordScale: "chord_scale" };
        for (const [name, param] of Object.entries(numeric)) if (name in saved) out[param] = String(saved[name]);
        return out;
      },
      forgetSong(key) { // a deleted song leaves no settings behind
        for (const name of ["transpose", "scroll"]) if (values[name]) delete values[name][key];
        save();
      },
      scrollLevelOf(key) { return (values.scroll || {})[key] || values.scrollDefault || 5; },
      setScrollLevel(key, level) {
        values.scroll = { ...(values.scroll || {}), [key]: level };
        values.scrollDefault = level; // a new song starts at the last speed used
        save();
      },
      transposeOf(key) { return (values.transpose || {})[key] || 0; },
      setTranspose(key, t) {
        values.transpose = { ...(values.transpose || {}) };
        if (t) values.transpose[key] = t; else delete values.transpose[key];
        save();
      },
    };
  })();

  // --- auto-scroll: the page moves at a steady speed while you play --------------------

  // Speed is a level from 1 to SCROLL_LEVELS; a level is a fraction of the reading size per
  // second, so larger type scrolls proportionally faster and a line passes at the same pace.
  const SCROLL_LEVELS = 12;
  const SCROLL_PER_LEVEL = 0.12; // reading sizes per second, per level
  const autoScroll = (function () {
    let running = false;
    let frame = 0;
    let last = 0;
    let position = 0; // fractional: the browser places it to the device pixel, so slow is smooth
    let wakeLock = null;
    let level = 5;
    let pxPerLevel = 2.4;
    const listeners = new Set();
    const notify = () => listeners.forEach((f) => f(running));
    async function keepAwake() {
      if (!navigator.wakeLock) return;
      let lock = null;
      try { lock = await navigator.wakeLock.request("screen"); } catch (_) { return; }
      if (!running) { lock.release().catch(() => {}); return; } // paused while the request was out
      if (wakeLock) wakeLock.release().catch(() => {});
      wakeLock = lock;
    }
    function step(now) {
      if (!running) return;
      const seconds = last ? Math.min((now - last) / 1000, 0.1) : 0; // a background tab never jumps
      last = now;
      if (Math.abs(window.scrollY - position) > 3) position = window.scrollY; // moved by something else: go on from there
      position += level * pxPerLevel * seconds;
      window.scrollTo(0, position);
      const bottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      if (bottom) { stop(); return; }
      frame = requestAnimationFrame(step);
    }
    function start() {
      if (running) return;
      running = true; last = 0; position = window.scrollY;
      keepAwake();
      frame = requestAnimationFrame(step);
      notify();
    }
    function stop() {
      if (!running) return;
      running = false;
      cancelAnimationFrame(frame);
      if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
      notify();
    }
    // A touch, the wheel or a scrolling key means the reader took over: pause.
    const isControl = (target) => target.closest && target.closest(".toolbar-wrap, .scroll-pill, input, select, textarea");
    for (const type of ["touchstart", "wheel", "mousedown"]) window.addEventListener(type, (e) => {
      if (running && !isControl(e.target)) stop();
    }, { passive: true });
    window.addEventListener("keydown", (e) => {
      const scrolls = ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(e.key);
      if (running && scrolls && !isControl(e.target)) stop();
    });
    document.addEventListener("visibilitychange", () => { if (running && document.visibilityState === "visible") keepAwake(); });
    return {
      start, stop,
      toggle() { if (running) stop(); else start(); },
      get running() { return running; },
      configure(next) { level = next.level; pxPerLevel = next.readSize * SCROLL_PER_LEVEL; },
      onChange(f) { listeners.add(f); return () => listeners.delete(f); },
    };
  })();

  // --- groups: the library's groups, a zodal-groups space shared through the server ----

  // Songs and groups are nodes; a membership is an edge (zodal-groups, profile "labels": a
  // song can be in several groups, and groups can hold groups). The page edits a local space
  // and saves its snapshot in the background, from the revision it was loaded at.
  //
  // What is kept until saved is not the deltas but the *intents* they carry: "S into G",
  // "S out of G". When someone else saved first (409), or a reload brings newer groups, the
  // page starts from those and replays its intents one by one: one already true is skipped,
  // one about a song deleted meanwhile is dropped, and one the profile refuses is counted.
  // Song nodes exist here only for their titles (labels); they are never saved.
  const groups = (function () {
    let zg = null; // the zodal-groups module, loaded on first use
    let space = null; // the live Groups handle
    let revision = 0;
    let intents = []; // [{op: "add" | "remove", parent, child}] not yet saved, oldest first
    let edgesById = new Map(); // id -> {parent, child}: what a "removed" edge id meant
    let saveTimer = null;
    let saving = null; // the save in flight (a promise)
    let retryDelay = 0;
    let blocked = ""; // why saving stopped ("" while it works)
    let rebuilds = 0; // bumps when the space is replaced: a save in flight then re-saves
    let unsubscribe = null;
    let labels = new Map(); // stored song key -> "Title · Artist"
    const listeners = new Set();
    const notify = (event) => listeners.forEach((f) => f(event));

    async function library() {
      if (!zg) {
        document.head.append(h("link", { rel: "stylesheet", href: CONFIG.api + "/ui/vendor/zodal-groups.css" }));
        zg = await import(CONFIG.api + "/ui/vendor/zodal-groups.js");
      }
      return zg;
    }
    function setSongs(songs) {
      labels = new Map(songs.map((s) => [s.key, [s.title, s.artist].filter(Boolean).join(" · ") || s.key]));
    }
    // A new space from a snapshot, or an Error: the current one is untouched until it works.
    function build(snapshot) {
      const nodes = snapshot.nodes.map((n) => (labels.has(n.id) ? { ...n, label: labels.get(n.id) } : n));
      const present = new Set(nodes.map((n) => n.id));
      for (const [key, label] of labels) if (!present.has(key)) nodes.push({ id: key, label });
      return zg.defineGroups({ profile: "labels", nodes, edges: snapshot.edges });
    }
    function swap(next) {
      if (unsubscribe) unsubscribe();
      space = next;
      edgesById = new Map([...space.space.edges.values()].map((e) => [e.id, { parent: e.parent, child: e.child }]));
      unsubscribe = space.subscribe(({ delta }) => {
        for (const e of delta.added || []) {
          intents.push({ op: "add", parent: e.parent, child: e.child });
          edgesById.set(e.id, { parent: e.parent, child: e.child });
        }
        for (const id of delta.removed || []) {
          const e = edgesById.get(id);
          if (e) intents.push({ op: "remove", parent: e.parent, child: e.child });
          edgesById.delete(id);
        }
        schedule();
        notify({ type: "change" });
      });
    }
    const isIn = (child, parent) => space.parents(child).includes(parent);
    const known = (id, snapshot) => labels.has(id) || snapshot.nodes.some((n) => n.id === id) || snapshot.edges.some((e) => e.parent === id);
    // Start from `doc` and replay what this page did that it has not saved.
    function adopt(doc) {
      let next;
      try {
        next = build(doc.snapshot);
      } catch (error) {
        notify({ type: "error", message: `The saved groups could not be read (${error.message}).`, fatal: true });
        return false;
      }
      const mine = intents;
      intents = [];
      revision = doc.revision;
      rebuilds += 1;
      swap(next);
      let refused = 0;
      for (const it of mine) {
        if (!known(it.child, doc.snapshot)) { refused += 1; continue; } // a song deleted meanwhile
        if (it.op === "add") {
          if (!isIn(it.child, it.parent) && !space.add(it.child, it.parent).ok) refused += 1;
        } else if (isIn(it.child, it.parent) && !space.remove(it.child, it.parent).ok) {
          refused += 1;
        }
      }
      notify({ type: "rebuilt" });
      return { replayed: mine.length, refused };
    }
    // (Re)load: on every library view and song page, so the other person's changes show.
    async function load(songs) {
      await library();
      const before = [...labels.keys()].join("\n");
      setSongs(songs);
      const asked = revision;
      const doc = await getJSON("/groups");
      if (space && doc.revision < revision) return space; // our own newer save landed meanwhile
      const sameSongs = before === [...labels.keys()].join("\n");
      if (space && doc.revision === asked && doc.revision === revision && sameSongs) return space; // nothing new
      if (blocked && blocked !== "session") { intents = []; blocked = ""; } // a refused change is not replayed forever
      const outcome = adopt(doc);
      if (outcome && outcome.replayed) schedule(0);
      return space;
    }
    function schedule(delay = 400) {
      if (blocked) return;
      clearTimeout(saveTimer);
      saveTimer = setTimeout(save, delay);
    }
    function snapshotToSave() {
      const snapshot = zg.toSnapshot(space.space);
      return { nodes: snapshot.nodes.filter((n) => !labels.has(n.id)), edges: snapshot.edges }; // songs: labels only
    }
    async function save({ keepalive = false } = {}) {
      if (saving) { await saving; if (intents.length) schedule(); return; }
      if (!intents.length || blocked) return;
      const sent = intents.length;
      const epoch = rebuilds;
      const body = JSON.stringify({ revision, snapshot: snapshotToSave() });
      saving = (async () => {
        let response;
        try {
          response = await fetch(CONFIG.api + "/groups", {
            method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body,
            keepalive: keepalive && body.length < 60000, // a save as the page goes away
          });
        } catch (_) {
          return retry("The groups could not be saved: no connection. Trying again…");
        }
        if (response.status === 409) {
          const current = (await response.json()).current;
          try { setSongs(await getJSON("/songs")); } catch (_) { /* titles may lag; the server drops deleted songs */ }
          const outcome = adopt(current);
          if (outcome) {
            notify({ type: "merged", refused: outcome.refused });
            if (intents.length) schedule(0);
          }
          return;
        }
        if (response.ok) {
          revision = (await response.json()).revision;
          if (epoch === rebuilds) intents = intents.slice(sent); // what changed during the save is saved next
          // else the space was rebuilt meanwhile: keep the replayed intents and save once more
          retryDelay = 0;
          notify({ type: "saved" });
          if (intents.length) schedule();
          return;
        }
        const detail = await errorText(response);
        if (response.status >= 500) return retry(`The groups could not be saved (${detail}). Trying again…`);
        blocked = response.status === 401 || response.status === 403 ? "session" : "refused";
        notify({
          type: "error",
          message: blocked === "session"
            ? "Your sign-in has expired: reload the page to keep changing groups."
            : `That change to the groups was refused (${detail}); it will be undone when the groups reload.`,
        });
      })();
      try { await saving; } finally { saving = null; }
    }
    function retry(message) {
      retryDelay = Math.min(retryDelay ? retryDelay * 2 : 5000, 60000);
      notify({ type: "error", message });
      schedule(retryDelay);
    }
    function songsIn(group) {
      return space ? space.members(group, { expand: "closure" }).filter((id) => labels.has(id)) : [];
    }
    return {
      load,
      get space() { return space; },
      get zg() { return zg; },
      // The groups (nodes that are not songs and hold something), with how many songs each
      // holds, nested groups included.
      list() {
        if (!space) return [];
        return [...space.space.nodes.keys()]
          .filter((id) => !labels.has(id) && space.children(id).length)
          .map((id) => ({ id, label: (space.space.nodes.get(id) || {}).label || id, count: songsIn(id).length }))
          .sort((a, b) => a.label.localeCompare(b.label));
      },
      songsIn,
      // The groups a song (or a group) is directly in.
      groupsOf(key) { return space ? space.parents(key).filter((id) => !labels.has(id)) : []; },
      labelOf(id) { return (space && (space.space.nodes.get(id) || {}).label) || id; },
      isSong(id) { return labels.has(id); },
      onChange(f) { listeners.add(f); return () => listeners.delete(f); },
      flush() { if (intents.length && !blocked) { clearTimeout(saveTimer); save({ keepalive: true }); } },
    };
  })();
  window.addEventListener("pagehide", () => groups.flush()); // last chance to save

  // A small message at the bottom of the screen: a filing done, a save that failed, a merge.
  function toast(text) {
    const old = document.querySelector(".toast");
    if (old) old.remove();
    const el = h("div", { class: "toast", role: "status" }, text);
    document.body.append(el);
    setTimeout(() => el.remove(), 5000);
  }
  let lastToast = "";
  groups.onChange((event) => {
    if (event.type === "error" && event.message !== lastToast) { lastToast = event.message; toast(event.message); }
    else if (event.type === "saved") lastToast = "";
    else if (event.type === "merged") {
      toast(event.refused
        ? `The groups were changed elsewhere; ${event.refused} of your changes no longer applied.`
        : "The groups were changed elsewhere; your changes were added to them.");
    }
  });

  // --- the route: one module owns history ------------------------------------------------

  function readRoute() {
    const params = new URLSearchParams(location.search);
    const song = params.get("song") || "";
    const t = params.has("t") ? Math.round(Number(params.get("t"))) || 0 : (song ? prefs.transposeOf(song) : 0);
    return {
      q: params.get("q") || "",
      lyrics: params.get("lyrics") || "",
      group: params.get("ungrouped") ? UNGROUPED : params.get("group") || "",
      song,
      t,
      view: params.get("view") === "print" ? "print" : "read",
      layout: params.get("layout") || "", // "": the reader's settings decide
    };
  }

  // One spelling per route: the params in a fixed order, defaults left out.
  function formatRoute(route) {
    const params = new URLSearchParams();
    if (route.song) {
      params.set("song", route.song);
      if (route.t) params.set("t", String(route.t));
      if (route.view === "print") params.set("view", "print");
      if (route.layout) params.set("layout", route.layout);
    } else {
      if (route.q) params.set("q", route.q);
      if (route.lyrics) params.set("lyrics", route.lyrics);
      if (route.group === UNGROUPED) params.set("ungrouped", "1");
      else if (route.group) params.set("group", route.group);
    }
    const query = params.toString();
    return location.pathname + (query ? "?" + query : "");
  }

  function navigate(route, { replace = false, state = {} } = {}) {
    const url = formatRoute(route);
    if (replace || url === location.pathname + location.search) history.replaceState(state, "", url);
    else history.pushState(state, "", url);
    render();
  }

  // The page redraws a list it returns to, so the browser cannot put the scroll back: the
  // entry being left keeps its scroll, and the list restores it once drawn.
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  function rememberScroll() {
    history.replaceState({ ...(history.state || {}), scrollY: window.scrollY }, "", location.href);
  }
  const savedScroll = () => (history.state && typeof history.state.scrollY === "number" ? history.state.scrollY : null);

  window.addEventListener("popstate", () => {
    // Back or Forward between two groups of the library on screen: refine it in place.
    const route = readRoute();
    if (!route.song && !route.q && !route.lyrics && activeLibrary && activeLibrary.element.isConnected) {
      activeLibrary.setGroup(route.group);
      window.scrollTo(0, savedScroll() || 0);
      return;
    }
    render();
  });

  // --- tiny DOM helpers (text only goes in through textContent) -------------------------

  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value === false || value == null) continue;
      if (name.startsWith("on")) el.addEventListener(name.slice(2), value);
      else if (value === true) el.setAttribute(name, "");
      else el.setAttribute(name, value);
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  async function getJSON(path) {
    const response = await fetch(CONFIG.api + path, { credentials: "same-origin" });
    if (!response.ok) throw new Error(await errorText(response));
    return response.json();
  }

  async function errorText(response) {
    try {
      const body = await response.json();
      if (body && body.detail) return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (_) { /* not JSON */ }
    return `${response.status} ${response.statusText}`;
  }

  async function getOptions() {
    if (!options) options = await getJSON("/layouts");
    return options;
  }

  function loading(label, slowNote) {
    const note = slowNote && h("p", { class: "muted slow", hidden: true }, slowNote);
    const timer = note && setTimeout(() => { note.hidden = false; }, SLOW_MS);
    const box = h("div", { class: "loading", "aria-busy": "true" }, h("span", { class: "spinner" }), label, note);
    box.stop = () => clearTimeout(timer);
    return box;
  }

  function errorBox(message, retry) {
    return h("div", { class: "error", role: "alert" },
      h("p", {}, message),
      retry && h("button", { type: "button", onclick: retry }, "Try again"));
  }

  function rgba(hex, alpha) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  // --- views -----------------------------------------------------------------------------

  let shownView = ""; // the song and view on screen: redrawing the same one keeps the scroll going
  let firstRender = true; // the page was just opened (not reached with Back)
  function render() {
    const next = readRoute();
    const view = next.song ? `${next.song}|${next.view}` : "";
    if (view !== shownView) autoScroll.stop(); // a new song, or Print, never inherits the motion
    shownView = view;
    while (scrollUnsubscribers.length) scrollUnsubscribers.pop()(); // toolbars about to be replaced
    clearTimeout(searchTimer); // a search typed just before leaving must not fire on the next view
    generation += 1;
    applyLook(prefs.look()); // the paper (light or dark) is the whole page's, search included
    const route = readRoute();
    const fresh = firstRender;
    firstRender = false;
    if (route.song) renderSong(route, generation);
    else renderSearch(route, generation, fresh);
  }

  // ----- search --------------------------------------------------------------------------

  function renderSearch(route, gen, fresh) {
    activeLibrary = null;
    const restoreY = savedScroll(); // set when this entry was left for a song or a group
    if (restoreY === null) window.scrollTo(0, 0);
    document.title = route.q || route.lyrics ? `${route.q || route.lyrics} · ${CONFIG.title}` : CONFIG.title;
    const results = h("section", { class: "results", "aria-live": "polite" });
    // A refinement replaces the URL and refreshes the results only: the inputs stay as
    // they are, so typing (and a phone's keyboard) is never interrupted.
    const refine = () => {
      clearTimeout(searchTimer);
      const next = { q: query.value.trim(), lyrics: lyrics.value.trim(), group: readRoute().group };
      history.replaceState({}, "", formatRoute(next));
      document.title = next.q || next.lyrics ? `${next.q || next.lyrics} · ${CONFIG.title}` : CONFIG.title;
      generation += 1;
      showResults(next, results, generation, { clear });
    };
    const clear = (input) => { input.value = ""; refine(); };
    const onInput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(refine, SEARCH_DEBOUNCE_MS);
    };
    const query = h("input", {
      type: "search", name: "q", value: route.q, placeholder: "Title or artist",
      "aria-label": "Title or artist", autocomplete: "off", enterkeyhint: "search", oninput: onInput,
    });
    const lyrics = h("input", {
      type: "search", name: "lyrics", value: route.lyrics, placeholder: "Words in the lyrics",
      "aria-label": "Words in the lyrics", autocomplete: "off", enterkeyhint: "search", oninput: onInput,
    });
    const form = h("form", { class: "search", role: "search", onsubmit: (e) => { e.preventDefault(); refine(); query.blur(); lyrics.blur(); } },
      query, lyrics);
    app.replaceChildren(h("header", {}, h("h1", {}, CONFIG.title)), form, results);
    // Focus the search only on a fresh page with nothing in the library: never on Back, where
    // a phone would raise its keyboard over the list the reader came back to.
    showResults(route, results, gen, {
      clear: (name) => clear(name === "lyrics" ? lyrics : query),
      restoreY,
      onEmpty: fresh && restoreY === null ? () => query.focus() : null,
    });
  }

  function showResults(route, results, gen, after = {}) {
    if (route.q || route.lyrics) showHits(route, results, gen, after);
    else showStored(results, gen, route, after);
  }

  // What was searched, in words, for the message that says nothing matched.
  function noMatch(route, clear) {
    const quoted = (text) => `“${text}”`;
    const message = route.q && route.lyrics
      ? `No song has ${quoted(route.q)} in its title or artist and ${quoted(route.lyrics)} in its lyrics.`
      : route.q
        ? `No song has ${quoted(route.q)} in its title or artist. Try fewer words, or check the spelling.`
        : `No song has the words ${quoted(route.lyrics)} in its lyrics. Try fewer words.`;
    // Offer to relax the narrower field: the lyrics when both are set.
    const relax = route.q && route.lyrics ? ["lyrics", "Search without the lyrics"] : null;
    return h("div", { class: "empty" }, h("p", { class: "muted" }, message),
      relax && clear && h("button", { type: "button", class: "text", onclick: () => clear(relax[0]) }, relax[1]));
  }

  async function showHits(route, results, gen, after = {}) {
    const spinner = loading("Searching…", "The first search after a restart loads the song index, which takes a few seconds.");
    results.replaceChildren(spinner);
    const params = new URLSearchParams({ q: route.q, lyrics: route.lyrics, limit: "25" });
    try {
      const hits = await getJSON("/search?" + params);
      if (gen !== generation) return;
      results.replaceChildren(hits.length ? songList(hits) : noMatch(route, after.clear));
      if (after.restoreY != null) window.scrollTo(0, after.restoreY);
    } catch (error) {
      if (gen !== generation) return;
      results.replaceChildren(errorBox(`The search did not go through (${error.message}).`,
        () => { generation += 1; showHits(route, results, generation, after); }));
    } finally {
      spinner.stop();
    }
  }

  // Grey rows in the shape of the list, while it loads: the list then replaces them in place.
  function librarySkeleton() {
    return h("div", { class: "library", "aria-busy": "true" },
      h("div", { class: "library-head" }, h("h2", {}, "Your songs")),
      h("ul", { class: "songs skeleton", "aria-label": "Loading your songs" },
        Array.from({ length: 6 }, (_, i) => h("li", {},
          h("span", { class: "bar", style: `width:${[46, 62, 38, 54, 44, 58][i]}%` }),
          h("span", { class: "bar short" })))));
  }

  // The library draws once, when the songs and their groups are both in (or the groups are
  // late: then it draws without them, and they appear when they arrive).
  async function showStored(results, gen, route, after = {}) {
    results.replaceChildren(librarySkeleton());
    const retry = () => { generation += 1; showStored(results, generation, readRoute(), after); };
    let songs;
    try {
      songs = await getJSON("/songs");
    } catch (error) {
      if (gen !== generation) return;
      results.replaceChildren(errorBox(`Your songs could not be loaded (${error.message}).`, retry));
      return;
    }
    if (gen !== generation) return;
    if (!songs.length) {
      results.replaceChildren(h("p", { class: "muted" }, "Search by title or artist, or by words of the lyrics. The songs you open are kept here."));
      if (after.onEmpty) after.onEmpty();
      return;
    }
    let groupsError = null;
    await Promise.race([
      groups.load(songs).catch((error) => { groupsError = error; }),
      new Promise((resolve) => setTimeout(resolve, GROUPS_WAIT_MS)),
    ]);
    if (gen !== generation) return;
    const shelf = library(songs, retry, route);
    results.replaceChildren(shelf.element);
    activeLibrary = shelf;
    if (groupsError) toast(`The groups could not be loaded (${groupsError.message}). The songs are all here.`);
    if (after.restoreY != null) window.scrollTo(0, after.restoreY);
  }

  // Group navigation as chips: All · the top groups · Ungrouped, and under a chosen group that
  // holds groups, a row of those (a drill-down: a row per level of the path). Local on purpose:
  // zodal-groups is getting a drill-down chip widget, and this is the one function to swap for
  // it. `model` is what it reads (see groupModel); `value` is a group id, "" for all songs, or
  // UNGROUPED; `onPick(value)` is called for a deliberate change.
  function renderGroupChips(host, model, { value, onPick }) {
    const path = model.pathTo(value);
    const chip = (id, text, n, checked) => h("button", {
      type: "button", role: "radio", class: "chip", "aria-checked": String(checked),
      onclick: () => { if (id !== value) onPick(id); },
    }, text, h("span", { class: "count" }, String(n)));
    const rows = [h("div", { class: "chip-row", role: "radiogroup", "aria-label": "Show" },
      chip("", "All", model.total, value === ""),
      model.roots().map((g) => chip(g.id, g.label, g.count, path[0] === g.id)),
      model.ungrouped && chip(UNGROUPED, "Ungrouped", model.ungrouped, value === UNGROUPED))];
    path.forEach((id, depth) => {
      const subs = model.subgroups(id);
      if (!subs.length) return;
      const here = model.find(id);
      rows.push(h("div", { class: "chip-row sub", role: "radiogroup", "aria-label": `In ${here.label}` },
        chip(id, `All of ${here.label}`, here.count, value === id),
        subs.map((g) => chip(g.id, g.label, g.count, path[depth + 1] === g.id))));
    });
    host.replaceChildren(...rows);
    for (const row of rows) { // a chosen chip scrolled out of its row (a reload, Back) comes into view
      const on = row.querySelector('[aria-checked="true"]');
      if (on && on.offsetLeft + on.offsetWidth > row.scrollLeft + row.clientWidth) row.scrollLeft = on.offsetLeft - 16;
    }
  }

  // What the group chips read: the groups as a hierarchy, with how many songs each holds.
  function groupModel(songs) {
    const list = groups.list();
    const byId = new Map(list.map((g) => [g.id, g]));
    const parentsOf = (id) => groups.groupsOf(id).filter((p) => byId.has(p));
    return {
      total: songs.length,
      ungrouped: list.length ? songs.filter((s) => !groups.groupsOf(s.key).length).length : 0,
      find: (id) => byId.get(id),
      roots: () => list.filter((g) => !parentsOf(g.id).length),
      subgroups: (id) => list.filter((g) => parentsOf(g.id).includes(id)),
      // From a top group down to `id`, through the first parent at each level (a group in
      // several groups is reached through one of them); [] for all songs and Ungrouped.
      pathTo(id) {
        const path = [];
        for (let at = id; at && byId.has(at) && !path.includes(at); at = parentsOf(at)[0]) path.unshift(at);
        return path;
      },
    };
  }

  // File songs into groups: the zodal-groups tag menu over `keys`, staged until Apply (the
  // same menu from the library's Group… and from a song's page). It closes after an Apply that
  // went through, and a toast says what changed.
  const coarsePointer = window.matchMedia ? window.matchMedia("(pointer: coarse)") : null;
  function openTagMenu(host, keys, { onClose = () => {} } = {}) {
    if (!groups.space || !keys.length) return null;
    const handle = groups.space;
    const atOpen = handle.space;
    const before = new Map(keys.map((k) => [k, new Set(groups.groupsOf(k))]));
    const panel = h("div", { class: "panel group-menu" });
    host.replaceChildren(panel);
    let menu = null;
    const close = () => {
      if (!menu) return;
      const open = menu;
      menu = null;
      open.destroy();
      host.replaceChildren();
      onClose();
    };
    menu = groups.zg.renderTagMenu(panel, handle, {
      selection: keys,
      candidates: () => groups.list().map((g) => g.id), // groups only: never a song
      label: keys.length === 1 ? "Groups of this song" : `Groups of ${keys.length} songs`,
      autoFocus: !(coarsePointer && coarsePointer.matches), // a phone would cover the menu with its keyboard
      onClose: close,
      onChange: () => {
        // After an Apply: the space moved on and nothing is left staged.
        if (!menu || groups.space !== handle || handle.space === atOpen || menu.session.state.pending.size) return;
        const sentence = filingSentence(keys, before);
        setTimeout(close, 0); // let the menu finish its own update first
        if (sentence) toast(sentence);
      },
    });
    return { close, get open() { return !!menu; } };
  }

  // "Added to To learn, removed from Campfire.": what a filing changed, from before and after.
  function filingSentence(keys, before) {
    const added = new Set();
    const removed = new Set();
    for (const key of keys) {
      const now = new Set(groups.groupsOf(key));
      for (const g of now) if (!before.get(key).has(g)) added.add(g);
      for (const g of before.get(key)) if (!now.has(g)) removed.add(g);
    }
    const names = (ids) => [...ids].map((id) => groups.labelOf(id)).join(", ");
    const parts = [];
    if (added.size) parts.push(`added to ${names(added)}`);
    if (removed.size) parts.push(`removed from ${names(removed)}`);
    if (!parts.length) return "";
    const who = keys.length === 1 ? "" : `${keys.length} songs `;
    const text = who + parts.join(", ");
    return text.charAt(0).toUpperCase() + text.slice(1) + ".";
  }

  // Your songs: one list, narrowed by the group chips (the chosen group is in the URL), and an
  // Edit mode to pick songs and group or delete them. On a wide screen, "Arrange groups" holds
  // the zodal-groups tree, for dragging a song or a group onto a group (nesting groups is done
  // there). A change to the groups redraws the counts and the list; a rebuilt space (a reload,
  // a merge) re-binds everything to the new one.
  let activeLibrary = null; // the library on screen, refined in place by Back between groups
  const wideScreen = window.matchMedia ? window.matchMedia("(min-width: 700px)") : null;
  if (wideScreen && wideScreen.addEventListener) {
    wideScreen.addEventListener("change", () => { if (activeLibrary && activeLibrary.element.isConnected) activeLibrary.redraw(); });
  }
  function library(songs, refresh, route) {
    const selected = new Set();
    let editing = false;
    let busy = false;
    let group = route.group || "";
    let tree = null; // the arrange tree, kept across data redraws so expanded groups stay open
    let menu = null; // the tag menu, while open
    const listHost = h("div");
    const navHost = h("nav", { class: "group-nav", "aria-label": "Groups" });
    const menuHost = h("div", { class: "group-menu-host" });
    const arrangeHost = h("div");
    const count = h("span", { class: "muted" });
    const remove = h("button", {
      type: "button", class: "danger", disabled: true,
      onclick: async () => {
        if (busy) return;
        const keys = [...selected]; // what was confirmed is what is deleted
        const one = keys.length === 1 && songs.find((s) => s.key === keys[0]);
        const what = one ? `“${one.title || one.key}”` : `these ${keys.length} songs`;
        if (!window.confirm(`Delete ${what} from your songs? Search finds ${one ? "it" : "them"} again.`)) return;
        busy = true;
        listHost.inert = true; edit.disabled = true; // nothing changes while deleting
        remove.disabled = true; label.disabled = true;
        remove.textContent = "Deleting…";
        let failed = 0;
        for (const key of keys) {
          try {
            const response = await fetch(CONFIG.api + "/songs?" + new URLSearchParams({ key }), { method: "DELETE", credentials: "same-origin" });
            if (response.ok || response.status === 404) prefs.forgetSong(key);
            else failed += 1;
          } catch (_) {
            failed += 1;
          }
        }
        if (failed) window.alert(`${failed} could not be deleted. Check the connection and try again.`);
        refresh();
      },
    }, "Delete");
    const label = h("button", {
      type: "button", class: "secondary-button", disabled: true,
      onclick: () => { menu = openTagMenu(menuHost, [...selected], { onClose: () => { menu = null; redraw(); } }); },
    }, "Group…");
    const actions = h("div", { class: "edit-actions", hidden: true }, count, h("div", { class: "edit-buttons" }, label, remove));
    const edit = h("button", {
      type: "button", class: "text",
      onclick: () => { editing = !editing; selected.clear(); draw(); },
    });

    const sync = () => {
      count.textContent = selected.size ? `${selected.size} selected` : "Pick songs";
      remove.disabled = busy || !selected.size;
      label.disabled = busy || !selected.size || !groups.space;
    };
    function shown() { // the songs the chosen group lets through, in library order
      if (!group || !groups.space) return songs;
      if (group === UNGROUPED) return songs.filter((s) => !groups.groupsOf(s.key).length);
      const keep = new Set(groups.songsIn(group));
      return songs.filter((s) => keep.has(s.key));
    }
    function drawNav() {
      const model = groupModel(songs);
      const known = group === UNGROUPED ? model.ungrouped > 0 : !group || model.find(group);
      if (groups.space && !known) { // a group emptied or renamed elsewhere: show all, and say so in the URL
        group = "";
        history.replaceState(history.state, "", formatRoute({ group: "" }));
      }
      navHost.hidden = !groups.list().length;
      if (navHost.hidden) navHost.replaceChildren();
      else renderGroupChips(navHost, model, { value: group, onPick: pick });
    }
    // A deliberate change of group is a history entry: Back undoes it, a reload keeps it.
    function pick(id) {
      rememberScroll();
      history.pushState({}, "", formatRoute({ group: id }));
      setGroup(id);
    }
    function setGroup(id) {
      group = id || "";
      redraw();
    }
    function emptyNote() {
      const text = group === UNGROUPED ? "Every song is in a group." : `No songs in ${groups.labelOf(group)} yet.`;
      return h("div", { class: "empty" }, h("p", { class: "muted" }, text),
        h("button", { type: "button", class: "text", onclick: () => pick("") }, "Show all songs"));
    }
    function drawList() {
      const items = shown();
      const visible = new Set(items.map((s) => s.key));
      for (const key of [...selected]) if (!visible.has(key)) selected.delete(key); // never act on a hidden song
      if (!items.length) listHost.replaceChildren(emptyNote());
      else listHost.replaceChildren(editing ? pickList(items, selected, sync) : songList(items));
    }
    function drawArrange() {
      if (!wideScreen || !wideScreen.matches || !groups.space || !groups.list().length) {
        tree = null;
        arrangeHost.replaceChildren();
        return;
      }
      if (tree && tree.space === groups.space) { tree.renderer.render(); return; }
      const host = h("div", { class: "group-tree" });
      const details = h("details", { class: "arrange", ontoggle: () => { arrangeOpen = details.open; } },
        h("summary", {}, "Arrange groups"),
        h("p", { class: "muted hint" }, "Drag a song or a group onto a group to add it there. Tap a song to open it."),
        host);
      details.open = arrangeOpen;
      const renderer = groups.zg.renderTree(host, groups.space, {
        onSelect: (id) => { const song = songs.find((s) => s.key === id); if (song) openSong(song); },
        onChange: () => {},
      });
      tree = { space: groups.space, renderer };
      arrangeHost.replaceChildren(details);
    }
    function openSong(song) {
      rememberScroll();
      navigate({ song: song.key, t: prefs.transposeOf(song.key) }, { state: { from: "search", title: song.title, artist: song.artist } });
    }
    // Counts, chips, list and tree: after any change to the groups. The menu stays.
    function redraw() {
      drawNav();
      drawList();
      drawArrange();
      sync();
    }
    // Everything: after a mode switch, and when the space is rebuilt.
    function draw() {
      edit.textContent = editing ? "Done" : "Edit";
      actions.hidden = !editing;
      if (menu) menu.close();
      tree = null;
      redraw();
    }
    draw();
    const unsubscribe = groups.onChange((event) => {
      if (!listHost.isConnected) { unsubscribe(); return; } // this view is gone
      if (event.type === "rebuilt") draw();
      else if (event.type === "change" && !(menu && menu.open)) redraw(); // the menu redraws itself; we follow on close
    });
    const element = h("div", { class: "library" },
      h("div", { class: "library-head" }, h("h2", {}, "Your songs"), edit),
      navHost, actions, menuHost, listHost, arrangeHost);
    return { element, setGroup, redraw };
  }
  let arrangeOpen = false; // "Arrange groups" stays open across redraws, for this page's lifetime

  function pickList(songs, selected, onChange) {
    return h("ul", { class: "songs picking" }, songs.map((song) => h("li", {}, h("label", {},
      h("input", {
        type: "checkbox", checked: selected.has(song.key),
        onchange: (e) => { if (e.target.checked) selected.add(song.key); else selected.delete(song.key); onChange(); },
      }),
      h("span", { class: "title" }, song.title || song.key),
      song.artist && h("span", { class: "artist" }, song.artist)))));
  }

  function songList(songs) {
    return h("ul", { class: "songs" }, songs.map((song) => {
      const route = { song: song.key, t: prefs.transposeOf(song.key) };
      return h("li", {}, h("a", {
        href: formatRoute(route),
        onclick: (e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // let new-tab work
          e.preventDefault();
          rememberScroll();
          navigate(route, { state: { from: "search", title: song.title, artist: song.artist } });
        },
      }, h("span", { class: "title" }, song.title || song.key), song.artist && h("span", { class: "artist" }, song.artist),
        groupLine(song.key)));
    }));
  }

  function groupLine(key) {
    const names = groups.groupsOf(key).map((id) => groups.labelOf(id));
    return names.length ? h("span", { class: "in-groups" }, names.join(" · ")) : null;
  }

  // ----- a song: reader and print views share the header and the toolbar -----------------

  // Content first: on a phone the header and one row of controls take the top of the screen,
  // and the song starts under them. Preferences live in panels that open under the toolbar,
  // one at a time: the key, the look (Aa), the groups and the rest (⋯).
  let currentPanels = null; // the panels of the song on screen
  let pendingFocus = ""; // a control to focus once the song is redrawn (a choice redraws the song)

  function panelController(host) {
    let cleanup = null;
    const mark = (name) => {
      for (const b of app.querySelectorAll("[data-panel]")) b.setAttribute("aria-expanded", String(b.dataset.panel === name));
    };
    const dispose = () => { if (cleanup) { const c = cleanup; cleanup = null; c(); } };
    function shut() {
      dispose();
      host.replaceChildren();
      openPanel = null;
      mark(null);
    }
    function open(name, build) {
      dispose();
      host.replaceChildren();
      openPanel = name;
      mark(name);
      cleanup = build(host) || null; // a builder appends its panel, and may return how to tear it down
    }
    return { open, shut, dispose, toggle(name, build) { if (openPanel === name) shut(); else open(name, build); } };
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !currentPanels || !openPanel) return;
    const name = openPanel;
    currentPanels.shut();
    const button = app.querySelector(`[data-panel="${name}"]`);
    if (button) button.focus();
  });

  async function renderSong(route, gen) {
    activeLibrary = null;
    const known = history.state || {};
    const sameSong = app.dataset.song === route.song;
    const reopen = sameSong ? openPanel : null; // a choice made in a panel redraws the song; the panel stays open
    if (currentPanels) currentPanels.dispose();
    openPanel = reopen;
    if (!sameSong) window.scrollTo(0, 0);
    app.dataset.song = route.song;
    const heading = h("h1", { tabindex: "-1" }, known.title || "Song");
    const artist = h("span", { class: "artist" }, known.artist || "");
    const capo = h("span", { class: "capo" });
    const groupsButton = h("button", { type: "button", class: "in-groups-button", hidden: true, "aria-expanded": "false", "data-panel": "groups" });
    const byline = h("p", { class: "byline" }, artist, capo, groupsButton);
    document.title = `${known.title || route.song} · ${CONFIG.title}`;
    const back = h("a", {
      href: location.pathname, class: "back",
      onclick: (e) => {
        e.preventDefault();
        // Back to the list this song was opened from, when it is the page underneath; a song
        // reached by a pasted link has nothing of ours underneath, so go to search
        if (known.from === "search") history.back();
        else { delete app.dataset.song; navigate({ q: "", lyrics: "" }); }
      },
    }, "← Search");
    const body = h("section", { class: "song-body" });
    app.replaceChildren(h("header", { class: "song-head" }, back, heading, byline), body);
    if (!sameSong) heading.focus({ preventScroll: true });

    const spinner = loading("Opening the song…");
    body.replaceChildren(spinner);
    let song;
    try {
      song = songCache.get(route.song) || await getJSON("/song?" + new URLSearchParams({ key: route.song }));
      await getOptions().catch(() => null);
    } catch (error) {
      if (gen !== generation) return;
      body.replaceChildren(errorBox(`This song could not be opened (${error.message}).`, () => { generation += 1; renderSong(route, generation); }));
      return;
    } finally {
      spinner.stop();
    }
    if (gen !== generation) return;
    songCache.set(route.song, song);
    const t = wrapShift(route.t, song); // a URL may name any shift; the song offers -5..+6
    if (t !== route.t) {
      route = { ...route, t };
      history.replaceState(history.state, "", formatRoute(route));
    }
    heading.textContent = song.title || song.key;
    artist.textContent = song.artist || "";
    const meta = song.meta || {};
    capo.textContent = meta.capo ? `Capo ${meta.capo}` : "";
    document.title = `${heading.textContent} · ${CONFIG.title}`;
    history.replaceState({ ...(history.state || {}), title: song.title, artist: song.artist }, "", location.href);

    const panelHost = h("div", { class: "panels" });
    const panels = panelController(panelHost);
    currentPanels = panels;
    const table = tableFor(song, route.t);
    const builders = {
      key: (host) => { host.append(transposePanel(song, route)); },
      look: (host) => { host.append(lookSheet(route)); },
      more: (host) => { host.append(morePanel(route, () => panels.open("groups", builders.groups))); },
      groups: (host) => {
        const menu = openTagMenu(host, [route.song], { onClose: () => { if (openPanel === "groups") panels.shut(); } });
        return () => { if (menu) menu.close(); };
      },
    };
    groupsButton.addEventListener("click", () => panels.toggle("groups", builders.groups));
    const toolbar = buildToolbar(song, route, table, panels, builders, panelHost);
    const look = prefs.look();
    applyLook(look);
    const content = route.view === "print"
      ? printView(song, route, gen)
      : h("div", { class: "read" }, readerView(song, table, look), scrollControls(route.song, look));
    body.replaceChildren(toolbar, content);
    showSongGroups(route.song, groupsButton, { reload: !sameSong });
    if (reopen && builders[reopen] && (reopen !== "groups" || groups.space)) panels.open(reopen, builders[reopen]);
    else openPanel = null;
    if (pendingFocus) {
      const target = app.querySelector(pendingFocus);
      if (target) target.focus({ preventScroll: true });
      pendingFocus = "";
    }
  }

  // The song's groups, as a muted line under the title ("in Campfire · Slow ones", or "Add to
  // a group"): it opens the same tag menu as the library's Group….
  function drawGroupsButton(button, key) {
    if (!groups.space) { button.hidden = true; return; }
    const names = groups.groupsOf(key).map((id) => groups.labelOf(id));
    button.hidden = false;
    button.textContent = names.length ? `in ${names.join(" · ")}` : "Add to a group";
    button.classList.toggle("none", !names.length);
    button.title = names.length ? "Change this song's groups" : "Put this song in a group";
  }

  async function showSongGroups(key, button, { reload }) {
    drawGroupsButton(button, key);
    if (reload || !groups.space) {
      try {
        await groups.load(await getJSON("/songs")); // after /song, which stores the song
      } catch (_) {
        return; // groups are extra: the song reads without them
      }
    }
    if (!button.isConnected) return;
    drawGroupsButton(button, key);
    const unsubscribe = groups.onChange((event) => {
      if (!button.isConnected) { unsubscribe(); return; }
      drawGroupsButton(button, key);
      if (event.type === "rebuilt" && openPanel === "groups" && currentPanels) currentPanels.shut(); // the menu was on the old space
    });
  }

  function tableFor(song, t) {
    return (song.transpositions || []).find((x) => x.semitones === t)
      || { semitones: 0, key: song.song_key, chords: Object.fromEntries((song.chords || []).map((c) => [c, c])) };
  }

  function goSong(route, changes) {
    const next = { ...route, ...changes };
    if ("t" in changes) prefs.setTranspose(route.song, next.t);
    navigate(next, { replace: true, state: history.state || {} });
  }

  // One row: [A− size A+] [−1 key +1] [Aa] [⋯]. Panels open under it.
  function buildToolbar(song, route, table, panels, builders, panelHost) {
    const look = prefs.look();
    const reading = route.view !== "print";

    const sizeLabel = h("span", { class: "size-value", "aria-live": "polite" },
      reading ? String(look.readSize) : `${Math.round(look.printScale * 100)}%`);
    const resize = (direction) => {
      if (reading) {
        const value = clamp(look.readSize + direction * READ_SIZES.step, READ_SIZES.min, READ_SIZES.max);
        look.readSize = value;
        prefs.setLook({ readSize: value });
        applyLook(look);
        autoScroll.configure({ level: prefs.scrollLevelOf(route.song), readSize: value });
        sizeLabel.textContent = String(value);
      } else {
        const value = round1(clamp(look.printScale + direction * PRINT_SCALES.step, PRINT_SCALES.min, PRINT_SCALES.max));
        prefs.setLook({ printScale: value });
        goSong(route, {}); // re-render the sheet at the new size
      }
    };
    const size = h("div", { class: "group", role: "group", "aria-label": reading ? "Text size" : "Sheet size" },
      h("button", { type: "button", class: "icon", title: "Smaller", "aria-label": "Smaller", onclick: () => resize(-1) }, "A−"),
      sizeLabel,
      h("button", { type: "button", class: "icon big", title: "Larger", "aria-label": "Larger", onclick: () => resize(1) }, "A+"));

    const hasChords = (song.chords || []).length > 0;
    const shift = (n) => goSong(route, { t: wrapShift(route.t + n, song) });
    const keyGroup = hasChords && h("div", { class: "group", role: "group", "aria-label": "Transpose" },
      h("button", { type: "button", class: "icon", title: "Down a semitone", "aria-label": "Down a semitone", onclick: () => shift(-1) }, "−1"),
      h("button", {
        type: "button", class: "text key", "aria-expanded": "false", "data-panel": "key",
        onclick: () => panels.toggle("key", builders.key),
        title: "Every key, and what the chords become", "aria-label": `Key ${table.key || ""}, transpose`,
      }, table.key || "Key", route.t ? h("small", {}, ` ${route.t > 0 ? "+" : ""}${route.t}`) : null),
      h("button", { type: "button", class: "icon", title: "Up a semitone", "aria-label": "Up a semitone", onclick: () => shift(1) }, "+1"));

    const settings = h("button", {
      type: "button", class: "text tool", "aria-expanded": "false", "data-panel": "look",
      title: reading ? "Paper, chords, columns, colours, spacing" : "The sheet's colours and chord size", "aria-label": "Look",
      onclick: () => panels.toggle("look", builders.look),
    }, "Aa");
    const more = h("button", {
      type: "button", class: "text tool", "aria-expanded": "false", "data-panel": "more",
      title: reading ? "Print, groups" : "Back to reading, groups", "aria-label": "More",
      onclick: () => panels.toggle("more", builders.more),
    }, "⋯");

    const bar = h("div", { class: "toolbar" }, size, keyGroup, settings, more);
    return h("div", { class: "toolbar-wrap" }, bar, panelHost);
  }

  // The rest, behind ⋯: printing (rare on a phone) and the song's groups.
  function morePanel(route, openGroups) {
    const reading = route.view !== "print";
    const item = (text, hint, onclick) => h("button", { type: "button", class: "menu-item", onclick },
      h("span", {}, text), hint && h("small", {}, hint));
    return h("div", { class: "panel more", role: "group", "aria-label": "More" },
      reading
        ? item("Print or save as PDF", "One A4 page, the lyrics as large as fit", () => { openPanel = null; goSong(route, { view: "print" }); })
        : item("Back to reading", null, () => { openPanel = null; goSong(route, { view: "read" }); }),
      groups.space && item("Groups…", "Put this song in a group, or take it out", openGroups));
  }

  // Auto-scroll: a ▶ that floats over the song. While it runs (and for a moment after a tap)
  // it opens into ❚❚ − speed +. The speed is remembered per song.
  function scrollControls(key, look) {
    let level = prefs.scrollLevelOf(key);
    let idle = 0;
    autoScroll.configure({ level, readSize: look.readSize });
    const play = h("button", { type: "button", class: "icon play", onclick: () => autoScroll.toggle() });
    const value = h("span", { class: "size-value", "aria-live": "polite" }, String(level));
    const extras = [
      h("button", { type: "button", class: "icon", title: "Slower", "aria-label": "Slower", onclick: () => setLevel(level - 1) }, "−"),
      value,
      h("button", { type: "button", class: "icon", title: "Faster", "aria-label": "Faster", onclick: () => setLevel(level + 1) }, "+"),
    ];
    const pill = h("div", { class: "scroll-pill", role: "group", "aria-label": "Auto-scroll" }, play, ...extras);
    const expand = (open) => {
      pill.classList.toggle("expanded", open);
      for (const el of extras) el.hidden = !open;
    };
    const settle = () => { // stay open while running; fold back a moment after the last tap
      clearTimeout(idle);
      expand(true);
      if (!autoScroll.running) idle = setTimeout(() => { if (!autoScroll.running) expand(false); }, PILL_IDLE_MS);
    };
    function setLevel(next) {
      level = clamp(next, 1, SCROLL_LEVELS);
      prefs.setScrollLevel(key, level);
      autoScroll.configure({ level, readSize: prefs.look().readSize });
      value.textContent = String(level);
      settle();
    }
    const show = (running) => {
      play.textContent = running ? "❚❚" : "▶";
      play.title = running ? "Pause scrolling" : "Scroll the song";
      play.setAttribute("aria-label", play.title);
      play.setAttribute("aria-pressed", String(running));
    };
    show(autoScroll.running);
    expand(autoScroll.running);
    const unsubscribe = autoScroll.onChange((running) => { show(running); settle(); });
    scrollUnsubscribers.push(() => { unsubscribe(); clearTimeout(idle); });
    return pill;
  }
  const scrollUnsubscribers = [];

  // Every key the song can move to, and what its chords become in the one being chosen.
  function transposePanel(song, route) {
    const tables = song.transpositions || [];
    const chosen = route.t;
    const grid = h("div", { class: "keys", role: "radiogroup", "aria-label": "Key" });
    const chart = h("table", { class: "chord-map" });
    const showChords = () => {
      const table = tableFor(song, chosen);
      chart.replaceChildren(
        h("thead", {}, h("tr", {}, h("th", {}, `Original (${song.song_key})`), h("th", {}, `In ${table.key}`))),
        h("tbody", {}, (song.chords || []).map((c) =>
          h("tr", { class: table.chords[c] === c ? "same" : "" }, h("td", {}, c), h("td", {}, table.chords[c] || c)))));
      for (const b of grid.children) b.setAttribute("aria-checked", String(Number(b.value) === chosen));
    };
    for (const table of tables) {
      const n = table.semitones;
      grid.append(h("button", {
        type: "button", role: "radio", value: String(n), "data-shift": String(n),
        title: n ? `${n > 0 ? "Up" : "Down"} ${Math.abs(n)} semitone${Math.abs(n) > 1 ? "s" : ""}` : "As written",
        onclick: () => { pendingFocus = `[data-shift="${n}"]`; goSong(route, { t: n }); }, // the panel stays open on the new key
      }, h("span", { class: "key-name" }, table.key), h("span", { class: "shift" }, n ? (n > 0 ? `+${n}` : String(n)) : "0")));
    }
    showChords();
    return h("div", { class: "panel" },
      h("p", { class: "muted hint" }, "Tap a key: the song and this table change together."),
      grid, chart,
      route.t ? h("button", { type: "button", class: "text", onclick: () => goSong(route, { t: 0 }) }, "Back to the original key") : null);
  }

  // ----- the look (Aa): a sheet generated from LOOK_SCHEMA -----------------------------------

  // One control per kind of setting. Each gets the field, its current value and the handlers:
  // onPreview(field, value) while it moves, onCommit(field, value) once it is chosen.
  const LOOK_WIDGETS = {
    choice(field, value, on) {
      const choices = typeof field.choices === "function" ? field.choices() : field.choices;
      const current = String(value);
      const buttons = Object.entries(choices).map(([v, text]) => {
        const button = h("button", {
          type: "button", role: "radio", class: "chip", "aria-checked": String(v === current),
          "data-key": field.key, "data-value": v,
          onclick: () => {
            for (const b of buttons) b.setAttribute("aria-checked", String(b === button));
            on.onCommit(field, field.parse ? field.parse(v) : v);
          },
        }, text);
        if (field.swatches) {
          const palette = PAPERS[v];
          button.prepend(h("span", {
            class: "swatch" + (palette ? "" : " auto"), style: palette ? `background:${palette.paper}` : null, "aria-hidden": "true",
          }));
        }
        if (field.fontPreview && FONTS[v]) button.style.fontFamily = FONTS[v];
        return button;
      });
      return h("div", { class: "row choice", role: "radiogroup", "aria-label": field.label },
        h("span", { class: "label" }, field.label), h("div", { class: "chips" }, buttons));
    },
    switch(field, value, on) {
      return h("label", { class: "row switch" },
        h("input", { type: "checkbox", role: "switch", "data-key": field.key, checked: !!value, onchange: (e) => on.onCommit(field, e.target.checked) }),
        h("span", {}, field.label));
    },
    color(field, value, on) {
      return h("label", { class: "row" }, h("span", { class: "label" }, field.label),
        h("input", {
          type: "color", value, "data-key": field.key,
          oninput: (e) => on.onPreview(field, e.target.value),
          onchange: (e) => on.onCommit(field, e.target.value),
          onblur: () => on.onPreview(null), // a cancelled pick leaves nothing
        }));
    },
    slider(field, value, on) {
      const out = h("output", {}, field.format(value));
      const input = h("input", {
        type: "range", min: String(field.min), max: String(field.max), step: String(field.step), value: String(value),
        "aria-label": field.label, "aria-valuetext": field.format(value), "data-key": field.key,
        oninput: (e) => {
          const v = Number(e.target.value);
          out.textContent = field.format(v);
          input.setAttribute("aria-valuetext", field.format(v));
          on.onPreview(field, v);
        },
        onchange: (e) => on.onCommit(field, Number(e.target.value)),
      });
      return h("div", { class: "row" }, h("span", { class: "label" }, field.label), input, out);
    },
  };

  // The sheet for one surface: the essentials, then "Fine tuning" (collapsed) with the rest and
  // a reset. A surface with no essentials (print) shows its settings directly.
  function renderLookSheet(schema, look, on) {
    const fields = schema.filter((f) => f.surfaces.includes(on.surface));
    const row = (f) => LOOK_WIDGETS[f.widget](f, look[f.key], on);
    const essentials = fields.filter((f) => f.essential).map(row);
    const rest = fields.filter((f) => !f.essential);
    const tail = [
      ...rest.map(row),
      on.note && h("p", { class: "muted hint" }, on.note),
      h("button", { type: "button", class: "text", onclick: () => on.onReset(rest.map((f) => f.key)) }, "Reset to defaults"),
    ];
    if (!essentials.length) return tail;
    const details = h("details", { class: "fine", ontoggle: () => on.onFineToggle(details.open) }, h("summary", {}, "Fine tuning"), ...tail);
    details.open = !!on.fineOpen;
    return [...essentials, details];
  }

  let fineTuningOpen = false; // "Fine tuning" stays as the reader left it, for this page's lifetime
  function lookSheet(route) {
    const surface = route.view === "print" ? "print" : "read";
    const resolve = () => (surface === "print" ? prefs.look("light") : prefs.look()); // a PDF is printed on light paper
    const panel = h("div", { class: "panel look" });
    const focusSelector = (field, value) => `[data-key="${field.key}"]` + (field.widget === "choice" ? `[data-value="${CSS.escape(String(value))}"]` : "");
    const draw = () => {
      const look = resolve();
      panel.replaceChildren(...renderLookSheet(LOOK_SCHEMA, look, handlers(look)));
    };
    const handlers = (look) => ({
      surface,
      fineOpen: fineTuningOpen,
      onFineToggle: (open) => { fineTuningOpen = open; },
      note: surface === "print"
        ? "Colours are those for light paper; opacity prints as the matching shade on white."
        : `Colours are kept for ${look.palette.label.toLowerCase()} paper; the printed sheet uses those for light paper.`,
      onPreview: (field, value) => {
        if (surface === "print") return;
        applyLook(field ? { ...prefs.look(), [field.key]: value } : prefs.look());
      },
      onCommit: (field, value) => {
        if (field.ink) prefs.setInk(look.paperName, { [field.key]: value });
        else prefs.setLook({ [field.key]: value });
        if (surface === "print" || field.redraw) { // the song (or the sheet) is drawn again
          pendingFocus = focusSelector(field, value);
          goSong(route, {});
          return;
        }
        applyLook(prefs.look());
        if (field.key === "paper") { // the inks shown are the new paper's
          draw();
          const again = panel.querySelector(focusSelector(field, value));
          if (again) again.focus();
        }
      },
      onReset: (keys) => {
        prefs.resetLook(look.paperName, keys);
        applyLook(prefs.look());
        if (surface === "print") goSong(route, {});
        else draw();
      },
    });
    draw();
    return panel;
  }

  // The paper, its inks and the reader's type, as CSS variables on the page. The paper also
  // sets light or dark for the whole page, so the toolbar and search match it.
  function applyLook(look) {
    const root = document.documentElement;
    root.dataset.theme = look.palette.theme;
    root.style.setProperty("--bg", look.palette.paper);
    for (const [name, value] of [["--chorus-band", look.palette.chorusBand], ["--bridge-band", look.palette.bridgeBand]]) {
      if (value) root.style.setProperty(name, value); else root.style.removeProperty(name);
    }
    root.style.setProperty("--read-size", `${look.readSize}px`);
    root.style.setProperty("--lyric-ink", rgba(look.lyricColor, look.lyricAlpha));
    root.style.setProperty("--chord-ink", rgba(look.chordColor, look.chordAlpha));
    root.style.setProperty("--chord-scale", String(look.chordScale));
    root.style.setProperty("--read-line", String(look.lineHeight));
    root.style.setProperty("--read-font", FONTS[look.font] || FONTS.sans);
    const meta = document.querySelector('meta[name="theme-color"]') || document.head.appendChild(h("meta", { name: "theme-color" }));
    meta.setAttribute("content", look.palette.paper);
  }

  if (darkQuery && darkQuery.addEventListener) { // "auto" paper follows the phone as it changes
    // Colours only: inks and paper are CSS variables, so nothing is rebuilt (a search being
    // typed, a sheet being shown) and nothing is fetched again.
    darkQuery.addEventListener("change", () => { if (!PAPERS[prefs.look().paper]) applyLook(prefs.look()); });
  }

  // ----- the reader: the song as text, chords over (or in, or without) its syllables -------

  function readerView(song, table, look) {
    const text = song.text || "";
    const chordsAt = new Map(); // offset -> [symbols], in song order
    for (const a of song.annotations || []) {
      if (a.kind !== "chord") continue;
      const symbol = table.chords[a.body.symbol] || a.body.symbol;
      if (!chordsAt.has(a.start)) chordsAt.set(a.start, []);
      chordsAt.get(a.start).push(symbol);
    }
    const sections = song.sections || [];
    const labelsAt = new Map(sections.filter((x) => x.label).map((x) => [x.start, x.label]).reverse());
    const familyAt = (offset) => {
      const found = sections.find((x) => x.start <= offset && offset <= x.end); // end inclusive, as printed
      return found ? found.family : "";
    };
    const classes = ["reader", `chords-${look.chordMode}`];
    if (look.columns === 2) classes.push("two-columns");
    if (look.shade) classes.push("shaded");
    // The key is in the toolbar and the capo under the title: the song starts with its first line.
    const out = h("article", { class: classes.join(" "), lang: (song.meta && song.meta.lang) || "" });
    const draw = { above: chordsAbove, inline: chordsInline, off: chordsOff }[look.chordMode] || chordsAbove;
    let start = 0;
    let pendingLabel = null; // drawn only above a line that is drawn (chords Off drops some)
    for (const line of text.split("\n")) {
      const end = start + line.length;
      const family = familyAt(start);
      const label = labelsAt.get(start);
      if (label) pendingLabel = h("div", { class: `section-label ${family ? "fam-" + family : ""}` }, label);
      const el = draw(line, start, end, chordsAt);
      if (el && !el.classList.contains("blank")) {
        if (pendingLabel) { out.append(pendingLabel); pendingLabel = null; }
      }
      if (el) {
        if (family) el.classList.add("fam-" + family);
        out.append(el);
      }
      start = end + 1;
    }
    return out;
  }

  function chordOffsets(start, end, chordsAt) {
    const offsets = [];
    for (let i = start; i <= end; i += 1) if (chordsAt.has(i)) offsets.push(i);
    return offsets;
  }

  function tidy(text) { return text.replace(/ {2,}/g, " "); } // alignment spaces from the chart

  function chordsOnlyLine(offsets, chordsAt) { // an instrumental line
    return h("div", { class: "line chords-only" }, offsets.flatMap((i) => chordsAt.get(i)).map((c) => h("span", { class: "ch" }, c)));
  }

  // Chords over the syllables they land on. Pieces break at every chord and after every
  // space; pieces join into words, and a line wraps only between words, never inside one.
  function chordsAbove(line, start, end, chordsAt) {
    const offsets = chordOffsets(start, end, chordsAt);
    if (!line.trim() && !offsets.length) return h("div", { class: "line blank" });
    if (!offsets.length) return h("div", { class: "line" }, tidy(line));
    if (!line.trim()) return chordsOnlyLine(offsets, chordsAt);
    const cuts = new Set([start, ...offsets.filter((i) => i < end)]);
    for (let i = start + 1; i < end; i += 1) if (line[i - start - 1] === " " && line[i - start] !== " ") cuts.add(i);
    const sorted = [...cuts].sort((a, b) => a - b);
    const el = h("div", { class: "line with-chords" });
    let word = null;
    sorted.forEach((cut, k) => {
      const next = k + 1 < sorted.length ? sorted[k + 1] : end;
      const piece = line.slice(cut - start, next - start);
      const chords = chordsAt.get(cut);
      const startsWord = cut === start || line[cut - start - 1] === " ";
      if (startsWord || !word) { word = h("span", { class: "w" }); el.append(word); }
      word.append(h("span", { class: "p" },
        h("span", { class: "ch" }, chords ? chords.join(" ") : "\u00a0"),
        h("span", { class: "ly" }, tidy(piece) || "\u00a0")));
    });
    const trailing = chordsAt.get(end); // chords after the last syllable
    if (trailing && end > start) el.append(h("span", { class: "w" }, h("span", { class: "p" },
      h("span", { class: "ch" }, trailing.join(" ")), h("span", { class: "ly" }, "\u00a0"))));
    return el;
  }

  // Chords in the line, just before the syllable they land on: one line of type per line.
  function chordsInline(line, start, end, chordsAt) {
    const offsets = chordOffsets(start, end, chordsAt);
    if (!line.trim() && !offsets.length) return h("div", { class: "line blank" });
    if (!line.trim()) return chordsOnlyLine(offsets, chordsAt);
    const el = h("div", { class: "line" });
    let from = start;
    for (const at of offsets) {
      if (at > from) el.append(tidy(line.slice(from - start, at - start)));
      el.append(h("span", { class: "ch in" }, chordsAt.get(at).join(" ")));
      from = Math.max(from, at);
    }
    if (from < end) el.append(tidy(line.slice(from - start)));
    return el;
  }

  // Lyrics only: instrumental lines go, the words stay.
  function chordsOff(line, start, end, chordsAt) {
    if (!line.trim()) return chordOffsets(start, end, chordsAt).length ? null : h("div", { class: "line blank" });
    return h("div", { class: "line" }, tidy(line));
  }

  // ----- the printed sheet: layout options, size, page images, PDF ------------------------

  // The sheet follows the reader's settings (chords in the line, two columns, shading) unless a
  // layout was chosen here, which the URL then carries as `layout=`.
  function readerLayout(look) {
    const parts = [];
    if (look.chordMode === "inline") parts.push("inline");
    if (look.columns === 2) parts.push("two-column");
    if (look.shade) parts.push("shaded");
    return parts.join("+") || "dense";
  }
  const layoutSet = (spec) => new Set(spec.split("+").filter((n) => n && n !== "dense"));
  const sameLayout = (a, b) => { const x = layoutSet(a), y = layoutSet(b); return x.size === y.size && [...x].every((n) => y.has(n)); };

  function printView(song, route, gen) {
    const look = prefs.look();
    const derived = readerLayout(look);
    const layout = route.layout || derived;
    const controls = h("div", { class: "layout" });
    const actions = h("div", { class: "actions" });
    const viewer = h("div", { class: "viewer" });
    const params = new URLSearchParams({ key: route.song, layout });
    if (route.t) params.set("transpose", String(route.t));
    if (look.printScale !== 1) params.set("scale", String(look.printScale));
    for (const [name, value] of Object.entries(prefs.printParams())) params.set(name, value);
    buildLayoutControls(route, controls, layout, derived);
    showSheet(params, route, { viewer, actions, controls }, gen);
    return h("div", { class: "print" }, actions, controls, viewer);
  }

  // One row per control the server describes (/layouts `controls`, in plain words); choosing
  // in one row replaces that row's option in the layout.
  function buildLayoutControls(route, controls, layout, derived) {
    if (!options || !options.controls) return;
    for (const control of options.controls) {
      const names = control.choices.map((c) => c.option).filter(Boolean);
      const chips = control.choices.map((choice) => h("button", {
        type: "button", role: "radio", class: "chip", "data-control": control.name, "data-option": choice.option,
        onclick: () => {
          const next = [...layoutSet(layout)].filter((n) => !names.includes(n));
          if (choice.option) next.push(choice.option);
          const spec = next.join("+") || "dense";
          pendingFocus = `[data-control="${control.name}"][data-option="${choice.option}"]`;
          goSong(route, { layout: sameLayout(spec, derived) ? "" : spec });
        },
      }, choice.label));
      controls.append(h("div", { class: "row choice", role: "radiogroup", "aria-label": control.label },
        h("span", { class: "label" }, control.label), h("div", { class: "chips" }, chips)));
    }
    if (route.layout && !sameLayout(route.layout, derived)) {
      controls.append(h("button", { type: "button", class: "text", onclick: () => goSong(route, { layout: "" }) }, "Match my reading settings"));
    }
    markLayout(controls, layout);
  }

  // Check the chips of a layout spec. The server's spelling (from /sheet) wins over the URL's,
  // which may use an alias ("2col") or another case.
  function markLayout(controls, layout) {
    const chosen = layoutSet(layout.toLowerCase());
    for (const row of controls.querySelectorAll('[role="radiogroup"]')) {
      const chips = [...row.querySelectorAll("[data-option]")];
      const hit = chips.find((b) => b.dataset.option && chosen.has(b.dataset.option)) || chips.find((b) => !b.dataset.option);
      for (const b of chips) b.setAttribute("aria-checked", String(b === hit));
    }
  }

  async function showSheet(params, route, { viewer, actions, controls }, gen) {
    const back = h("button", { type: "button", class: "text", onclick: () => { openPanel = null; goSong(route, { view: "read" }); } }, "Back to reading");
    actions.replaceChildren(back);
    const spinner = loading("Making the sheet…");
    viewer.replaceChildren(spinner);
    try {
      const info = await getJSON("/sheet?" + params);
      if (gen !== generation) return;
      markLayout(controls, info.layout);
      const pdfUrl = CONFIG.api + "/sheet.pdf?" + params;
      const facts = [info.font_size && `${Math.round(info.font_size)} pt`, info.pages > 1 && `${info.pages} pages`];
      const pages = [];
      for (let page = 1; page <= info.pages; page += 1) pages.push(pageImage(params, page, info, pdfUrl));
      // One button: the PDF opens, and the browser offers to save or print it.
      const fit = prefs.look().printScale !== 1 && h("button", {
        type: "button", class: "text", title: "Back to the size that fills the page",
        onclick: () => { prefs.setLook({ printScale: 1 }); goSong(route, {}); },
      }, "Fit to the page");
      actions.replaceChildren(
        h("a", { class: "button", href: pdfUrl, target: "_blank", rel: "noopener" }, "PDF"),
        back, fit,
        h("span", { class: "muted" }, facts.filter(Boolean).join(" · ")));
      viewer.replaceChildren(...pages);
    } catch (error) {
      if (gen !== generation) return;
      viewer.replaceChildren(errorBox(`The sheet could not be made (${error.message}).`,
        () => { generation += 1; showSheet(params, route, { viewer, actions, controls }, generation); }));
    } finally {
      spinner.stop();
    }
  }

  // One page as an image, in a box reserved at A4 proportions before the bytes arrive.
  // Tapping it opens the PDF. A failed image gets its own message and a retry.
  function pageImage(params, page, info, pdfUrl) {
    const src = CONFIG.api + "/sheet.png?" + new URLSearchParams({ ...Object.fromEntries(params), page: String(page) });
    const frame = h("a", { class: "page is-loading", href: pdfUrl, target: "_blank", rel: "noopener", "aria-busy": "true" });
    const img = h("img", {
      src, width: "595", height: "842", decoding: "async",
      alt: `${info.title || "Song"} sheet${info.pages > 1 ? `, page ${page}` : ""}`,
    });
    const settle = () => { frame.classList.remove("is-loading"); frame.removeAttribute("aria-busy"); };
    img.addEventListener("load", settle);
    img.addEventListener("error", () => {
      settle();
      const box = errorBox("The page image did not load. The PDF may still open.",
        () => box.replaceWith(pageImage(params, page, info, pdfUrl)));
      frame.replaceWith(box);
    });
    frame.append(img);
    if (img.complete && img.naturalWidth) settle();
    return frame;
  }

  // --- small numeric helpers ---------------------------------------------------------------

  function clamp(value, low, high) { return Math.min(high, Math.max(low, value)); }
  function round1(value) { return Math.round(value * 10) / 10; }
  function wrapShift(t, song) { // the same key, inside the shifts the song offers
    const shifts = (song.transpositions || []).map((x) => x.semitones);
    if (!shifts.length) return 0;
    const low = Math.min(...shifts), period = Math.max(...shifts) - low + 1;
    return ((((t - low) % period) + period) % period) + low;
  }

  render();
})();
