"""Score snippets (songleaf#12): the ABC subset, the segment rule, the row on the sheet."""

import io

import pytest

from songleaf import tools
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import SheetLayout, fit_font_size, render_sheet
from songleaf.model import score_link
from songleaf.render import _flow_rows, _Row, DenseStyle
from songleaf.snippets import (
    Bar,
    ScoreSnippet,
    abc_snippet,
    choose_segment,
    first_snippet,
    layout_tune,
    mark_segment,
    parse_abc,
    segment_at_line,
)

TUNE = '"G"G2 AB | "C"c3/2 B/ ^F2 | z2 d\'4 |]'


def test_the_abc_subset():
    tune = parse_abc(TUNE)
    notes = tune.notes
    assert notes[0].chord == "G" and notes[0].length == 0.25
    assert notes[3].length == pytest.approx(3 / 16) and notes[4].length == 1 / 16
    assert notes[5].accidental == "^"
    assert notes[6].pitch is None
    assert notes[7].pitch == 1 + 7 * 6  # d' is D6
    assert [e.kind for e in tune.events if isinstance(e, Bar)] == ["|", "|", "|]"]
    assert [n.pitch for n in parse_abc("T:Title\nK:G\n!fermata!G A").notes] == [32, 33]
    for bad in ("", "| | |", "x" * 500, "C0", "C5", "A/" + "9" * 330, "A" + "9" * 330):
        with pytest.raises(ValueError):
            parse_abc(bad)


def test_layout_has_a_size_and_grows_with_the_tune():
    short, long = layout_tune(parse_abc("C D")), layout_tune(parse_abc(TUNE))
    assert 0 < short.width < long.width
    assert long.height > short.height  # chord names add a row


def test_the_segment_rule(chart):
    song = parse_chords_over_lyrics(chart)
    segment = choose_segment(song)
    assert segment.rule == "chorus-first-line"
    assert song.text[segment.start : segment.end] == "Sing it slow, sing it low"

    plain = parse_chords_over_lyrics("C\nrow row on\nG\nsome other line\nC\nrow row on\n")
    repeated = choose_segment(plain)
    assert (repeated.rule, plain.text[repeated.start : repeated.end]) == (
        "most-repeated-line",
        "row row on",
    )
    single = parse_chords_over_lyrics("C\njust this one\n")
    assert choose_segment(single).rule == "first-line"
    assert segment_at_line(plain, 2).rule == "chosen"
    with pytest.raises(ValueError):
        segment_at_line(plain, 9)


def test_marking_records_and_overrides(chart):
    song = parse_chords_over_lyrics(chart)
    marked = mark_segment(song, TUNE)
    (score,) = marked.of_kind("score")
    assert score.body["rule"] == "chorus-first-line" and score.body["notation"] == TUNE
    again = mark_segment(marked, "C D E", segment=segment_at_line(marked, 1))
    (score,) = again.of_kind("score")
    assert score.body["rule"] == "chosen" and score.start == segment_at_line(song, 1).start
    assert song.of_kind("score") == []  # the original is untouched
    with pytest.raises(ValueError):
        mark_segment(song, "| |: :|")


def test_the_snippet_costs_font_size_and_fits_one_page(chart, page_count):
    song = mark_segment(parse_chords_over_lyrics(chart), TUNE)
    plain = fit_font_size(song, layout=SheetLayout())
    for columns in (1, 2):
        layout = SheetLayout(score=True, columns=columns)
        with_snippet = fit_font_size(song, layout=layout)
        assert with_snippet < fit_font_size(song, layout=SheetLayout(columns=columns))
        buffer = io.BytesIO()
        info = render_sheet(song, buffer, layout=layout)
        assert info["pages"] == 1 == page_count(buffer.getvalue())
    assert fit_font_size(song, layout="score") < plain


def test_no_snippet_no_cost(chart):
    song = parse_chords_over_lyrics(chart)
    assert abc_snippet(song) is None
    assert fit_font_size(song, layout="score") == fit_font_size(song, layout="dense")


def test_the_provider_is_injected(chart):
    song = parse_chords_over_lyrics(chart)
    drawn = []

    def provider(song):
        return ScoreSnippet(10, 4, lambda *args, **kwargs: drawn.append(args), start=0)

    buffer = io.BytesIO()
    render_sheet(song, buffer, layout="score", snippets=first_snippet([abc_snippet, provider]))
    assert len(drawn) == 1
    assert fit_font_size(song, layout="score", snippets=provider) < fit_font_size(song)


def test_the_tool_records_a_snippet(memory_source, tmp_path, page_count):
    from songleaf.store import song_store

    store = song_store(str(tmp_path / "songs"))
    info = tools.snippet("memory:1", "G2 AB c2", store=store, sources=[memory_source])
    assert info["rule"] == "chorus-first-line"
    info = tools.snippet("memory:1", "G2 AB c2", line=1, store=store, sources=[memory_source])
    assert info["rule"] == "chosen"
    assert abc_snippet(store["memory:1"]) is not None


def test_marking_keeps_score_links(chart):
    song = parse_chords_over_lyrics(chart)
    song.annotations.append(score_link(0, 5, source="scoreseek", id="x"))
    marked = mark_segment(mark_segment(song, "C D"), "E F")
    assert sorted(a.body.get("notation", "") for a in marked.of_kind("score")) == ["", "E F"]


def test_a_snippet_row_is_never_left_alone_at_a_frame_end():
    snippet = ScoreSnippet(10, 4, lambda *a, **k: None)
    rows = [_Row([], 30, 0), _Row([], 30, 0, figure=(snippet, 1.0)), _Row([], 30, 0)]
    frames, _ = _flow_rows(rows, 10, DenseStyle(row_gap=0), [70, 100])
    assert [len(f) for f in frames] == [1, 2] and frames[1][0].figure


def test_an_empty_snippet_is_ignored(chart):
    song = parse_chords_over_lyrics(chart)
    empty = lambda song: ScoreSnippet(0, 0, lambda *a, **k: None)  # noqa: E731
    assert fit_font_size(song, layout="score", snippets=empty) == fit_font_size(song)
