"""Transposition: chords move, words and the stored song do not."""

from songleaf import tools
from songleaf.harmony import transpose, transposition_table
from songleaf.model import Song, chord
from songleaf.store import song_store


def test_transposing_moves_chords_and_nothing_else():
    song = Song("la la", [chord(0, "G"), chord(3, "D/F#")], meta={"title": "T"})
    moved = transpose(song, 2)
    assert [a.body["symbol"] for a in moved.of_kind("chord")] == ["A", "E/G#"]
    assert moved.text == song.text and moved.meta["transposed"] == 2
    assert [a.body["symbol"] for a in song.of_kind("chord")] == ["G", "D/F#"]
    assert transpose(song, 12) is song


def test_a_full_turn_comes_back_and_flat_keys_spell_flats():
    symbols = ["F", "C", "Dm", "Bb"]
    there = transposition_table(symbols, 5)["chords"]
    back = transposition_table(list(there.values()), -5)["chords"]
    assert list(back.values()) == symbols
    assert transposition_table(symbols, 5)["key"] == "Bb" and there["F"] == "Bb"


def test_sheet_transposes_without_touching_the_store(memory_source, tmp_path):
    store = song_store(str(tmp_path / "songs"))
    result = tools.sheet(
        "memory:1",
        output=str(tmp_path / "s.pdf"),
        transpose=-2,
        sources=[memory_source],
        store=store,
    )
    assert result["pages"] == 1
    assert store["memory:1"].of_kind("chord")[0].body["symbol"] == "G"
