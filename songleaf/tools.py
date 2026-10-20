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
    list_songs: int = 3,
    sources=None,
    store=None,
    library_root=None,
) -> list[dict]:
    """Find songs with one query: in your lists' names, then titles, artists and lyrics.

    With only ``query``, every song comes once, tagged with where it matched (``match``):
    ``"list"`` (the first ``list_songs`` stored songs of each list whose name the query
    names; ``list`` and ``list_name`` say which, and the list's other songs are found in
    the later kinds as usual), then ``"title"``, ``"artist"`` and ``"lyrics"``, in that order,
    at most ``limit`` of each, best first within each. A song that matches its title and
    its lyrics is a title match only. ``highlight`` holds the matched words of the title and
    artist (and of ``list_name``) as ``[start, end]`` spans; a lyrics match carries
    ``snippet``, the line that matched, with its spans.

    With ``title``, ``artist`` or ``lyrics``, it is a narrower search instead: songs that
    match every field given (and ``query``, fuzzily over title and artist), ``match: ""``.
    """
    if title or artist or lyrics:
        hits = _sources.search(
            query,
            title=title,
            artist=artist,
            lyrics=lyrics,
            limit=limit,
            sources=sources,
        )
        return [_tagged(hit.to_dict(), "", query) for hit in hits]
    if not query.strip():
        return []
    rows = _list_hits(
        query, per_list=list_songs, store=store, library_root=library_root
    )
    seen = {row["key"] for row in rows}
    for kind, hits in _sources.search_tiers(
        query, limit=limit, sources=sources
    ).items():
        for hit in hits:
            if hit.key in seen:
                continue
            seen.add(hit.key)
            row = _tagged(hit.to_dict(), kind, query)
            snippet = row["meta"].pop("snippet", None)
            if snippet:
                row["snippet"] = snippet
            rows.append(row)
    return rows


def _tagged(row: dict, kind: str, query: str) -> dict:
    from songleaf.match import word_spans

    row["match"] = kind
    row["highlight"] = {
        "title": word_spans(row["title"], query),
        "artist": word_spans(row.get("artist", ""), query),
    }
    return row


def _list_hits(query: str, *, per_list: int, store, library_root) -> list[dict]:
    """The first stored songs of the lists whose name ``query`` names, ``per_list`` of each."""
    from songleaf.library import list_members, lists_matching, read_groups

    snapshot = read_groups(root=library_root)["snapshot"]
    matched = lists_matching(query, snapshot)
    if not matched:
        return []
    store = song_store() if store is None else store
    rows, seen = [], set()
    for found in matched:
        taken = 0
        for key in list_members(snapshot, found["id"]):
            if taken >= per_list:
                break
            if key in seen or not _is_stored(store, key):
                continue
            song = store[key]
            source, _, song_id = key.partition(":")
            row = {
                "key": key,
                "source": source,
                "id": song_id,
                "title": song.title,
                "artist": song.artist,
                "score": 1.0,
                "meta": {},
            }
            row = _tagged(row, "list", query)
            row.update(list=found["id"], list_name=found["name"])
            row["highlight"]["list_name"] = found["spans"]
            rows.append(row)
            seen.add(key)
            taken += 1
    return rows


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


def songbook(
    group: str,
    *,
    output: str = "",
    title: str = "",
    layout: str = "dense",
    scale: float = 1.0,
    library_root=None,
    sources=None,
    store=None,
    renderer=None,
) -> dict:
    """Render a list (group) of songs as one PDF: a table of contents, then every song at its fitted size.

    ``group`` is a list's id or its name (the best match of the name). The
    songs come in the order they were filed in the list, nested lists
    included, so the list order is the set list. Page numbers are stamped on
    every page and each song is a PDF bookmark. ``title`` defaults to the
    list's name. ``layout`` and ``scale`` are as for ``sheet``. The PDF goes to
    ``output``, by default the ``sheets`` data directory.
    """
    from songleaf.library import list_members, list_names, lists_matching, read_groups
    from songleaf.render import make_renderer
    from songleaf.songbook import render_songbook

    snapshot = read_groups(root=library_root)["snapshot"]
    names = list_names(snapshot)
    if group in names:
        list_id = group
    else:
        found = lists_matching(group, snapshot)
        if not found:
            raise LookupError(f"No list named {group!r}")
        list_id = found[0]["id"]
    keys = list_members(snapshot, list_id)
    if not keys:
        raise LookupError(f"The list {names[list_id]!r} has no songs")
    if renderer is None:
        renderer = make_renderer(layout, scale=scale)
    elif layout != "dense" or scale != 1.0:
        raise ValueError(
            "Pass a layout and scale, or a renderer, not both: the renderer decides them"
        )
    store = song_store() if store is None else store
    songs, skipped = [], []
    for key in keys:
        try:
            songs.append(
                _resolve(key, pick=1, refresh=False, sources=sources, store=store)
            )
        except (LookupError, RuntimeError, ValueError):
            skipped.append(key)  # a song whose source is gone does not sink the book
    if not songs:
        raise LookupError(f"None of the songs in {names[list_id]!r} could be found")
    title = title or names[list_id]
    output = output or os.path.join(
        data_dir("sheets"),
        re.sub(r"\W+", "-", title.lower()).strip("-") + "-songbook.pdf",
    )
    return {
        "group": list_id,
        **render_songbook(songs, output, title=title, renderer=renderer),
        "skipped": skipped,
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


def export(
    query: str,
    *,
    format: str = "chordpro",
    transpose: int = 0,
    output: str = "",
    pick: int = 1,
    refresh: bool = False,
    sources=None,
    store=None,
) -> dict:
    """Export a song as ChordPro (``chordpro``) or plain text with chords over lyrics (``text``).

    ``query`` is a song key or a search, as for ``sheet``. ``transpose`` moves every chord
    by that many semitones (the stored song keeps its chords). The result has the ``text``;
    with ``output`` set it is also written to that file, and ``path`` says where.
    ChordPro is the fleet's interchange (Songbook Pro, OnSong and the ChordPro app read it);
    chords that sound before their syllable travel in the ``x_songleaf_before`` directive.
    """
    from songleaf.export import FORMATS

    if format not in FORMATS:
        raise ValueError(f"format is one of {sorted(FORMATS)}, got {format!r}")
    if pick < 1:
        raise ValueError(f"pick counts from 1, got {pick}")
    key, found = _resolve(
        query, pick=pick, refresh=refresh, sources=sources, store=store
    )
    write, _, _ = FORMATS[format]
    result = {
        "key": key,
        "title": found.title,
        "artist": found.artist,
        "format": format,
        "text": write(found, transpose=transpose),
    }
    if output:
        with open(output, "w", encoding="utf-8") as file:
            file.write(result["text"])
        result["path"] = output
    return result


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


def import_text(
    text: str,
    *,
    title: str = "",
    artist: str = "",
    url: str = "",
    key: str = "",
    capo: str = "",
    format: str = "",
    store=None,
) -> dict:
    """Store a song pasted from anywhere: Ultimate Guitar markup, ChordPro, OpenSong or plain chords over lyrics.

    The format is detected (``format`` forces one of ``ultimate-guitar``,
    ``chordpro``, ``opensong``, ``chords-over-lyrics``). ``url`` is only
    recorded as provenance: songleaf never contacts it (an official or Pro
    Ultimate Guitar URL is refused). The song is stored under ``paste:<hash>``
    (the same text, the same key), or ``ug:<id>`` for an Ultimate Guitar URL,
    and is then usable like any other: ``sheet <key>``, ``song <key>``.
    """
    from songleaf.importers import import_song

    imported = import_song(
        text, title=title, artist=artist, url=url, key=key, capo=capo, format=format
    )
    return _stored(imported.key, imported.song, imported.format, store=store)


def _stored(key: str, song, format: str, *, store) -> dict:
    store = song_store() if store is None else store
    store[key] = song
    return _summary(key, song, format)


def _summary(key: str, song, format: str) -> dict:
    return {
        "key": key,
        "format": format,
        "title": song.title,
        "artist": song.artist,
        "lines": len(song.text.split("\n")),
        "chords": len(song.of_kind("chord")),
    }


def import_file(
    path: str = "-",
    *,
    title: str = "",
    artist: str = "",
    url: str = "",
    format: str = "",
    store=None,
) -> dict:
    """Read pasted song text from a file (``-``: standard input) and store it; see ``import_text``."""
    import sys

    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    return import_text(
        text, title=title, artist=artist, url=url, format=format, store=store
    )


import_file.__name__ = "import"  # the CLI command is ``songleaf import``


def import_url(url: str, *, refresh: bool = False, store=None, source=None) -> dict:
    """Fetch one community Ultimate Guitar chord page and store its chart as ``ug:<id>``.

    Local command line only, and off unless ``SONGLEAF_UG_URL=1`` is set: prefer
    pasting, or the bookmarklet run on the page you opened (see
    ``songleaf.ultimate_guitar``). Official and Pro pages are refused. A chart
    already stored is not fetched again unless ``refresh``.
    """
    from songleaf.ultimate_guitar import UltimateGuitarURLSource, ug_key

    store = song_store() if store is None else store
    key = ug_key(url)
    if not key:
        raise ValueError(f"Not an Ultimate Guitar tab URL (no tab id): {url!r}")
    if not refresh and _is_stored(store, key):
        song = store[key]
        return {**_summary(key, song, "ultimate-guitar"), "cached": True}
    source = UltimateGuitarURLSource() if source is None else source
    song = source.get(url)
    return {**_stored(key, song, "ultimate-guitar", store=store), "cached": False}


def forget(key: str, *, store=None, library_root=None) -> dict:
    """Remove a song from the stored songs, from every list it was in, and from every Viewed list.

    It can be found and stored again by searching. Returns ``{"key", "deleted"}``;
    ``deleted`` is False when it was not stored.
    """
    from songleaf.library import drop_item
    from songleaf.viewed import drop_everywhere

    store = song_store() if store is None else store
    try:
        del store[key]  # one step: two deletes at once cannot both find it
        deleted = True
    except (KeyError, FileNotFoundError, ValueError):
        deleted = False
    drop_item(key, root=library_root)
    drop_everywhere(key, root=library_root)
    return {"key": key, "deleted": deleted}


def sync(
    query: str,
    *,
    lrc: str = "",
    lrclib: bool = False,
    pick: int = 1,
    store=None,
    sources=None,
    get_json=None,
) -> dict:
    """Time the song's lines from an LRC, so the page can scroll with the recording.

    ``lrc`` is the LRC text (an ``.lrc`` file's content); with ``lrclib`` and no
    ``lrc``, LRCLIB is asked for the song's synced lyrics. Only the times are stored
    (``"time"`` annotations), never the LRC's text. Returns ``{"key", "timed",
    "lines"}``: how many lyric lines got a time, of how many.
    """
    from songleaf.timing import fetch_lrclib, with_lrc

    key, found = _resolve(query, pick=pick, refresh=False, sources=sources, store=store)
    if not lrc and lrclib:
        lrc = fetch_lrclib(found.title, found.artist, get_json=get_json) or ""
    if not lrc:
        raise ValueError("no LRC: pass lrc= (an .lrc file's text) or lrclib=True")
    timed = with_lrc(found, lrc)
    store = song_store() if store is None else store
    store[key] = timed
    lyric_lines = sum(1 for line in found.lines() if line.text.strip())
    return {"key": key, "timed": len(timed.of_kind("time")), "lines": lyric_lines}


def snippet(
    query: str,
    notation: str,
    *,
    line: int = 0,
    format: str = "abc",
    pick: int = 1,
    store=None,
    sources=None,
) -> dict:
    """Put a score snippet over one line of a song; the ``score`` layout draws it on the sheet.

    ``notation`` is a few bars of ABC (``"G2 AB c2 | d4"``; the unit is an eighth
    note). ``line`` is the 1-based lyric line it goes with; ``0`` lets the rule
    choose (the first line of the chorus, else the most repeated line, else the
    first). ``format`` may also be ``musicxml`` or ``mei`` (drawn with the
    ``score`` extra only). Returns ``{"key", "start", "end", "rule"}``.
    """
    from songleaf.snippets import mark_segment, segment_at_line

    key, found = _resolve(query, pick=pick, refresh=False, sources=sources, store=store)
    segment = segment_at_line(found, line) if line else None
    marked = mark_segment(found, notation, segment=segment, format=format)
    store = song_store() if store is None else store
    store[key] = marked
    (score,) = marked.of_kind("score")
    return {
        "key": key,
        "start": score.start,
        "end": score.end,
        "rule": score.body["rule"],
    }


def media(
    query: str,
    *,
    youtube: str = "",
    spotify: str = "",
    pick: int = 1,
    store=None,
    sources=None,
) -> dict:
    """Link the song's recording: a YouTube video and/or a Spotify track, by id or link.

    An id given as ``""`` is left as it is; ``"-"`` removes it. Returns
    ``{"key", "media"}``.
    """
    from songleaf.timing import media_id, with_media

    key, found = _resolve(query, pick=pick, refresh=False, sources=sources, store=store)
    changes = {
        service: (None if value == "-" else media_id(service, value))
        for service, value in (("youtube", youtube), ("spotify", spotify))
        if value
    }
    linked = with_media(found, **changes)
    store = song_store() if store is None else store
    store[key] = linked
    return {"key": key, "media": dict(linked.meta.get("media") or {})}


def viewed(*, user: str = "", store=None, library_root=None) -> list[dict]:
    """The songs ``user`` opened, the most recent first: ``key``, ``title``, ``artist``, ``viewed_at``.

    ``user`` is who the host says is asking (no one: the list everyone shares). Songs no
    longer stored are left out. ``viewed_at`` is in seconds since the epoch.
    """
    from songleaf.viewed import read_viewed

    store = song_store() if store is None else store
    rows = []
    for entry in read_viewed(user=user, root=library_root):
        if not _is_stored(store, entry["key"]):
            continue
        song = store[entry["key"]]
        rows.append({**entry, "title": song.title, "artist": song.artist})
    return rows


def view(
    key: str, *, user: str = "", at: float = 0.0, store=None, library_root=None
) -> dict:
    """Put a stored song at the top of ``user``'s Viewed list: they just opened it.

    ``at`` (seconds since the epoch) records that time instead, which is how an undo puts
    a song it took out back where it was. Returns ``{"key", "viewed_at"}``.
    """
    from songleaf.viewed import record_view

    store = song_store() if store is None else store
    if not _is_stored(store, key):
        raise _sources.SongNotFound(f"{key!r} is not among the stored songs")
    when = record_view(key, user=user, at=at or None, root=library_root)
    return {"key": key, "viewed_at": when}


def unview(key: str, *, user: str = "", library_root=None) -> dict:
    """Take a song out of ``user``'s Viewed list. It stays stored, and in its lists.

    Returns ``{"key", "removed", "viewed_at"}``: when it had been viewed, so the same
    time can be given back to :func:`view` to undo.
    """
    from songleaf.viewed import remove_view

    at = remove_view(key, user=user, root=library_root)
    return {"key": key, "removed": at is not None, "viewed_at": at}


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
TOOLS = (
    search,
    sheet,
    songbook,
    song,
    export,
    songs,
    import_file,
    import_url,
    viewed,
    view,
    unview,
    forget,
    build_index,
    sync,
    media,
    snippet,
)
