import pytest

from songleaf.parse import is_chord_line, parse_chords_over_lyrics


def chords_of(song):
    return [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]


def labels_of(song):
    return [a.body["label"] for a in song.of_kind("section")]


def test_a_chord_anchors_on_the_syllable_under_it():
    song = parse_chords_over_lyrics("G     D\nPaper boats drift")
    assert song.text == "Paper boats drift"
    assert chords_of(song) == [(0, "G"), (6, "D")]


def test_a_chord_inside_a_word_anchors_on_that_syllable():
    song = parse_chords_over_lyrics("    Am\nlanterns hum")
    assert chords_of(song) == [(4, "Am")]


def test_a_chord_over_a_space_moves_to_the_next_syllable():
    assert chords_of(parse_chords_over_lyrics("  C\nab cd")) == [(3, "C")]


def test_indented_lyrics_keep_their_chords_aligned():
    song = parse_chords_over_lyrics("  G    D\n  go on home")
    assert song.text == "go on home"
    assert chords_of(song) == [(0, "G"), (6, "D")]


def test_a_chord_past_the_end_of_the_line_anchors_at_its_end():
    assert chords_of(parse_chords_over_lyrics("C          G\nla la")) == [
        (0, "C"),
        (5, "G"),
    ]


def test_every_chord_defaults_to_sounding_at_its_syllable(chart):
    assert {
        a.body["timing"] for a in parse_chords_over_lyrics(chart).of_kind("chord")
    } == {"at"}


def test_the_sample_chart(chart):
    song = parse_chords_over_lyrics(chart, meta={"title": "Paper Boats"})
    assert song.meta == {"title": "Paper Boats", "capo": 2}
    assert labels_of(song) == ["Intro", "Verse 1", "Chorus", "Chorus"]
    intro, verse, chorus, repeat = song.of_kind("section")
    assert song.text[verse.start : verse.end] == (
        "Paper boats on a silver stream\ncarry the names of a morning dream"
    )
    assert (
        song.text[chorus.start : chorus.end]
        == "Sing it slow, sing it low\nlet the river know"
    )
    # a chord-only line (the intro) is an empty line carrying its chords in order
    assert [
        a.body["symbol"] for a in song.of_kind("chord") if a.start == intro.start
    ] == [
        "G",
        "D",
        "Em",
        "C",
    ]
    # a bare "[Chorus]" is a label-only section on a line of its own
    assert repeat.start == repeat.end
    assert "|" not in song.text  # tablature is dropped


@pytest.mark.parametrize(
    "line",
    [
        "G  D/F#  Em",
        "C#m7b5 E7(#9) Gsus2/B",
        "Bb7M  Am7(9)  F#m7(5-)",
        "| G | D | (x2)",
        "G N.C.",
    ],
)
def test_chord_lines(line):
    assert is_chord_line(line)


@pytest.mark.parametrize(
    "line", ["", "Bad Dad", "A lone voice", "Break my heart", "N.C."]
)
def test_not_chord_lines(line):
    assert not is_chord_line(line)


@pytest.mark.parametrize(
    "header, label",
    [
        ("Verse 2:", "Verse 2"),
        ("[Pre-Chorus]", "Pre-Chorus"),
        ("CHORUS x2", "CHORUS x2"),
        ("Refrão:", "Refrão"),
    ],
)
def test_section_headers(header, label):
    assert labels_of(parse_chords_over_lyrics(f"{header}\nla la la")) == [label]


def test_a_header_owns_the_lines_after_a_blank_and_a_bare_one_is_a_marker():
    song = parse_chords_over_lyrics(
        "Pre-Chorus\n\nla la la\nli li li\n\n[Chorus]\n\nVerse 2:\nlo lo"
    )
    pre, chorus, verse = song.of_kind("section")
    assert song.text[pre.start : pre.end] == "la la la\nli li li"
    assert chorus.start == chorus.end
    assert song.text[verse.start : verse.end] == "lo lo"


def test_lyrics_that_start_with_a_section_word_stay_lyrics():
    song = parse_chords_over_lyrics("Break my heart again\nBridge over the water")
    assert song.of_kind("section") == []
    assert song.text == "Break my heart again\nBridge over the water"


def test_blank_runs_collapse_and_the_edges_are_trimmed():
    assert parse_chords_over_lyrics("\n\n\nla\n\n\n\nli\n\n").text == "la\n\nli"


def test_crlf_and_lf_parse_alike(chart):
    assert parse_chords_over_lyrics(
        chart.replace("\n", "\r\n")
    ) == parse_chords_over_lyrics(chart)


def test_key_and_tuning_lines_become_metadata():
    song = parse_chords_over_lyrics("Tom: G\nTuning: DADGAD\nla")
    assert song.meta == {"key": "G", "tuning": "DADGAD"}
    assert song.text == "la"
