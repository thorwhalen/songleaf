"""Parse chords-over-lyrics text into a :class:`~songleaf.model.Song`.

This is the format most chord sites use, and the one in the Kaggle corpus: a
line of chord symbols, column-aligned over the lyric line it belongs to.

- Each chord is anchored on the syllable under it (a chord over a space moves
  to the start of the next syllable).
- A chord line with no lyric line under it (an intro, a solo) becomes an empty
  text line carrying its chords in order.
- Section headers (``Verse 1:``, ``[Chorus]``, ``Intro 2x: G D``) become
  section annotations; a header with no lines of its own is a *marker*
  (``{"marker": True}``), usually meaning "play that section again".
- ``Capo``, ``Key``/``Tom`` and ``Tuning`` lines become metadata.
- Tablature and decoration lines (``e|--3--|``, ``=====``) are dropped.

>>> song = parse_chords_over_lyrics("Verse 1:\\nC       G\\nHello there my friend")
>>> song.text
'Hello there my friend'
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(0, 'C'), (8, 'G')]
>>> song.of_kind("section")[0].body["label"]
'Verse 1'
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from songleaf.model import Annotation, Song, chord, section

_CHORD_RE = re.compile(
    r"[*.]{0,3}\(?"  # leading marks: *D, ...Dm6
    r"[A-G][#b]?"  # root
    r"(?:maj|min|dim|aug|sus|add|m|M|\+|°|º|ø)?"  # quality
    r"\d{0,2}[M+\-]?"  # extension: 7, 9, 13; Brazilian 7M, 7+, 5-
    r"(?:sus\d{0,2}|(?:maj|add|dim|aug|no|m|b|#|\+|-)\d{1,2}[+\-]?)*"  # b5, sus, add9
    r"(?:/[#b]?\d{1,2}[+\-#b]?)*"  # stacked extensions: 7/9, 4/7, 5-/7, /b13, 7/9b
    r"(?:\([^()\s]{1,10}\))?"  # parenthesised alterations: (#9), (4/9), (b5)
    r"(?:/[A-G][#b]?)?"  # bass
    r"\)?\*?"
)
# Tokens allowed on a chord line besides chords: bars, repeats, "no chord", stray
# marks, and short notes such as "(riff)" or "(walking bass)".
_FILLER_RE = re.compile(
    r"\|+:?|:?\|+|-+|/+|%|\.+|\*+|[()?]|x|\d{1,2}"
    r"|\(?(?:x\s*\d+|\d+\s*x)\)?|N\.?C\.?|\(\w{1,12}\)?|\w{1,12}\)",
    re.IGNORECASE,
)
_SECTION_WORDS = (
    r"(?:pr[eé]-?|post-?)?"
    r"(?:intro\w*|intr\.|verses?|verso|estrofa|chorus|refr[aã]o|coro|estribillo|bridge|ponte"
    r"|puente|outro|final|solo|interlude|instrumental|refrain|hook|coda|ending|break"
    r"|tag|riff)"
)
_HEADER_PLAIN_RE = re.compile(
    rf"^\s*(?P<label>{_SECTION_WORDS}(?:\s*\d+)?"
    r"(?:\s*\(?\s*(?:x\s*\d+|\d+\s*x)\s*\)?)?"  # repeats: x2, 2x, (x2)
    r"(?:\s*\([^)]{1,20}\))?)"  # a note: (repeat)
    r"\s*(?::\s*(?P<rest>.*))?$",
    re.IGNORECASE,
)
_HEADER_BRACKET_RE = re.compile(
    rf"^\s*\[\s*(?P<label>{_SECTION_WORDS}[^\]]*)\]\s*(?P<rest>.*)$", re.IGNORECASE
)
# "Intro G D Em": a section word followed directly by its chords, no colon.
_HEADER_INLINE_RE = re.compile(
    rf"^\s*(?P<label>{_SECTION_WORDS}(?:\s*\d+)?)\s*[:.]?\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)
_CAPO_RE = re.compile(r"^\s*capo\b\D*(\d+)", re.IGNORECASE)
_NO_CAPO_RE = re.compile(r"^\s*(?:no|sem|sin)\s+capo\b.*$", re.IGNORECASE)
_META_RE = re.compile(
    r"^\s*(?P<field>tuning|afina[cç][aã]o|afinaci[oó]n|key|tom|tono)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE,
)
_META_FIELDS = {"tom": "key", "tono": "key", "key": "key"}
_TAB_RE = re.compile(r"[A-Ga-g]?[#b]?\s*[|:]?[-0-9hpbrvx/\\~|*.()\s]+")
_DECORATION_RE = re.compile(r"[=_\-~*.#^\s]{3,}")


def is_chord_token(token: str) -> bool:
    """True if ``token`` reads as a chord symbol (``G``, ``F#m7b5``, ``E7(#9)``, ``C/G``)."""
    return bool(_CHORD_RE.fullmatch(token))


def is_chord_line(line: str) -> bool:
    """True if every token is a chord or chord-line filler, and at least one is a chord.

    >>> is_chord_line("G   D/F#   Em  (x2)")
    True
    >>> is_chord_line("Bad Dad")
    False
    """
    tokens = line.split()
    return any(is_chord_token(t) for t in tokens) and all(
        is_chord_token(t) or _FILLER_RE.fullmatch(t) for t in tokens
    )


def _is_tab_line(line: str) -> bool:
    stripped = line.strip()
    if _DECORATION_RE.fullmatch(stripped):
        return True
    looks_like_tab = "|" in stripped or any(ch.isdigit() for ch in stripped)
    return (
        stripped.count("-") >= 4
        and looks_like_tab
        and bool(_TAB_RE.fullmatch(stripped))
    )


def _header(line: str) -> tuple[str, str] | None:
    match = _HEADER_BRACKET_RE.match(line) or _HEADER_PLAIN_RE.match(line)
    if not match:
        match = _HEADER_INLINE_RE.match(line)
        if not (match and is_chord_line(match.group("rest"))):
            return None
    label = " ".join(match.group("label").split()).strip(" :")
    rest = (match.group("rest") or "").strip()
    if rest and all(_FILLER_RE.fullmatch(token) for token in rest.split()):
        return f"{label} {rest}", ""  # "Chorus: x2"
    return label, rest


def _kind(line: str) -> str:
    if not line.strip():
        return "blank"
    if _CAPO_RE.match(line) or _NO_CAPO_RE.match(line) or _META_RE.match(line):
        return "meta"
    if _is_tab_line(line):
        return "tab"
    if _header(line):
        return "header"
    if is_chord_line(line):
        return "chords"
    return "lyric"


def _meta_of(line: str) -> dict:
    if capo := _CAPO_RE.match(line):
        return {"capo": int(capo.group(1))}
    if field := _META_RE.match(line):
        name = field.group("field").lower()
        return {_META_FIELDS.get(name, "tuning"): field.group("value").strip()}
    return {}


def _anchored_chords(chord_line: str, lyric_line: str) -> tuple[str, list]:
    """The stripped lyric text, and its chords as ``(offset, symbol)``."""
    indent = len(lyric_line) - len(lyric_line.lstrip())
    text = lyric_line.strip()
    chords = []
    for match in re.finditer(r"\S+", chord_line):
        if not is_chord_token(match.group()):
            continue
        offset = min(max(match.start() - indent, 0), len(text))
        while offset < len(text) and text[offset] == " ":
            offset += 1
        chords.append((offset, match.group()))
    return text, chords


def _bare_chords(line: str) -> list:
    return [(0, token) for token in line.split() if is_chord_token(token)]


def parse_chords_over_lyrics(
    raw: str, *, meta: Mapping | None = None, provenance: Mapping | None = None
) -> Song:
    """Parse chords-over-lyrics text into a :class:`Song`.

    Args:
        raw: The chord chart, chord lines column-aligned over lyric lines.
        meta: Metadata to start from (``title``, ``artist``, ...); ``capo``,
            ``key`` and ``tuning`` found in the text are added to it.
        provenance: Where the text came from, stored as is.
    """
    raw_lines = [line.expandtabs(8).rstrip() for line in re.split(r"\r\n|\r|\n", raw)]
    lines: list[tuple[str, list]] = []  # (text, [(offset, symbol)])
    sections: list[tuple[str, int, bool]] = []  # (label, line index, marker)
    markers: set[int] = set()  # empty lines that carry a marker section
    pending = None  # a header's label, waiting for the first line of its section
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
        # A header with no lines before the next header or the end is a marker
        # ("[Chorus]": play the chorus again), on an empty line of its own.
        nonlocal pending
        if pending is not None:
            sections.append((pending, len(lines), True))
            markers.add(len(lines))
            lines.append(("", []))
            pending = None

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        kind = _kind(line)
        if kind == "blank":
            if pending is None and lines and not is_blank(len(lines) - 1):
                lines.append(("", []))
        elif kind == "meta":
            meta.update(_meta_of(line))
        elif kind == "header":
            close_pending()
            pending, rest = _header(line)
            if rest:
                add(*(("", _bare_chords(rest)) if is_chord_line(rest) else (rest, [])))
        elif kind == "chords":
            if i + 1 < len(raw_lines) and _kind(raw_lines[i + 1]) == "lyric":
                add(*_anchored_chords(line, raw_lines[i + 1]))
                i += 2
                continue
            add("", _bare_chords(line))
        elif kind == "lyric":
            add(line.strip(), [])
        i += 1
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
