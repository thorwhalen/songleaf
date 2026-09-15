import json
import os

import pytest

from songleaf.model import Annotation, Song, chord, score_link, section
from songleaf.store import DATA_DIR_ENVVAR, data_dir, song_store


def a_song():
    text = "Paper boats drift\nlanterns hum"
    return Song(
        text,
        [
            section(0, len(text), "Verse 1"),
            chord(0, "G"),
            chord(6, "D", timing="before"),
            score_link(0, 17, source="thesession", id="42", format="abc"),
        ],
        meta={"title": "Paper Boats", "artist": "The Invented Band", "capo": 2},
        provenance={"source": "memory", "id": "1"},
    )


def test_a_song_round_trips_through_json():
    song = a_song()
    assert Song.from_dict(json.loads(json.dumps(song.to_dict()))) == song


def test_annotations_are_kept_in_text_order():
    song = Song("abc def", [chord(4, "D"), chord(0, "C")])
    assert [a.start for a in song.annotations] == [0, 4]


def test_invalid_annotations_are_refused():
    with pytest.raises(ValueError):
        Annotation("chord", 3, 2)
    with pytest.raises(ValueError):
        Song("ab", [chord(5, "C")])
    with pytest.raises(ValueError):
        chord(0, "C", timing="after")


def test_lines_carry_their_offsets():
    lines = [(line.start, line.end, line.text) for line in Song("ab\n\ncd").lines()]
    assert lines == [(0, 2, "ab"), (3, 3, ""), (4, 6, "cd")]


def test_the_store_is_a_mutable_mapping_of_songs(tmp_path):
    store = song_store(str(tmp_path))
    song = a_song()
    store["memory:1"] = song
    assert "memory:1" in store
    assert list(store) == ["memory:1"] and len(store) == 1
    assert store["memory:1"] == song
    del store["memory:1"]
    assert list(store) == []


def test_any_key_is_a_safe_file_name(tmp_path):
    key = "scoreseek:https://example.org/a b?c"
    store = song_store(str(tmp_path))
    store[key] = Song("la", meta={"title": "Café ñ"})
    (name,) = os.listdir(tmp_path)
    assert "/" not in name and ":" not in name
    assert list(store) == [key]
    assert store[key].title == "Café ñ"


def test_the_default_store_lives_under_the_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv(DATA_DIR_ENVVAR, str(tmp_path))
    song_store()["memory:1"] = a_song()
    assert os.listdir(tmp_path / "songs") == ["memory%3A1.json"]
    assert data_dir("sheets") == str(tmp_path / "sheets")
