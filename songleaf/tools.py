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
    layout: str = "dense",
    transpose: int = 0,
    scale: float = 1.0,
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

    ``layout`` is ``dense`` (the default), or options joined with ``+``:
    ``overlap`` (chords over the words themselves), ``inline`` (chords in the
    line, before their syllable), ``packed`` (rows break where the lyrics do),
    ``two-column``, ``shaded`` (sections, repeated lines and chord functions);
    for example ``inline+packed+two-column``. A ``renderer`` decides the layout
    itself, so it does not go with ``layout`` or ``scale``.

    ``transpose`` moves every chord by that many semitones (spelled for the new
    key); the stored song keeps its chords. ``scale`` multiplies the font size
    that fills the page: ``0.8`` for smaller type, ``1.2`` for larger type over
    more pages.
    """
    if pick < 1:
        raise ValueError(f"pick counts from 1, got {pick}")
    layout_name = ""
    if renderer is None:
        from songleaf.render import layout_spec, make_renderer

        # a bad layout fails before any search
        renderer = make_renderer(layout, scale=scale)
        layout_name = "" if layout_spec(layout) == "dense" else layout_spec(layout)
    elif layout != "dense" or scale != 1.0:
        raise ValueError(
            "Pass a layout and scale, or a renderer, not both: the renderer decides them"
        )
    key, song = _resolve(
        query, pick=pick, refresh=refresh, sources=sources, store=store
    )
    if transpose:
        from songleaf.harmony import transpose as transposed

        song = transposed(song, transpose)
        layout_name = "+".join(filter(None, (layout_name, f"t{transpose:+d}")))
    output = output or os.path.join(
        data_dir("sheets"), _file_name(song, key, layout_name)
    )
    return {
        "key": key,
        "title": song.title,
        "artist": song.artist,
        **renderer(song, output),
    }


def song(
    query: str,
    *,
    pick: int = 1,
    refresh: bool = False,
    transpositions: int = 6,
    sources=None,
    store=None,
) -> dict:
    """The song itself as JSON: lyrics text, chords and sections, and every key it can move to.

    ``query`` is a song key or a search, as for ``sheet``; the song is stored
    the same way. Besides the song's own fields (``text``, ``annotations``,
    ``meta``, ``provenance``), the result has ``chords`` (the distinct chords,
    in order of first appearance), ``sections`` (``{"start", "end", "label",
    "family"}``, the family as the printed sheet shades it: ``"chorus"``,
    ``"bridge"`` or ``""``), ``song_key`` (the estimated key, ``""`` with
    no chords) and ``transpositions``: one table per shift from
    ``-transpositions + 1`` to ``transpositions`` semitones, each
    ``{"semitones", "key", "chords": {original: transposed}}``.
    """
    from songleaf.harmony import transposition_table
    from songleaf.render import section_family

    if pick < 1:
        raise ValueError(f"pick counts from 1, got {pick}")
    key, found = _resolve(
        query, pick=pick, refresh=refresh, sources=sources, store=store
    )
    symbols = [a.body["symbol"] for a in found.of_kind("chord")]
    shifts = range(-transpositions + 1, transpositions + 1)
    tables = [transposition_table(symbols, n) for n in shifts]
    return {
        "key": key,
        "title": found.title,
        "artist": found.artist,
        **found.to_dict(),
        "chords": list(dict.fromkeys(symbols)),
        "sections": [
            {
                "start": a.start,
                "end": a.end,
                "label": a.body.get("label", ""),
                "family": section_family(a.body.get("label", "")),
            }
            for a in found.of_kind("section")
        ],
        "song_key": transposition_table(symbols, 0)["key"],
        "transpositions": tables,
    }


def _resolve(query: str, *, pick: int, refresh: bool, sources, store):
    """``(key, song)`` for a song key or a search, fetching the song into the store if needed."""
    store = song_store() if store is None else store
    key = _key_named_by(query, store=store, sources=sources)
    if key is None:
        hits = _sources.search(query, limit=pick, sources=sources)
        if len(hits) < pick:
            found = f"only {len(hits)} match" if hits else "nothing matches"
            raise _sources.SongNotFound(f"No song number {pick} for {query!r}: {found}")
        key = hits[pick - 1].key
    if refresh or not _is_stored(store, key):
        store[key] = _sources.get_song(key, sources=sources)
    return key, store[key]


def forget(key: str, *, store=None) -> dict:
    """Remove a song from the stored songs. It can be found and stored again by searching.

    Returns ``{"key", "deleted"}``; ``deleted`` is False when it was not stored.
    """
    store = song_store() if store is None else store
    deleted = _is_stored(store, key)
    if deleted:
        del store[key]
    return {"key": key, "deleted": deleted}


def songs(*, store=None) -> list[str]:
    """The keys of the stored songs."""
    store = song_store() if store is None else store
    return sorted(store)


def build_index(*, path: str = "") -> dict:
    """Build the search index of the Kaggle corpus, once, where the corpus zip is.

    Searching then reads the index instead of loading the whole corpus into
    memory (tens of MB instead of over a GB per process). Run it again after
    replacing the zip. ``path`` defaults to beside the zip under the data root.
    """
    from songleaf.kaggle_index import build_kaggle_index

    result = build_kaggle_index(path=path or None)
    _sources.default_sources.cache_clear()  # this process now searches the index too
    return result


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


def _file_name(song, key: str, layout: str = "") -> str:
    def slug(text):
        return re.sub(r"\W+", "-", text.lower()).strip("-")

    stem = slug(f"{song.artist} {song.title}")[:_MAX_FILE_STEM].strip("-")
    return "-".join(filter(None, (stem, slug(key), slug(layout)))) + ".pdf"


#: Every operation, in the order the CLI lists them.
TOOLS = (search, sheet, song, songs, forget, build_index)
