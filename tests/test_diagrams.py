"""Chord diagrams: tones, generated guitar shapes, the strip on the sheet (songleaf#13)."""

import io

import pytest

from songleaf.diagrams import chord_tones, guitar_shape, song_chords, strip_height
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import SheetLayout, fit_font_size, render_sheet


@pytest.mark.parametrize(
    "symbol, tones",
    [
        ("C", (0, 4, 7)),
        ("Am", (9, 0, 4)),
        ("Bdim", (11, 2, 5)),
        ("Caug", (0, 4, 8)),
        ("Dsus2", (2, 4, 9)),
        ("Dsus4", (2, 7, 9)),
        ("E5", (4, 11)),
        ("G7", (7, 11, 2, 5)),
        ("Fmaj7", (5, 9, 0, 4)),
        ("Cdim7", (0, 3, 6, 9)),
        ("Bm7b5", (11, 2, 5, 9)),
        ("A6", (9, 1, 4, 6)),
        ("Cadd9", (0, 4, 7, 2)),
        ("D/F#", (6, 2, 9)),
        ("Chorus", None),
    ],
)
def test_chord_tones(symbol, tones):
    assert chord_tones(symbol) == tones


@pytest.mark.parametrize(
    "symbol, shape",
    [
        ("C", (None, 3, 2, 0, 1, 0)),
        ("G", (3, 2, 0, 0, 0, 3)),
        ("D", (None, None, 0, 2, 3, 2)),
        ("Am", (None, 0, 2, 2, 1, 0)),
        ("Em", (0, 2, 2, 0, 0, 0)),
        ("F", (1, 3, 3, 2, 1, 1)),
        ("Bm", (None, 2, 4, 4, 3, 2)),
        ("A7", (None, 0, 2, 0, 2, 0)),
    ],
)
def test_guitar_shapes_are_the_familiar_ones(symbol, shape):
    assert guitar_shape(symbol) == shape


def test_every_generated_shape_sounds_the_chord_with_the_bass_lowest():
    tuning = (4, 9, 2, 7, 11, 4)
    for symbol in ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B",
                   "Cm7", "F#m", "Bbmaj7", "E7", "G/B", "Asus4"]:
        frets, tones = guitar_shape(symbol), chord_tones(symbol)
        sounding = [(s, f) for s, f in enumerate(frets) if f is not None]
        assert {(tuning[s] + f) % 12 for s, f in sounding} == set(tones), symbol
        assert (tuning[sounding[0][0]] + sounding[0][1]) % 12 == tones[0], symbol
        fretted = [f for _, f in sounding if f]
        assert not fretted or max(fretted) - min(fretted) <= 3, symbol


def test_song_chords_are_distinct_in_order(chart):
    song = parse_chords_over_lyrics(chart)
    chords = song_chords(song)
    assert len(chords) == len(set(chords)) and chords
    symbols = [a.body["symbol"] for a in song.of_kind("chord")]
    assert chords == list(dict.fromkeys(s for s in symbols if chord_tones(s)))


def test_the_strip_costs_font_size_and_fits_one_page(chart, page_count):
    song = parse_chords_over_lyrics(chart)
    plain = fit_font_size(song, layout=SheetLayout())
    for kind in ("piano", "guitar"):
        with_strip = fit_font_size(song, layout=SheetLayout(diagrams=kind))
        assert with_strip < plain
        buffer = io.BytesIO()
        info = render_sheet(song, buffer, layout=kind)
        assert info["pages"] == 1 == page_count(buffer.getvalue())


def test_strip_height_grows_with_rows_and_bad_kinds_fail_early():
    one_row = strip_height(3, "piano", 10, 500)
    assert 0 == strip_height(0, "piano", 10, 500) < one_row < strip_height(30, "piano", 10, 500)
    with pytest.raises(ValueError, match="diagrams"):
        SheetLayout(diagrams="ukulele")
