"""The one-command path on the real Kaggle corpus. Local only: the corpus is in neither the repo nor CI.

Run with ``SONGLEAF_TEST_CORPUS=1`` on a machine that has the corpus zip (see
``sung.chords_and_lyrics.local_chords_and_lyrics_zip``). The test asserts
structure only and keeps no song text.
"""

import io
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SONGLEAF_TEST_CORPUS") != "1",
    reason="set SONGLEAF_TEST_CORPUS=1 to run against the local Kaggle corpus",
)


def test_a_real_song_renders_on_one_page(page_count):
    from songleaf.render import render_dense_a4
    from songleaf.sources import KaggleChordsSource

    source = KaggleChordsSource()
    (best, *_) = source.search("10000 hours justin bieber", limit=3)
    assert best.artist.lower() == "justin bieber"
    song = source.get(best.id)
    assert song.of_kind("chord") and song.of_kind("section")
    buffer = io.BytesIO()
    assert render_dense_a4(song, buffer)["pages"] == 1
    assert page_count(buffer.getvalue()) == 1
