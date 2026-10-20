"""The ``score`` extra (songleaf#12): Verovio-engraved snippets on the sheet."""

import io

import pytest

from songleaf import engrave
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import fit_font_size, render_sheet
from songleaf.snippets import abc_snippet, default_provider, mark_segment, parse_abc

pytestmark = pytest.mark.skipif(not engrave.available(), reason="needs the score extra")

BODY = '"G"G2 AB c2 d2 | "C"e4 d4 |]'
MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1"><part-list><score-part id="P1"><part-name/></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note>
</measure></part></score-partwise>"""


def test_an_abc_body_gets_a_header_and_a_tune_keeps_its_own():
    assert engrave.as_abc_tune(BODY).startswith("X:1\nL:1/8")
    tune = "X:7\nK:G\nGABc|]\n"
    assert engrave.as_abc_tune(tune) == tune
    assert [n.pitch for n in parse_abc(tune).notes] == [32, 33, 34, 35]  # K:G is not a note


@pytest.mark.parametrize("notation, format", [(BODY, "abc"), (MUSICXML, "musicxml")])
def test_engraved_snippets_render_on_one_page(chart, page_count, notation, format):
    song = mark_segment(parse_chords_over_lyrics(chart), notation, format=format)
    snippet = engrave.engraved_snippet(song)
    assert snippet is not None and snippet.width > snippet.height > 2
    assert fit_font_size(song, layout="score") < fit_font_size(song, layout="dense")
    buffer = io.BytesIO()
    info = render_sheet(song, buffer, layout="score", snippets=engrave.engraved_snippet)
    assert info["pages"] == 1 == page_count(buffer.getvalue())


def test_the_default_provider_prefers_engraving_and_falls_back(chart):
    song = mark_segment(parse_chords_over_lyrics(chart), BODY)
    engraved = default_provider()(song)
    assert engraved is not None and engraved.width != abc_snippet(song).width
    broken = mark_segment(parse_chords_over_lyrics(chart), "<not xml", format="musicxml")
    assert engrave.engraved_snippet(broken) is None
    with pytest.raises(ValueError):
        engrave.engrave_svg("C D", "lilypond")
