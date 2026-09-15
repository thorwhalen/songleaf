"""songleaf: dense, readable one-page song sheets from searchable sources.

Find a song, keep it as lyrics plus anchored annotations (sections, chords,
provenance, score links), and render it onto one A4 page with the lyrics as
large as will fit.

>>> import songleaf
>>> song = songleaf.parse_chords_over_lyrics("C       G\\nHello there my friend")
>>> [a.body["symbol"] for a in song.of_kind("chord")]
['C', 'G']

From a query to a PDF, on the Kaggle chords-and-lyrics corpus::

    songleaf.sheet("wonderwall oasis")   # -> {'path': '.../sheets/oasis-wonderwall.pdf', ...}

or ``python -m songleaf sheet "wonderwall oasis"``.
"""

from songleaf.model import Annotation, Song, chord, score_link, section
from songleaf.parse import parse_chords_over_lyrics
from songleaf.render import DenseStyle, fit_font_size, render_dense_a4
from songleaf.sources import Hit, KaggleChordsSource, get_song, search
from songleaf.store import song_store
from songleaf.tools import sheet, songs

__all__ = [
    "Annotation",
    "DenseStyle",
    "Hit",
    "KaggleChordsSource",
    "Song",
    "chord",
    "fit_font_size",
    "get_song",
    "parse_chords_over_lyrics",
    "render_dense_a4",
    "score_link",
    "search",
    "section",
    "sheet",
    "song_store",
    "songs",
]
