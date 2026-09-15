"""The layouts of songleaf#4: overlap, inline weave, structured packing, two columns, shading.

Every lyric here is invented for the tests.
"""

import io
import random

import pytest

from songleaf import tools
from songleaf.__main__ import main
from songleaf.harmony import Key, chord_function, estimate_key, parse_chord
from songleaf.model import Song, chord
from songleaf.packing import line_break_costs, pack_greedy, pack_structured, rhyme_key
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import (
    DFLT_MARGIN,
    LAYOUT_OPTIONS,
    DenseStyle,
    InlineChords,
    SheetLayout,
    _flow,
    _heading,
    _page_dimensions,
    _paint,
    _pieces,
    _width,
    fit_font_size,
    layout_named,
    make_renderer,
    render_dense_a4,
    render_sheet,
)

STYLE = DenseStyle()
PAGE_WIDTH, PAGE_HEIGHT = _page_dimensions("A4")
WIDTH, HEIGHT = PAGE_WIDTH - 2 * DFLT_MARGIN, PAGE_HEIGHT - 2 * DFLT_MARGIN
SPECS = [
    *LAYOUT_OPTIONS,
    *(f"{name}+two-column" for name in LAYOUT_OPTIONS if name != "two-column"),
    "inline+packed+two-column+shaded",
]


def as_layout(spec):
    return layout_named(spec) if isinstance(spec, str) else spec


def flow_at(song, size, spec):
    layout = as_layout(spec)
    paint = _paint(song, layout.style, layout.shading)
    return _flow(
        _pieces(song),
        _heading(song),
        size,
        width=WIDTH,
        height=HEIGHT,
        layout=layout,
        paint=paint,
    )


def rows_of(flow):
    return [row for frame in flow.frames for row in frame]


def fits(song, size, spec):
    flow = flow_at(song, size, spec)
    return len(flow.frames) <= as_layout(spec).columns and not flow.overflow


def right_edge(item):
    return item.x + _width(item.text, item.font) * item.size


def lyric_texts(row):
    return [item.text for item in row.items if item.color == STYLE.lyric_color]


# --- every layout ------------------------------------------------------------


@pytest.mark.parametrize("spec", SPECS)
def test_every_layout_fills_one_page(spec, chart, long_chart, page_count):
    for song in (
        parse_chords_over_lyrics(chart),
        parse_chords_over_lyrics(long_chart(60)),
    ):
        buffer = io.BytesIO()
        info = render_sheet(song, buffer, layout=spec)
        assert info["pages"] == 1 == page_count(buffer.getvalue())
        size = info["font_size"]
        assert fits(song, size, spec)
        assert size == 72 or not fits(song, size * 1.1, spec)


@pytest.mark.parametrize("spec", SPECS)
def test_nothing_runs_past_its_column(spec, long_chart):
    song = parse_chords_over_lyrics(long_chart(40))
    flow = flow_at(song, fit_font_size(song, layout=spec), spec)
    for row in rows_of(flow):
        assert all(right_edge(item) <= flow.column_width + 1e-6 for item in row.items)


@pytest.mark.parametrize("spec", SPECS)
def test_a_pile_of_chords_on_a_short_line_moves_to_a_chord_row(spec):
    symbols = ["Cmaj7", "G/B", "Am7", "Fmaj7", "Dsus4", "E7", "Bb", "Ebmaj7"] * 3
    song = Song("la\nla la", [chord(2, symbol) for symbol in symbols])
    size = 30
    flow = flow_at(song, size, spec)
    rows = rows_of(flow)
    for row in rows:
        assert all(right_edge(item) <= flow.column_width + 1e-6 for item in row.items)
    drawn = [item.text for row in rows for item in row.items if item.text in symbols]
    assert drawn == symbols  # every chord, in order
    assert lyric_texts(rows[0])[0].startswith("la")


def test_layouts_are_named_by_joining_options():
    layout = layout_named("inline + packed+2col, shaded")
    assert (layout.chords, layout.packing, layout.columns, layout.shading) == (
        "inline",
        "structured",
        2,
        True,
    )
    assert layout_named("dense") == SheetLayout()
    assert layout_named("overlap").style.chord_halo
    assert make_renderer("two-column").keywords["layout"].columns == 2


def test_bad_layouts_are_refused_early():
    with pytest.raises(ValueError, match="two-column"):
        layout_named("inline+three-column")
    with pytest.raises(ValueError, match="chord placement"):
        SheetLayout(chords="sideways")
    with pytest.raises(ValueError, match="columns"):
        SheetLayout(columns=0)


@pytest.mark.parametrize(
    "lines, font_size, rows", [(None, 68.49, 10), (60, 15.18, 37), (20, 29.78, 21)]
)
def test_the_dense_layout_keeps_the_numbers_of_v1(
    chart, long_chart, lines, font_size, rows
):
    # measured with songleaf 0.0.2, before the layouts existed
    text = chart if lines is None else long_chart(lines)
    meta = {"title": "Paper Boats", "artist": "The Invented Band"}
    song = parse_chords_over_lyrics(text, meta=meta)
    for info in (
        render_dense_a4(song, io.BytesIO()),
        render_sheet(song, io.BytesIO(), layout="dense"),
    ):
        assert (info["font_size"], info["pages"], info["rows"]) == (font_size, 1, rows)


def test_strategies_can_be_passed_as_objects(chart):
    song = parse_chords_over_lyrics(chart)
    layout = SheetLayout(
        chords=InlineChords(snap_to_syllables=False), packing=pack_greedy
    )
    assert render_sheet(song, io.BytesIO(), layout=layout)["pages"] == 1


# --- overlap -----------------------------------------------------------------


def test_overlap_chords_sit_on_the_words_and_are_drawn_over_them():
    size, song = 20, Song("Paper boats drift", [chord(0, "G"), chord(6, "D")])
    style = layout_named("overlap").style
    (row,) = rows_of(flow_at(song, size, "overlap"))
    chords = [item for item in row.items if item.text in ("G", "D")]
    assert len(chords) == 2
    assert all(c.halo and 0 < c.rise < style.ascent * size for c in chords)
    assert set(row.items[-2:]) == set(chords)  # drawn after the lyrics
    (dense_row,) = rows_of(flow_at(song, size, "dense"))
    assert row.top < dense_row.top


# --- inline ------------------------------------------------------------------


def inline_row(song, size=20, spec="inline"):
    (row,) = rows_of(flow_at(song, size, spec))
    return row


def test_inline_chords_come_right_before_their_syllable_in_the_line():
    size = 20
    row = inline_row(Song("Paper boats", [chord(6, "D")]), size)
    first, second = [item for item in row.items if item.color == STYLE.lyric_color]
    (d,) = [item for item in row.items if item.color == STYLE.chord_color]
    assert (first.text, second.text) == ("Paper ", "boats")
    assert right_edge(first) <= d.x and right_edge(d) < second.x
    assert row.top == pytest.approx(STYLE.ascent * size)  # no height for the chords


def test_a_chord_that_sounds_before_its_syllable_carries_the_marker():
    song = Song("Paper boats", [chord(0, "G", timing="before"), chord(6, "D")])
    row = inline_row(song)
    chords = [item.text for item in row.items if item.color == STYLE.chord_color]
    assert chords == [STYLE.before_marker + "G", "D"]


def test_a_chord_inside_a_word_shows_at_the_word_or_syllable_start():
    song = Song("silver lighter", [chord(2, "D"), chord(12, "C")])
    assert lyric_texts(inline_row(song)) == ["silver ligh", "ter"]
    exact = SheetLayout(chords=InlineChords(snap_to_syllables=False))
    assert lyric_texts(inline_row(song, spec=exact)) == ["si", "lver light", "er"]
    assert song.of_kind("chord")[0].start == 2  # the song itself is unchanged


def test_inline_lines_wrap_with_their_chords():
    words = " ".join(f"w{i:02d}" for i in range(80))
    rows = rows_of(flow_at(Song(words, [chord(words.index("w50"), "G")]), 30, "inline"))
    assert len(rows) > 1
    for row in rows:
        assert all(right_edge(item) <= WIDTH + 1e-6 for item in row.items)
    (holder,) = [row for row in rows if any(item.text == "G" for item in row.items)]
    (g,) = [item for item in holder.items if item.text == "G"]
    after = min(
        (
            item
            for item in holder.items
            if item.color == STYLE.lyric_color and item.x > g.x
        ),
        key=lambda item: item.x,
    )
    assert after.text.startswith("w50")


# --- structured packing --------------------------------------------------------


def test_structured_packing_does_not_split_a_couplet_to_fill_a_row():
    song = Song("\n".join(["aa bb", "cc dd", "ee ff", "gg hh", "ii jj"]))

    def lines_per_row(size, spec):
        return [len(lyric_texts(row)) for row in rows_of(flow_at(song, size, spec))]

    size = next(s for s in range(72, 5, -1) if lines_per_row(s, "dense") == [3, 2])
    assert lines_per_row(size, "packed") == [2, 3]


def test_break_costs_follow_couplets_rhymes_and_repeats():
    assert line_break_costs(["one", "two", "three", "four", "five"]) == [
        1.0,
        0.3,
        1.0,
        0.0,
    ]
    pickup = line_break_costs(["well", "a stream", "a dream", "go slow", "go slow"])
    assert pickup[0] < pickup[1] and pickup[3] > 1  # before the pair; the repeat stays
    assert rhyme_key("above (x2)") == rhyme_key("love") == "ov"


def test_free_breaks_pack_as_few_rows_as_greedy():
    generator = random.Random(4)
    for _ in range(200):
        widths = [generator.uniform(0.5, 6) for _ in range(generator.randint(0, 12))]
        greedy = pack_greedy(widths, width=8, separator=0.3)
        structured = pack_structured(widths, width=8, separator=0.3)
        assert structured == greedy
        assert [i for row in structured for i in range(*row)] == list(
            range(len(widths))
        )


# --- two columns ---------------------------------------------------------------


def test_two_columns_flow_under_a_full_width_heading(page_count):
    lines = [f"invented line {i} rolls along" for i in range(120)]
    meta = {"title": "Quiet Road", "artist": "The Invented Band"}
    song = Song("\n\n".join(lines), meta=meta)  # a paragraph per line: nothing packs
    one, two = fit_font_size(song), fit_font_size(song, layout="two-column")
    assert two > one
    flow = flow_at(song, two, "two-column")
    assert flow.heading is not None and len(flow.frames) == 2 and all(flow.frames)
    assert flow.column_width < WIDTH / 2
    buffer = io.BytesIO()
    assert render_sheet(song, buffer, layout="two-column")["pages"] == 1
    assert page_count(buffer.getvalue()) == 1


def test_two_columns_spill_onto_more_pages_at_the_smallest_size(long_chart, page_count):
    buffer = io.BytesIO()
    info = render_sheet(
        parse_chords_over_lyrics(long_chart(1500)), buffer, layout="two-column"
    )
    assert info["font_size"] == 6 and info["pages"] > 1
    assert page_count(buffer.getvalue()) == info["pages"]


# --- shading -------------------------------------------------------------------

SHADED_CHART = "\n".join(
    [
        "Verse:",
        "G           D",
        "paper boats drift",
        "Chorus:",
        "G        Bb",
        "sing it slow",
        "C        G",
        "sing it slow",
    ]
)


def test_shading_bands_choruses_greys_repeats_and_colours_chords_by_function():
    song = parse_chords_over_lyrics(SHADED_CHART)
    rows = rows_of(flow_at(song, 14, "shaded"))
    verse, *chorus = rows
    assert verse.shade == "" and {row.shade for row in chorus} == {STYLE.chorus_shade}
    lyric_colors = [
        item.color for row in chorus for item in row.items if item.size == 14
    ]
    assert STYLE.repeat_color in lyric_colors and STYLE.lyric_color in lyric_colors
    chord_colors = {
        item.text: item.color
        for row in rows
        for item in row.items
        if item.text in ("G", "D", "Bb", "C")
    }
    assert chord_colors == {
        "G": STYLE.tonic_chord_color,
        "D": STYLE.chord_color,
        "C": STYLE.chord_color,
        "Bb": STYLE.outside_chord_color,
    }


def test_without_shading_nothing_is_shaded():
    rows = rows_of(flow_at(parse_chords_over_lyrics(SHADED_CHART), 14, "dense"))
    assert {row.shade for row in rows} == {""}


@pytest.mark.parametrize(
    "symbol, parsed",
    [
        ("C#m7b5", (1, "diminished")),
        ("Gsus4", (7, "open")),
        ("E5", (4, "open")),
        ("Dm9", (2, "minor")),
        ("D/F#", (2, "major")),
        ("*Ebmaj7", (3, "major")),
        ("N.C.", None),
    ],
)
def test_chord_symbols_are_read_for_their_function(symbol, parsed):
    assert parse_chord(symbol) == parsed


def test_keys_are_estimated_from_the_chords():
    assert estimate_key(["Em", "C", "G", "D", "Em"]) == Key(4, minor=True)
    assert estimate_key([]) is None
    assert chord_function("Gsus4", Key(7)) == "tonic"


def test_a_song_without_chords_can_be_shaded():
    song = Song("sing it slow\nsing it slow")
    assert render_sheet(song, io.BytesIO(), layout="shaded")["pages"] == 1


# --- tools and CLI -------------------------------------------------------------


def test_sheet_takes_a_layout_and_names_the_file_after_it(
    memory_source, tmp_path, monkeypatch
):
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    result = tools.sheet(
        "paper boats", layout="inline+two-column", sources=[memory_source]
    )
    assert result["path"].endswith("paper-boats-memory-1-inline-two-column.pdf")
    with pytest.raises(ValueError, match="Unknown layout option"):
        tools.sheet("paper boats", layout="sideways", sources=[memory_source])


def test_the_cli_takes_a_layout(memory_source, monkeypatch, tmp_path, capsys):
    from songleaf import sources as sources_module

    monkeypatch.setattr(sources_module, "default_sources", lambda: (memory_source,))
    output = tmp_path / "cli.pdf"
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "sheet",
                "paper boats",
                "--layout",
                "overlap+packed",
                "--output",
                str(output),
            ]
        )
    assert exit_info.value.code == 0 and output.exists()
    with pytest.raises(SystemExit) as exit_info:
        main(["sheet", "paper boats", "--layout", "sideways"])
    _, err = capsys.readouterr()
    assert exit_info.value.code == 1 and "Unknown layout option" in err
