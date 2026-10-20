import json

import pandas as pd
import pytest

from songleaf.kaggle_index import KaggleChordsIndex, build_kaggle_index
from songleaf.sources import KaggleChordsSource, get_song, search


@pytest.fixture(params=["dataframe", "index"])
def kaggle(chart, request, tmp_path):
    """The same corpus as a DataFrame source and as an index: every test runs on both."""
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
    if request.param == "dataframe":
        return KaggleChordsSource(loader=lambda: corpus)
    path = str(tmp_path / "index.sqlite")
    build_kaggle_index(path=path, loader=lambda: corpus)
    return KaggleChordsIndex(path)


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


def test_a_local_folder_id_never_leaves_the_folder(tmp_path):
    from songleaf.sources import LocalFolderSource, SongNotFound

    folder = tmp_path / "imports"
    folder.mkdir()
    (tmp_path / "outside.txt").write_text("C\nnot yours")
    with pytest.raises(SongNotFound):
        LocalFolderSource(str(folder)).get("../outside.txt")


def test_the_index_is_used_by_default_once_built(monkeypatch, tmp_path):
    import songleaf.sources as sources_module
    from songleaf.kaggle_index import kaggle_index_path

    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    sources_module.default_sources.cache_clear()
    try:
        assert type(sources_module.default_sources()[0]) is KaggleChordsSource
        corpus = pd.DataFrame(
            {name: ["x"] for name in KaggleChordsSource.columns}
        ).assign(**{"Unnamed: 0": [5], "popularity": [1]})
        build_kaggle_index(loader=lambda: corpus)
        sources_module.default_sources.cache_clear()
        (source,) = sources_module.default_sources()
        assert type(source) is KaggleChordsIndex and source.path == kaggle_index_path()
    finally:
        sources_module.default_sources.cache_clear()


def test_a_rebuilt_index_is_picked_up_and_a_failed_build_leaves_nothing(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "index.sqlite")

    def corpus(title):
        return pd.DataFrame(
            {name: ["x"] for name in KaggleChordsSource.columns}
        ).assign(**{"Unnamed: 0": [1], "song_name": [title], "popularity": [1]})

    build_kaggle_index(path=path, loader=lambda: corpus("First Title"))
    source = KaggleChordsIndex(path)
    assert source.search(title="first title")[0].title == "First Title"
    build_kaggle_index(path=path, loader=lambda: corpus("Second Title"))
    assert source.search(title="second title")[0].title == "Second Title"

    def broken(conn, batch):  # fails mid-write, after the file exists
        raise OSError("disk gone")

    monkeypatch.setattr("sung.chords_index._insert", broken)  # the writer is sung's
    with pytest.raises(OSError):
        build_kaggle_index(path=path, loader=lambda: corpus("Third"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index.sqlite"]
    assert source.search(title="second title")[0].title == "Second Title"
