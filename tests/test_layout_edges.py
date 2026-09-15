"""Edge cases of the layouts found by an independent review (songleaf#4). Invented lyrics only."""

import io

import pytest

from songleaf import tools
from songleaf.harmony import parse_chord
from songleaf.model import Song
from songleaf.packing import line_break_costs
from songleaf.render import (
    DenseStyle,
    InlineChords,
    OverChords,
    SheetLayout,
    _break_costs,
    _Piece,
    _wrap,
    layout_named,
    layout_spec,
    make_renderer,
    render_dense_a4,
    render_sheet,
)


@pytest.mark.parametrize("chords", [OverChords(), InlineChords()])
def test_a_word_broken_inside_never_leaves_chords_past_the_column(chords):
    style, size, width = DenseStyle(), 18.7, 92
    piece = _Piece("dravenstrength", [(2, "Am", "at"), (2, "Dsus4", "at")])
    parts = _wrap(piece, size, width, style, chords)
    assert all(chords.extent(part, size, style) <= width + 1e-6 for part in parts)
    assert [symbol for part in parts for _, symbol, _ in part.chords] == ["Am", "Dsus4"]
    assert "".join(part.text for part in parts) == "dravenstrength"


def test_a_wrapped_line_rhymes_and_repeats_as_a_whole():
    run = [
        _Piece("sing the road ahead", line=0),
        _Piece("go slow", line=0),
        _Piece("go slow", line=1),
    ]
    whole = line_break_costs(["sing the road ahead go slow", "go slow"])
    assert _break_costs(run) == [0.0, whole[0]]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"columns": True}, "columns"),
        ({"columns": 0}, "columns"),
        ({"shading": "no"}, "shading"),
        ({"chords": 3}, "chords"),
        ({"chords": "sideways"}, "chord placement"),
        ({"packing": None}, "packing"),
    ],
)
def test_bad_layouts_fail_when_made(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SheetLayout(**kwargs)


def test_equal_layouts_are_equal():
    assert SheetLayout(chords=InlineChords()) == SheetLayout(chords=InlineChords())
    assert InlineChords() != InlineChords(snap_to_syllables=False)


def test_one_layout_has_one_spelling():
    assert layout_spec("Dense") == "dense"
    assert layout_spec("2col+inline") == layout_spec("two-column + INLINE")
    assert layout_named("inline+overlap+inline").chords == "inline"


def test_bad_render_options_fail_when_the_renderer_is_made():
    with pytest.raises(TypeError):
        make_renderer("dense", style=DenseStyle())


def test_too_many_columns_is_an_error_not_a_blank_page():
    with pytest.raises(ValueError, match="column"):
        render_sheet(Song("la la"), io.BytesIO(), layout=SheetLayout(columns=150))


@pytest.mark.parametrize(
    "symbol, parsed",
    [
        ("Bridge", None),
        ("Dance", None),
        ("C-", (0, "minor")),
        ("C-7", (0, "minor")),
        ("A7sus4", (9, "open")),
    ],
)
def test_only_chords_are_read_as_chords(symbol, parsed):
    assert parse_chord(symbol) == parsed


def test_a_layout_and_a_renderer_do_not_go_together(memory_source):
    with pytest.raises(ValueError, match="not both"):
        tools.sheet(
            "paper boats",
            layout="inline",
            renderer=render_dense_a4,
            sources=[memory_source],
        )


def test_a_layout_names_its_file_one_way(memory_source, tmp_path, monkeypatch):
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))

    def path(spec):
        return tools.sheet("paper boats", layout=spec, sources=[memory_source])["path"]

    assert path("inline+2col") == path("INLINE + two-column")
    assert path("Dense").endswith("paper-boats-memory-1.pdf")
