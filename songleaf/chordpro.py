"""Parse ChordPro text into a :class:`~songleaf.model.Song`.

ChordPro puts chords inline, in square brackets, at the syllable they land on
(``Paper [G]boats [D]drift``), and describes the song with ``{directive: value}``
lines.

- ``[X]`` becomes a ``chord`` annotation at that character offset of the
  bracket-free lyric line; a line of chords only becomes an empty text line
  carrying its chords in order, as in :mod:`songleaf.parse`.
- ``{title}``, ``{artist}``, ``{key}``, ``{capo}``, ``{tempo}`` (and their short
  forms) become metadata.
- ``{soc}``/``{eoc}`` (and verse, bridge, tab-less variants) and ``{c: label}``
  comments become ``section`` annotations; a section with no lines of its own is
  a *marker* (``{"marker": True}``), as in :mod:`songleaf.parse`.
- ``# comments`` and unknown directives are dropped.

>>> song = parse_chordpro("{title: Paper Boats}\\n{soc}\\nPaper [G]boats [D]drift\\n{eoc}")
>>> song.text
'Paper boats drift'
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(6, 'G'), (12, 'D')]
>>> song.meta["title"], song.of_kind("section")[0].body["label"]
('Paper Boats', 'Chorus')
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from songleaf.model import Annotation, Song, chord, section

_DIRECTIVE_RE = re.compile(
    r"^\s*\{\s*(?P<name>[\w-]+)\s*(?::\s*(?P<value>.*?))?\s*\}\s*$"
)
_CHORD_RE = re.compile(r"\[([^\[\]]*)\]")

_META_NAMES = {
    "title": "title",
    "t": "title",
    "artist": "artist",
    "key": "key",
    "capo": "capo",
    "tempo": "tempo",
}
_INT_META = frozenset({"capo", "tempo"})

#: ``start_of_*`` environments: short and long name -> default label.
_ENVIRONMENTS = {
    "soc": "Chorus",
    "start_of_chorus": "Chorus",
    "sov": "Verse",
    "start_of_verse": "Verse",
    "sob": "Bridge",
    "start_of_bridge": "Bridge",
}
_END_ENVIRONMENTS = frozenset(
    {"eoc", "end_of_chorus", "eov", "end_of_verse", "eob", "end_of_bridge"}
)
_COMMENTS = frozenset({"c", "comment", "ci", "comment_italic", "cb", "comment_box"})


def _meta_value(name: str, value: str):
    if name in _INT_META:
        digits = re.match(r"\d+", value)
        return int(digits.group()) if digits else value
    return value


def _lyric_line(raw: str) -> tuple[str, list]:
    """A ChordPro line as its lyric text and ``(offset, symbol)`` chords."""
    text, chords, last = "", [], 0
    for match in _CHORD_RE.finditer(raw):
        text += raw[last : match.start()]
        if symbol := match.group(1).strip():
            chords.append((len(text), symbol))
        last = match.end()
    text += raw[last:]
    shift = len(text) - len(text.lstrip())
    return text.strip(), [(max(at - shift, 0), symbol) for at, symbol in chords]


def parse_chordpro(
    raw: str, *, meta: Mapping | None = None, provenance: Mapping | None = None
) -> Song:
    """Parse ChordPro text into a :class:`Song`.

    Args:
        raw: The ChordPro text.
        meta: Metadata to start from; directives in the text override it.
        provenance: Where the text came from, stored as is.
    """
    lines: list[tuple[str, list]] = []  # (text, [(offset, symbol)])
    sections: list[tuple[str, int, bool]] = []  # (label, line index, marker)
    markers: set[int] = set()
    pending = None  # a section label, waiting for the first line of its content
    meta = dict(meta or {})

    def is_blank(index):
        text, chords = lines[index]
        return not text and not chords and index not in markers

    def add(text, chords):
        nonlocal pending
        if pending is not None:
            sections.append((pending, len(lines), False))
            pending = None
        lines.append((text, chords))

    def close_pending():
        nonlocal pending
        if pending is not None:
            sections.append((pending, len(lines), True))
            markers.add(len(lines))
            lines.append(("", []))
            pending = None

    for line in re.split(r"\r\n|\r|\n", raw):
        line = line.expandtabs(8).rstrip()
        if line.lstrip().startswith("#"):
            continue
        if directive := _DIRECTIVE_RE.match(line):
            name = directive.group("name").lower().replace("-", "_")
            value = (directive.group("value") or "").strip()
            if name in _META_NAMES:
                if value:
                    key = _META_NAMES[name]
                    meta[key] = _meta_value(key, value)
            elif name in _ENVIRONMENTS or name in _COMMENTS:
                if name in _ENVIRONMENTS or value:
                    close_pending()
                    pending = value or _ENVIRONMENTS[name]
            elif name in _END_ENVIRONMENTS:
                close_pending()
            continue
        if not line.strip():
            if pending is None and lines and not is_blank(len(lines) - 1):
                lines.append(("", []))
            continue
        add(*_lyric_line(line))
    close_pending()

    while lines and is_blank(len(lines) - 1):
        lines.pop()

    starts, offset = [], 0
    for text, _ in lines:
        starts.append(offset)
        offset += len(text) + 1
    text = "\n".join(text for text, _ in lines)

    annotations: list[Annotation] = [
        chord(starts[index] + at, symbol)
        for index, (_, chords) in enumerate(lines)
        for at, symbol in chords
    ]
    for k, (label, index, marker) in enumerate(sections):
        start = starts[index]
        if marker:
            annotations.append(
                Annotation("section", start, start, {"label": label, "marker": True})
            )
            continue
        last = (sections[k + 1][1] if k + 1 < len(sections) else len(lines)) - 1
        while last > index and is_blank(last):
            last -= 1
        annotations.append(section(start, starts[last] + len(lines[last][0]), label))
    return Song(text, annotations, meta=meta, provenance=dict(provenance or {}))
