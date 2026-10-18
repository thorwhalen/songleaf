"""One query, sectioned results: lists, then titles, artists and lyrics, each song once.

Every title, artist and lyric here is invented for the tests.
"""

import pandas as pd
import pytest

from songleaf import tools
from songleaf.kaggle_index import KaggleChordsIndex, build_kaggle_index
from songleaf.library import save_groups
from songleaf.parse import parse_chords_over_lyrics
from songleaf.sources import KaggleChordsSource, search_tiers

ROWS = [
    # id, artist, title, chart, popularity
    (0, "The Invented Band", "Paper Boats", "G\nPaper boats drift down the lane", 10),
    (1, "Nobody Real", "Paper Boats", "C\nfolded paper on the water", 80),
    (2, "Silver Lining Band", "Quiet Road", "D\nwalking home alone", 50),
    (3, "Tin Kettle", "Morning Song", "G\nthe silver light of morning\nla la", 40),
    (4, "Tin Kettle", "Silver Stream", "C\nthe silver stream runs cold", 30),
    (5, "Wombat Choir", "As", "G\nan oasis of calm", 99),
    (6, "The Invented Band", "Paper Boats (ver. 2)", "G\nPaper boats again", 5),
    (7, "Tin Kettle", "10,000 Lanterns", "Am\nso many lanterns", 20),
]


@pytest.fixture(params=["dataframe", "index"])
def corpus(request, tmp_path):
    """The same synthetic corpus as a DataFrame source and as an index: each test runs on both."""
    df = pd.DataFrame(
        {
            "Unnamed: 0": [r[0] for r in ROWS],
            "artist_name": [r[1] for r in ROWS],
            "song_name": [r[2] for r in ROWS],
            "chords&lyrics": [r[3] for r in ROWS],
            "lang": ["en"] * len(ROWS),
            "popularity": [r[4] for r in ROWS],
        }
    )
    if request.param == "dataframe":
        return KaggleChordsSource(loader=lambda: df)
    path = str(tmp_path / "index.sqlite")
    build_kaggle_index(path=path, loader=lambda: df)
    return KaggleChordsIndex(path)


def _keys(hits):
    return [hit.id for hit in hits]


def test_each_song_lands_in_the_first_kind_it_matches(corpus):
    tiers = corpus.search_tiers("silver")
    assert _keys(tiers["title"]) == [
        "4"
    ]  # in its title and its lyrics: a title match only
    assert _keys(tiers["artist"]) == ["2"]
    assert _keys(tiers["lyrics"]) == ["3"]


def test_a_lyrics_match_carries_the_line_that_matched(corpus):
    (hit,) = corpus.search_tiers("silver light")["lyrics"]
    snippet = hit.meta["snippet"]
    assert snippet["text"] == "the silver light of morning"
    assert [snippet["text"][a:b] for a, b in snippet["spans"]] == ["silver", "light"]


def test_a_word_is_never_matched_by_a_piece_of_another(corpus):
    # "As" is inside "oasis" as letters, not as a word: no title match (a fuzzy score would say 90)
    tiers = corpus.search_tiers("oasis")
    assert tiers["title"] == [] and tiers["artist"] == []
    assert _keys(tiers["lyrics"]) == ["5"]


def test_title_and_artist_in_one_query_put_that_artist_first(corpus):
    titles = corpus.search_tiers("paper boats invented band")["title"]
    assert _keys(titles)[0] == "0"  # the less popular one, but the artist named
    assert "1" in _keys(titles)


def test_an_artist_match_whose_title_holds_the_rest_is_a_title_match(corpus):
    tiers = corpus.search_tiers("paper boats invented band")
    assert "6" in _keys(tiers["title"]) and "6" not in _keys(tiers["artist"])


def test_a_partly_typed_word_and_a_typo_both_find_the_title(corpus):
    assert _keys(corpus.search_tiers("silver str")["title"]) == ["4"]
    assert _keys(corpus.search_tiers("sliver stream")["title"]) == ["4"]


def test_numbers_with_separators_are_one_word(corpus):
    assert _keys(corpus.search_tiers("10000 lanterns")["title"]) == ["7"]


def test_limit_is_per_kind_and_an_empty_query_finds_nothing(corpus):
    tiers = corpus.search_tiers("paper", limit=1)
    assert len(tiers["title"]) == 1
    assert corpus.search_tiers("  ") == {"title": [], "artist": [], "lyrics": []}


def test_sources_with_only_search_are_tiered_too(memory_source):
    tiers = search_tiers("invented band", sources=[memory_source])
    assert _keys(tiers["artist"]) == ["1", "2"] and tiers["title"] == []
    assert _keys(search_tiers("paper boats", sources=[memory_source])["title"]) == ["1"]


@pytest.fixture
def library(tmp_path, corpus):
    """A store holding songs 0 and 4, and the lists Campfire (song 0) and Silver Nights (song 4)."""
    store = {
        "kaggle_chords:0": parse_chords_over_lyrics(
            "G\nla", meta={"title": "Paper Boats", "artist": "The Invented Band"}
        ),
        "kaggle_chords:4": parse_chords_over_lyrics(
            "C\nla", meta={"title": "Silver Stream", "artist": "Tin Kettle"}
        ),
    }
    root = str(tmp_path / "root")
    edges = [
        {
            "id": "1",
            "parent": "Campfire",
            "child": "kaggle_chords:0",
            "kind": "contains",
        },
        {
            "id": "2",
            "parent": "Silver Nights",
            "child": "kaggle_chords:4",
            "kind": "contains",
        },
        {
            "id": "3",
            "parent": "Silver Nights",
            "child": "kaggle_chords:99",
            "kind": "contains",
        },
    ]
    save_groups({"nodes": [], "edges": edges}, revision=0, root=root)
    return {"sources": [corpus], "store": store, "library_root": root}


def test_lists_come_first_and_their_songs_are_not_repeated(library):
    rows = tools.search("silver", **library)
    kinds = [(row["match"], row["key"]) for row in rows]
    assert kinds[0] == (
        "list",
        "kaggle_chords:4",
    )  # Silver Nights; its unstored song is left out
    assert (
        "title",
        "kaggle_chords:4",
    ) not in kinds  # each song once, in its first kind
    assert [k for k, _ in kinds] == ["list", "artist", "lyrics"]
    first = rows[0]
    assert (first["list"], first["list_name"]) == ("Silver Nights", "Silver Nights")
    assert first["highlight"]["list_name"] == [[0, 6]]


def test_a_list_is_found_by_the_start_of_its_words(library):
    rows = tools.search("camp", **library)
    assert [(r["match"], r["list"]) for r in rows if r["match"] == "list"] == [
        ("list", "Campfire")
    ]


def test_hits_mark_the_words_that_matched(library):
    (row, *_) = [
        r for r in tools.search("paper boats", **library) if r["match"] == "title"
    ]
    assert row["highlight"]["title"] == [[0, 5], [6, 11]]


def test_the_narrower_field_search_still_works(library):
    rows = tools.search(lyrics="silver light", **library)
    assert [(r["key"], r["match"]) for r in rows] == [("kaggle_chords:3", "")]
