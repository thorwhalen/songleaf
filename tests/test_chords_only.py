"""The chords-only layout (songleaf#68): chord symbols per section, never lyric text."""

import io

import pytest

pytest.importorskip("reportlab")
from pypdf import PdfReader

from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import (
    SheetLayout,
    _generic_label,
    chords_only,
    layout_named,
    make_renderer,
    render_sheet,
)
from songleaf.songbook import render_songbook

CHART = """[Intro]
C G

[Verse 1]
C        G
purple walrus kitchen
Am       F
velvet lantern drifting

[Whisper the secret words]
C   G
orange paper boats

[Chorus]
"""


@pytest.fixture
def song():
    return parse_chords_over_lyrics(
        CHART, meta={"title": "Invented Tune", "key": "C", "capo": 2}
    )


def test_the_text_is_the_chord_symbols_and_nothing_else(song):
    only = chords_only(song)
    assert only.text.split() == ["C", "G", "C", "G", "Am", "F", "C", "G"]
    assert not only.of_kind("chord")
    assert "walrus" not in only.text


def test_only_structure_words_survive_as_labels(song):
    labels = [a.body["label"] for a in chords_only(song).of_kind("section")]
    assert labels == ["Intro", "Verse 1", "Chorus"]
    assert _generic_label("Chorus x2", 2) == "Chorus x2"
    assert _generic_label("Whisper the secret words", 2) == "Part 2"


def test_a_song_without_markers_numbers_its_paragraphs():
    song = parse_chords_over_lyrics("C  G\nla la\n\nAm F\nna na")
    labels = [a.body["label"] for a in chords_only(song).of_kind("section")]
    assert labels == ["Part 1", "Part 2"]


def test_the_meta_is_kept(song):
    assert chords_only(song).meta == song.meta


def test_the_sheet_has_no_lyric_text(song):
    out = io.BytesIO()
    result = render_sheet(song, out, layout=SheetLayout(lyrics=False))
    text = PdfReader(io.BytesIO(out.getvalue())).pages[0].extract_text()
    assert result["pages"] == 1
    assert "Invented Tune" in text and "capo 2" in text and "key C" in text
    assert "walrus" not in text and "secret" not in text
    assert "Am" in text


def test_the_option_is_a_layout_spec(song):
    assert layout_named("chords-only+two-column").lyrics is False
    assert layout_named("dense").lyrics is True
    with pytest.raises(ValueError):
        SheetLayout(lyrics="no")


def test_a_songbook_takes_the_option(song):
    out = io.BytesIO()
    book = render_songbook(
        [("a", song), ("b", song)], out, renderer=make_renderer("chords-only")
    )
    text = PdfReader(io.BytesIO(out.getvalue())).pages[1].extract_text()
    assert book["pages"] == 3 and "walrus" not in text
