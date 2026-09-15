"""Edge cases found by reviewing v1 against real charts, and behaviour no other test pinned."""

import io
import os
import time

import pandas as pd
import pytest

from songleaf import tools
from songleaf.model import Annotation, Song, chord
from songleaf.parse import is_chord_line, is_chord_token, parse_chords_over_lyrics
from songleaf.render import (
    DFLT_MARGIN,
    DenseStyle,
    _heading,
    _layout,
    _page_dimensions,
    _pieces,
    _width,
    fit_font_size,
    render_dense_a4,
)
from songleaf.sources import KaggleChordsSource
from songleaf.store import song_store

STYLE = DenseStyle()
PAGE_WIDTH, _ = _page_dimensions("A4")
WIDTH = PAGE_WIDTH - 2 * DFLT_MARGIN


def rows_at(song, size):
    return _layout(_pieces(song), size, WIDTH, STYLE, _heading(song))


def right_edge(item):
    return item.x + _width(item.text, item.font) * item.size


# --- parsing ---------------------------------------------------------------


@pytest.mark.parametrize("token", ["F7+", "D7/9", "Bm5-/7", "A4/7", "D7sus", "Gsus"])
def test_more_chord_spellings(token):
    assert is_chord_token(token)


def test_a_chord_line_may_carry_a_note():
    assert is_chord_line("G  D  Em  C  (riff)")


@pytest.mark.parametrize(
    "header, label",
    [("Pré-Refrão:", "Pré-Refrão"), ("Chorus (repeat)", "Chorus (repeat)")],
)
def test_more_section_headers(header, label):
    song = parse_chords_over_lyrics(f"{header}\nla la")
    assert [a.body["label"] for a in song.of_kind("section")] == [label]


def test_brackets_without_a_section_word_are_lyrics():
    song = parse_chords_over_lyrics("[laughs]\nla la")
    assert song.of_kind("section") == []
    assert song.text == "[laughs]\nla la"


def test_a_header_whose_rest_is_a_repeat_is_a_marker():
    (marker,) = parse_chords_over_lyrics("Chorus: x2").of_kind("section")
    assert marker.body == {"label": "Chorus x2", "marker": True}


def test_markers_are_flagged_and_chord_only_sections_are_not(chart):
    intro, verse, chorus, repeat = parse_chords_over_lyrics(chart).of_kind("section")
    assert intro.start == intro.end and "marker" not in intro.body
    assert repeat.body.get("marker") is True


def test_decoration_is_dropped_but_dashes_in_lyrics_are_not():
    song = parse_chords_over_lyrics("==========\nlove ---- ----\n|--0--2--|")
    assert song.text == "love ---- ----"


@pytest.mark.parametrize(
    "line",
    ["( G D )", "G D Em/b13 C7/9b", "*D ...Dm6", "G D (walking bass)", "G x 2 ?"],
)
def test_chord_lines_with_marks_and_notes(line):
    assert is_chord_line(line)


@pytest.mark.parametrize(
    "line, label",
    [("Intro G D Em", "Intro"), ("Solo: A E", "Solo"), ("Intr.: G C", "Intr.")],
)
def test_a_section_word_followed_by_chords_is_a_header(line, label):
    song = parse_chords_over_lyrics(line)
    (header,) = song.of_kind("section")
    assert header.body["label"] == label
    assert song.text == "" and song.of_kind("chord")


def test_blank_lines_between_a_header_and_its_lines_are_skipped():
    song = parse_chords_over_lyrics("Verse:\n\n\nla la")
    (verse,) = song.of_kind("section")
    assert song.text == "la la" and (verse.start, verse.end) == (0, 5)


# --- rendering -------------------------------------------------------------


def test_nothing_runs_off_the_page_sideways():
    unbreakable = "x" * 90
    song = Song(f"{unbreakable}\n{'=' * 200}\nshort line")
    size = fit_font_size(song)
    for row in rows_at(song, size):
        assert all(right_edge(item) <= WIDTH + 1e-6 for item in row.items)


def test_a_long_label_is_shortened():
    song = Song("la la", [Annotation("section", 0, 5, {"label": "Verse " + "x" * 200})])
    (row,) = rows_at(song, 20)
    (label,) = [i for i in row.items if i.color == STYLE.label_color]
    assert len(label.text) <= 16 and label.text.endswith("…")


def test_a_very_long_line_renders_quickly():
    song = Song(" ".join(["word"] * 5000))
    started = time.perf_counter()
    info = render_dense_a4(song, io.BytesIO())
    assert info["pages"] >= 1
    assert time.perf_counter() - started < 20


def test_colliding_chords_are_pushed_apart():
    (row,) = rows_at(Song("abc", [chord(0, "Cmaj7"), chord(1, "G")]), 20)
    first, second = [i for i in row.items if i.color == STYLE.chord_color]
    assert second.x >= right_edge(first)


def test_a_chord_at_the_end_of_a_line_stays_on_that_line():
    first, second = _pieces(Song("ab\ncd", [chord(2, "G")]))
    assert [c[1] for c in first.chords] == ["G"] and second.chords == []


def test_chords_stay_on_their_syllable_after_wrapping():
    words = [f"w{i:02d}" for i in range(80)]
    text = " ".join(words)
    at = text.index("w50")
    size = 30
    for row in rows_at(Song(text, [chord(at, "G")]), size):
        (lyric,) = [i for i in row.items if i.color == STYLE.lyric_color]
        if "w50" in lyric.text:
            (g,) = [i for i in row.items if i.color == STYLE.chord_color]
            before = lyric.text[: lyric.text.index("w50")]
            assert g.x == pytest.approx(
                lyric.x + _width(before, STYLE.lyric_font) * size
            )
            break
    else:
        pytest.fail("no row holds the chord's syllable")


def test_chord_only_lines_and_lyric_lines_take_separate_rows():
    rows = rows_at(Song("\nla la", [chord(0, "G")]), 20)
    assert len(rows) == 2
    (bare,) = [i for i in rows[0].items if i.color == STYLE.chord_color]
    assert bare.rise == 0


# --- sources, store, tools -------------------------------------------------


@pytest.fixture
def kaggle(chart):
    corpus = pd.DataFrame(
        {
            "Unnamed: 0": [0, 1],
            "artist_name": ["The Invented Band", "Nobody Real"],
            "song_name": ["Paper Boats", "Silver Stream"],
            "chords&lyrics": [chart, "[email\xa0protected]\nC\nla la thing"],
            "lang": ["en", "en"],
            "popularity": [10, 90],
        }
    )
    return KaggleChordsSource(loader=lambda: corpus)


def test_lyrics_match_whole_words_only(kaggle):
    assert kaggle.search(lyrics="in") == []
    assert [hit.id for hit in kaggle.search(lyrics="thing")] == ["1"]


def test_obfuscated_email_lines_are_dropped(kaggle):
    assert kaggle.get("1").text == "la la thing"


def test_keys_differing_only_in_case_are_different_songs(tmp_path):
    store = song_store(str(tmp_path))
    store["src:Abc"] = Song("upper")
    store["src:abc"] = Song("lower")
    assert (store["src:Abc"].text, store["src:abc"].text) == ("upper", "lower")
    assert len({name.lower() for name in os.listdir(tmp_path)}) == 2


def test_a_key_too_long_for_a_file_name_is_refused(tmp_path):
    with pytest.raises(ValueError, match="too long"):
        song_store(str(tmp_path))["src:" + "x" * 300] = Song("la")


def test_only_song_files_are_songs(tmp_path):
    store = song_store(str(tmp_path))
    store["memory:1"] = Song("la")
    (tmp_path / "notes.txt").write_text("not a song")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "other.json").write_text("{}")
    assert list(store) == ["memory:1"]


def test_a_key_of_a_known_source_is_fetched_not_searched(memory_source, tmp_path):
    result = tools.sheet(
        "memory:2", output=str(tmp_path / "s.pdf"), sources=[memory_source]
    )
    assert (result["key"], result["title"]) == ("memory:2", "Quiet Road")


def test_a_long_query_is_searched_not_refused(memory_source):
    with pytest.raises(LookupError):
        tools.sheet("zzz " * 80, sources=[memory_source])


def test_refresh_replaces_the_stored_copy(memory_source, tmp_path):
    store = song_store(str(tmp_path / "songs"))
    store["memory:1"] = Song("an edited copy")
    output = str(tmp_path / "s.pdf")
    tools.sheet("memory:1", output=output, sources=[memory_source], store=store)
    assert store["memory:1"].text == "an edited copy"
    tools.sheet(
        "memory:1", output=output, refresh=True, sources=[memory_source], store=store
    )
    assert store["memory:1"].title == "Paper Boats"
