"""Turn pasted text into a :class:`~songleaf.model.Song`: a registry of format importers.

Each :class:`Importer` is a strategy: ``detect(text)`` says whether the text is
in its format, ``parse(text, meta=, provenance=)`` builds the song. The registry
:data:`IMPORTERS` is tried in order and the first match wins; the last one
(plain chords-over-lyrics) matches anything, so :func:`import_text` always
answers. A new format is a new :class:`Importer` in the registry, or one passed
as ``importers=``.

- ``ultimate-guitar``: ``[ch]G[/ch]`` / ``[tab]...[/tab]`` markup, stripped to
  columns, then parsed as chords-over-lyrics (``[Verse 1]`` headers become
  sections).
- ``chordpro``: ``{directive}`` lines or ``[G]`` chords inline in the lyrics.
- ``opensong``: lines prefixed ``.`` (chords), `` `` (lyrics), ``;`` (comment),
  ``[V1]``-style section tags.
- ``chords-over-lyrics``: the fallback.

songleaf never contacts the site the text came from.

>>> import_song("[ch]G[/ch]    [ch]D[/ch]\\nPaper boats drift").format
'ultimate-guitar'
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from songleaf import chordpro as _chordpro
from songleaf import parse as _parse
from songleaf.model import Song

#: Provenance recorded for every pasted song (``url`` is added when known).
PASTE_PROVENANCE = {"source": "paste", "license": "personal"}

#: Characters of the text hashed into the ``paste:<hash>`` key.
KEY_HASH_CHARS = 12

#: Characters a given ``key`` or ``capo`` may have at most (``"F#m"``, ``"2"``).
MAX_META_CHARS = 20

#: Pasted text longer than this is refused (a chord chart is a few KB).
MAX_PASTE_CHARS = 200_000

_UG_RE = re.compile(r"\[/?(?:ch|tab)\]", re.IGNORECASE)
_DIRECTIVE_RE = re.compile(r"^\s*\{\s*[\w-]+\s*(?::.*)?\}\s*$", re.MULTILINE)
_INLINE_CHORD_RE = re.compile(r"\w[^\n\[\]]*\[([^\[\]\s]+)\]|^\[([^\[\]\s]+)\]\S", re.M)
_OPENSONG_CHORD_LINE_RE = re.compile(r"^\.", re.MULTILINE)
_OPENSONG_TAGS = {
    "V": "Verse",
    "C": "Chorus",
    "B": "Bridge",
    "P": "Pre-chorus",
    "T": "Tag",
}
_OPENSONG_TAG_RE = re.compile(r"^\[([VCBPT])(\d*)\]\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Importer:
    """One text format: how to recognise it and how to read it."""

    name: str
    detect: Callable[[str], bool]
    parse: Callable[..., Song]


def _strip_ultimate_guitar(text: str) -> str:
    return re.sub(r"\[/?(?:ch|tab)\]", "", text, flags=re.IGNORECASE)


def _parse_ultimate_guitar(text, *, meta=None, provenance=None) -> Song:
    return _parse.parse_chords_over_lyrics(
        _strip_ultimate_guitar(text), meta=meta, provenance=provenance
    )


def _is_chordpro(text: str) -> bool:
    if _DIRECTIVE_RE.search(text):
        return True
    return any(
        _parse.is_chord_token(m.group(1) or m.group(2))
        for m in _INLINE_CHORD_RE.finditer(text)
    )


def _parse_opensong(text, *, meta=None, provenance=None) -> Song:
    lines = []
    for line in text.splitlines():
        if line.startswith(";"):
            continue
        # '.' and ' ' are both one character, so the columns stay aligned.
        lines.append(" " + line[1:] if line.startswith(".") else line)
    text = _OPENSONG_TAG_RE.sub(
        lambda m: f"[{_OPENSONG_TAGS[m.group(1)]} {m.group(2)}]".replace(" ]", "]"),
        "\n".join(lines),
    )
    return _parse.parse_chords_over_lyrics(text, meta=meta, provenance=provenance)


#: Tried in order; the last one accepts anything.
IMPORTERS: tuple[Importer, ...] = (
    Importer(
        "ultimate-guitar", lambda t: bool(_UG_RE.search(t)), _parse_ultimate_guitar
    ),
    Importer("chordpro", _is_chordpro, _chordpro.parse_chordpro),
    Importer(
        "opensong",
        lambda t: bool(_OPENSONG_CHORD_LINE_RE.search(t)),
        _parse_opensong,
    ),
    Importer("chords-over-lyrics", lambda t: True, _parse.parse_chords_over_lyrics),
)


def detect_format(text: str, *, importers: Sequence[Importer] = IMPORTERS) -> str:
    """The name of the first importer that recognises *text*."""
    return _choose(text, importers, "").name


def _choose(text: str, importers: Sequence[Importer], format: str) -> Importer:
    if format:
        for importer in importers:
            if importer.name == format:
                return importer
        raise ValueError(
            f"Unknown format {format!r}; choose from {[i.name for i in importers]}."
        )
    for importer in importers:
        if importer.detect(text):
            return importer
    raise ValueError("No importer recognised the text.")


def paste_key(text: str) -> str:
    """The store key of pasted *text*: ``paste:<hash>`` (the same text, the same key)."""
    digest = hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()
    return f"paste:{digest[:KEY_HASH_CHARS]}"


@dataclass(frozen=True)
class Imported:
    """A parsed paste: the song, its key and the format that read it."""

    key: str
    format: str
    song: Song


def import_song(
    text: str,
    *,
    title: str = "",
    artist: str = "",
    url: str = "",
    key: str = "",
    capo: str = "",
    format: str = "",
    importers: Sequence[Importer] = IMPORTERS,
) -> Imported:
    """Parse pasted *text* with the first importer that recognises it (or *format*).

    ``title``/``artist``/``key``/``capo`` given here win over those in the text.
    A ``url`` on ultimate-guitar.com is checked first (official and Pro pages are
    refused, see :mod:`songleaf.ultimate_guitar`), keys the song ``ug:<id>``
    instead of ``paste:<hash>``, and is noted as ``provenance.site``.
    """
    from songleaf import ultimate_guitar as _ug

    if not text.strip():
        raise ValueError("Nothing to import: the text is empty.")
    if len(text) > MAX_PASTE_CHARS:
        raise ValueError(
            f"The text is too long ({len(text)} > {MAX_PASTE_CHARS} characters)."
        )
    for name, value in (("key", key), ("capo", capo)):
        if len(value) > MAX_META_CHARS:
            raise ValueError(
                f"The {name} is too long (over {MAX_META_CHARS} characters)."
            )
    why = _ug.refusal(url)
    if why:
        raise ValueError(why)
    importer = _choose(text, importers, format)
    provenance = {**PASTE_PROVENANCE, **({"url": url} if url else {})}
    if url and _ug.is_ultimate_guitar_url(url):
        provenance["site"] = "ultimate-guitar"
    song = importer.parse(text, meta=None, provenance=provenance)
    given = (("title", title), ("artist", artist), ("key", key), ("capo", capo))
    song.meta.update({k: v.strip() for k, v in given if v and v.strip()})
    song.meta.setdefault("title", "Pasted song")
    return Imported(_ug.ug_key(url) or paste_key(text), importer.name, song)


def format_names(importers: Mapping | Sequence[Importer] = IMPORTERS) -> list[str]:
    return [i.name for i in importers]
