"""ChordPro parsing, and the local folder source routing ChordPro files to it."""

import pytest

from songleaf.chordpro import parse_chordpro
from songleaf.sources import LocalFolderSource

CHART = """\
# a synthesized song
{title: Paper Boats}
{artist: The Invented Band}
{key: G}
{capo: 2}
{tempo: 96}
{c: Intro}
[G] [D] [Em]

{sov: Verse 1}
Paper [G]boats [D]drift
on the [Em]stream[C]
{eov}
{soc}
[G]Sing it [D]slow
{eoc}
{c: Outro}
"""


def chords_of(song):
    return [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]


def test_directives_become_metadata():
    meta = parse_chordpro(CHART).meta
    assert meta == {
        "title": "Paper Boats",
        "artist": "The Invented Band",
        "key": "G",
        "capo": 2,
        "tempo": 96,
    }


def test_inline_chords_anchor_on_the_bracket_free_text():
    song = parse_chordpro(CHART)
    assert "[" not in song.text and "{" not in song.text
    assert song.text.startswith("\n\nPaper boats drift\non the stream\n")
    assert chords_of(song)[:5] == [
        (0, "G"), (0, "D"), (0, "Em"), (8, "G"), (14, "D"),
    ]


def test_chord_only_line_is_an_empty_line_with_its_chords_in_order():
    song = parse_chordpro("[G] [D] [Em]\nla")
    assert song.text == "\nla"
    assert chords_of(song) == [(0, "G"), (0, "D"), (0, "Em")]


def test_sections_span_their_lines_and_trailing_comment_is_a_marker():
    song = parse_chordpro(CHART)
    sections = song.of_kind("section")
    assert [a.body["label"] for a in sections] == ["Intro", "Verse 1", "Chorus", "Outro"]
    verse = sections[1]
    assert song.text[verse.start : verse.end] == "Paper boats drift\non the stream"
    assert sections[-1].body.get("marker") is True
    assert "marker" not in verse.body


def test_comments_unknown_directives_and_blank_runs_are_dropped():
    song = parse_chordpro("# note\n{define: G base-fret 1}\n\n\nla\n\n\n\nli\n")
    assert song.text == "la\n\nli"


def test_empty_input():
    song = parse_chordpro("")
    assert song.text == "" and not song.annotations


@pytest.mark.parametrize("ext", [".cho", ".chopro", ".crd", ".pro"])
def test_local_folder_routes_chordpro_extensions(tmp_path, ext):
    (tmp_path / f"Nobody Real - Paper Boats{ext}").write_text(CHART)
    source = LocalFolderSource(str(tmp_path))
    (hit,) = source.search("paper boats")
    song = source.get(hit.id)
    assert "[" not in song.text and "{" not in song.text
    assert song.of_kind("chord")
    assert song.meta["capo"] == 2 and song.meta["artist"] == "The Invented Band"


def test_txt_files_still_use_chords_over_lyrics(tmp_path, chart):
    (tmp_path / "Nobody Real - Paper Boats.txt").write_text(chart)
    source = LocalFolderSource(str(tmp_path))
    (hit,) = source.search("paper boats")
    assert source.get(hit.id).of_kind("chord")
