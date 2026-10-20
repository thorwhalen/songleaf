// The Ultimate Guitar bookmarklet (songleaf#28). The page turns this file into a
// `javascript:` link the reader saves as a bookmark, with the PAGE placeholder replaced by
// the songleaf page's own address. Clicked on a community chord page the reader opened on
// ultimate-guitar.com, it reads the chart from that page and opens songleaf's paste form
// filled in with it; nothing is stored until the reader presses Import there.
//
// It refuses official and Pro pages (their content is UG's own player's, behind its
// subscription), the same rule as songleaf.ultimate_guitar.refusal on the server.
// The chart travels in the URL fragment, which no server sees.
(function () {
  var PAGE = "__SONGLEAF_PAGE__";
  var REFUSED_TYPES = ["official", "pro", "power", "video"];
  var OFFICIAL =
    "This is an official or Pro tab: Ultimate Guitar serves it only in its own player, " +
    "and songleaf does not copy it from there. Open a community 'Chords' version of the song instead.";
  var NO_CHART = "This page has no text chord chart for songleaf to read. Open a community 'Chords' or 'Tabs' page.";
  function say(message) { window.alert("songleaf: " + message); }

  if (!/(^|\.)ultimate-guitar\.com$/i.test(window.location.hostname)) {
    say("open a song's chord page on ultimate-guitar.com, then use this bookmark there.");
    return;
  }
  if (/-(?:official|pro|power|video)-\d+|\/pro\/|\/official\//i.test(window.location.pathname)) { say(OFFICIAL); return; }

  var store = null;
  try {
    var element = document.querySelector(".js-store");
    if (element) store = JSON.parse(element.getAttribute("data-content") || "null");
    else if (window.UGAPP && window.UGAPP.store) store = window.UGAPP.store;
  } catch (error) { store = null; }
  var inner = store && (store.store || store);
  var data = (inner && inner.page && inner.page.data) || {};
  var tab = data.tab || {};
  var view = data.tab_view || {};
  if (REFUSED_TYPES.indexOf(String(tab.type || "").toLowerCase()) >= 0) { say(OFFICIAL); return; }
  var text = view.wiki_tab && view.wiki_tab.content;
  if (typeof text !== "string" || !text.trim()) { say(NO_CHART); return; }

  var capo = view.meta && view.meta.capo;
  var chart = {
    text: text,
    title: String(tab.song_name || ""),
    artist: String(tab.artist_name || ""),
    key: String(tab.tonality_name || ""),
    capo: capo ? String(capo) : "",
    url: window.location.origin + window.location.pathname,
    format: "ultimate-guitar",
  };
  var target = PAGE + "#import=" + encodeURIComponent(JSON.stringify(chart));
  var opened = window.open(target, "_blank");
  if (opened) { try { opened.opener = null; } catch (error) { /* already elsewhere */ } }
  else window.location.assign(target);
})();
