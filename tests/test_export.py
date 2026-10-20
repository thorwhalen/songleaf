"""Export as ChordPro and plain text (#29): round trip through the ChordPro import."""

import pytest

from songleaf.chordpro import parse_chordpro
from songleaf.export import FORMATS, to_chordpro, to_text
from songleaf.harmony import transpose
from songleaf.model import Annotation, Song, chord, section

SYNTH = """{title: Paper Boats}
{artist: The Invented}
{key: G}
{capo: 2}
{tempo: 96}
{start_of_verse: Verse 1}
Paper [G]boats [D]drift
Down the [Em]quiet [C]stream

{start_of_chorus: Chorus}
[G]Sail, sail a[D/F#]way
[Am] [C] [D]
{end_of_chorus}
{start_of_chorus: Chorus}
{end_of_chorus}
{start_of_bridge: Bridge}
Under a [Bm]paper [E]moon
{end_of_bridge}
"""


def _same(a: Song, b: Song) -> None:
    assert b.text == a.text
    assert b.annotations == a.annotations
    assert b.meta == a.meta


def test_round_trip_on_a_synthesized_song() -> None:
    song = parse_chordpro(SYNTH)
    assert any(a.body.get("marker") for a in song.of_kind("section"))
    _same(song, parse_chordpro(to_chordpro(song)))


def test_round_trip_keeps_chords_that_sound_before_their_syllable() -> None:
    song = Song(
        "Paper boats drift",
        [chord(0, "C", timing="before"), chord(6, "G"), chord(12, "D", timing="before"),
         section(0, 17, "Verse")],
        meta={"title": "T"},
    )
    out = to_chordpro(song)
    assert "{x_songleaf_before: 0, 2}" in out
    _same(song, parse_chordpro(out))


def test_unaware_importers_see_plain_chordpro() -> None:
    song = Song("Hi there", [chord(3, "G", timing="before")])
    out = to_chordpro(song)
    assert "Hi [G]there" in out and "x_songleaf_before" in out


def test_transposition_is_applied_to_both_formats() -> None:
    song = parse_chordpro("{title: T}\nPaper [G]boats [D]drift")
    assert "[A]boats [E]drift" in to_chordpro(song, transpose=2)
    assert "A" in to_text(song, transpose=2).splitlines()[2]
    assert to_chordpro(song, transpose=12) == to_chordpro(song)


def test_to_text_puts_chords_over_their_syllables() -> None:
    song = parse_chordpro("{title: T}\n{artist: A}\n{start_of_chorus: Chorus}\nPaper [G]boats [D]drift\n{end_of_chorus}")
    assert to_text(song).splitlines() == [
        "T - A", "", "[Chorus]", "      G     D", "Paper boats drift",
    ]


def test_to_text_keeps_adjacent_chords_apart() -> None:
    song = Song("ab", [chord(0, "Gmaj7"), chord(1, "D")])
    chord_line = to_text(song).splitlines()[0]
    assert chord_line == "Gmaj7 D"


def test_to_text_chord_only_lines_and_markers() -> None:
    song = parse_chordpro(SYNTH)
    lines = to_text(song).splitlines()
    assert "Am  C  D" in lines
    assert lines.count("[Chorus]") == 2 and lines.index("[Bridge]") > 0


def test_formats_table_names_extension_and_media_type() -> None:
    assert FORMATS["chordpro"][1] == "cho" and FORMATS["text"][1] == "txt"


@pytest.mark.parametrize("semitones", [-3, 5])
def test_transposed_round_trip(semitones) -> None:
    song = parse_chordpro(SYNTH)
    moved = transpose(song, semitones)
    back = parse_chordpro(to_chordpro(song, transpose=semitones))
    assert [a.body["symbol"] for a in back.of_kind("chord")] == [
        a.body["symbol"] for a in moved.of_kind("chord")
    ]


def test_the_export_tool_and_cli(memory_source, tmp_path, capsys) -> None:
    from songleaf import tools
    from songleaf.__main__ import main
    from songleaf.store import song_store

    store = song_store(str(tmp_path / "songs"))
    out = tmp_path / "x.cho"
    result = tools.export("paper boats", transpose=2, output=str(out), sources=[memory_source], store=store)
    assert result["path"] == str(out) and out.read_text() == result["text"]
    assert result["text"].startswith("{title: Paper Boats}")
    with pytest.raises(ValueError, match="format is one of"):
        tools.export("memory:1", format="pdf", store=store)
    commands = [t.__name__ for t in tools.TOOLS]
    assert "export" in commands
