"""Render a song onto one dense page, with the lyrics as large as will fit.

A :class:`SheetLayout` is one way of laying a song out: where the chords go
(``chords``), which lines share a row (``packing``), how many ``columns``, and
whether sections, repeated lines and chord functions are ``shading``-ed.
:func:`render_sheet` draws any layout, and :func:`render_dense_a4` is the v1
layout. A layout can be named by a spec that joins the options of
:data:`LAYOUT_OPTIONS` with ``+`` (:func:`layout_named`), and
:func:`make_renderer` turns a spec into the ``(song, output) -> dict`` function
that the ``renderer=`` seam of :func:`songleaf.tools.sheet` takes.

Every layout finds the largest lyric font size at which the whole song fits on
one page (:func:`fit_font_size`), then draws it:

- consecutive lines of a paragraph share a row, separated by a light ``/``: as
  many as fit (``packing="greedy"``), or breaking where the lyrics break
  (``"structured"``: between couplets and quatrains, not inside a rhyming pair
  or a repeat; see :mod:`songleaf.packing`). A blank line or a new section
  starts a new row, and a line too long for its column wraps at a space (inside
  a word only when a single word is wider than the column);
- ``chords="over"``: chords ride on their lyric row, smaller and in a lighter
  colour, overlapping the letters instead of taking a line of their own. A chord
  starts over the syllable it lands on, and a ``timing="before"`` chord ends
  there. ``DenseStyle.chord_rise`` sets how deep they overlap: the tops of the
  letters by default, the words themselves with the ``overlap`` option;
- ``chords="inline"``: chords sit in the lyric line itself, in a lighter colour,
  right before the syllable they land on. A chord that sounds before its
  syllable is preceded by a small marker (``DenseStyle.before_marker``);
- ``columns=2``: the rows flow down two columns, under a full-width heading;
- ``shading``: chorus-like sections get a light warm band and pre-chorus or
  bridge sections a light cool one, lines sung earlier in the song are set in
  dark grey, and chords are coloured by their function in the key estimated
  from the chords (:mod:`songleaf.harmony`): the tonic darker, the key's other
  chords in the usual blue, chords outside the key in a warm accent;
- section labels are small grey prefixes (``V1``, ``Ch``) on a section's first row;
- only a song that cannot fit at ``min_font_size`` spills onto more pages.

Text is set in reportlab's built-in Helvetica, which covers Latin-1.

>>> short_label("Verse 1"), short_label("Pre-Chorus"), short_label("Coda")
('V1', 'Pre', 'Coda')
>>> layout = layout_named("inline+two-column")
>>> layout.chords, layout.columns, layout.packing
('inline', 2, 'greedy')
"""

from __future__ import annotations

import inspect
import itertools
import math
import os
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache, partial
from typing import Protocol

from songleaf.harmony import chord_function, estimate_key
from songleaf.model import Song
from songleaf.packing import line_break_costs, pack_greedy, pack_structured

#: Page margin in points (5 mm), about the least a printer leaves blank anyway.
DFLT_MARGIN = 14.0
_EPSILON = 1e-6
_MAX_LABEL_CHARS = 16
#: After the bisection, sizes up to this many points larger are tried as well,
#: since packing lines into rows makes "fits" not quite monotonic in the size.
_PROBE_SPAN = 1.0
_PROBE_STEP = 0.1
_VOWELS = "aeiouy"


@dataclass(frozen=True)
class DenseStyle:
    """Typography of the dense layouts. Lengths are fractions of the lyric font size."""

    lyric_font: str = "Helvetica"
    chord_font: str = "Helvetica-Bold"
    label_font: str = "Helvetica-Bold"
    title_font: str = "Helvetica-Bold"
    lyric_color: str = "#000000"
    chord_color: str = "#3b73c4"
    label_color: str = "#8c8c8c"
    separator_color: str = "#a6a6a6"
    title_color: str = "#595959"
    chord_scale: float = 0.62  # chord size / lyric size
    label_scale: float = 0.5
    title_scale: float = 0.6
    chord_rise: float = 0.56  # chord baseline above the lyric baseline
    chord_halo: str = ""  # outline colour: chords then draw over the lyrics
    chord_halo_width: float = 0.16  # in chord sizes
    ascent: float = 0.72  # height of capitals above the baseline, per unit of font size
    descent: float = 0.21
    row_gap: float = 0.06
    paragraph_gap: float = 0.3
    separator: str = " / "
    chord_gap: float = 0.3  # least space between chords on a lyric row, in chord sizes
    bare_chord_gap: float = (
        0.9  # space between the chords of a chord-only line, in chord sizes
    )
    label_gap: float = 0.4  # space after a section label, in label sizes
    # chords="inline"
    inline_chord_scale: float = 0.7
    inline_chord_rise: float = 0.2  # keeps the chord's top at the lyric's cap height
    inline_chord_pad: float = 0.15  # space around an inline chord, in chord sizes
    before_marker: str = "‹"  # precedes an inline chord that sounds before its syllable
    # columns > 1
    column_gap: float = 0.8
    column_rule_color: str = "#d9d9d9"  # "" for no rule between columns
    # shading
    chorus_shade: str = "#f3efe4"
    bridge_shade: str = "#e8eef6"
    band_pad: float = 0.12  # how far a section band reaches past its column's sides
    repeat_color: str = "#4d4d4d"
    tonic_chord_color: str = "#1c4a91"
    outside_chord_color: str = "#c0602a"


_LABEL_ABBREVIATIONS = {
    "verse": "V",
    "chorus": "Ch",
    "pre-chorus": "Pre",
    "prechorus": "Pre",
    "post-chorus": "Post",
    "bridge": "Br",
    "outro": "Out",
    "instrumental": "Inst",
    "interlude": "Int",
    "refrain": "Ref",
}
_BRIDGE_RE = re.compile(r"\b(?:pr[eé]|bridge|ponte|puente)", re.IGNORECASE)
_CHORUS_RE = re.compile(
    r"\b(?:chorus|refr[aã]o|refrain|coro|estribillo|hook)", re.IGNORECASE
)


def short_label(label: str) -> str:
    """A compact section label: ``"Verse 1"`` -> ``"V1"``, ``"Chorus x2"`` -> ``"Ch x2"``."""
    match = re.match(r"\s*([^\W\d_][\w-]*)(.*)", label)
    if not match:
        short = label.strip()
    else:
        word, rest = match.group(1), match.group(2).strip(" :-")
        abbreviation = _LABEL_ABBREVIATIONS.get(word.lower(), word)
        short = (
            f"{abbreviation}{rest}"
            if rest.isdigit()
            else f"{abbreviation} {rest}".strip()
        )
    if len(short) > _MAX_LABEL_CHARS:
        short = short[: _MAX_LABEL_CHARS - 1].rstrip() + "…"
    return short


def section_family(label: str) -> str:
    """``"chorus"`` for a chorus or refrain, ``"bridge"`` for a pre-chorus or bridge, else ``""``.

    >>> section_family("Pre-Chorus"), section_family("Refrão 2"), section_family("Verse")
    ('bridge', 'chorus', '')
    """
    if _BRIDGE_RE.search(label):
        return "bridge"
    return "chorus" if _CHORUS_RE.search(label) else ""


@lru_cache(maxsize=65536)
def _width(text: str, font: str) -> float:
    """Width of ``text`` at font size 1 (widths scale linearly with the size)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, font, 1)


@lru_cache(maxsize=4096)
def _prefix_widths(text: str, font: str) -> tuple:
    """``widths[i]`` is the width of ``text[:i]`` at font size 1 (the fonts have no kerning)."""
    widths = [0.0]
    for character in text:
        widths.append(widths[-1] + _width(character, font))
    return tuple(widths)


@dataclass
class _Piece:
    """A run of lyrics with its chords: a line of the song, or part of a wrapped one."""

    text: str
    chords: list = field(default_factory=list)  # (offset in text, symbol, timing)
    label: str = ""
    new_paragraph: bool = False
    line: int = 0  # the song line it comes from: the parts of a wrapped line share it
    section: str = ""  # the label of the section it is in
    repeat: bool = False  # the same words were on an earlier line of the song


@dataclass(frozen=True)
class _Item:
    layer: int  # drawing order: chords first, lyrics on top (haloed chords last)
    x: float
    rise: float  # above the row's baseline
    text: str
    font: str
    size: float
    color: str
    halo: str = ""  # outline colour, drawn under the text


@dataclass
class _Row:
    items: list
    top: float  # extent above the baseline
    bottom: float  # extent below the baseline
    gap_before: float = 0.0
    shade: str = ""  # background colour of the row's band, if any


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def _pieces(song: Song) -> list[_Piece]:
    chords, sections = song.of_kind("chord"), song.of_kind("section")
    pieces, new_paragraph, c, s = [], True, 0, 0
    current, sung = None, set()
    for index, line in enumerate(song.lines()):
        line_chords = []
        while c < len(chords) and chords[c].start <= line.end:
            body = chords[c].body
            line_chords.append(
                (
                    chords[c].start - line.start,
                    body.get("symbol", ""),
                    body.get("timing", "at"),
                )
            )
            c += 1
        labels = []
        while s < len(sections) and sections[s].start <= line.end:
            labels.append(short_label(sections[s].body.get("label", "")))
            current = sections[s]
            s += 1
        label = " ".join(filter(None, labels))
        if not (line.text or line_chords or label):
            new_paragraph = True
            continue
        in_section = current is not None and current.start <= line.start <= current.end
        words = _words(line.text)
        pieces.append(
            _Piece(
                line.text,
                line_chords,
                label,
                new_paragraph or bool(label),
                line=index,
                section=current.body.get("label", "") if in_section else "",
                repeat=bool(words) and words in sung,
            )
        )
        sung.add(words)
        new_paragraph = False
    return pieces


def _heading(song: Song) -> str:
    extras = []
    if song.meta.get("capo"):
        extras.append(f"capo {song.meta['capo']}")
    if song.meta.get("key"):
        extras.append(f"key {song.meta['key']}")
    names = " — ".join(filter(None, (song.title, song.artist)))
    return " · ".join(filter(None, [names, *extras]))


@dataclass(frozen=True)
class _Paint:
    """The colours of a song's lyrics, chords and row bands, with or without shading."""

    style: DenseStyle
    shading: bool = False
    chord_colors: Mapping = field(default_factory=dict)  # symbol -> colour

    def chord(self, symbol: str) -> str:
        return self.chord_colors.get(symbol, self.style.chord_color)

    def lyric(self, piece: _Piece) -> str:
        if self.shading and piece.repeat:
            return self.style.repeat_color
        return self.style.lyric_color

    def shade(self, piece: _Piece) -> str:
        if not self.shading:
            return ""
        family = section_family(piece.section)
        return {
            "chorus": self.style.chorus_shade,
            "bridge": self.style.bridge_shade,
        }.get(family, "")


def _paint(song: Song, style: DenseStyle, shading: bool) -> _Paint:
    if not shading:
        return _Paint(style)
    symbols = [a.body.get("symbol", "") for a in song.of_kind("chord")]
    key = estimate_key(symbols)
    if key is None:  # no chord to read a key from
        return _Paint(style, shading=True)
    colors = {
        "tonic": style.tonic_chord_color,
        "outside": style.outside_chord_color,
    }
    chord_colors = {
        symbol: colors.get(chord_function(symbol, key), style.chord_color)
        for symbol in set(symbols)
    }
    return _Paint(style, shading=True, chord_colors=chord_colors)


def _label_width(piece: _Piece, size: float, style: DenseStyle) -> float:
    if not piece.label:
        return 0.0
    label_size = size * style.label_scale
    return (_width(piece.label, style.label_font) + style.label_gap) * label_size


def _chord_positions(piece: _Piece, size: float, style: DenseStyle):
    """The chords' x positions relative to the piece's text, and the piece's extent."""
    chord_size = size * style.chord_scale
    gap = (style.chord_gap if piece.text else style.bare_chord_gap) * chord_size
    prefix = _prefix_widths(piece.text, style.lyric_font)
    placed, free, extent = [], 0.0, prefix[-1] * size
    for offset, symbol, timing in piece.chords:
        chord_width = _width(symbol, style.chord_font) * chord_size
        x = free
        if piece.text:
            x = prefix[min(offset, len(piece.text))] * size
            if timing == "before":
                x -= chord_width + gap
        x = max(x, free)
        placed.append((x, symbol))
        free = x + chord_width + gap
        extent = max(extent, x + chord_width)
    return placed, extent


def _fitting_length(text: str, font: str, limit: float) -> int:
    """How many leading characters of ``text`` fit within ``limit`` (at font size 1).

    Stops at the first character past the limit, so the cost is one row, not
    the whole text: a very long line wraps in time proportional to its length.
    """
    total = 0.0
    for index, character in enumerate(text):
        total += _width(character, font)
        if total > limit + _EPSILON:
            return index
    return len(text)


class ChordPlacement(Protocol):
    """Where a piece's chords go relative to its lyrics: the strategy behind ``SheetLayout.chords``."""

    def extent(self, piece: _Piece, size: float, style: DenseStyle) -> float:
        """The width the piece takes, chords included (its label excluded)."""

    def fitting_length(
        self, piece: _Piece, available: float, size: float, style: DenseStyle
    ) -> int:
        """How many leading characters of the piece's text fit in ``available``."""

    def items(
        self, piece: _Piece, x: float, size: float, style: DenseStyle, paint: _Paint
    ) -> list[_Item]:
        """What to draw for the piece, starting at ``x``."""


@dataclass(frozen=True)
class OverChords:
    """Chords above their syllables, smaller and lighter, overlapping the lyric row by ``chord_rise``."""

    def extent(self, piece, size, style):
        return _chord_positions(piece, size, style)[1]

    def fitting_length(self, piece, available, size, style):
        return _fitting_length(piece.text, style.lyric_font, available / size)

    def items(self, piece, x, size, style, paint):
        chord_size = size * style.chord_scale
        placed, _ = _chord_positions(piece, size, style)
        rise = style.chord_rise * size if piece.text else 0.0
        layer = 3 if style.chord_halo else 0
        items = [
            _Item(
                layer,
                x + cx,
                rise,
                symbol,
                style.chord_font,
                chord_size,
                paint.chord(symbol),
                style.chord_halo,
            )
            for cx, symbol in placed
        ]
        if piece.text:
            items.append(
                _Item(2, x, 0.0, piece.text, style.lyric_font, size, paint.lyric(piece))
            )
        return items


def _inline_label(symbol: str, timing: str, style: DenseStyle) -> str:
    return style.before_marker + symbol if timing == "before" else symbol


def _is_vowel(character: str) -> bool:
    return unicodedata.normalize("NFKD", character)[:1].lower() in _VOWELS


def _syllable_start(text: str, offset: int) -> int:
    """Where a chord that lands inside a word shows in an inline weave.

    At the word's start if it lands in the word's first half; otherwise at the
    start of its syllable (the last consonant before a vowel, at or before the
    offset), or the word's start if there is none. Charts align chords by
    column, often a letter or two off, and a word cut at a random letter reads
    badly.

    >>> [_syllable_start(t, o) for t, o in [("silver", 2), ("lighter", 5), ("rolls", 3), ("a b", 2)]]
    [0, 4, 0, 2]
    """
    if not 0 < offset < len(text) or not (
        text[offset].isalpha() and text[offset - 1].isalpha()
    ):
        return offset
    start, end = offset, offset
    while start and text[start - 1].isalpha():
        start -= 1
    while end < len(text) and text[end].isalpha():
        end += 1
    if offset - start <= (end - start) / 2:
        return start
    for j in range(offset, start, -1):
        if not _is_vowel(text[j]) and j + 1 < end and _is_vowel(text[j + 1]):
            return j
    return start


def _inline_chords(text: str, chords: list, snap: bool) -> list:
    clipped = [
        (min(offset, len(text)), symbol, timing) for offset, symbol, timing in chords
    ]
    if not snap:
        return clipped
    snapped = [(_syllable_start(text, o), s, t) for o, s, t in clipped]
    return sorted(
        snapped, key=lambda chord: chord[0]
    )  # stable: same-offset chords keep order


def _inline_positions(piece: _Piece, size: float, style: DenseStyle, snap: bool = True):
    """The lyric segments ``(x, text)``, chords ``(x, label, symbol)`` and extent of an inline piece."""
    text, font = piece.text, style.chord_font
    chord_size = size * style.inline_chord_scale
    pad = style.inline_chord_pad * chord_size
    prefix = _prefix_widths(text, style.lyric_font)
    segments, placed, shift, start = [], [], 0.0, 0
    for offset, symbol, timing in _inline_chords(text, piece.chords, snap):
        if offset > start:
            segments.append((prefix[start] * size + shift, text[start:offset]))
            start = offset
        if offset and text[offset - 1] != " ":
            shift += pad  # a chord inside a word: space it from the letters before
        label = _inline_label(symbol, timing, style)
        placed.append((prefix[offset] * size + shift, label, symbol))
        shift += _width(label, font) * chord_size + pad
    if start < len(text):
        segments.append((prefix[start] * size + shift, text[start:]))
    return segments, placed, prefix[-1] * size + shift


@dataclass(frozen=True, kw_only=True)
class InlineChords:
    """Chords in the lyric line, right before their syllable; a chord-only line is a row of chords.

    Args:
        snap_to_syllables: Show a chord that lands inside a word at the word's
            or the syllable's start (see :func:`_syllable_start`); the song's
            annotations are not changed.
    """

    snap_to_syllables: bool = True
    _bare = OverChords()  # not a field: how a line of bare chords is set

    def extent(self, piece, size, style):
        if not piece.text:
            return self._bare.extent(piece, size, style)
        return _inline_positions(piece, size, style, self.snap_to_syllables)[2]

    def fitting_length(self, piece, available, size, style):
        text, font = piece.text, style.lyric_font
        chord_size = size * style.inline_chord_scale
        pad = style.inline_chord_pad * chord_size
        chords, total = (
            iter(_inline_chords(text, piece.chords, self.snap_to_syllables)),
            0.0,
        )
        pending = next(chords, None)
        for index, character in enumerate(text):
            while pending is not None and pending[0] <= index:
                _, symbol, timing = pending
                if index and text[index - 1] != " ":
                    total += pad
                label = _inline_label(symbol, timing, style)
                total += _width(label, style.chord_font) * chord_size + pad
                pending = next(chords, None)
            total += _width(character, font) * size
            if total > available + _EPSILON:
                return index
        return len(text)

    def items(self, piece, x, size, style, paint):
        if not piece.text:
            return self._bare.items(piece, x, size, style, paint)
        segments, placed, _ = _inline_positions(
            piece, size, style, self.snap_to_syllables
        )
        chord_size, rise = (
            size * style.inline_chord_scale,
            style.inline_chord_rise * size,
        )
        items = [
            _Item(
                1,
                x + cx,
                rise,
                label,
                style.chord_font,
                chord_size,
                paint.chord(symbol),
            )
            for cx, label, symbol in placed
        ]
        color = paint.lyric(piece)
        items += [
            _Item(2, x + sx, 0.0, segment, style.lyric_font, size, color)
            for sx, segment in segments
        ]
        return items


#: The chord placements a :class:`SheetLayout` can name.
CHORD_PLACEMENTS: dict[str, ChordPlacement] = {
    "over": OverChords(),
    "inline": InlineChords(),
}
#: The line packers a :class:`SheetLayout` can name (see :mod:`songleaf.packing`).
PACKERS: dict[str, Callable] = {
    "greedy": pack_greedy,
    "structured": pack_structured,
}
_OVER = CHORD_PLACEMENTS["over"]


def _split_at(piece: _Piece, cut: int) -> tuple[_Piece, _Piece]:
    text = piece.text
    tail_start = len(text) - len(text[cut:].lstrip())
    head_text = text[:cut].rstrip()
    head_chords = [
        (min(o, len(head_text)), s, t) for o, s, t in piece.chords if o < tail_start
    ]
    tail_chords = [
        (o - tail_start, s, t) for o, s, t in piece.chords if o >= tail_start
    ]
    head = replace(piece, text=head_text, chords=head_chords)
    tail = replace(
        piece, text=text[tail_start:], chords=tail_chords, label="", new_paragraph=False
    )
    return head, tail


def _split_text(
    piece: _Piece,
    available: float,
    size: float,
    style: DenseStyle,
    chords: ChordPlacement = _OVER,
):
    """Split off the longest head that fits in ``available``; None if no split is needed or possible."""
    text = piece.text
    fitting = chords.fitting_length(piece, available, size, style)
    if fitting == len(text) and chords.extent(piece, size, style) <= available:
        return None
    # Break at the latest space that fits, stepping back while a chord
    # overhanging the head's end would still break the fit.
    for cut in range(min(fitting, len(text) - 1), 0, -1):
        if text[cut] == " " and text[cut - 1] != " ":
            head, tail = _split_at(piece, cut)
            if tail.text and chords.extent(head, size, style) <= available:
                return head, tail
    if fitting == len(text) or len(text) < 2:
        # The words fit but the chords run past them (a chart's chord line is
        # often longer than its lyric): the chords that do not fit go on a
        # chord-only row after the words.
        return _split_overhanging_chords(piece, available, size, style, chords)
    # No break at a space fits: break inside the word, as late as fits.
    return _split_at(piece, max(fitting, 1))


def _split_overhanging_chords(
    piece: _Piece,
    available: float,
    size: float,
    style: DenseStyle,
    chords: ChordPlacement = _OVER,
):
    """The piece with the chords that fit in ``available``, and a chord-only piece of the rest; None if none can move."""
    for k in range(len(piece.chords) - 1, -1, -1):
        head = replace(piece, chords=piece.chords[:k])
        if chords.extent(head, size, style) <= available:
            rest = [(0, symbol, timing) for _, symbol, timing in piece.chords[k:]]
            tail = replace(piece, text="", chords=rest, label="", new_paragraph=False)
            return head, tail
    return None


def _split_chords(
    piece: _Piece,
    available: float,
    size: float,
    style: DenseStyle,
    chords: ChordPlacement = _OVER,
):
    """Split a chord-only piece so its head fits in ``available``; None if it fits or can't split."""
    if len(piece.chords) < 2 or chords.extent(piece, size, style) <= available:
        return None
    for k in range(len(piece.chords) - 1, 0, -1):
        head = replace(piece, chords=piece.chords[:k])
        if k == 1 or chords.extent(head, size, style) <= available:
            tail = replace(
                piece, chords=piece.chords[k:], label="", new_paragraph=False
            )
            return head, tail


def _wrap(
    piece: _Piece,
    size: float,
    width: float,
    style: DenseStyle,
    chords: ChordPlacement = _OVER,
) -> list[_Piece]:
    parts = []
    while True:
        split_piece = _split_text if piece.text else _split_chords
        available = width - _label_width(piece, size, style)
        split = split_piece(piece, available, size, style, chords)
        if split is None:  # it fits, or it cannot be split any further
            parts.append(piece)
            return parts
        head, piece = split
        if head.text and head.chords and chords.extent(head, size, style) > available:
            # A word broken inside can leave the head ending in chords that do not fit.
            overhang = _split_overhanging_chords(head, available, size, style, chords)
            if overhang:
                parts.extend(overhang)
                continue
        parts.append(head)


def _row(
    pieces: list[_Piece],
    size: float,
    style: DenseStyle,
    gap_before: float,
    *,
    chords: ChordPlacement = _OVER,
    paint: _Paint | None = None,
) -> _Row:
    paint = paint or _Paint(style)
    chord_size, label_size = size * style.chord_scale, size * style.label_scale
    has_text = any(piece.text for piece in pieces)
    items, x = [], 0.0
    for k, piece in enumerate(pieces):
        if k:
            sep_size = size if has_text else chord_size
            items.append(
                _Item(
                    1,
                    x,
                    0.0,
                    style.separator,
                    style.lyric_font,
                    sep_size,
                    style.separator_color,
                )
            )
            x += _width(style.separator, style.lyric_font) * sep_size
        if piece.label:
            items.append(
                _Item(
                    1,
                    x,
                    0.0,
                    piece.label,
                    style.label_font,
                    label_size,
                    style.label_color,
                )
            )
            x += _label_width(piece, size, style)
        items += chords.items(piece, x, size, style, paint)
        x += chords.extent(piece, size, style)
    top = max((style.ascent * item.size + item.rise for item in items), default=0.0)
    bottom = style.descent * (size if has_text else max(item.size for item in items))
    rows_items = sorted(items, key=lambda item: item.layer)
    return _Row(rows_items, top, bottom, gap_before, paint.shade(pieces[0]))


def _heading_row(heading: str, size: float, width: float, style: DenseStyle) -> _Row:
    heading_size = min(
        size * style.title_scale, width / _width(heading, style.title_font)
    )
    item = _Item(
        1, 0.0, 0.0, heading, style.title_font, heading_size, style.title_color
    )
    return _Row([item], style.ascent * heading_size, style.descent * heading_size)


def _runs(parts: Iterable[_Piece]):
    """Maximal stretches of parts that may share rows: one paragraph, all lyrics or all chords."""
    run = []
    for part in parts:
        if run and (part.new_paragraph or bool(part.text) != bool(run[-1].text)):
            yield run
            run = []
        run.append(part)
    if run:
        yield run


def _break_costs(run: list[_Piece]) -> list[float]:
    """The cost of a row break after each part of a run: free inside a wrapped line."""
    if not run[0].text:
        return [0.0] * (len(run) - 1)
    texts, index_of_line = [], {}
    for part in run:
        if part.line in index_of_line:  # the whole line: it rhymes and repeats as one
            texts[index_of_line[part.line]] += " " + part.text
        else:
            index_of_line[part.line] = len(texts)
            texts.append(part.text)
    line_costs = line_break_costs(texts)
    return [
        0.0 if before.line == after.line else line_costs[index_of_line[before.line]]
        for before, after in zip(run, run[1:])
    ]


def _layout(
    pieces: list[_Piece],
    size: float,
    width: float,
    style: DenseStyle,
    heading: str = "",
    *,
    chords: ChordPlacement = _OVER,
    packer: Callable = pack_greedy,
    paint: _Paint | None = None,
) -> list[_Row]:
    paint = paint or _Paint(style)
    rows = [_heading_row(heading, size, width, style)] if heading else []
    parts = (
        part for whole in pieces for part in _wrap(whole, size, width, style, chords)
    )
    for run in _runs(parts):
        widths = [
            _label_width(part, size, style) + chords.extent(part, size, style)
            for part in run
        ]
        sep_size = size if run[0].text else size * style.chord_scale
        separator = _width(style.separator, style.lyric_font) * sep_size
        packing = packer(
            widths, width=width, separator=separator, break_costs=_break_costs(run)
        )
        for start, stop in packing:
            new = start == 0 and run[0].new_paragraph
            gap = style.paragraph_gap * size if rows and new else 0.0
            rows.append(
                _row(run[start:stop], size, style, gap, chords=chords, paint=paint)
            )
    return rows


def _height(rows: list[_Row], size: float, style: DenseStyle) -> float:
    gaps = style.row_gap * size * max(len(rows) - 1, 0)
    return sum(row.gap_before + row.top + row.bottom for row in rows) + gaps


def _page_dimensions(page_size) -> tuple[float, float]:
    if isinstance(page_size, str):
        from reportlab.lib import pagesizes

        dimensions = getattr(pagesizes, page_size.upper(), None)
        if not isinstance(dimensions, tuple):
            raise ValueError(
                f"Unknown page size {page_size!r}: use a name such as 'A4' or "
                "'LETTER', or (width, height) in points"
            )
        return dimensions
    width, height = page_size
    return float(width), float(height)


@dataclass(frozen=True)
class SheetLayout:
    """One way to lay a song out on a page.

    Args:
        chords: Where chords go: ``"over"`` (overlapping the lyric row) or
            ``"inline"`` (in the line, before their syllable), or any
            :class:`ChordPlacement`.
        packing: Which lines share a row: ``"greedy"`` or ``"structured"``, or
            any packer with the signature of :func:`songleaf.packing.pack_greedy`.
        columns: Columns per page.
        shading: Shade sections, repeated lines and chord functions.
        style: Typography and colours.
    """

    chords: str | ChordPlacement = "over"
    packing: str | Callable = "greedy"
    columns: int = 1
    shading: bool = False
    style: DenseStyle = field(default_factory=DenseStyle)

    def __post_init__(self):  # a bad layout fails here, not mid-render
        columns = self.columns
        if isinstance(columns, bool) or not isinstance(columns, int) or columns < 1:
            raise ValueError(f"columns must be a positive integer, got {columns!r}")
        if not isinstance(self.shading, bool):
            raise ValueError(f"shading must be True or False, got {self.shading!r}")
        methods = ("extent", "fitting_length", "items")
        if not all(callable(getattr(self.placement, name, None)) for name in methods):
            raise ValueError(
                f"chords must be one of {sorted(CHORD_PLACEMENTS)} or a "
                f"ChordPlacement, got {self.chords!r}"
            )
        if not callable(self.packer):
            raise ValueError(
                f"packing must be one of {sorted(PACKERS)} or a packer function, "
                f"got {self.packing!r}"
            )

    @property
    def placement(self) -> ChordPlacement:
        """The chord placement strategy."""
        return _named(self.chords, CHORD_PLACEMENTS, "chord placement")

    @property
    def packer(self) -> Callable:
        """The line packer."""
        return _named(self.packing, PACKERS, "packing")


def _named(value, registry: Mapping, what: str):
    if not isinstance(value, str):
        return value
    try:
        return registry[value]
    except KeyError:
        raise ValueError(
            f"Unknown {what} {value!r}: use one of {sorted(registry)}"
        ) from None


#: Chords lowered onto the words, outlined in white and drawn over them: the ``overlap`` option's style.
_OVERLAP_STYLE = {"chord_rise": 0.42, "chord_halo": "#ffffff"}
#: What each option of a layout spec changes, from the v1 layout (``dense``).
LAYOUT_OPTIONS: dict[str, dict] = {
    "dense": {},
    "overlap": {"chords": "over", "style": _OVERLAP_STYLE},
    "inline": {"chords": "inline"},
    "packed": {"packing": "structured"},
    "two-column": {"columns": 2},
    "shaded": {"shading": True},
}
_OPTION_ALIASES = {
    "2col": "two-column",
    "two_column": "two-column",
    "structured": "packed",
}


def _spec_options(spec: str) -> list[str]:
    """The options of a spec, in order: aliases resolved, ``dense`` and earlier repeats dropped."""
    options = []
    for token in filter(None, re.split(r"[+,\s]+", spec.strip().lower())):
        name = _OPTION_ALIASES.get(token, token)
        if name not in LAYOUT_OPTIONS:
            raise ValueError(
                f"Unknown layout option {token!r}: join options from "
                f"{', '.join(LAYOUT_OPTIONS)} with '+', as in 'inline+two-column'"
            )
        if name in options:
            options.remove(name)  # the last mention decides, as in layout_named
        if name != "dense":
            options.append(name)
    return options


def layout_spec(spec: str) -> str:
    """The one spelling of a layout spec, for names: ``"Dense"`` -> ``"dense"``.

    >>> layout_spec("2col + INLINE"), layout_spec("dense+"), layout_spec("inline+2col+inline")
    ('two-column+inline', 'dense', 'two-column+inline')
    """
    return "+".join(_spec_options(spec)) or "dense"


def layout_named(spec: str, *, style: DenseStyle | None = None) -> SheetLayout:
    """The layout of a spec: options of :data:`LAYOUT_OPTIONS` joined by ``+`` (``"inline+two-column"``).

    Options apply in order, over the v1 layout and ``style`` (default
    :class:`DenseStyle`).
    """
    changes, style_changes = {}, {}
    for option_name in _spec_options(spec):
        for name, value in LAYOUT_OPTIONS[option_name].items():
            if name == "style":
                style_changes.update(value)
            else:
                changes[name] = value
    return SheetLayout(**changes, style=replace(style or DenseStyle(), **style_changes))


def _as_layout(layout, style: DenseStyle | None) -> SheetLayout:
    if layout is None:
        layout = SheetLayout()
    elif isinstance(layout, str):
        layout = layout_named(layout)
    return layout if style is None else replace(layout, style=style)


@dataclass
class _Flow:
    """A song laid out at one font size, its rows flowed into frames (the columns of the pages)."""

    heading: _Row | None  # a full-width heading above the columns, if any
    frames: list  # lists of rows
    overflow: bool  # some row is taller than its frame
    column_width: float
    heading_block: float  # the height the heading takes from the first page's columns


def _flow_rows(rows, size: float, style: DenseStyle, capacities) -> tuple[list, bool]:
    frames, current, used, overflow = [], [], 0.0, False
    capacities = iter(capacities)
    capacity = next(capacities)
    for row in rows:
        need = row.top + row.bottom
        if current:
            need += row.gap_before + style.row_gap * size
        if current and used + need > capacity + _EPSILON:
            frames.append(current)
            current, used, capacity = [], 0.0, next(capacities)
            need = row.top + row.bottom
        if not current and need > capacity + _EPSILON:
            overflow = True
        current.append(row)
        used += need
    frames.append(current)
    return frames, overflow


def _flow(
    pieces, heading: str, size: float, *, width, height, layout: SheetLayout, paint
) -> _Flow:
    style, columns = layout.style, layout.columns
    options = {"chords": layout.placement, "packer": layout.packer, "paint": paint}
    if columns == 1:  # the heading is the first row of the only column
        rows = _layout(pieces, size, width, style, heading, **options)
        frames, overflow = _flow_rows(rows, size, style, itertools.repeat(height))
        return _Flow(None, frames, overflow, width, 0.0)
    column_width = (width - style.column_gap * size * (columns - 1)) / columns
    head = _heading_row(heading, size, width, style) if heading else None
    block = head.top + head.bottom + style.row_gap * size if head else 0.0
    if column_width <= 0 or block > height:
        return _Flow(head, [[]] * (columns + 1), True, max(column_width, 0.0), block)
    rows = _layout(pieces, size, column_width, style, **options)
    capacities = itertools.chain(
        itertools.repeat(height - block, columns), itertools.repeat(height)
    )
    frames, overflow = _flow_rows(rows, size, style, capacities)
    return _Flow(head, frames, overflow, column_width, block)


def fit_font_size(
    song: Song,
    *,
    page_size="A4",
    margin: float = DFLT_MARGIN,
    style: DenseStyle | None = None,
    layout: SheetLayout | str | None = None,
    min_font_size: float = 6.0,
    max_font_size: float = 72.0,
    precision: float = 0.05,
) -> float:
    """The largest lyric font size at which ``song`` fits one page in ``layout`` (default: v1's).

    ``style``, if given, replaces the layout's style. Returns ``min_font_size``
    if even that does not fit (the song then needs more pages).
    """
    layout = _as_layout(layout, style)
    page_width, page_height = _page_dimensions(page_size)
    width, height = page_width - 2 * margin, page_height - 2 * margin
    gaps = layout.style.column_gap * min_font_size * (layout.columns - 1)
    if width - gaps <= 0:
        raise ValueError(
            f"{layout.columns} column(s) do not fit across a {page_width:g} pt page "
            f"with {margin:g} pt margins, even at {min_font_size:g} pt"
        )
    pieces, heading = _pieces(song), _heading(song)
    paint = _paint(song, layout.style, layout.shading)

    def fits(size):
        flow = _flow(
            pieces,
            heading,
            size,
            width=width,
            height=height,
            layout=layout,
            paint=paint,
        )
        return len(flow.frames) <= layout.columns and not flow.overflow

    if fits(max_font_size):
        return max_font_size
    if not fits(min_font_size):
        return min_font_size
    low, high = min_font_size, max_font_size
    while high - low > precision:
        middle = (low + high) / 2
        low, high = (middle, high) if fits(middle) else (low, middle)
    best, probe = low, low + _PROBE_STEP
    while probe <= min(low + _PROBE_SPAN, max_font_size):
        if fits(probe):
            best = probe
        probe += _PROBE_STEP
    return best


def _draw_items(
    canvas, row: _Row, left: float, baseline: float, style: DenseStyle
) -> None:
    from reportlab.lib.colors import HexColor

    for item in row.items:
        x, y = left + item.x, baseline + item.rise
        if (
            item.halo
        ):  # the render mode and line width would outlive the text: scope them
            canvas.saveState()
            outline = canvas.beginText(x, y)
            outline.setFont(item.font, item.size)
            outline.setTextRenderMode(1)  # stroke only
            outline.setStrokeColor(HexColor(item.halo))
            canvas.setLineWidth(style.chord_halo_width * item.size)
            canvas.setLineJoin(1)
            outline.textOut(item.text)
            canvas.drawText(outline)
            canvas.restoreState()
        canvas.setFillColor(HexColor(item.color))
        canvas.setFont(item.font, item.size)
        canvas.drawString(x, y, item.text)


def render_sheet(
    song: Song,
    output,
    *,
    layout: SheetLayout | str = "dense",
    page_size="A4",
    margin: float = DFLT_MARGIN,
    min_font_size: float = 6.0,
    max_font_size: float = 72.0,
) -> dict:
    """Render ``song`` in ``layout`` (a :class:`SheetLayout` or a spec) as a PDF to ``output``.

    ``output`` is a path or a binary file object. Returns
    ``{"path", "font_size", "pages", "rows"}``; ``path`` is ``None`` when
    ``output`` is a file object.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen.canvas import Canvas

    layout = _as_layout(layout, None)
    style, columns = layout.style, layout.columns
    page_width, page_height = _page_dimensions(page_size)
    width, height = page_width - 2 * margin, page_height - 2 * margin
    size = fit_font_size(
        song,
        page_size=(page_width, page_height),
        margin=margin,
        layout=layout,
        min_font_size=min_font_size,
        max_font_size=max_font_size,
    )
    heading = _heading(song)
    paint = _paint(song, style, layout.shading)
    flow = _flow(
        _pieces(song),
        heading,
        size,
        width=width,
        height=height,
        layout=layout,
        paint=paint,
    )

    target = os.fspath(output) if isinstance(output, (str, os.PathLike)) else output
    canvas = Canvas(target, pagesize=(page_width, page_height))
    canvas.setTitle(heading or "song sheet")
    canvas.setCreator("songleaf")
    top, column_gap = page_height - margin, style.column_gap * size
    row_gap, band_pad = style.row_gap * size, min(style.band_pad * size, margin / 2)
    previous_bottom = top
    for index, rows in enumerate(flow.frames):
        page, column = divmod(index, columns)
        if index and not column:
            canvas.showPage()
        if index == 0 and flow.heading:
            _draw_items(canvas, flow.heading, margin, top - flow.heading.top, style)
        frame_top = top - (flow.heading_block if page == 0 else 0.0)
        left = margin + column * (flow.column_width + column_gap)
        baselines, y = [], frame_top
        for k, row in enumerate(rows):
            baseline = y - (row.gap_before if k else 0.0) - row.top
            baselines.append(baseline)
            y = baseline - row.bottom - row_gap
        for row, baseline in zip(rows, baselines):  # bands under all the text
            if row.shade:
                canvas.setFillColor(HexColor(row.shade))
                band_top = baseline + row.top + row_gap / 2
                band_bottom = baseline - row.bottom - row_gap / 2
                canvas.rect(
                    left - band_pad,
                    band_bottom,
                    flow.column_width + 2 * band_pad,
                    band_top - band_bottom,
                    stroke=0,
                    fill=1,
                )
        for row, baseline in zip(rows, baselines):
            _draw_items(canvas, row, left, baseline, style)
        bottom = y + row_gap
        if column and rows and style.column_rule_color:
            rule_x = left - column_gap / 2
            canvas.setStrokeColor(HexColor(style.column_rule_color))
            canvas.setLineWidth(0.5)
            canvas.line(rule_x, frame_top, rule_x, min(bottom, previous_bottom))
        previous_bottom = bottom
    canvas.showPage()  # also emits the page of a song with nothing to draw
    canvas.save()
    return {
        "path": target if isinstance(target, str) else None,
        "font_size": round(size, 2),
        "pages": max(1, math.ceil(len(flow.frames) / columns)),
        "rows": sum(map(len, flow.frames)) + (1 if flow.heading else 0),
    }


def render_dense_a4(
    song: Song,
    output,
    *,
    page_size="A4",
    margin: float = DFLT_MARGIN,
    style: DenseStyle | None = None,
    min_font_size: float = 6.0,
    max_font_size: float = 72.0,
) -> dict:
    """Render ``song`` in the v1 layout as a PDF to ``output`` (a path or a binary file object).

    The same as :func:`render_sheet` with ``layout="dense"``. Returns
    ``{"path", "font_size", "pages", "rows"}``; ``path`` is ``None`` when
    ``output`` is a file object.
    """
    return render_sheet(
        song,
        output,
        layout=SheetLayout(style=style or DenseStyle()),
        page_size=page_size,
        margin=margin,
        min_font_size=min_font_size,
        max_font_size=max_font_size,
    )


def make_renderer(layout: SheetLayout | str = "dense", **render_options) -> Callable:
    """A ``(song, output) -> dict`` renderer for ``layout``, the shape ``sheet``'s ``renderer=`` takes.

    ``render_options`` are passed to :func:`render_sheet` (``page_size``,
    ``margin``, ...). A bad spec fails here, not at render time.

    >>> make_renderer("packed+shaded").keywords["layout"].packing
    'structured'
    """
    layout = _as_layout(layout, None)
    inspect.signature(render_sheet).bind(None, None, layout=layout, **render_options)
    return partial(render_sheet, layout=layout, **render_options)
