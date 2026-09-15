import pytest

from songleaf.sources import LocalFolderSource


@pytest.fixture
def folder(tmp_path, chart):
    (tmp_path / "The Invented Band - Paper Boats.txt").write_text(chart)
    (tmp_path / "Nobody Real - Silver Stream.gpx").write_bytes(b"not-real-guitar-pro")
    (tmp_path / "ignored.jpg").write_bytes(b"not a chart or score")
    return LocalFolderSource(str(tmp_path))


def test_search_matches_title_and_artist(folder):
    hits = folder.search("paper boats")
    assert [hit.title for hit in hits] == ["Paper Boats"]
    assert hits[0].artist == "The Invented Band"
    assert hits[0].source == "local_folder"


def test_non_chart_non_score_files_are_ignored(folder):
    assert "ignored" not in " ".join(hit.id for hit in folder.search("ignored"))


def test_lyrics_constraint_only_matches_text_files(folder):
    # The .gpx file's name mentions rivers, but it's binary: no lyrics to search.
    assert [h.id for h in folder.search(title="silver", lyrics="silver")] == []
    assert len(folder.search(lyrics="sing it slow")) == 1


def test_get_parses_a_text_chart(folder):
    (hit,) = folder.search("paper boats")
    song = folder.get(hit.id)
    assert (song.title, song.artist) == ("Paper Boats", "The Invented Band")
    assert song.of_kind("chord")
    assert song.provenance["source"] == "local_folder"


def test_get_score_links_a_binary_file(folder):
    (hit,) = folder.search("silver stream")
    song = folder.get(hit.id)
    assert song.text == ""
    (link,) = song.of_kind("score")
    assert link.body["format"] == "guitarpro"
    assert link.body["url"].endswith("Silver Stream.gpx")


def test_get_raises_for_a_missing_file(folder):
    with pytest.raises(KeyError):
        folder.get("nope.txt")


def test_default_root_is_the_imports_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path / "data"))
    local = LocalFolderSource()
    assert local.root == str(tmp_path / "data" / "imports")
