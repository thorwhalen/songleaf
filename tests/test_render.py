import io

import pytest

from songleaf.model import Song, chord
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import (
    DFLT_MARGIN,
    DenseStyle,
    _heading,
    _height,
    _layout,
    _page_dimensions,
    _pieces,
    _width,
    fit_font_size,
    render_dense_a4,
)

STYLE = DenseStyle()
PAGE_WIDTH, PAGE_HEIGHT = _page_dimensions("A4")
WIDTH, HEIGHT = PAGE_WIDTH - 2 * DFLT_MARGIN, PAGE_HEIGHT - 2 * DFLT_MARGIN


def rows_at(song, size):
    return _layout(_pieces(song), size, WIDTH, STYLE, _heading(song))


def items_of(row, color):
    return [item for item in row.items if item.color == color]


def test_a_song_renders_on_one_page(chart, page_count):
    buffer = io.BytesIO()
    info = render_dense_a4(parse_chords_over_lyrics(chart), buffer)
    assert info["pages"] == 1 and info["path"] is None
    assert page_count(buffer.getvalue()) == 1


def test_the_font_is_as_large_as_fits(long_chart):
    song = parse_chords_over_lyrics(long_chart(60))
    size = fit_font_size(song)
    assert _height(rows_at(song, size), size, STYLE) <= HEIGHT
    bigger = size * 1.03
    assert _height(rows_at(song, bigger), bigger, STYLE) > HEIGHT


def test_shorter_songs_get_larger_lyrics(long_chart):
    short = fit_font_size(parse_chords_over_lyrics(long_chart(20)))
    assert short > fit_font_size(parse_chords_over_lyrics(long_chart(80)))


def test_a_song_too_long_for_a_page_spills_over_at_the_smallest_size(
    long_chart, page_count
):
    buffer = io.BytesIO()
    info = render_dense_a4(
        parse_chords_over_lyrics(long_chart(600)), buffer, min_font_size=6
    )
    assert info["font_size"] == 6 and info["pages"] > 1
    assert page_count(buffer.getvalue()) == info["pages"]


def test_chords_overlap_their_lyric_line_instead_of_taking_one():
    size = 20
    (row,) = rows_at(Song("Paper boats drift", [chord(0, "G"), chord(6, "D")]), size)
    chords = items_of(row, STYLE.chord_color)
    assert len(chords) == 2
    assert all(0 < c.rise < STYLE.ascent * size for c in chords)
    chord_line_above_lyrics = (
        (STYLE.ascent + STYLE.descent) * size * (1 + STYLE.chord_scale)
    )
    assert row.top + row.bottom < chord_line_above_lyrics


def test_a_chord_starts_over_its_syllable_and_a_before_chord_ends_there():
    size = 20
    syllable_x = _width("Paper ", STYLE.lyric_font) * size
    (row,) = rows_at(Song("Paper boats", [chord(6, "D")]), size)
    (at,) = items_of(row, STYLE.chord_color)
    assert at.x == pytest.approx(syllable_x)
    (row,) = rows_at(Song("Paper boats", [chord(6, "D", timing="before")]), size)
    (before,) = items_of(row, STYLE.chord_color)
    assert (
        before.x + _width("D", STYLE.chord_font) * size * STYLE.chord_scale
        <= syllable_x
    )


def test_lines_of_a_paragraph_share_a_row_but_sections_do_not():
    song = parse_chords_over_lyrics(
        "Verse:\nshort one\nshort two\nChorus:\nshort three"
    )
    rows = rows_at(song, 14)
    texts = [[item.text for item in items_of(row, STYLE.lyric_color)] for row in rows]
    assert texts == [["short one", "short two"], ["short three"]]


def test_a_long_line_wraps_and_keeps_its_chords():
    words = " ".join(["drift"] * 40)
    rows = rows_at(Song(words, [chord(len(words) - 5, "G")]), 30)
    assert len(rows) > 1
    assert [item.text for item in items_of(rows[-1], STYLE.chord_color)] == ["G"]
    for row in rows:
        (lyric,) = items_of(row, STYLE.lyric_color)
        assert _width(lyric.text, STYLE.lyric_font) * 30 <= WIDTH


def test_the_heading_and_section_labels_are_drawn(chart):
    meta = {"title": "Paper Boats", "artist": "The Invented Band"}
    rows = rows_at(parse_chords_over_lyrics(chart, meta=meta), 14)
    assert rows[0].items[0].text == "Paper Boats — The Invented Band · capo 2"
    labels = {item.text for row in rows for item in items_of(row, STYLE.label_color)}
    assert labels == {"Intro", "V1", "Ch"}


def test_page_sizes(chart, tmp_path):
    song = parse_chords_over_lyrics(chart)
    info = render_dense_a4(song, tmp_path / "letter.pdf", page_size="letter")
    assert info["path"] == str(tmp_path / "letter.pdf")
    assert (tmp_path / "letter.pdf").stat().st_size > 0
    assert render_dense_a4(song, io.BytesIO(), page_size=(300, 400))["pages"] == 1
    with pytest.raises(ValueError):
        render_dense_a4(song, io.BytesIO(), page_size="papyrus")


def test_an_empty_song_is_a_blank_page(page_count):
    buffer = io.BytesIO()
    assert render_dense_a4(Song(""), buffer)["pages"] == 1
    assert page_count(buffer.getvalue()) == 1
