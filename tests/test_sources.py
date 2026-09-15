import json

import pandas as pd
import pytest

from songleaf.sources import KaggleChordsSource, get_song, search


@pytest.fixture
def kaggle(chart):
    corpus = pd.DataFrame(
        {
            "Unnamed: 0": [0, 1, 2],
            "artist_name": ["The Invented Band", "Nobody Real", "The Invented Band"],
            "song_name": ["Paper Boats", "Silver Stream", "Morning Dream"],
            "chords&lyrics": [
                chart,
                "C\nla la silver",
                "hide this tab\r\nG\r\nwake up dreamer",
            ],
            "lang": ["en", "en", "en"],
            "popularity": [10, 90, 50],
        }
    )
    return KaggleChordsSource(loader=lambda: corpus)


def test_a_fuzzy_query_forgives_typos_and_word_order(kaggle):
    (best, *_) = kaggle.search("invented band papr boats")
    assert best.key == "kaggle_chords:0"
    assert best.title == "Paper Boats"


def test_equal_matches_rank_by_popularity(kaggle):
    hits = kaggle.search(artist="the invented band")
    assert [hit.title for hit in hits] == ["Morning Dream", "Paper Boats"]


def test_lyrics_match_every_word_ignoring_case_and_punctuation(kaggle):
    assert [hit.id for hit in kaggle.search(lyrics="SLOW sing river")] == ["0"]


def test_constraints_combine(kaggle):
    assert kaggle.search("paper boats", lyrics="dreamer") == []
    assert kaggle.search() == []


def test_get_parses_the_chart_and_records_provenance(kaggle):
    song = kaggle.get("0")
    assert (song.title, song.artist) == ("Paper Boats", "The Invented Band")
    assert song.provenance["source"] == "kaggle_chords"
    assert song.provenance["license"] == "gray"
    assert song.of_kind("chord")
    with pytest.raises(KeyError):
        kaggle.get("999")


def test_the_chords_site_page_text_is_dropped(kaggle):
    assert kaggle.get("2").text == "wake up dreamer"


def test_hits_are_json_ready(kaggle):
    json.dumps([hit.to_dict() for hit in kaggle.search("paper boats")])


def test_search_merges_sources_best_first(kaggle, memory_source):
    hits = search("paper boats", sources=[kaggle, memory_source])
    assert {hit.source for hit in hits} == {"kaggle_chords", "memory"}
    assert [hit.score for hit in hits] == sorted(
        (hit.score for hit in hits), reverse=True
    )


def test_get_song_routes_by_source_name(kaggle, memory_source):
    assert (
        get_song("memory:1", sources=[kaggle, memory_source]).provenance["source"]
        == "memory"
    )
    with pytest.raises(KeyError):
        get_song("nowhere:1", sources=[kaggle])
    with pytest.raises(KeyError):
        get_song("no-colon", sources=[kaggle])
