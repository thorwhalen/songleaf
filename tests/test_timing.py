"""Play-along: LRC times aligned to song lines, media ids (songleaf#30). Synthesized lyrics only."""

import pytest

from songleaf import tools
from songleaf.model import Song, chord
from songleaf.timing import align_lrc, parse_lrc, token_f1, with_lrc, with_media

SONG = Song(
    "Paper boats on a silver stream\ncarry the names of a morning dream\n\n"
    "Sing it slow, sing it low\nlet the river know",
    [chord(0, "G"), chord(31, "D")],
    meta={"title": "Paper Boats", "artist": "Nobody"},
)
LRC = """[ar:Nobody]
[ti:Paper Boats]
[offset:+500]
[00:10.00]Paper boats on a silver stream
[00:14.50]Carry the names of a mornin' dream
[00:18.00](ooh, ooh)
[00:20.25][01:30.00]Sing it slow, sing it low
[00:24.00]Let the river know
"""


def test_parse_lrc_reads_tags_offset_and_repeats():
    lines = parse_lrc(LRC)
    assert lines[0] == (9500, "Paper boats on a silver stream")
    assert [ms for ms, text in lines if text.startswith("Sing")] == [19750, 89500]
    assert all(not text.startswith("[") for _, text in lines)
    assert parse_lrc("[00:01:50]x") == [(1500, "x")]


def test_alignment_keeps_order_and_skips_ad_libs():
    pairs = align_lrc(SONG, parse_lrc(LRC))
    starts = [SONG.text[a:].split("\n")[0][:10] for a, _ in pairs]
    assert starts == ["Paper boat", "carry the ", "Sing it sl", "let the ri"]
    assert [ms for _, ms in pairs] == [9500, 14000, 19750, 23500]


def test_only_times_are_stored_and_earlier_times_are_replaced():
    timed = with_lrc(SONG, LRC)
    times = timed.of_kind("time")
    assert len(times) == 4 and all(set(a.body) == {"ms", "source"} for a in times)
    assert timed.text == SONG.text and timed.of_kind("chord") == SONG.of_kind("chord")
    again = with_lrc(timed, "[00:01.00]Paper boats on a silver stream")
    assert [a.body["ms"] for a in again.of_kind("time")] == [1000]
    assert "mornin'" not in str(Song.to_dict(timed))


def test_token_f1():
    assert token_f1("a b c", "a b c") == 1.0 and token_f1("a b", "c d") == 0.0


def test_media_ids_are_checked():
    song = with_media(SONG, youtube="dQw4w9WgXcQ", spotify="4uLU6hMCjMI75M1A2tKUQC")
    assert song.meta["media"] == {
        "youtube": "dQw4w9WgXcQ",
        "spotify": "4uLU6hMCjMI75M1A2tKUQC",
    }
    assert (
        "media"
        not in with_media(with_media(SONG, youtube="dQw4w9WgXcQ"), youtube=None).meta
    )
    with pytest.raises(ValueError, match="youtube id"):
        with_media(SONG, youtube="https://youtu.be/x")
    with pytest.raises(ValueError, match="unknown media"):
        with_media(SONG, vimeo="123")


def test_tools_sync_and_media_store_the_song():
    store = {"paste:abc": SONG}
    out = tools.sync("paste:abc", lrc=LRC, store=store)
    assert out == {"key": "paste:abc", "timed": 4, "lines": 4}
    assert len(store["paste:abc"].of_kind("time")) == 4
    fake = lambda url, params: {
        "syncedLyrics": "[00:02.00]Paper boats on a silver stream"
    }
    assert (
        tools.sync("paste:abc", lrclib=True, store=store, get_json=fake)["timed"] == 1
    )
    with pytest.raises(ValueError, match="no LRC"):
        tools.sync("paste:abc", store=store)
    linked = tools.media("paste:abc", youtube="dQw4w9WgXcQ", store=store)
    assert linked["media"] == {"youtube": "dQw4w9WgXcQ"}
    assert tools.media("paste:abc", youtube="-", store=store)["media"] == {}
