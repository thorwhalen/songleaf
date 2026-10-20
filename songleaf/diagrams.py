"""Chord diagrams for the sheet: piano keys or guitar shapes (songleaf#13).

The chords a song uses (:func:`song_chords`, in order of first use) are drawn as a strip
of small diagrams. Both kinds come from the chord's pitch classes alone
(:func:`chord_tones`), so no fingering table is needed, and none has to be licensed:

- **piano**: a two-octave keyboard with the chord's notes marked, in close position
  from the bass;
- **guitar**: a shape in standard tuning found by search (:func:`guitar_shape`): the
  lowest sounding string plays the bass (the root, or the slash bass), every chord
  tone sounds, the fret span is at most four frets and four fingers (notes at the
  lowest fret share one barre finger, unless an open string lies under the barre),
  and fewer muted strings, lower positions, fewer fingers and no open string between
  fretted ones are preferred.

The layout reserves the strip's height before it fits the font size, so the lyrics
shrink to make room (:func:`strip_height`); :func:`draw_strip` draws it.

>>> chord_tones("Cmaj7"), chord_tones("Am/G"), chord_tones("F#m7b5")
((0, 4, 7, 11), (7, 9, 0, 4), (6, 9, 0, 4))
>>> guitar_shape("C"), guitar_shape("E"), guitar_shape("G")
((None, 3, 2, 0, 1, 0), (0, 2, 2, 1, 0, 0), (3, 2, 0, 0, 0, 3))
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from songleaf.harmony import parse_chord

_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_RE = re.compile(r"([A-G])([#b]?)")
#: Standard guitar tuning, low to high, as pitch classes (E A D G B E).
STANDARD_TUNING = (4, 9, 2, 7, 11, 4)
DIAGRAM_KINDS = ("piano", "guitar")
MAX_FRET = 12
MAX_SPAN = 3  # a shape spans at most four frets (lowest fretted to highest, inclusive)


def _note(text: str) -> int | None:
    m = _NOTE_RE.match(text.strip())
    if not m:
        return None
    return (_LETTERS[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]) % 12


def chord_tones(symbol: str) -> tuple[int, ...] | None:
    """The chord's pitch classes, bass first (the root, or the bass of a slash chord).

    Triads by quality (``m``, ``dim``, ``aug``/``+``, ``sus2``, ``sus4``, ``5``), then
    sevenths (``7``, ``maj7``, ``dim7``, ``m7b5``), sixths and added ninths. ``None``
    for what :func:`songleaf.harmony.parse_chord` does not read as a chord.
    """
    parsed = parse_chord(symbol)
    if parsed is None:
        return None
    root, quality = parsed
    head, _, bass_text = symbol.strip().partition("/")
    rest = _NOTE_RE.sub("", head, count=1)
    third = {"minor": 3, "diminished": 3}.get(quality, 4)
    fifth = 6 if quality == "diminished" else 7
    if "aug" in rest or rest.startswith("+"):
        fifth = 8
    intervals = [0, third, fifth]
    if quality == "open":  # suspended or power: no third
        intervals = [0, 7] if re.match(r"5(?!\d)", rest) else [0, 2 if "sus2" in rest else 5, 7]
    if "dim7" in rest or rest in ("°7", "o7"):
        intervals.append(9)
    elif re.search(r"(maj|M|Δ)(7|9|11|13)", rest):
        intervals.append(11)
    elif re.search(r"(?<!add)(7|9|11|13)", rest):
        intervals.append(10)
    if re.search(r"(?<!\d)6", rest):
        intervals.append(9)
    if re.search(r"9|add2", rest) and 2 not in intervals:
        intervals.append(2)
    tones = list(dict.fromkeys((root + i) % 12 for i in intervals))
    bass = _note(bass_text) if bass_text else None
    if bass is not None:
        tones = [bass] + [t for t in tones if t != bass]
    return tuple(tones)


def song_chords(song) -> list[str]:
    """The distinct chord symbols of ``song`` that :func:`chord_tones` reads, in order."""
    seen = []
    for annotation in song.of_kind("chord"):
        symbol = annotation.body.get("symbol", "")
        if symbol not in seen and chord_tones(symbol) is not None:
            seen.append(symbol)
    return seen


def guitar_shape(
    symbol: str, *, tuning: Sequence[int] = STANDARD_TUNING, max_fret: int = MAX_FRET
) -> tuple[int | None, ...] | None:
    """Frets per string, low to high (``None`` = not played), or None if none is found."""
    tones = chord_tones(symbol)
    if tones is None:
        return None
    bass, wanted = tones[0], set(tones)
    best, best_cost = None, None
    for low in range(0, max_fret - MAX_SPAN + 1):
        window = [0, *range(max(low, 1), low + MAX_SPAN + 1)]
        options = [
            [None] + [f for f in window if (string + f) % 12 in wanted] for string in tuning
        ]
        for frets in itertools.product(*options):
            sounding = [(i, f) for i, f in enumerate(frets) if f is not None]
            if len(sounding) < min(3, len(wanted)):
                continue
            lowest = sounding[0][0]
            if (tuning[lowest] + frets[lowest]) % 12 != bass:
                continue
            if any(f is None for f in frets[lowest:]):
                continue  # muted strings only below the bass: one strum, no gaps
            if {(tuning[i] + f) % 12 for i, f in sounding} != wanted:
                continue
            fretted = [f for _, f in sounding if f > 0]
            span = max(fretted) - min(fretted) if fretted else 0
            if span > MAX_SPAN:
                continue
            low_fret = min(fretted) if fretted else 0
            at_low = [i for i, f in enumerate(frets) if f and f == low_fret]
            # one finger barres the lowest fret, unless an open string lies under it
            barre = len(at_low) > 1 and all(
                frets[i] != 0 for i in range(at_low[0], at_low[-1] + 1)
            )
            fingers = len(fretted) - len(at_low) + (1 if barre else len(at_low))
            if fingers > 4:
                continue
            played = [i for i, f in enumerate(frets) if f]
            interior_open = (
                sum(1 for i in range(played[0], played[-1]) if frets[i] == 0)
                if played
                else 0
            )
            cost = (
                2 * lowest  # muted strings
                + 2 * low_fret  # position on the neck
                + fingers
                + span
                + interior_open  # an open string between fretted ones
            )
            if best_cost is None or cost < best_cost:
                best, best_cost = tuple(frets), cost
    return best


# --------------------------------------------------------------------- drawing


@dataclass(frozen=True)
class DiagramStyle:
    """Sizes of a diagram, in units of the lyric font size, and its colours."""

    piano_width: float = 4.2
    piano_height: float = 1.5
    guitar_width: float = 1.9
    guitar_height: float = 2.2
    label_scale: float = 0.6  # chord name size, of the lyric size
    gap: float = 0.7  # between diagrams, and between the strip and the lyrics
    line_color: str = "#555555"
    mark_color: str = "#222222"
    black_key_color: str = "#444444"


def _box(kind: str, size: float, style: DiagramStyle) -> tuple[float, float]:
    if kind == "piano":
        return style.piano_width * size, style.piano_height * size
    return style.guitar_width * size, style.guitar_height * size


def strip_height(
    n: int, kind: str, size: float, width: float, *, style: DiagramStyle = DiagramStyle()
) -> float:
    """The height a strip of ``n`` diagrams takes across ``width`` (0 for none)."""
    if not n:
        return 0.0
    w, h = _box(kind, size, style)
    gap = style.gap * size
    per_row = max(1, int((width + gap) // (w + gap)))
    rows = -(-n // per_row)
    return rows * (h + style.label_scale * size * 1.3 + gap) + gap


def draw_strip(
    canvas,
    symbols: Iterable[str],
    kind: str,
    *,
    left: float,
    bottom: float,
    width: float,
    size: float,
    font: str,
    style: DiagramStyle = DiagramStyle(),
) -> None:
    """Draw the diagrams in rows, left to right, the strip's bottom at ``bottom``."""
    symbols = list(symbols)
    w, h = _box(kind, size, style)
    gap, label = style.gap * size, style.label_scale * size
    per_row = max(1, int((width + gap) // (w + gap)))
    row_height = h + label * 1.3 + gap
    top = bottom + strip_height(len(symbols), kind, size, width, style=style) - gap
    for k, symbol in enumerate(symbols):
        row, col = divmod(k, per_row)
        x, y_top = left + col * (w + gap), top - row * row_height
        canvas.setFillColor(_color(style.mark_color))
        canvas.setFont(font, label)
        canvas.drawCentredString(x + w / 2, y_top - label, symbol)
        box_top = y_top - label * 1.3
        if kind == "piano":
            _draw_piano(canvas, chord_tones(symbol), x, box_top - h, w, h, style)
        else:
            _draw_guitar(canvas, guitar_shape(symbol), x, box_top - h, w, h, style, size)


def _color(hex_color: str):
    from reportlab.lib.colors import HexColor

    return HexColor(hex_color)


_WHITE = (0, 2, 4, 5, 7, 9, 11)
_BLACK = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}  # pitch class -> white key it sits after


def _voicing(tones: Sequence[int]) -> list[int]:
    """Close position from the bass, as semitones above the keyboard's lowest C."""
    notes, prev = [], -1
    for pc in tones:
        n = pc
        while n <= prev:
            n += 12
        notes.append(n)
        prev = n
    return notes


def _draw_piano(canvas, tones, x, y, w, h, style) -> None:
    key_w = w / 14
    canvas.setStrokeColor(_color(style.line_color))
    canvas.setLineWidth(0.4)
    for i in range(14):
        canvas.rect(x + i * key_w, y, key_w, h, stroke=1, fill=0)
    canvas.setFillColor(_color(style.black_key_color))
    for octave in range(2):
        for pc, after in _BLACK.items():
            bx = x + (octave * 7 + after + 1) * key_w - key_w * 0.3
            canvas.rect(bx, y + h * 0.4, key_w * 0.6, h * 0.6, stroke=0, fill=1)
    for note in _voicing(tones or ()):
        if note >= 24:
            continue
        octave, pc = divmod(note, 12)
        if pc in _WHITE:
            cx, cy, white = x + (octave * 7 + _WHITE.index(pc) + 0.5) * key_w, y + h * 0.18, True
        else:
            cx, cy, white = x + (octave * 7 + _BLACK[pc] + 1) * key_w, y + h * 0.55, False
        canvas.setFillColor(_color(style.mark_color if white else "#ffffff"))
        canvas.circle(cx, cy, key_w * 0.28, stroke=0, fill=1)


def _draw_guitar(canvas, frets, x, y, w, h, style, size) -> None:
    strings, rows = 6, 4
    dx, dy = w / (strings - 1) * 0.8, h / (rows + 0.6)
    left = x + w * 0.1
    grid_top = y + h - dy * 0.6
    fretted = [f for f in (frets or ()) if f]
    base = min(fretted) if fretted and max(fretted) > rows else 1
    canvas.setStrokeColor(_color(style.line_color))
    canvas.setLineWidth(1.4 if base == 1 else 0.4)
    canvas.line(left, grid_top, left + dx * (strings - 1), grid_top)  # the nut
    canvas.setLineWidth(0.4)
    for r in range(1, rows + 1):
        canvas.line(left, grid_top - r * dy, left + dx * (strings - 1), grid_top - r * dy)
    for s in range(strings):
        canvas.line(left + s * dx, grid_top, left + s * dx, grid_top - rows * dy)
    canvas.setFillColor(_color(style.mark_color))
    if base > 1:
        canvas.setFont("Helvetica", size * 0.5)
        canvas.drawRightString(left - dx * 0.3, grid_top - dy * 0.8, f"{base}fr")
    for s, fret in enumerate(frets or ()):
        cx = left + s * dx
        if fret is None:
            canvas.setFont("Helvetica", size * 0.5)
            canvas.drawCentredString(cx, grid_top + dy * 0.15, "×")
        elif fret == 0:
            canvas.circle(cx, grid_top + dy * 0.3, dx * 0.18, stroke=1, fill=0)
        else:
            cy = grid_top - (fret - base + 0.5) * dy
            canvas.circle(cx, cy, dx * 0.3, stroke=0, fill=1)
