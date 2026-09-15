"""Shared fixtures: synthesized chord charts and an in-memory source.

Every lyric here is invented for the tests. No text from any real song or
source belongs in this repository.
"""

import re

import pytest

from songleaf.parse import parse_chords_over_lyrics
from songleaf.sources import Hit

CHART = "\n".join(
    [
        "Capo on 2nd fret",
        "",
        "Intro: G  D  Em  C",
        "",
        "Verse 1:",
        "G              D",
        "Paper boats on a silver stream",
        "Em             C",
        "carry the names of a morning dream",
        "",
        "Chorus",
        "C          G",
        "Sing it slow, sing it low",
        "Am            D",
        "let the river know",
        "",
        "[Chorus]",
        "",
        "e|-----3-----2-----|",
    ]
)


def _long_chart(n_lines: int) -> str:
    lines = []
    for i in range(n_lines):
        if i % 8 == 0:
            lines += ["", f"Verse {i // 8 + 1}:"]
        lines += ["C        G", f"invented line {i} rolls along the quiet road"]
    return "\n".join(lines)


class MemorySource:
    """A source over a dict of synthesized charts: ``{id: (title, artist, chart)}``."""

    name = "memory"

    def __init__(self, charts):
        self.charts = charts

    def search(self, query="", *, title="", artist="", lyrics="", limit=10):
        words = query.lower().split()
        return [
            Hit(self.name, song_id, song_title, song_artist, score=1.0)
            for song_id, (song_title, song_artist, _) in self.charts.items()
            if words and all(w in f"{song_title} {song_artist}".lower() for w in words)
        ][:limit]

    def get(self, song_id):
        song_title, song_artist, chart = self.charts[song_id]
        return parse_chords_over_lyrics(
            chart,
            meta={"title": song_title, "artist": song_artist},
            provenance={"source": self.name, "id": song_id},
        )


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """No test writes to the real data root."""
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def chart():
    return CHART


@pytest.fixture
def long_chart():
    return _long_chart


@pytest.fixture
def memory_source():
    return MemorySource(
        {
            "1": ("Paper Boats", "The Invented Band", CHART),
            "2": ("Quiet Road", "The Invented Band", _long_chart(40)),
        }
    )


@pytest.fixture
def page_count():
    def count(pdf: bytes) -> int:
        return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf))

    return count
