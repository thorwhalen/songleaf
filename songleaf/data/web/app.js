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
  // The reader's own defaults. Colours come from the server's sheet style (/layouts) when
  // it has answered; the PDF gets only what the viewer changed, so it keeps its own tuning.
  const DEFAULT_LOOK = {
    readSize: 20,
    printScale: 1,
    lyricColor: "#000000",
    lyricAlpha: 1,
    chordColor: "#3b73c4",
    chordAlpha: 1,
    chordScale: 0.62,
    lineHeight: 1.25,
    font: "sans",
  };
  const PRINT_PARAMS = { // reader setting -> /sheet parameter
    lyricColor: "lyric_color", lyricAlpha: "lyric_alpha",
    chordColor: "chord_color", chordAlpha: "chord_alpha", chordScale: "chord_scale",
  };
  const FONTS = {
    sans: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
    mono: 'ui-monospace, "SF Mono", Menlo, monospace',
  };
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
    function save() {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(values)); } catch (_) { /* not kept */ }
    }
    return {
      look() {
        const server = options && options.style
          ? { lyricColor: options.style.lyric_color, chordColor: options.style.chord_color, chordScale: options.style.chord_scale }
          : {};
        return { ...DEFAULT_LOOK, ...server, ...(values.look || {}) };
      },
      changed() { return { ...(values.look || {}) }; }, // only what the viewer set
      setLook(changes) { values.look = { ...(values.look || {}), ...changes }; save(); },
      resetLook() { delete values.look; save(); },
      transposeOf(key) { return (values.transpose || {})[key] || 0; },
      setTranspose(key, t) {
        values.transpose = { ...(values.transpose || {}) };
        if (t) values.transpose[key] = t; else delete values.transpose[key];
        save();
      },
    };
  })();

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

  function render() {
    clearTimeout(searchTimer); // a search typed just before leaving must not fire on the next view
    generation += 1;
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
          ? h("div", {}, h("h2", {}, "Songs you opened before"), songList(songs))
          : h("p", { class: "muted" }, "Search by title or artist, or by words of the lyrics.")
      );
    } catch (error) {
      if (gen !== generation) return;
      results.replaceChildren(errorBox(error.message, () => showStored(results, gen)));
    }
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
      }, h("span", { class: "title" }, song.title || song.key), song.artist && h("span", { class: "artist" }, song.artist)));
    }));
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
    const content = route.view === "print" ? printView(song, route, gen) : readerView(song, table);
    body.replaceChildren(toolbar, content);
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
  function lookPanel(route) {
    const look = prefs.look();
    const printing = route.view === "print";
    const commit = (changes) => {
      prefs.setLook(changes);
      if (printing) goSong(route, {}); // one re-render per deliberate change
    };
    const preview = (changes) => applyLook({ ...prefs.look(), ...changes });

    function colorRow(label, colorName, alphaName) {
      const color = h("input", {
        type: "color", value: look[colorName], "aria-label": `${label} colour`,
        oninput: (e) => preview({ [colorName]: e.target.value }),
        onchange: (e) => commit({ [colorName]: e.target.value }),
      });
      const value = h("output", {}, `${Math.round(look[alphaName] * 100)}%`);
      const alpha = h("input", {
        type: "range", min: "0.1", max: "1", step: "0.05", value: String(look[alphaName]),
        "aria-label": `${label} opacity`,
        oninput: (e) => { value.textContent = `${Math.round(e.target.value * 100)}%`; preview({ [alphaName]: Number(e.target.value) }); },
        onchange: (e) => commit({ [alphaName]: Number(e.target.value) }),
      });
      return h("div", { class: "row" }, h("span", { class: "label" }, label), color, alpha, value);
    }

    function rangeRow(label, name, min, max, step, format) {
      const value = h("output", {}, format(look[name]));
      const input = h("input", {
        type: "range", min: String(min), max: String(max), step: String(step), value: String(look[name]),
        "aria-label": label,
        oninput: (e) => { value.textContent = format(Number(e.target.value)); preview({ [name]: Number(e.target.value) }); },
        onchange: (e) => commit({ [name]: Number(e.target.value) }),
      });
      return h("div", { class: "row" }, h("span", { class: "label" }, label), input, value);
    }

    const font = h("select", {
      "aria-label": "Font",
      onchange: (e) => { preview({ font: e.target.value }); commit({ font: e.target.value }); },
    }, Object.keys(FONTS).map((name) => h("option", { value: name, selected: name === look.font }, name)));

    return h("div", { class: "panel look" },
      colorRow("Lyrics", "lyricColor", "lyricAlpha"),
      colorRow("Chords", "chordColor", "chordAlpha"),
      rangeRow("Chord size", "chordScale", 0.4, 1.3, 0.05, (v) => `${Math.round(v * 100)}%`),
      printing ? null : rangeRow("Line spacing", "lineHeight", 1, 2, 0.05, (v) => v.toFixed(2)),
      printing ? null : h("div", { class: "row" }, h("span", { class: "label" }, "Font"), font),
      h("p", { class: "muted hint" }, printing
        ? "Colours and opacity print as the matching shade on white paper."
        : "These settings apply to the printed sheet too."),
      h("button", { type: "button", class: "text", onclick: () => { prefs.resetLook(); goSong(route, {}); } }, "Reset to defaults"));
  }

  function applyLook(look) {
    const root = document.documentElement.style;
    root.setProperty("--read-size", `${look.readSize}px`);
    root.setProperty("--lyric-ink", rgba(look.lyricColor, look.lyricAlpha));
    root.setProperty("--chord-ink", rgba(look.chordColor, look.chordAlpha));
    root.setProperty("--chord-scale", String(look.chordScale));
    root.setProperty("--read-line", String(look.lineHeight));
    root.setProperty("--read-font", FONTS[look.font] || FONTS.sans);
  }

  // ----- the reader: the song as text, chords over the syllables they land on --------------

  function readerView(song, table) {
    applyLook(prefs.look());
    const text = song.text || "";
    const chordsAt = new Map(); // offset -> [symbols], in song order
    const labelsAt = new Map(); // offset -> section label
    for (const a of song.annotations || []) {
      if (a.kind === "chord") {
        const symbol = table.chords[a.body.symbol] || a.body.symbol;
        if (!chordsAt.has(a.start)) chordsAt.set(a.start, []);
        chordsAt.get(a.start).push(symbol);
      } else if (a.kind === "section" && a.body.label && !labelsAt.has(a.start)) {
        labelsAt.set(a.start, a.body.label);
      }
    }
    const out = h("article", { class: "reader", lang: (song.meta && song.meta.lang) || "" });
    const meta = song.meta || {};
    const facts = [meta.capo && `Capo ${meta.capo}`, table.key && `Key ${table.key}`].filter(Boolean);
    if (facts.length) out.append(h("p", { class: "facts" }, facts.join(" · ")));
    let start = 0;
    for (const line of text.split("\n")) {
      const end = start + line.length;
      const label = labelsAt.get(start);
      if (label) out.append(h("div", { class: "section-label" }, label));
      out.append(readerLine(line, start, end, chordsAt));
      start = end + 1;
    }
    return out;
  }

  function readerLine(line, start, end, chordsAt) {
    const offsets = [];
    for (let i = start; i <= end; i += 1) if (chordsAt.has(i)) offsets.push(i);
    if (!line.trim() && !offsets.length) return h("div", { class: "line blank" });
    if (!offsets.length) return h("div", { class: "line" }, line);
    if (!line.trim()) { // an instrumental line: chords only
      const all = offsets.flatMap((i) => chordsAt.get(i));
      return h("div", { class: "line chords-only" }, all.map((c) => h("span", { class: "ch" }, c)));
    }
    // Pieces break at every chord and after every space; pieces join into words, and a
    // line wraps only between words, never inside one.
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
        h("span", { class: "ch" }, chords ? chords.join(" ") : " "),
        h("span", { class: "ly" }, piece.replace(/ {2,}/g, " ") || " ")));
    });
    const trailing = chordsAt.get(end); // chords after the last syllable
    if (trailing && end > start) el.append(h("span", { class: "w" }, h("span", { class: "p" },
      h("span", { class: "ch" }, trailing.join(" ")), h("span", { class: "ly" }, " "))));
    return el;
  }

  // ----- the printed sheet: layout options, size, page images, PDF ------------------------

  function printView(song, route, gen) {
    const look = prefs.look();
    const controls = h("fieldset", { class: "layout" }, h("legend", {}, "Layout"));
    const viewer = h("div", { class: "viewer" });
    const params = new URLSearchParams({ key: route.song, layout: route.layout });
    if (route.t) params.set("transpose", String(route.t));
    if (look.printScale !== 1) params.set("scale", String(look.printScale));
    for (const [name, value] of Object.entries(prefs.changed())) {
      if (PRINT_PARAMS[name]) params.set(PRINT_PARAMS[name], String(value));
    }
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
