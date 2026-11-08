"""Import by URL and kept songs in local search (songleaf.online.import_url, StoredWebSource).

Every page is invented and ``fetch`` is injected: no test reaches the network.
"""

import html
import json

import pytest

from songleaf import online, tools
from songleaf import ultimate_guitar as ug
from songleaf.online import ChartPageSite, StoredWebSource, import_url, site_for_url
from songleaf.parse import parse_chords_over_lyrics

CHART = "\n".join(
    [
        "G              D",
        "Paper boats on a silver stream",
        "Em             C",
        "carry the names of a morning dream",
        "C          G",
        "Sing it slow, sing it low",
        "Am            D",
        "let the river know",
    ]
)
PAGE_URL = "https://chords.example/song.pere/paper-boats-1.html"
SITE = ChartPageSite(
    name="invented",
    search_url="https://www.chords.example/search?q={query}",
    result_link=r'<a[^>]+href="(?P<url>[^"]*song\.pere/[^"]+)"[^>]*>(?P<label>.*?)</a>',
    page_path=r"^/song\.pere/",
)
UG_URL = "https://tabs.ultimate-guitar.com/tab/the-invented-band/paper-boats-chords-424242"
UG_CHART = "[Verse 1]\n" + "\n".join(
    f"[tab][ch]G[/ch]          [ch]D[/ch]\n{line}[/tab]"
    for line in CHART.split("\n")[1::2]
)


def song_page(chart=CHART, *, heading="Paper Boats&nbsp;&nbsp;<a>The Invented Band</a>"):
    escaped = chart.replace("&", "&amp;").replace("<", "&lt;")
    return (
        "<html><head><title>Paper Boats chords | Invented</title></head><body>"
        f"<h1>{heading}</h1><pre>Tuning: E A D G B E</pre><pre>{escaped}</pre></body></html>"
    )


def ug_page():
    store = {
        "store": {
            "page": {
                "data": {
                    "tab": {
                        "id": 424242,
                        "type": "Chords",
                        "song_name": "Paper Boats",
                        "artist_name": "The Invented Band",
                        "tab_url": UG_URL,
                    },
                    "tab_view": {"wiki_tab": {"content": UG_CHART}, "meta": {}},
                }
            }
        }
    }
    return f'<div class="js-store" data-content="{html.escape(json.dumps(store))}"></div>'


def counting(page):
    asked = []

    def fetch(url):
        asked.append(url)
        return page

    fetch.asked = asked
    return fetch


def test_a_chart_site_claims_only_its_own_song_pages():
    claimed = SITE.candidate_for(PAGE_URL)
    assert claimed.site == "invented" and claimed.url == PAGE_URL
    assert claimed.id == online.url_id(PAGE_URL)  # what its search gives the same page
    assert SITE.candidate_for("https://www.chords.example/song.pere/x.html")  # www. or not
    for other in [
        "https://elsewhere.example/song.pere/x.html",
        "http://chords.example/song.pere/x.html",
        "https://user@chords.example/song.pere/x.html",
        "https://chords.example/search?q=x",
    ]:
        assert SITE.candidate_for(other) is None


def test_import_url_keeps_the_page_once_with_its_heading_and_provenance():
    store, fetch = {}, counting(song_page())
    first = import_url(PAGE_URL, sites=[SITE], fetch=fetch, store=store)
    again = import_url(PAGE_URL, sites=[SITE], fetch=fetch, store=store)
    assert first.key == again.key == f"web:invented:{online.url_id(PAGE_URL)}"
    assert (first.cached, again.cached) == (False, True) and fetch.asked == [PAGE_URL]
    song = store[first.key]
    assert (song.title, song.artist) == ("Paper Boats", "The Invented Band")
    assert song.provenance["url"] == PAGE_URL and song.provenance["license"] == "personal"
    assert online.chart_counts(song)[1] >= 8
    import_url(PAGE_URL, sites=[SITE], fetch=fetch, store=store, refresh=True)
    assert len(fetch.asked) == 2


def test_a_page_with_no_chart_is_refused_and_not_kept():
    store = {}
    with pytest.raises(ValueError):
        import_url(PAGE_URL, sites=[SITE], fetch=counting("<html>ads</html>"), store=store)
    assert store == {}


def test_an_unknown_host_names_the_sites_that_read_pages():
    with pytest.raises(ValueError, match="invented"):
        site_for_url("https://nowhere.example/a-song", sites=[SITE])
    with pytest.raises(ValueError, match="chordie"):
        site_for_url("https://nowhere.example/a-song")  # the registry by default


def test_the_registry_reads_chordie_and_ultimate_guitar_pages_but_searches_neither_by_default():
    assert site_for_url("https://www.chordie.com/chord.pere/x.example/a.html")[0].name == (
        "chordie"
    )
    site, candidate = site_for_url(UG_URL)
    assert site.name == "ug" and candidate.key == "ug:424242"
    assert site.find("paper boats") == []
    assert "ug" not in online.DEFAULT_WEB_SITES and "chordie" not in online.DEFAULT_WEB_SITES


def test_ultimate_guitar_by_url_is_opt_in_and_a_kept_chart_needs_no_request(monkeypatch):
    store, fetch = {}, counting(ug_page())
    monkeypatch.delenv(ug.URL_SOURCE_ENVVAR, raising=False)
    with pytest.raises(ValueError, match="off"):
        tools.import_url(UG_URL, store=store, fetch=fetch)
    assert fetch.asked == []
    monkeypatch.setenv(ug.URL_SOURCE_ENVVAR, "1")
    kept = tools.import_url(UG_URL, store=store, fetch=fetch)
    assert kept["key"] == "ug:424242" and kept["site"] == "ultimate-guitar"
    monkeypatch.delenv(ug.URL_SOURCE_ENVVAR)
    assert tools.import_url(UG_URL, store=store, fetch=fetch)["cached"] is True
    assert fetch.asked == [UG_URL]
    with pytest.raises(ug.RefusedPage):
        tools.import_url(UG_URL.replace("chords-424242", "official-5150"), store=store)


def test_imported_and_pasted_songs_are_found_by_local_search(monkeypatch):
    monkeypatch.setenv(ug.URL_SOURCE_ENVVAR, "1")
    store = {}
    tools.import_url(UG_URL, store=store, fetch=counting(ug_page()))
    tools.import_url(PAGE_URL, store=store, fetch=counting(song_page()), source=SITE)
    pasted = tools.import_text(
        CHART.replace("Paper boats", "Lantern light"), title="Lantern Light", store=store
    )
    store["kaggle_chords:9"] = parse_chords_over_lyrics(CHART, meta={"title": "Paper Boats"})
    sources = [StoredWebSource(store)]
    found = {row["key"] for row in tools.search("paper boats", sources=sources, web="off")}
    assert found == {"ug:424242", f"web:invented:{online.url_id(PAGE_URL)}"}  # not the cache
    rows = tools.search("lantern light", sources=sources, web="off")
    assert [(row["key"], row["source"]) for row in rows] == [(pasted["key"], "paste")]
