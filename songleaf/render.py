"""Render a song onto one dense A4 page, with the lyrics as large as will fit.

:func:`render_dense_a4` finds the largest lyric font size at which the whole
song fits on one page (:func:`fit_font_size`), then draws it:

- consecutive lines of a paragraph are packed onto one row while they fit,
  separated by a light ``/``; a blank line or a new section starts a new row,
  and a line too long for the page wraps at a space;
- chords ride on their lyric row, smaller and in a lighter colour, overlapping
  the tops of the letters instead of taking a line of their own; a chord starts
  over the syllable it lands on (a ``timing="before"`` chord ends there);
- section labels are small grey prefixes (``V1``, ``Ch``) on the first row;
- only a song that cannot fit at ``min_font_size`` spills onto more pages.

Text is set in reportlab's built-in Helvetica, which covers Latin-1.

>>> short_label("Verse 1"), short_label("Pre-Chorus"), short_label("Coda")
('V1', 'Pre', 'Coda')
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from songleaf.model import Song

#: Page margin in points (5 mm), about the least a printer leaves blank anyway.
DFLT_MARGIN = 14.0
_EPSILON = 1e-6


@dataclass(frozen=True)
class DenseStyle:
    """Typography of the dense layout. Lengths are fractions of the lyric font size."""

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


def short_label(label: str) -> str:
    """A compact section label: ``"Verse 1"`` -> ``"V1"``, ``"Chorus x2"`` -> ``"Ch x2"``."""
    match = re.match(r"\s*([^\W\d_][\w-]*)(.*)", label)
    if not match:
        return label.strip()
    word, rest = match.group(1), match.group(2).strip(" :-")
    short = _LABEL_ABBREVIATIONS.get(word.lower(), word)
    return f"{short}{rest}" if rest.isdigit() else f"{short} {rest}".strip()


@lru_cache(maxsize=65536)
def _width(text: str, font: str) -> float:
    """Width of ``text`` at font size 1 (widths scale linearly with the size)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, font, 1)


@dataclass
class _Piece:
    """A run of lyrics with its chords: a line of the song, or part of a wrapped one."""

    text: str
    chords: list = field(default_factory=list)  # (offset in text, symbol, timing)
    label: str = ""
    new_paragraph: bool = False


@dataclass(frozen=True)
class _Item:
    layer: int  # drawing order: chords first, lyrics on top
    x: float
    rise: float  # above the row's baseline
    text: str
    font: str
    size: float
    color: str


@dataclass
class _Row:
    items: list
    top: float  # extent above the baseline
    bottom: float  # extent below the baseline
    gap_before: float = 0.0


def _pieces(song: Song) -> list[_Piece]:
    chords, sections = song.of_kind("chord"), song.of_kind("section")
    pieces, new_paragraph, c, s = [], True, 0, 0
    for line in song.lines():
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
            s += 1
        label = " ".join(filter(None, labels))
        if not (line.text or line_chords or label):
            new_paragraph = True
            continue
        pieces.append(
            _Piece(line.text, line_chords, label, new_paragraph or bool(label))
        )
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


def _label_width(piece: _Piece, size: float, style: DenseStyle) -> float:
    if not piece.label:
        return 0.0
    label_size = size * style.label_scale
    return (_width(piece.label, style.label_font) + style.label_gap) * label_size


def _chord_positions(piece: _Piece, size: float, style: DenseStyle):
    """The chords' x positions relative to the piece's text, and the piece's extent."""
    chord_size = size * style.chord_scale
    gap = (style.chord_gap if piece.text else style.bare_chord_gap) * chord_size
    placed, free = [], 0.0
    extent = _width(piece.text, style.lyric_font) * size
    for offset, symbol, timing in piece.chords:
        chord_width = _width(symbol, style.chord_font) * chord_size
        x = free
        if piece.text:
            x = _width(piece.text[:offset], style.lyric_font) * size
            if timing == "before":
                x -= chord_width + gap
        x = max(x, free)
        placed.append((x, symbol))
        free = x + chord_width + gap
        extent = max(extent, x + chord_width)
    return placed, extent


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
    head = _Piece(head_text, head_chords, piece.label, piece.new_paragraph)
    return head, _Piece(text[tail_start:], tail_chords)


def _split(piece: _Piece, available: float, size: float, style: DenseStyle):
    """Split a piece in two, the head as long as fits in ``available``; None if it can't split."""
    if piece.text:
        spaces = [i for i, ch in enumerate(piece.text) if ch == " " and i > 0]
        splits = [_split_at(piece, i) for i in reversed(spaces)]
        splits = [(head, tail) for head, tail in splits if head.text and tail.text]
        for head, tail in splits:
            if _chord_positions(head, size, style)[1] <= available:
                return head, tail
        return splits[-1] if splits else None
    if len(piece.chords) < 2:
        return None
    for k in range(len(piece.chords) - 1, 0, -1):
        head = _Piece("", piece.chords[:k], piece.label, piece.new_paragraph)
        if k == 1 or _chord_positions(head, size, style)[1] <= available:
            return head, _Piece("", piece.chords[k:])


def _wrap(piece: _Piece, size: float, width: float, style: DenseStyle) -> list[_Piece]:
    available = width - _label_width(piece, size, style)
    if _chord_positions(piece, size, style)[1] <= available:
        return [piece]
    split = _split(piece, available, size, style)
    if split is None:  # a single word or chord wider than the page: let it overflow
        return [piece]
    head, tail = split
    return [head, *_wrap(tail, size, width, style)]


def _row(
    pieces: list[_Piece], size: float, style: DenseStyle, gap_before: float
) -> _Row:
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
        placed, extent = _chord_positions(piece, size, style)
        rise = style.chord_rise * size if piece.text else 0.0
        items += [
            _Item(
                0, x + cx, rise, symbol, style.chord_font, chord_size, style.chord_color
            )
            for cx, symbol in placed
        ]
        if piece.text:
            items.append(
                _Item(2, x, 0.0, piece.text, style.lyric_font, size, style.lyric_color)
            )
        x += extent
    top = max((style.ascent * item.size + item.rise for item in items), default=0.0)
    bottom = style.descent * (size if has_text else max(item.size for item in items))
    return _Row(sorted(items, key=lambda item: item.layer), top, bottom, gap_before)


def _heading_row(heading: str, size: float, width: float, style: DenseStyle) -> _Row:
    heading_size = min(
        size * style.title_scale, width / _width(heading, style.title_font)
    )
    item = _Item(
        1, 0.0, 0.0, heading, style.title_font, heading_size, style.title_color
    )
    return _Row([item], style.ascent * heading_size, style.descent * heading_size)


def _layout(
    pieces: list[_Piece],
    size: float,
    width: float,
    style: DenseStyle,
    heading: str = "",
) -> list[_Row]:
    rows = [_heading_row(heading, size, width, style)] if heading else []
    current, current_width = [], 0.0

    def close():
        if current:
            gap = (
                style.paragraph_gap * size if rows and current[0].new_paragraph else 0.0
            )
            rows.append(_row(current, size, style, gap))

    for piece in (
        part for whole in pieces for part in _wrap(whole, size, width, style)
    ):
        piece_width = (
            _label_width(piece, size, style) + _chord_positions(piece, size, style)[1]
        )
        sep_size = size if piece.text else size * style.chord_scale
        joined_width = (
            current_width
            + _width(style.separator, style.lyric_font) * sep_size
            + piece_width
        )
        if (
            current
            and not piece.new_paragraph
            and bool(piece.text) == bool(current[-1].text)
            and joined_width <= width
        ):
            current.append(piece)
            current_width = joined_width
        else:
            close()
            current, current_width = [piece], piece_width
    close()
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


def fit_font_size(
    song: Song,
    *,
    page_size="A4",
    margin: float = DFLT_MARGIN,
    style: DenseStyle | None = None,
    min_font_size: float = 6.0,
    max_font_size: float = 72.0,
    precision: float = 0.05,
) -> float:
    """The largest lyric font size at which ``song`` fits one page.

    ``min_font_size`` if even that does not fit (the song then needs more pages).
    """
    style = style or DenseStyle()
    page_width, page_height = _page_dimensions(page_size)
    width, height = page_width - 2 * margin, page_height - 2 * margin
    pieces, heading = _pieces(song), _heading(song)

    def fits(size):
        rows = _layout(pieces, size, width, style, heading)
        return _height(rows, size, style) <= height + _EPSILON

    if fits(max_font_size) or not fits(min_font_size):
        return max_font_size if fits(max_font_size) else min_font_size
    low, high = min_font_size, max_font_size
    while high - low > precision:
        middle = (low + high) / 2
        low, high = (middle, high) if fits(middle) else (low, middle)
    return low


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
    """Render ``song`` as a PDF to ``output`` (a path or a binary file object).

    Returns ``{"path", "font_size", "pages", "rows"}``; ``path`` is ``None``
    when ``output`` is a file object.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen.canvas import Canvas

    style = style or DenseStyle()
    page_width, page_height = _page_dimensions(page_size)
    size = fit_font_size(
        song,
        page_size=(page_width, page_height),
        margin=margin,
        style=style,
        min_font_size=min_font_size,
        max_font_size=max_font_size,
    )
    heading = _heading(song)
    rows = _layout(_pieces(song), size, page_width - 2 * margin, style, heading)

    target = os.fspath(output) if isinstance(output, (str, os.PathLike)) else output
    canvas = Canvas(target, pagesize=(page_width, page_height))
    canvas.setTitle(heading or "song sheet")
    canvas.setCreator("songleaf")
    top = page_height - margin
    y, pages = top, 1
    for row in rows:
        gap = row.gap_before if y < top else 0.0
        if y < top and y - gap - row.top - row.bottom < margin - _EPSILON:
            canvas.showPage()
            pages += 1
            y, gap = top, 0.0
        baseline = y - gap - row.top
        for item in row.items:
            canvas.setFillColor(HexColor(item.color))
            canvas.setFont(item.font, item.size)
            canvas.drawString(margin + item.x, baseline + item.rise, item.text)
        y = baseline - row.bottom - style.row_gap * size
    canvas.showPage()  # also emits the page of a song with nothing to draw
    canvas.save()
    return {
        "path": target if isinstance(target, str) else None,
        "font_size": round(size, 2),
        "pages": pages,
        "rows": len(rows),
    }
