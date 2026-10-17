// songleaf page: search the corpus, read a song with its chords, transpose it, print it.
//
// The URL is the state: `?q=..&lyrics=..` is the search view; `?song=<key>` opens a song,
// with `t=<semitones>` (transposition), `view=print` (the PDF) and `layout=<spec>`.
// Opening a song pushes a history entry (Back returns to the results); everything done
// on the song (transpose, layout, view) replaces it. The reader's look (size, colours,
// opacity) is per viewer, kept through `prefs`, the one place that touches browser storage.
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
  // The reader's defaults. The printed sheet's colours come from the server (/layouts), and
  // the PDF gets only what the viewer changed, so it keeps its own tuning.
  const DEFAULT_LOOK = {
    readSize: 20,
    printScale: 1,
    lyricAlpha: 1,
    chordAlpha: 1,
    chordScale: 0.62,
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
  const CHORD_MODES = { above: "Above", inline: "Inline", off: "Off" };
  const FONTS = {
    sans: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
    mono: 'ui-monospace, "SF Mono", Menlo, monospace',
  };
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
          ...(server.chord_scale ? { chordScale: server.chord_scale } : {}),
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
      // Back to the defaults for what the Look panel sets: one paper's inks, opacity, type.
      // The paper and the display choices stay.
      resetLook(paperName) {
        const saved = { ...(values.look || {}) };
        for (const name of ["lyricAlpha", "chordAlpha", "chordScale", "lineHeight", "font"]) delete saved[name];
        if (saved.inks) saved.inks = Object.fromEntries(Object.entries(saved.inks).filter(([k]) => k !== paperName));
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
        const numeric = { lyricAlpha: "lyric_alpha", chordAlpha: "chord_alpha", chordScale: "chord_scale" };
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
  // and saves its snapshot in the background. If someone else saved in between, the save is
  // refused (409) with their groups: we start from those and replay our own changes on top.
  const groups = (function () {
    let zg = null; // the zodal-groups module, loaded on first use
    let space = null; // the live Groups handle
    let revision = 0;
    let pending = []; // changes made here and not yet saved, oldest first
    let saveTimer = null;
    let saving = false;
    let unsubscribe = null;
    let labels = new Map(); // song key -> "Title · Artist"
    const listeners = new Set();
    const notify = (event) => listeners.forEach((f) => f(event));

    async function library() {
      if (!zg) {
        document.head.append(h("link", { rel: "stylesheet", href: CONFIG.api + "/ui/vendor/zodal-groups.css" }));
        zg = await import(CONFIG.api + "/ui/vendor/zodal-groups.js");
      }
      return zg;
    }
    function build(snapshot) {
      // every stored song is a node with its title, so trees and menus show titles, not keys
      const nodes = snapshot.nodes.map((n) => (labels.has(n.id) ? { ...n, label: labels.get(n.id) } : n));
      const present = new Set(nodes.map((n) => n.id));
      for (const [key, label] of labels) if (!present.has(key)) nodes.push({ id: key, label });
      if (unsubscribe) unsubscribe();
      space = zg.defineGroups({ profile: "labels", nodes, edges: snapshot.edges });
      unsubscribe = space.subscribe(({ delta }) => { pending.push(delta); schedule(); notify({ type: "change" }); });
    }
    // (Re)load from the server: on every library view, so the other person's changes show.
    async function load(songs) {
      await library();
      labels = new Map(songs.map((s) => [s.key, [s.title, s.artist].filter(Boolean).join(" · ") || s.key]));
      if (pending.length) return space; // unsaved changes win until they are saved
      const doc = await getJSON("/groups");
      revision = doc.revision;
      build(doc.snapshot);
      return space;
    }
    function schedule(delay = 400) { clearTimeout(saveTimer); saveTimer = setTimeout(save, delay); }
    async function save() {
      if (saving) { schedule(); return; }
      if (!pending.length) return;
      saving = true;
      const sent = pending.length;
      const snapshot = zg.toSnapshot(space.space);
      try {
        const response = await fetch(CONFIG.api + "/groups", {
          method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision, snapshot: { nodes: snapshot.nodes, edges: snapshot.edges } }),
        });
        if (response.status === 409) {
          rebase((await response.json()).current);
        } else if (!response.ok) {
          throw new Error(await errorText(response));
        } else {
          revision = (await response.json()).revision;
          pending = pending.slice(sent);
          notify({ type: pending.length ? "saving" : "saved" });
        }
      } catch (error) {
        notify({ type: "error", message: error.message });
        schedule(5000); // try again; nothing is lost while the page is open
      } finally {
        saving = false;
      }
    }
    function rebase(current) {
      const mine = pending;
      pending = [];
      revision = current.revision;
      build(current.snapshot);
      let refused = 0;
      for (const delta of mine) if (!space.apply(delta).ok) refused += 1; // each replay re-queues a save
      notify({ type: "merged", refused });
    }
    return {
      load,
      get space() { return space; },
      get zg() { return zg; },
      // The groups (nodes that hold something), with how many songs each holds, nested included.
      list() {
        if (!space) return [];
        return [...space.space.nodes.keys()]
          .filter((id) => !labels.has(id) && space.children(id).length)
          .map((id) => ({ id, label: (space.space.nodes.get(id) || {}).label || id, count: songsIn(id).length }))
          .sort((a, b) => a.label.localeCompare(b.label));
      },
      songsIn,
      groupsOf(key) { return space ? space.parents(key).filter((id) => !labels.has(id)) : []; },
      onChange(f) { listeners.add(f); return () => listeners.delete(f); },
      flush() { if (pending.length) { clearTimeout(saveTimer); return save(); } return Promise.resolve(); },
    };
    function songsIn(group) {
      return space ? space.members(group, { expand: "closure" }).filter((id) => labels.has(id)) : [];
    }
  })();
  window.addEventListener("pagehide", () => { groups.flush(); }); // last chance to save

  // A small message at the bottom of the screen: a save that failed, a merge.
  function toast(text) {
    const old = document.querySelector(".toast");
    if (old) old.remove();
    const el = h("div", { class: "toast", role: "status" }, text);
    document.body.append(el);
    setTimeout(() => el.remove(), 4000);
  }
  groups.onChange((event) => {
    if (event.type === "error") toast("Couldn't save the groups. Trying again…");
    else if (event.type === "merged") {
      toast(event.refused
        ? `The groups were changed elsewhere; ${event.refused} of your changes no longer fit and were dropped.`
        : "The groups were changed elsewhere; your changes were added to them.");
      render();
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
      song,
      t,
      view: params.get("view") === "print" ? "print" : "read",
      layout: params.get("layout") || "dense",
    };
  }

  function formatRoute(route) {
    const params = new URLSearchParams();
    if (route.song) {
      params.set("song", route.song);
      if (route.t) params.set("t", String(route.t));
      if (route.view === "print") params.set("view", "print");
      if (route.layout && route.layout !== "dense") params.set("layout", route.layout);
    } else {
      if (route.q) params.set("q", route.q);
      if (route.lyrics) params.set("lyrics", route.lyrics);
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

  window.addEventListener("popstate", render);

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
    if (route.song) renderSong(route, generation);
    else renderSearch(route, generation);
  }

  // ----- search --------------------------------------------------------------------------

  function renderSearch(route, gen) {
    window.scrollTo(0, 0);
    document.title = route.q || route.lyrics ? `${route.q || route.lyrics} · ${CONFIG.title}` : CONFIG.title;
    const results = h("section", { class: "results", "aria-live": "polite" });
    // A refinement replaces the URL and refreshes the results only: the inputs stay as
    // they are, so typing (and a phone's keyboard) is never interrupted.
    const refine = () => {
      clearTimeout(searchTimer);
      const next = { q: query.value.trim(), lyrics: lyrics.value.trim() };
      history.replaceState({}, "", formatRoute(next));
      document.title = next.q || next.lyrics ? `${next.q || next.lyrics} · ${CONFIG.title}` : CONFIG.title;
      generation += 1;
      showResults(next, results, generation);
    };
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
    if (!route.q && !route.lyrics) query.focus();
    showResults(route, results, gen);
  }

  function showResults(route, results, gen) {
    if (route.q || route.lyrics) showHits(route, results, gen);
    else showStored(results, gen);
  }

  async function showHits(route, results, gen) {
    const spinner = loading("Searching…", "The first search after a restart loads the song index, which takes a few seconds.");
    results.replaceChildren(spinner);
    const params = new URLSearchParams({ q: route.q, lyrics: route.lyrics, limit: "25" });
    try {
      const hits = await getJSON("/search?" + params);
      if (gen !== generation) return;
      results.replaceChildren(
        hits.length ? songList(hits) : h("p", { class: "muted" }, "No song matches. Try fewer words, or check the spelling of the artist.")
      );
    } catch (error) {
      if (gen !== generation) return;
      results.replaceChildren(errorBox(error.message, () => showHits(route, results, gen)));
    } finally {
      spinner.stop();
    }
  }

  async function showStored(results, gen) {
    try {
      const songs = await getJSON("/songs");
      if (gen !== generation) return;
      results.replaceChildren(
        songs.length
          ? library(songs, () => showStored(results, generation))
          : h("p", { class: "muted" }, "Search by title or artist, or by words of the lyrics.")
      );
    } catch (error) {
      if (gen !== generation) return;
      results.replaceChildren(errorBox(error.message, () => showStored(results, gen)));
    }
  }

  // The stored songs, with an Edit mode: pick songs, then act on them (delete).
  let libraryFilter = ""; // the group the list is narrowed to ("" for all), for this page's lifetime
  let libraryView = "list"; // "list" or "tree"

  function library(songs, refresh) {
    const selected = new Set();
    let editing = false;
    const listHost = h("div");
    const filterHost = h("div", { class: "group-filter", role: "radiogroup", "aria-label": "Show" });
    const menuHost = h("div", { class: "group-menu-host" });
    const count = h("span", { class: "muted" });
    let busy = false;
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
        remove.disabled = true;
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
      onclick: () => openGroupMenu(),
    }, "Group…");
    const actions = h("div", { class: "edit-actions", hidden: true }, count, h("div", { class: "edit-buttons" }, label, remove));
    function openGroupMenu() {
      if (!groups.space || !selected.size) return;
      menuHost.replaceChildren();
      const panel = h("div", { class: "panel group-menu" });
      menuHost.append(panel);
      groups.zg.renderTagMenu(panel, groups.space, {
        selection: [...selected],
        candidates: () => groups.list().map((g) => g.id), // groups only: never a song
        onClose: () => menuHost.replaceChildren(),
        onChange: () => {},
      });
    }
    const edit = h("button", {
      type: "button", class: "text",
      onclick: () => { editing = !editing; selected.clear(); draw(); },
    });
    const sync = () => {
      count.textContent = selected.size ? `${selected.size} selected` : "Pick songs";
      remove.disabled = !selected.size;
      label.disabled = !selected.size || !groups.space;
    };
    const viewSwitch = h("div", { class: "group seg-switch small", role: "group", "aria-label": "View" });
    function shown() { // the songs the filter lets through, in library order
      if (!libraryFilter || !groups.space) return songs;
      const keep = new Set(groups.songsIn(libraryFilter));
      return songs.filter((s) => keep.has(s.key));
    }
    function drawFilter() {
      const list = groups.list();
      if (libraryFilter && !list.some((g) => g.id === libraryFilter)) libraryFilter = "";
      filterHost.hidden = !list.length || libraryView === "tree";
      const chip = (id, text, n) => h("button", {
        type: "button", role: "radio", class: "chip", "aria-checked": String(libraryFilter === id),
        onclick: () => { libraryFilter = id; draw(); },
      }, text, n == null ? null : h("span", { class: "count" }, String(n)));
      filterHost.replaceChildren(chip("", "All", songs.length), ...list.map((g) => chip(g.id, g.label, g.count)));
      viewSwitch.replaceChildren(
        ...[["list", "List"], ["tree", "Groups"]].map(([value, text]) => h("button", {
          type: "button", "aria-pressed": String(libraryView === value),
          onclick: () => { libraryView = value; editing = false; draw(); },
        }, text)));
      viewSwitch.hidden = !list.length;
    }
    function draw() {
      edit.textContent = editing ? "Done" : "Edit";
      actions.hidden = !editing;
      edit.hidden = libraryView === "tree";
      menuHost.replaceChildren();
      drawFilter();
      if (libraryView === "tree" && groups.space) {
        const host = h("div", { class: "group-tree" });
        listHost.replaceChildren(host,
          h("p", { class: "muted hint" }, "Tap a song to open it. On a computer, drag a song or a group onto a group to add it there."));
        groups.zg.renderTree(host, groups.space, {
          onSelect: (id) => {
            const song = songs.find((s) => s.key === id);
            if (song) navigate({ song: song.key, t: prefs.transposeOf(song.key) }, { state: { from: "search", title: song.title, artist: song.artist } });
          },
        });
      } else {
        listHost.replaceChildren(editing ? pickList(shown(), selected, sync) : songList(shown()));
      }
      sync();
    }
    draw();
    groups.load(songs).then(() => draw()).catch(() => {}); // groups arrive after the list
    const unsubscribe = groups.onChange((event) => {
      if (!document.body.contains(listHost)) { unsubscribe(); return; }
      if (event.type === "change" && !menuHost.hasChildNodes()) draw(); // the menu redraws itself
    });
    return h("div", { class: "library" },
      h("div", { class: "library-head" }, h("h2", {}, "Your songs"), h("div", { class: "head-tools" }, viewSwitch, edit)),
      filterHost, actions, menuHost, listHost);
  }

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
          navigate(route, { state: { from: "search", title: song.title, artist: song.artist } });
        },
      }, h("span", { class: "title" }, song.title || song.key), song.artist && h("span", { class: "artist" }, song.artist),
        groupLine(song.key)));
    }));
  }

  function groupLine(key) {
    const names = groups.groupsOf(key).map((id) => (groups.space.space.nodes.get(id) || {}).label || id);
    return names.length ? h("span", { class: "in-groups" }, names.join(" · ")) : null;
  }

  // ----- a song: reader and print views share the header and the toolbar -----------------

  async function renderSong(route, gen) {
    const known = history.state || {};
    const sameSong = app.dataset.song === route.song;
    if (!sameSong) openPanel = null;
    if (!sameSong) window.scrollTo(0, 0);
    app.dataset.song = route.song;
    const heading = h("h1", { tabindex: "-1" }, known.title || "Song");
    const byline = h("p", { class: "artist" }, known.artist || "");
    document.title = `${known.title || route.song} · ${CONFIG.title}`;
    const back = h("a", {
      href: location.pathname, class: "back",
      onclick: (e) => {
        e.preventDefault();
        // Back to the results this song was opened from, when they are the page underneath;
        // a song reached by a pasted link has nothing of ours underneath, so go to search
        if (known.from === "search") history.back();
        else { delete app.dataset.song; navigate({ q: "", lyrics: "" }); }
      },
    }, "← Search");
    const body = h("section", { class: "song-body" });
    const groupsHost = h("div", { class: "song-groups" });
    app.replaceChildren(h("header", { class: "song-head" }, back, heading, byline, groupsHost), body);
    showSongGroups(route.song, groupsHost, gen);
    if (!sameSong) heading.focus({ preventScroll: true });

    const spinner = loading("Opening the song…");
    body.replaceChildren(spinner);
    let song;
    try {
      song = songCache.get(route.song) || await getJSON("/song?" + new URLSearchParams({ key: route.song }));
      await getOptions().catch(() => null);
    } catch (error) {
      if (gen !== generation) return;
      body.replaceChildren(errorBox(error.message, () => renderSong(route, gen)));
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
    byline.textContent = song.artist || "";
    document.title = `${heading.textContent} · ${CONFIG.title}`;
    history.replaceState({ ...(history.state || {}), title: song.title, artist: song.artist }, "", location.href);

    const table = tableFor(song, route.t);
    const toolbar = buildToolbar(song, route, table);
    const look = prefs.look();
    applyLook(look);
    const content = route.view === "print"
      ? printView(song, route, gen)
      : h("div", { class: "read" }, displayControls(route), readerView(song, table, look), scrollControls(route.song, look));
    body.replaceChildren(toolbar, content);
  }

  // The song's groups as chips: type to add it to a group (or make one), × to take it out.
  async function showSongGroups(key, host, gen) {
    try {
      await groups.load(await getJSON("/songs"));
    } catch (_) {
      return; // groups are extra: the song reads without them
    }
    if (gen !== generation || !groups.space) return;
    const holder = h("div", { class: "chips-host" });
    host.replaceChildren(h("span", { class: "label" }, "Groups"), holder);
    groups.zg.renderTagInput(holder, groups.space).show(key);
    suggestGroups(holder);
  }

  // The tag input takes any name; offer the existing groups as suggestions (a phone's keyboard
  // shows them above the keys). Re-attached after each redraw of the chips.
  function suggestGroups(holder) {
    const id = "song-groups-suggestions";
    const attach = () => {
      let list = document.getElementById(id);
      if (!list) { list = h("datalist", { id }); document.body.append(list); }
      list.replaceChildren(...groups.list().map((g) => h("option", { value: g.label })));
      const input = holder.querySelector("input");
      if (input && input.getAttribute("list") !== id) { input.setAttribute("list", id); input.setAttribute("enterkeyhint", "done"); }
    };
    attach();
    new MutationObserver(attach).observe(holder, { childList: true, subtree: true });
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

  // The toolbar: size, key, view, settings. Panels open under it; only one at a time.
  function buildToolbar(song, route, table) {
    const look = prefs.look();
    const panelHost = h("div", { class: "panels" });
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
    if (!reading) size.append(h("button", {
      type: "button", class: "text", title: "Back to the size that fills the page",
      onclick: () => { prefs.setLook({ printScale: 1 }); goSong(route, {}); },
    }, "Fit"));

    const hasChords = (song.chords || []).length > 0;
    const keyLabel = table.key || "Key";
    const shift = (n) => goSong(route, { t: wrapShift(route.t + n, song) });
    const keyGroup = hasChords && h("div", { class: "group", role: "group", "aria-label": "Transpose" },
      h("button", { type: "button", class: "icon", title: "Down a semitone", "aria-label": "Down a semitone", onclick: () => shift(-1) }, "♭"),
      h("button", {
        type: "button", class: "text key", "aria-expanded": "false",
        "data-panel": "key",
        onclick: (e) => togglePanel(panelHost, e.currentTarget, () => transposePanel(song, route), "key"),
        title: "Transpose", "aria-label": `Key ${table.key || ""}, transpose`,
      }, keyLabel, route.t ? h("small", {}, ` ${route.t > 0 ? "+" : ""}${route.t}`) : null),
      h("button", { type: "button", class: "icon", title: "Up a semitone", "aria-label": "Up a semitone", onclick: () => shift(1) }, "♯"));

    const viewSwitch = h("div", { class: "group seg-switch", role: "group", "aria-label": "View" },
      h("button", { type: "button", "aria-pressed": String(reading), onclick: () => { if (!reading) { openPanel = null; goSong(route, { view: "read" }); } } }, "Read"),
      h("button", { type: "button", "aria-pressed": String(!reading), onclick: () => { if (reading) { openPanel = null; goSong(route, { view: "print" }); } } }, "Print"));

    const settings = h("button", {
      type: "button", class: "text", "aria-expanded": "false",
      "data-panel": "look",
      title: "Colours, opacity, chord size, spacing", "aria-label": "Look",
      onclick: (e) => togglePanel(panelHost, e.currentTarget, () => lookPanel(route), "look"),
    }, "Aa");

    const bar = h("div", { class: "toolbar" }, size, keyGroup, viewSwitch, settings);
    const reopen = openPanel && bar.querySelector(`[data-panel="${openPanel}"]`);
    if (reopen) { // a choice made in a panel re-renders the song; the panel stays open
      reopen.setAttribute("aria-expanded", "true");
      panelHost.append(openPanel === "key" ? transposePanel(song, route) : lookPanel(route));
    } else {
      openPanel = null;
    }
    return h("div", { class: "toolbar-wrap" }, bar, panelHost);
  }

  // Play/pause and − speed +. The speed is remembered per song.
  function scrollControls(key, look) {
    let level = prefs.scrollLevelOf(key);
    autoScroll.configure({ level, readSize: look.readSize });
    const play = h("button", {
      type: "button", class: "icon play", onclick: () => autoScroll.toggle(),
    });
    const value = h("span", { class: "size-value", "aria-live": "polite" }, String(level));
    const setLevel = (next) => {
      level = clamp(next, 1, SCROLL_LEVELS);
      prefs.setScrollLevel(key, level);
      autoScroll.configure({ level, readSize: prefs.look().readSize });
      value.textContent = String(level);
    };
    const show = (running) => {
      play.textContent = running ? "❚❚" : "▶";
      play.title = running ? "Pause scrolling" : "Scroll the song";
      play.setAttribute("aria-label", play.title);
      play.setAttribute("aria-pressed", String(running));
    };
    show(autoScroll.running);
    const unsubscribe = autoScroll.onChange(show);
    const group = h("div", { class: "scroll-pill", role: "group", "aria-label": "Auto-scroll" },
      play,
      h("button", { type: "button", class: "icon", title: "Slower", "aria-label": "Slower", onclick: () => setLevel(level - 1) }, "−"),
      value,
      h("button", { type: "button", class: "icon", title: "Faster", "aria-label": "Faster", onclick: () => setLevel(level + 1) }, "+"));
    scrollUnsubscribers.push(unsubscribe);
    return group;
  }
  const scrollUnsubscribers = [];

  function togglePanel(host, button, build, name) {
    const open = button.getAttribute("aria-expanded") === "true";
    for (const b of button.closest(".toolbar").querySelectorAll("[aria-expanded]")) b.setAttribute("aria-expanded", "false");
    host.replaceChildren();
    openPanel = open ? null : name;
    if (!open) {
      button.setAttribute("aria-expanded", "true");
      host.append(build());
    }
  }

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
        type: "button", role: "radio", value: String(n),
        title: n ? `${n > 0 ? "Up" : "Down"} ${Math.abs(n)} semitone${Math.abs(n) > 1 ? "s" : ""}` : "As written",
        onclick: () => goSong(route, { t: n }), // the panel stays open on the new key
      }, h("span", { class: "key-name" }, table.key), h("span", { class: "shift" }, n ? (n > 0 ? `+${n}` : String(n)) : "0")));
    }
    showChords();
    return h("div", { class: "panel" },
      h("p", { class: "muted hint" }, "Tap a key: the song and this table change together."),
      grid, chart,
      route.t ? h("button", { type: "button", class: "text", onclick: () => goSong(route, { t: 0 }) }, "Back to the original key") : null);
  }

  // The reader's look. Sliders preview live; the printed sheet follows on release.
  // Fine tuning: inks (kept per paper), opacity, chord size, spacing, font. Sliders
  // preview live; the printed sheet follows on release.
  function lookPanel(route) {
    const printing = route.view === "print";
    const look = printing ? prefs.look("light") : prefs.look(); // a PDF is printed on light paper
    const after = () => { if (printing) goSong(route, {}); }; // one re-render per deliberate change
    const preview = (changes) => { if (!printing) applyLook({ ...prefs.look(), ...changes }); };
    const restore = () => { if (!printing) applyLook(prefs.look()); }; // a cancelled pick leaves nothing

    function colorRow(label, colorName, alphaName) {
      const color = h("input", {
        type: "color", value: look[colorName], "aria-label": `${label} colour`,
        oninput: (e) => preview({ [colorName]: e.target.value }),
        onchange: (e) => { prefs.setInk(look.paperName, { [colorName]: e.target.value }); after(); },
        onblur: restore,
      });
      const value = h("output", {}, `${Math.round(look[alphaName] * 100)}%`);
      const alpha = h("input", {
        type: "range", min: "0.1", max: "1", step: "0.05", value: String(look[alphaName]),
        "aria-label": `${label} opacity`,
        oninput: (e) => { value.textContent = `${Math.round(e.target.value * 100)}%`; preview({ [alphaName]: Number(e.target.value) }); },
        onchange: (e) => { prefs.setLook({ [alphaName]: Number(e.target.value) }); after(); },
      });
      return h("div", { class: "row" }, h("span", { class: "label" }, label), color, alpha, value);
    }

    function rangeRow(label, name, min, max, step, format) {
      const value = h("output", {}, format(look[name]));
      const input = h("input", {
        type: "range", min: String(min), max: String(max), step: String(step), value: String(look[name]),
        "aria-label": label,
        oninput: (e) => { value.textContent = format(Number(e.target.value)); preview({ [name]: Number(e.target.value) }); },
        onchange: (e) => { prefs.setLook({ [name]: Number(e.target.value) }); after(); },
      });
      return h("div", { class: "row" }, h("span", { class: "label" }, label), input, value);
    }

    const font = h("select", {
      "aria-label": "Font",
      onchange: (e) => { prefs.setLook({ font: e.target.value }); preview({}); },
    }, Object.keys(FONTS).map((name) => h("option", { value: name, selected: name === look.font }, name)));

    const paperName = printing ? "white" : look.palette.label.toLowerCase();
    return h("div", { class: "panel look" },
      colorRow("Lyrics", "lyricColor", "lyricAlpha"),
      colorRow("Chords", "chordColor", "chordAlpha"),
      rangeRow("Chord size", "chordScale", 0.4, 1.3, 0.05, (v) => `${Math.round(v * 100)}%`),
      printing ? null : rangeRow("Line spacing", "lineHeight", 1, 2, 0.05, (v) => v.toFixed(2)),
      printing ? null : h("div", { class: "row" }, h("span", { class: "label" }, "Font"), font),
      h("p", { class: "muted hint" }, printing
        ? "Colours are those for light paper; opacity prints as the matching shade on white."
        : `Colours are kept for ${paperName} paper; the printed sheet uses those for light paper.`),
      h("button", { type: "button", class: "text", onclick: () => { prefs.resetLook(look.paperName); applyLook(prefs.look()); goSong(route, {}); } }, "Reset to defaults"));
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

  // The reader's display, always in view above the song (as the layout is above the sheet).
  function displayControls(route) {
    const look = prefs.look();
    const set = (changes) => { prefs.setLook(changes); goSong(route, {}); };
    function choiceRow(label, name, choices, current) {
      return h("div", { class: "row", role: "radiogroup", "aria-label": label },
        h("span", { class: "label" }, label),
        Object.entries(choices).map(([value, text]) => h("button", {
          type: "button", role: "radio", class: "chip", "aria-checked": String(value === String(current)),
          "data-value": value, onclick: () => set({ [name]: name === "columns" ? Number(value) : value },
          ),
        }, text)));
    }
    const papers = { auto: "Auto", ...Object.fromEntries(Object.entries(PAPERS).map(([k, v]) => [k, v.label])) };
    const paperRow = choiceRow("Paper", "paper", papers, PAPERS[look.paper] ? look.paper : "auto");
    for (const button of paperRow.querySelectorAll("[data-value]")) { // a swatch of each paper
      const palette = PAPERS[button.dataset.value];
      button.prepend(h("span", {
        class: "swatch" + (palette ? "" : " auto"),
        style: palette ? `background:${palette.paper}` : null, "aria-hidden": "true",
      }));
    }
    return h("fieldset", { class: "display" }, h("legend", {}, "Display"),
      paperRow,
      choiceRow("Chords", "chordMode", CHORD_MODES, look.chordMode),
      choiceRow("Columns", "columns", { 1: "One", 2: "Two" }, look.columns),
      h("div", { class: "row" }, h("span", { class: "label" }, "Sections"),
        h("label", { class: "chip" },
          h("input", { type: "checkbox", checked: look.shade, onchange: (e) => set({ shade: e.target.checked }) }),
          "Shade choruses")));
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
    const out = h("article", { class: classes.join(" "), lang: (song.meta && song.meta.lang) || "" });
    const meta = song.meta || {};
    const facts = [meta.capo && `Capo ${meta.capo}`, table.key && `Key ${table.key}`].filter(Boolean);
    if (facts.length) out.append(h("p", { class: "facts" }, facts.join(" · ")));
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

  function printView(song, route, gen) {
    const look = prefs.look();
    const controls = h("fieldset", { class: "layout" }, h("legend", {}, "Layout"));
    const viewer = h("div", { class: "viewer" });
    const params = new URLSearchParams({ key: route.song, layout: route.layout });
    if (route.t) params.set("transpose", String(route.t));
    if (look.printScale !== 1) params.set("scale", String(look.printScale));
    for (const [name, value] of Object.entries(prefs.printParams())) params.set(name, value);
    buildLayoutControls(route, controls);
    showSheet(params, viewer, gen, controls);
    return h("div", { class: "print" }, controls, viewer);
  }

  function buildLayoutControls(route, controls) {
    if (!options) return;
    const boxes = {};
    for (const option of options.options) {
      const box = h("input", {
        type: "checkbox", value: option.name,
        onchange: () => {
          if (box.checked) {
            // two options that set the same thing (where chords go) exclude each other
            for (const other of options.options) {
              if (other.name !== option.name && other.sets.some((s) => option.sets.includes(s))) boxes[other.name].checked = false;
            }
          }
          const layout = options.options.map((o) => o.name).filter((n) => boxes[n].checked).join("+") || "dense";
          goSong(route, { layout });
        },
      });
      boxes[option.name] = box;
      controls.append(h("label", { class: "chip" }, box, option.name));
    }
    syncLayout(controls, route.layout);
  }

  // Tick the boxes of a layout spec. The server's spelling (from /sheet) wins over the URL's,
  // which may use an alias ("2col") or another case.
  function syncLayout(controls, layout) {
    const chosen = new Set(layout.split("+"));
    for (const box of controls.querySelectorAll("input[type=checkbox]")) box.checked = chosen.has(box.value);
  }

  async function showSheet(params, viewer, gen, controls) {
    const spinner = loading("Making the sheet…");
    viewer.replaceChildren(spinner);
    try {
      const info = await getJSON("/sheet?" + params);
      if (gen !== generation) return;
      syncLayout(controls, info.layout);
      const pdfUrl = CONFIG.api + "/sheet.pdf?" + params;
      const facts = [info.font_size && `${Math.round(info.font_size)} pt`, info.pages > 1 && `${info.pages} pages`];
      const pages = [];
      for (let page = 1; page <= info.pages; page += 1) pages.push(pageImage(params, page, info, pdfUrl));
      viewer.replaceChildren(
        h("p", { class: "actions" },
          h("a", { class: "button", href: pdfUrl, target: "_blank", rel: "noopener" }, "Open PDF"),
          h("a", { class: "button secondary", href: pdfUrl, download: info.file_name }, "Download"),
          h("span", { class: "muted" }, facts.filter(Boolean).join(" · "))),
        ...pages
      );
    } catch (error) {
      if (gen !== generation) return;
      viewer.replaceChildren(errorBox(error.message, () => showSheet(params, viewer, gen, controls)));
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
