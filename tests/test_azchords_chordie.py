"""Finding chart pages without a search box: AZChords by artist, Chordie by its result page.

Every page here is synthesized (invented artist, songs and slugs); no test reaches the network.
"""

import pytest

from songleaf import online

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.azchords.com/a.html</loc></url>
<url><loc>https://www.azchords.com/i/inventedband-tabs-11.html</loc></url>
<url><loc>https://www.azchords.com/s/sedakaneil-chords-22.html</loc></url>
<url><loc>https://www.azchords.com/d/dadimarcel-guitarpro-33.html</loc></url>
</urlset>"""

ARTIST_PAGE = """<html><head><title>Invented Band (Chords)  - AZ Chords</title></head><body>
<table>
<tr class="rowlink"><td><a href="/i/inventedband-tabs-11/paperboats-tabs-101.html">Paper Boats Chords</a></td></tr>
<tr class="rowlink"><td><a href="/i/inventedband-tabs-11/silverstream-tabs-102.html">Silver Stream Tab</a></td></tr>
<tr class="rowlink" data-type="go_dpd"><td class="dropdown">
<a class="dropdown-toggle link" href="#">Lantern Light Chords</a><ul>
<li><a href="/i/inventedband-tabs-11/lanternlight-tabs-103.html" style="x">Version 1<div>&#9733;4</div></a></li>
<li><a href="/i/inventedband-tabs-11/lanternlight-tabs-104.html">Version 2</a></li>
</ul></td></tr>
</table></body></html>"""

PAGES = {
    online.AZCHORDS.sitemap_url: SITEMAP,
    "https://www.azchords.com/i/inventedband-chords-11.html": ARTIST_PAGE,
}


class Spy:
    def __init__(self, pages=PAGES):
        self.pages, self.urls = pages, []

    def __call__(self, url):
        self.urls.append(url)
        return self.pages[url]


def titles(candidates):
    return [(c.title, c.artist) for c in candidates]


def test_azchords_lists_an_artists_songs_from_its_name():
    spy = Spy()
    found = online.AZCHORDS.find("invented band", limit=10, fetch=spy)
    assert titles(found) == [
        ("Paper Boats", "Invented Band"),
        ("Lantern Light", "Invented Band"),  # the tab row has no chords
        ("Lantern Light", "Invented Band"),
    ]
    assert found[1].url.endswith("/lanternlight-tabs-103.html")


def test_the_other_words_pick_the_title():
    found = online.AZCHORDS.find("lantern light by invented band", limit=10, fetch=Spy())
    assert [c.title for c in found] == ["Lantern Light"] * 2
    assert online.AZCHORDS.find("paper boats invented band", limit=10, fetch=Spy())[0].title == "Paper Boats"


def test_azchords_files_people_by_surname():
    assert online._artist_in(["neil", "sedaka", "oh"], {"sedakaneil": ("s", "sedakaneil", "22")}) == (
        ("s", "sedakaneil", "22"),
        ["oh"],
    )


def test_a_query_with_no_artist_finds_nothing_and_asks_for_nothing_more():
    spy = Spy()
    assert online.AZCHORDS.find("paper boats", limit=5, fetch=spy) == []
    assert spy.urls == [online.AZCHORDS.sitemap_url]


def test_the_artist_list_is_fetched_once_a_month():
    spy = Spy()
    online.AZCHORDS.find("invented band", limit=5, fetch=spy)
    online.AZCHORDS.find("invented band", limit=5, fetch=spy)
    assert spy.urls.count(online.AZCHORDS.sitemap_url) == 1


def test_a_candidate_reads_as_the_same_page_as_its_url_import():
    found = online.AZCHORDS.find("paper boats invented band", limit=1, fetch=Spy())[0]
    assert online.AZCHORDS.candidate_for(found.url).id == found.id


CHORDIE_PAGE = """<div class="songListContent"><a href="/chord.pere/www.example.test/a/b.html">
<span style="font-size: 18px; color: black;" >Paper Boats (live - 2019)</span>
&nbsp;&nbsp;<span style="color: grey;">Invented Band</span></a>
<a style="x" href="/chord.pere/www.example.test/a/b.html">snippet of the chart text</a></div>"""


def test_chordies_label_splits_at_the_artist_span_not_at_a_dash_in_the_title():
    found = online.CHORDIE.find("paper boats", limit=5, fetch=lambda url: CHORDIE_PAGE)
    assert titles(found) == [("Paper Boats (live - 2019)", "Invented Band")]


# --- charts re-hosted from sites that forbid kept copies ----------------------------------

CHORDIE_RESULTS = """
<a href="/chord.pere/www.copies.example/a/one.html"><span>Paper Boats</span>&nbsp;&nbsp;<span>Invented Band</span></a>
<a href="/chord.pere/chordiearchive.chordie.com/chord.pere/www.copies.example/a/two.html"><span>Paper Boats</span>&nbsp;&nbsp;<span>Invented Band</span></a>
<a href="/chord.pere/www.fine.example/a/three.html"><span>Paper Boats</span>&nbsp;&nbsp;<span>Invented Band</span></a>
"""
_CHART = "\n".join(
    f"C        G\npaper boat number {n} drifts\nAm       F\nalong the silver stream" for n in range(4)
)
CHART_PAGE = f"<html><body><pre>[Verse]\n{_CHART}</pre></body></html>"


@pytest.fixture
def rehosting_chordie(monkeypatch):
    from dataclasses import replace

    site = replace(online.CHORDIE, link_only_hosts=("copies.example",))
    monkeypatch.setitem(online.WEB_SITES, "chordie", site)
    return site


def test_a_result_from_a_forbidden_host_is_marked_link_only(rehosting_chordie):
    found = rehosting_chordie.find("paper boats", limit=9, fetch=lambda url: CHORDIE_RESULTS)
    assert [c.license for c in found] == [online.LINK_ONLY, online.LINK_ONLY, ""]


def test_such_a_page_is_never_extracted_and_its_url_import_says_why(rehosting_chordie):
    found = rehosting_chordie.find("paper boats", limit=9, fetch=lambda url: CHORDIE_RESULTS)
    with pytest.raises(online.LinkOnly, match="copies.example"):
        rehosting_chordie.extract(found[0], fetch=lambda url: pytest.fail("fetched"))
    store = {}
    with pytest.raises(online.LinkOnly):
        online.import_url(found[1].url, fetch=lambda url: pytest.fail("fetched"), store=store)
    assert store == {}


def test_a_search_keeps_the_allowed_page_and_skips_the_link_only_ones(rehosting_chordie):
    asked = []

    def fetch(url):
        asked.append(url)
        return CHORDIE_RESULTS if "result.php" in url else CHART_PAGE

    store = {}
    kept = online.expand("paper boats invented band", sites=["chordie"], fetch=fetch, store=store)
    assert kept.key in store and "fine.example" in store[kept.key].provenance["url"]
    assert not any("copies.example" in url for url in asked)
