// songleaf page: search the corpus, open a song as a one-page PDF sheet.
//
// The URL is the state. `?q=..&lyrics=..` is the search view, `?song=<key>&layout=<spec>`
// the sheet view. Opening a song pushes a history entry (Back returns to the results);
// typing a query and changing the layout replace it. Nothing is kept in browser storage.
(function () {
  "use strict";

  const CONFIG = window.SONGLEAF || { api: "", base: "", title: "songleaf" };
  const SEARCH_DEBOUNCE_MS = 300;
  const SLOW_MS = 3000; // past this, say why the wait is long
  const app = document.getElementById("app");
  let generation = 0; // bumps on every render: a late response from an older view is dropped
  let layoutOptions = null; // [{name, sets}] from /layouts, fetched once

  // --- the route: one module owns history ------------------------------------------------

  function readRoute() {
    const params = new URLSearchParams(location.search);
    return {
      q: params.get("q") || "",
      lyrics: params.get("lyrics") || "",
      song: params.get("song") || "",
      layout: params.get("layout") || "dense",
    };
  }

  function formatRoute(route) {
    const params = new URLSearchParams();
    const keys = route.song ? ["song", "layout"] : ["q", "lyrics"];
    for (const key of keys) {
      if (route[key] && !(key === "layout" && route[key] === "dense")) params.set(key, route[key]);
    }
    const query = params.toString();
    return location.pathname + (query ? "?" + query : "");
  }

  function navigate(route, { replace = false, state = {} } = {}) {
    const url = formatRoute(route);
    if (url === location.pathname + location.search) {
      history.replaceState(state, "", url);
    } else if (replace) {
      history.replaceState(state, "", url);
    } else {
      history.pushState(state, "", url);
    }
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

  function loading(label) {
    const note = h("p", { class: "muted slow", hidden: true },
      "The first search after a restart loads the song corpus, which can take a minute.");
    const timer = setTimeout(() => { note.hidden = false; }, SLOW_MS);
    const box = h("div", { class: "loading", "aria-busy": "true" }, h("span", { class: "spinner" }), label, note);
    box.stop = () => clearTimeout(timer);
    return box;
  }

  function errorBox(message, retry) {
    return h("div", { class: "error", role: "alert" },
      h("p", {}, message),
      retry && h("button", { type: "button", onclick: retry }, "Try again"));
  }

  // --- views -----------------------------------------------------------------------------

  function render() {
    generation += 1;
    const route = readRoute();
    window.scrollTo(0, 0);
    if (route.song) renderSheet(route, generation);
    else renderSearch(route, generation);
  }

  function renderSearch(route, gen) {
    document.title = route.q || route.lyrics ? `${route.q || route.lyrics} · ${CONFIG.title}` : CONFIG.title;
    const results = h("section", { class: "results", "aria-live": "polite" });
    let timer = null;
    // A refinement replaces the URL and refreshes the results only: the inputs stay as
    // they are, so typing (and a phone's keyboard) is never interrupted.
    const refine = () => {
      clearTimeout(timer);
      const next = { q: query.value.trim(), lyrics: lyrics.value.trim() };
      history.replaceState({}, "", formatRoute(next));
      document.title = next.q || next.lyrics ? `${next.q || next.lyrics} · ${CONFIG.title}` : CONFIG.title;
      generation += 1;
      showResults(next, results, generation);
    };
    const onInput = () => {
      clearTimeout(timer);
      timer = setTimeout(refine, SEARCH_DEBOUNCE_MS);
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
    const spinner = loading("Searching…");
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
    return h("ul", { class: "songs" }, songs.map((song) =>
      h("li", {}, h("a", {
        href: formatRoute({ song: song.key, layout: "dense" }),
        onclick: (e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // let new-tab work
          e.preventDefault();
          navigate({ song: song.key, layout: "dense" }, { state: { from: "search", title: song.title, artist: song.artist } });
        },
      }, h("span", { class: "title" }, song.title || song.key), song.artist && h("span", { class: "artist" }, song.artist)))
    ));
  }

  async function renderSheet(route, gen) {
    const known = history.state || {};
    const heading = h("h1", { tabindex: "-1" }, known.title || "Song sheet");
    const byline = h("p", { class: "artist" }, known.artist || "");
    document.title = `${known.title || route.song} · ${CONFIG.title}`;
    const back = h("a", {
      href: CONFIG.base + "/", class: "back",
      onclick: (e) => {
        e.preventDefault();
        // Back to the results this sheet was opened from, when they are the page underneath;
        // a sheet reached by a pasted link has nothing of ours underneath, so go forward to search
        if (known.from === "search") history.back();
        else navigate({ q: "", lyrics: "" });
      },
    }, "← Search");
    const controls = h("fieldset", { class: "layout" }, h("legend", {}, "Layout"));
    const viewer = h("section", { class: "viewer" });
    app.replaceChildren(h("header", {}, back, heading, byline), controls, viewer);
    heading.focus({ preventScroll: true });
    buildLayoutControls(route, controls);
    showPdf(route, viewer, gen, { heading, byline });
  }

  async function buildLayoutControls(route, controls) {
    try {
      if (!layoutOptions) layoutOptions = (await getJSON("/layouts")).options;
    } catch (_) {
      return; // the sheet still shows, in the layout the URL names
    }
    const chosen = new Set(route.layout.split("+").filter((o) => o && o !== "dense"));
    for (const option of layoutOptions) {
      const box = h("input", {
        type: "checkbox", value: option.name, checked: chosen.has(option.name),
        onchange: () => {
          if (box.checked) {
            // two options that set the same thing (where chords go) exclude each other
            for (const other of layoutOptions) {
              if (other.name !== option.name && other.sets.some((s) => option.sets.includes(s))) chosen.delete(other.name);
            }
            chosen.add(option.name);
          } else {
            chosen.delete(option.name);
          }
          const layout = layoutOptions.map((o) => o.name).filter((n) => chosen.has(n)).join("+") || "dense";
          navigate({ song: route.song, layout }, { replace: true, state: history.state || {} });
        },
      });
      controls.append(h("label", { class: "chip" }, box, option.name));
    }
  }

  async function showPdf(route, viewer, gen, { heading, byline }) {
    const spinner = loading("Making the sheet…");
    viewer.replaceChildren(spinner);
    const params = new URLSearchParams({ key: route.song, layout: route.layout });
    try {
      const info = await getJSON("/sheet?" + params);
      if (gen !== generation) return;
      heading.textContent = info.title || info.key;
      byline.textContent = info.artist || "";
      document.title = `${heading.textContent} · ${CONFIG.title}`;
      history.replaceState({ ...(history.state || {}), title: info.title, artist: info.artist }, "", location.href);
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
      viewer.replaceChildren(errorBox(error.message, () => showPdf(route, viewer, gen, { heading, byline })));
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

  render();
})();
