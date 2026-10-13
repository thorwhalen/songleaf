"""The bundled TrueType font (songleaf#9): wide coverage, embedded, with a fallback.

All text here is invented.
"""

import io
import warnings

import pytest

from songleaf import render
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import BUNDLED_FONTS, FONTS_DIR, DenseStyle, render_dense_a4, usable_font

#: Characters reportlab's standard fonts (cp1252) cannot draw.
BEYOND_LATIN_1 = "şğı ŞĞİ Москва Αθήνα"


def test_the_default_style_uses_a_bundled_font():
    style = DenseStyle()
    for font in (style.lyric_font, style.chord_font, style.label_font, style.title_font):
        assert font in BUNDLED_FONTS


def test_bundled_fonts_and_their_licence_ship_with_the_package():
    for filename, _ in BUNDLED_FONTS.values():
        assert (FONTS_DIR / filename).is_file()
    assert "Bitstream Vera" in (FONTS_DIR / "LICENSE-DejaVu.txt").read_text()


@pytest.mark.parametrize("font", sorted(BUNDLED_FONTS))
def test_bundled_fonts_cover_text_beyond_latin_1(font):
    from reportlab.pdfbase import pdfmetrics

    name = usable_font(font)
    assert name == font
    char_to_glyph = pdfmetrics.getFont(name).face.charToGlyph
    missing = [c for c in BEYOND_LATIN_1 if c != " " and ord(c) not in char_to_glyph]
    assert not missing


def test_a_sheet_beyond_latin_1_embeds_the_font():
    chart = "\n".join(["Verse 1:", "G        D", f"ılık {BEYOND_LATIN_1} rüzgar", "Em   C", "şarkı söyle"])
    buffer = io.BytesIO()
    info = render_dense_a4(parse_chords_over_lyrics(chart), buffer)
    pdf = buffer.getvalue()
    assert info["pages"] == 1
    assert b"/FontFile2" in pdf  # an embedded TrueType program
    assert b"DejaVuSans" in pdf


def test_a_font_that_cannot_load_falls_back_with_a_warning(monkeypatch, tmp_path):
    monkeypatch.setitem(BUNDLED_FONTS, "SongleafMissingFont", ("missing.ttf", "Helvetica"))
    monkeypatch.setattr(render, "FONTS_DIR", tmp_path)
    usable_font.cache_clear()
    try:
        with pytest.warns(UserWarning, match="missing.ttf"):
            assert usable_font("SongleafMissingFont") == "Helvetica"
    finally:
        usable_font.cache_clear()


def test_other_font_names_pass_through():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert usable_font("Helvetica") == "Helvetica"
        assert usable_font("Times-Roman") == "Times-Roman"


def test_the_old_look_is_one_keyword_away():
    style = DenseStyle(lyric_font="Helvetica", chord_font="Helvetica-Bold")
    buffer = io.BytesIO()
    render_dense_a4(parse_chords_over_lyrics("C   G\nplain words here"), buffer, style=style)
    assert buffer.getvalue().startswith(b"%PDF")


def test_an_unknown_font_name_says_what_to_do():
    with pytest.raises(ValueError, match="registerFont"):
        usable_font("SongleafNoSuchFont")
