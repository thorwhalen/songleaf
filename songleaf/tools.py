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

from songleaf import sources as _sources
from songleaf.store import data_dir, song_store

_MAX_FILE_STEM = 120


def search(
    query: str = "",
    *,
    title: str = "",
    artist: str = "",
    lyrics: str = "",
    limit: int = 10,
    sources=None,
) -> list[dict]:
    """Find songs: fuzzy title and artist (``query``), or by title, artist, or whole words of the lyrics."""
    hits = _sources.search(
        query, title=title, artist=artist, lyrics=lyrics, limit=limit, sources=sources
    )
    return [hit.to_dict() for hit in hits]


def sheet(
    query: str,
    *,
    output: str = "",
    pick: int = 1,
    refresh: bool = False,
    sources=None,
    store=None,
    renderer=None,
) -> dict:
    """Make a one-page song sheet (PDF) for the best match of ``query``.

    ``query`` may also be a song key, as ``search`` and ``songs`` show them
    (``kaggle_chords:1234``): a stored song renders without searching, and the
    key of a known source is fetched from it directly. ``pick`` chooses the n-th
    best match instead of the best. The song is saved to the store; ``refresh``
    fetches it from its source again, replacing the stored copy. The PDF goes to
    ``output``, by default the ``sheets`` data directory.
    """
    if pick < 1:
        raise ValueError(f"pick counts from 1, got {pick}")
    store = song_store() if store is None else store
    key = _key_named_by(query, store=store, sources=sources)
    if key is None:
        hits = _sources.search(query, limit=pick, sources=sources)
        if len(hits) < pick:
            found = f"only {len(hits)} match" if hits else "nothing matches"
            raise LookupError(f"No song number {pick} for {query!r}: {found}")
        key = hits[pick - 1].key
    if refresh or not _is_stored(store, key):
        store[key] = _sources.get_song(key, sources=sources)
    song = store[key]
    if renderer is None:
        from songleaf.render import render_dense_a4

        renderer = render_dense_a4
    output = output or os.path.join(data_dir("sheets"), _file_name(song, key))
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


def _is_stored(store, key: str) -> bool:
    try:
        return key in store
    except ValueError:  # not a storable key (too long, say), so not stored
        return False


def _key_named_by(query: str, *, store, sources) -> str | None:
    """``query`` itself when it names a song: a stored key, or ``<source>:<id>`` of a known source."""
    if _is_stored(store, query):
        return query
    name, sep, song_id = query.partition(":")
    known = _sources.default_sources() if sources is None else sources
    if sep and song_id and any(source.name == name for source in known):
        return query
    return None


def _file_name(song, key: str) -> str:
    def slug(text):
        return re.sub(r"\W+", "-", text.lower()).strip("-")

    stem = slug(f"{song.artist} {song.title}")[:_MAX_FILE_STEM].strip("-")
    return "-".join(filter(None, (stem, slug(key)))) + ".pdf"


#: Every operation, in the order the CLI lists them.
TOOLS = (search, sheet, songs)
