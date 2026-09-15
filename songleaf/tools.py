"""The single source of truth for every surface: plain functions, flat arguments, JSON-ready results.

The CLI (``python -m songleaf``) is ``cw`` over :data:`TOOLS`. Nothing here
knows about any surface. ``sources``, ``store`` and ``renderer`` are the seams:
library callers pass them, the CLI hides them. Code that wants objects rather
than dicts uses :mod:`songleaf.sources`, :mod:`songleaf.store` and
:mod:`songleaf.render` directly.
"""

from __future__ import annotations

import os
import re

from songleaf.sources import get_song
from songleaf.sources import search as search_hits
from songleaf.store import data_dir, song_store


def search(
    query: str = "",
    *,
    title: str = "",
    artist: str = "",
    lyrics: str = "",
    limit: int = 10,
    sources=None,
) -> list[dict]:
    """Find songs: fuzzy title and artist (``query``), or by title, artist, or words of the lyrics."""
    hits = search_hits(
        query, title=title, artist=artist, lyrics=lyrics, limit=limit, sources=sources
    )
    return [hit.to_dict() for hit in hits]


def sheet(
    query: str,
    *,
    output: str = "",
    pick: int = 1,
    sources=None,
    store=None,
    renderer=None,
) -> dict:
    """Make a one-page song sheet (PDF) for the best match of ``query``.

    ``query`` may also be the key of a stored song (as ``songs`` lists them),
    which renders it without searching. The song is saved to the store; the
    PDF goes to ``output``, by default the ``sheets`` data directory.
    ``pick`` chooses the n-th best match instead of the best.
    """
    if pick < 1:
        raise ValueError(f"pick counts from 1, got {pick}")
    store = song_store() if store is None else store
    if query in store:
        key = query
    else:
        hits = search_hits(query, limit=pick, sources=sources)
        if len(hits) < pick:
            found = f"only {len(hits)} match" if hits else "nothing matches"
            raise LookupError(f"No song number {pick} for {query!r}: {found}")
        key = hits[pick - 1].key
        if key not in store:
            store[key] = get_song(key, sources=sources)
    song = store[key]
    if renderer is None:
        from songleaf.render import render_dense_a4

        renderer = render_dense_a4
    output = output or os.path.join(
        data_dir("sheets"), _file_name(song.artist, song.title, key)
    )
    return {
        "key": key,
        "title": song.title,
        "artist": song.artist,
        **renderer(song, output),
    }


def songs(*, store=None) -> list[str]:
    """The keys of the stored songs."""
    store = song_store() if store is None else store
    return sorted(store)


def _file_name(artist: str, title: str, key: str) -> str:
    def slug(text):
        return re.sub(r"\W+", "-", text.lower()).strip("-")

    return (slug(f"{artist} {title}") or slug(key)) + ".pdf"


#: Every operation, in the order the CLI lists them.
TOOLS = (search, sheet, songs)
