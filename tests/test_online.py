"""The web expansion (songleaf.online), on synthesized pages and an injected fetch.

No test reaches the network: every page here is invented, and ``fetch`` is a dict.
"""

import json
import logging

import pytest

from songleaf import online, tools
from songleaf.online import (
    Candidate,
    ChartPageSite,
    LrclibSite,
    StoredWebSource,
    chart_text,
    expand,
    find_online,
    is_usable,
    web_mode,
    web_sites,
)
from songleaf.parse import parse_chords_over_lyrics

LYRICS = "\n".join(
    [
        "Paper boats on a silver stream",
        "carry the names of a morning dream",
        "sing it slow, sing it low",
        "let the river know",
        "",
        "lanterns drift where the willows lean",
        "past the mill and the meadow green",
    ]
)

CHORDPRO = "\n".join(
    [
        "{t:Paper Boats}",
        "{st:The Invented Band}",
        "[G]Paper boats on a [D]silver stream",
        "[Em]carry the names of a [C]morning dream",
        "[C]sing it slow, [G]sing it low",
        "[Am]let the river [D]know",
    ]
)

CHART_OVER = "\n".join(
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

LRCLIB_RECORDS = [
    {
        "id": 7,
        "trackName": "Paper Boats",
        "artistName": "The Invented Band",
        "albumName": "Rivers",
        "instrumental": False,
        "plainLyrics": LYRICS,
        "syncedLyrics": "[00:01.00] Paper boats on a silver stream\n"
        "[00:05.00] carry the names of a morning dream",
    },
    {
        "id": 8,
        "trackName": "Paper Boats (instrumental)",
        "artistName": "The Invented Band",
        "instrumental": True,
        "plainLyrics": "",
    },
    {
        "id": 9,
        "trackName": "Completely Different",
        "artistName": "Somebody Else",
        "instrumental": False,
        "plainLyrics": LYRICS,
    },
]

SEARCH_PAGE = """
<html><body>
<a href="/song.pere/paper-boats-1.html">Paper Boats&nbsp;&nbsp;The Invented Band</a>
<a href="/song.pere/paper-boats-1.html">Paper boats on a silver stream...</a>
<a href="/song.pere/quiet-road.html">Quiet Road&nbsp;&nbsp;The Invented Band</a>
<a href="https://elsewhere.example/song.pere/paper-boats.html">Paper Boats&nbsp;&nbsp;Elsewhere</a>
</body></html>
"""


def chart_page(chart, *, decoy="Tuning: E A D G B E"):
    """A chord page: navigation, a short decoy block, and the chart in a <pre>."""
    escaped = chart.replace("&", "&amp;").replace("<", "&lt;")
    return (
        "<html><body><nav>Home | Songs</nav>"
        f"<pre>{decoy}</pre><div class='ad'>buy now</div>"
        f"<pre class='chart'>{escaped}</pre></body></html>"
    )


SITE = ChartPageSite(
    name="invented",
    search_url="https://chords.example/search?q={query}",
    result_link=r'<a[^>]+href="(?P<url>[^"]*song\.pere/[^"]+)"[^>]*>(?P<label>.*?)</a>',
)


def fetcher(pages):
    """``url -> text`` over a dict, recording every URL asked for."""
    asked = []

    def fetch(url):
        asked.append(url)
        for prefix, page in pages.items():
            if url.startswith(prefix):
                return page
        raise online.FetchFailed(f"{url} answered 404")

    fetch.asked = asked
    return fetch


@pytest.fixture
def lrclib_fetch():
    return fetcher({"https://lrclib.net/api/search": json.dumps(LRCLIB_RECORDS)})


@pytest.fixture
def site_fetch():
    return fetcher(
        {
            "https://chords.example/search": SEARCH_PAGE,
            "https://chords.example/song.pere/paper-boats-1.html": chart_page(
                CHART_OVER
            ),
            "https://chords.example/song.pere/quiet-road.html": chart_page(
                "nothing but a note"
            ),
        }
    )


# --- configuration ------------------------------------------------------------------


def test_the_default_sites_are_lrclib_only_and_the_list_is_configuration(monkeypatch):
    assert [site.name for site in web_sites()] == ["lrclib"]
    monkeypatch.setenv("SONGLEAF_WEB_SITES", "chordie, lrclib")
    assert [site.name for site in web_sites()] == ["chordie", "lrclib"]
    assert web_sites([SITE]) == (SITE,)  # a site object is an entry too
    with pytest.raises(ValueError, match="No web site named 'nope'"):
        web_sites("nope")


def test_the_web_mode_defaults_to_fallback_and_is_checked(monkeypatch):
    monkeypatch.delenv("SONGLEAF_WEB_SEARCH")
    assert web_mode() == "fallback"
    assert web_mode("ALWAYS") == "always"
    with pytest.raises(ValueError, match="one of fallback, always, off"):
        web_mode("sometimes")


def test_a_site_is_a_web_site_by_its_shape():
    assert isinstance(LrclibSite(), online.WebSite)
    assert isinstance(SITE, online.WebSite)


# --- extraction ---------------------------------------------------------------------


def test_chart_text_picks_the_block_that_reads_as_a_chart():
    page = chart_page(CHART_OVER)
    assert chart_text(page) == CHART_OVER
    # a ChordPro source in a <textarea> beats a short <pre>
    page = f"<pre>Capo 2</pre><textarea>{CHORDPRO}</textarea>"
    assert chart_text(page) == CHORDPRO
    assert chart_text("<html><p>no chart here</p></html>") == ""
    assert chart_text("<pre>G D Em C</pre>") == ""  # chords alone are not a song


def test_is_usable_wants_lyrics_and_promised_chords():
    chart = parse_chords_over_lyrics(CHART_OVER)
    lyrics_only = parse_chords_over_lyrics(LYRICS)
    assert is_usable(chart, chords=True)
    assert is_usable(lyrics_only, chords=False)
    assert not is_usable(lyrics_only, chords=True)
    assert not is_usable(parse_chords_over_lyrics("la la"), chords=False)


def test_lrclib_finds_skips_instrumentals_and_extracts_lyrics_with_times(lrclib_fetch):
    site = LrclibSite()
    candidates = site.find("paper boats invented band", limit=5, fetch=lrclib_fetch)
    assert [c.id for c in candidates] == ["7", "9"]
    song = site.extract(candidates[0], fetch=lrclib_fetch)
    assert song.text.startswith("Paper boats on a silver stream")
    assert song.meta["album"] == "Rivers"
    assert [a.body["ms"] for a in song.of_kind("time")] == [1000, 5000]
    assert len(lrclib_fetch.asked) == 1  # the search answered with the lyrics


def test_a_chart_page_site_finds_on_its_own_host_and_extracts_the_chart(site_fetch):
    found = SITE.find("paper boats", limit=5, fetch=site_fetch)
    assert [(c.title, c.artist) for c in found] == [
        ("Paper Boats", "The Invented Band"),
        ("Quiet Road", "The Invented Band"),
    ]  # the duplicate link and the other host's link are dropped
    song = SITE.extract(found[0], fetch=site_fetch)
    assert song.title == "Paper Boats" and song.artist == "The Invented Band"
    assert song.of_kind("chord")[0].body["symbol"] == "G"


# --- ranking, picking, persisting ---------------------------------------------------


def test_candidates_rank_by_closeness_with_a_bonus_for_chords(lrclib_fetch, site_fetch):
    def fetch(url):
        return (lrclib_fetch if "lrclib" in url else site_fetch)(url)

    ranked = find_online(
        "paper boats invented band", sites=[LrclibSite(), SITE], fetch=fetch
    )
    sites = [site.name for _, _, site in ranked]
    assert sites[0] == "invented"  # the chart beats the lyrics of the same song
    names = [c.title for _, c, _ in ranked]
    assert "Completely Different" not in names  # too far from the query


def test_expand_stores_the_best_usable_song_with_provenance(lrclib_fetch):
    store = {}
    found = expand("paper boats invented band", fetch=lrclib_fetch, store=store)
    assert found.key == "web:lrclib:7" and not found.cached
    kept = store["web:lrclib:7"]
    assert kept.provenance["source"] == "web"
    assert kept.provenance["site"] == "lrclib"
    assert kept.provenance["url"] == "https://lrclib.net/api/get/7"
    assert kept.provenance["license"] == "personal"
    assert kept.provenance["fetched_at"]


def test_expand_skips_an_unusable_page_and_tries_the_next(site_fetch):
    store = {}
    found = expand("quiet road", sites=[SITE], fetch=site_fetch, store=store)
    assert found is None and store == {}  # its page has no chart
    found = expand("paper boats", sites=[SITE], fetch=site_fetch, store=store)
    assert found.key.startswith("web:invented:")


def test_a_kept_song_is_returned_without_a_request(lrclib_fetch):
    store = {}
    expand("paper boats invented band", fetch=lrclib_fetch, store=store)
    asked = len(lrclib_fetch.asked)
    found = expand("paper boats invented band", fetch=lrclib_fetch, store=store)
    assert found.cached and len(lrclib_fetch.asked) == asked + 1  # the search only


def test_a_failing_site_is_logged_and_the_others_still_answer(lrclib_fetch, caplog):
    def broken(url):
        if "chords.example" in url:
            raise online.FetchFailed("chords.example answered 503")
        return lrclib_fetch(url)

    with caplog.at_level(logging.WARNING, logger="songleaf.online"):
        ranked = find_online("paper boats", sites=[SITE, LrclibSite()], fetch=broken)
    assert {site.name for _, _, site in ranked} == {"lrclib"}
    assert "searching invented failed" in caplog.text


# --- the local source and the tools -------------------------------------------------


def test_the_stored_web_source_finds_kept_songs_locally(lrclib_fetch):
    store = {}
    expand("paper boats invented band", fetch=lrclib_fetch, store=store)
    store["kaggle_chords:1"] = parse_chords_over_lyrics(LYRICS, meta={"title": "Other"})
    web = StoredWebSource(store)
    (hit,) = web.search("paper boats")
    assert hit.key == "web:lrclib:7" and hit.meta == {"site": "lrclib"}
    assert web.search(artist="invented band")[0].key == "web:lrclib:7"
    assert web.search(lyrics="willows lean")[0].key == "web:lrclib:7"
    assert web.search("other") == []  # only the web: keys
    assert web.get("lrclib:7").title == "Paper Boats"
    with pytest.raises(KeyError):
        web.get("lrclib:404")


def test_search_falls_back_to_the_web_then_finds_the_song_locally(
    memory_source, lrclib_fetch
):
    store = {}
    kwargs = dict(store=store, fetch=lrclib_fetch, web="fallback")
    local = [memory_source, StoredWebSource(store)]
    # a local title match: no request
    rows = tools.search("quiet road", sources=local, **kwargs)
    assert rows and all(row["match"] != "web" for row in rows)
    assert lrclib_fetch.asked == []
    # nothing close enough here or online: nothing kept
    assert tools.search("silver willows", sources=local, **kwargs) == []
    assert store == {}
    # nothing here, the song online: one request, the song kept and reported
    only_web = [StoredWebSource(store)]
    (row,) = tools.search("Paper Boats Invented Band", sources=only_web, **kwargs)
    assert (row["match"], row["key"], row["cached"]) == ("web", "web:lrclib:7", False)
    assert row["meta"]["url"] == "https://lrclib.net/api/get/7"
    assert row["highlight"]["title"]  # tagged like any other row
    asked = len(lrclib_fetch.asked)
    # the next search is local: a title match, nothing fetched
    rows = tools.search("Paper Boats Invented Band", sources=only_web, **kwargs)
    assert (rows[0]["key"], rows[0]["match"]) == ("web:lrclib:7", "title")
    assert len(lrclib_fetch.asked) == asked


def test_search_expands_on_request_and_stays_off_when_told(memory_source, lrclib_fetch):
    store = {}
    common = dict(sources=[memory_source], store=store, fetch=lrclib_fetch)
    rows = tools.search("paper boats", web="always", **common)
    kinds = [row["match"] for row in rows]
    assert kinds[0] == "title" and "web" in kinds  # after the local title match
    lrclib_fetch.asked.clear()
    assert all(
        r["match"] != "web" for r in tools.search("nothing", web="off", **common)
    )
    assert lrclib_fetch.asked == []


def test_a_missing_online_extra_stops_only_an_explicit_always(
    monkeypatch, memory_source
):
    def unavailable(url):
        raise online.OnlineUnavailable("pip install 'songleaf[online]'")

    common = dict(sources=[memory_source], store={}, fetch=unavailable)
    assert tools.search("nowhere to be found", web="fallback", **common) == []
    with pytest.raises(online.OnlineUnavailable):
        tools.search("nowhere to be found", web="always", **common)


def test_sheet_falls_back_to_the_web_when_nothing_matches(
    monkeypatch, tmp_path, lrclib_fetch
):
    monkeypatch.setattr(online, "polite_fetch", lrclib_fetch)
    store = {}
    result = tools.sheet(
        "paper boats invented band",
        output=str(tmp_path / "sheet.pdf"),
        web="fallback",
        sources=[StoredWebSource(store)],
        store=store,
    )
    assert result["key"] == "web:lrclib:7" and result["title"] == "Paper Boats"
    with pytest.raises(LookupError):  # off: nothing here, so nothing
        tools.sheet("other song", web="off", sources=[], store={})


def test_the_cli_hides_the_fetch_seam():
    import songleaf.__main__ as cli

    assert "fetch" in cli._SEAMS


def test_candidate_keys_are_web_keys():
    assert Candidate("lrclib", "7", "T").key == "web:lrclib:7"


def test_a_kept_song_is_not_cut_by_the_corpus_near_misses(
    lrclib_fetch, memory_source, chart
):
    store = {}
    expand("paper boats invented band", fetch=lrclib_fetch, store=store)
    corpus = type(memory_source)(
        {str(i): (f"Paper Boats {i}", "The Invented Band", chart) for i in range(5)}
    )
    sources = [StoredWebSource(store), corpus]  # the order of default_sources
    rows = tools.search(
        "paper boats invented band", limit=2, sources=sources, store=store
    )
    assert rows[0]["key"] == "web:lrclib:7"


def test_default_sources_put_the_kept_web_songs_first(monkeypatch):
    from songleaf import sources as sources_module

    sources_module.default_sources.cache_clear()
    try:
        assert isinstance(sources_module.default_sources()[0], StoredWebSource)
    finally:
        sources_module.default_sources.cache_clear()
