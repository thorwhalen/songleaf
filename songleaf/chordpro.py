"""Parse ChordPro text into a :class:`~songleaf.model.Song`.

ChordPro puts chords inline, in square brackets, at the syllable they land on
(``Paper [G]boats [D]drift``), and describes the song with ``{directive: value}``
lines.

- ``[X]`` becomes a ``chord`` annotation at that character offset of the
  bracket-free lyric line; a line of chords only becomes an empty text line
  carrying its chords in order, as in :mod:`songleaf.parse`. Only brackets that
  are not something else are chords: a line of bracketed labels only
  (``[Verse 1]``, ``[---][Chorus]``) starts a section, and a repeat mark (``[x2]``)
  or a rule (``[---]``) elsewhere stays in the text as written.
- ``{title}``, ``{artist}``, ``{key}``, ``{capo}``, ``{tempo}`` (and their short
  forms) become metadata.
- ``{soc}``/``{eoc}`` (and verse, bridge, tab-less variants) and ``{c: label}``
  comments become ``section`` annotations; a section with no lines of its own is
  a *marker* (``{"marker": True}``), as in :mod:`songleaf.parse`.
- ``{x_songleaf_before: 0, 3}`` (written by :func:`songleaf.export.to_chordpro`) marks the
  chords at those positions, counted over the song's chords in text order, as sounding
  *before* their syllable (``timing="before"``): ChordPro has no way to say it.
- ``# comments`` and other unknown directives are dropped.

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
#: The namespaced directive carrying ``timing="before"`` chords; apps that don't know it skip it.
BEFORE_DIRECTIVE = "x_songleaf_before"
_COMMENTS = frozenset({"c", "comment", "ci", "comment_italic", "cb", "comment_box"})


def _meta_value(name: str, value: str):
    if name in _INT_META:
        digits = re.match(r"\d+", value)
        return int(digits.group()) if digits else value
    return value


#: A bracket that is a repeat mark, not a chord: ``[x2]``, ``[2x]``, ``[(x3)]``.
_REPEAT_RE = re.compile(r"\(?\s*(?:x\s*\d+|\d+\s*x)\s*\)?", re.IGNORECASE)
#: A bracket of decoration only: ``[---]``, ``[===]``.
_RULE_RE = re.compile(r"[-=_~.\s]+")


def _is_label(symbol: str) -> bool:
    """Whether a bracket's content is a section label (``Verse 1``), not a chord."""
    from songleaf.parse import _header

    return _header(f"[{symbol}]") is not None


def _is_chord(symbol: str) -> bool:
    """Whether a bracket's content is a chord: anything but a label, a repeat mark or a rule.

    ChordPro chords are free-form (``H7``, ``am``, ``N.C.``, ``*Coda``), so only what is
    plainly something else is not one.
    """
    return not (
        _is_label(symbol) or _REPEAT_RE.fullmatch(symbol) or _RULE_RE.fullmatch(symbol)
    )


def _section_label(raw: str) -> str | None:
    """The label of a line of bracketed labels only (``[---][Verse 1]``), or ``None``.

    >>> _section_label("[---][Verse 1]"), _section_label("[G]la"), _section_label("[x2]")
    ('Verse 1', None, None)
    """
    from songleaf.parse import _header

    if _CHORD_RE.sub("", raw).strip():
        return None
    labels = [m.group(1).strip() for m in _CHORD_RE.finditer(raw)]
    if not any(_is_label(label) for label in labels):
        return None
    if any(_is_chord(label) for label in labels if label):
        return None
    for label in labels:
        header = _header(f"[{label}]")
        if header:
            return header[0]
    return None


def _lyric_line(raw: str) -> tuple[str, list]:
    """A ChordPro line as its lyric text and ``(offset, symbol)`` chords.

    >>> _lyric_line("[G]Sing it [x2]")
    ('Sing it [x2]', [(0, 'G')])
    """
    text, chords, last = "", [], 0
    for match in _CHORD_RE.finditer(raw):
        text += raw[last : match.start()]
        symbol = match.group(1).strip()
        if symbol and not _is_chord(symbol):
            text += match.group(0)  # not a chord: the text as written
        elif symbol:
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
    before: set[int] = set()  # positions among the chords, in text order

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
            elif name == BEFORE_DIRECTIVE:
                before.update(int(n) for n in re.findall(r"\d+", value))
            continue
        if not line.strip():
            if pending is None and lines and not is_blank(len(lines) - 1):
                lines.append(("", []))
            continue
        if (label := _section_label(line)) is not None:
            if pending is None:  # "{soc}" then "[Chorus]": one section, not two
                close_pending()
            pending = label
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

    placed = [
        (starts[index] + at, symbol)
        for index, (_, chords) in enumerate(lines)
        for at, symbol in chords
    ]
    annotations: list[Annotation] = [
        chord(at, symbol, timing="before" if n in before else "at")
        for n, (at, symbol) in enumerate(placed)
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
