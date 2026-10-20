"""Score snippets on the sheet (songleaf#12): which stretch of a song, and a small staff for it.

A snippet is a few bars of notation drawn above one line of the lyrics, for a
sense of the melody or the rhythm. Three parts, each replaceable:

- **Which stretch**: :func:`choose_segment` picks a line by rule (the first line
  of the chorus, else the most repeated line, else the first line), and
  :func:`mark_segment` records the choice, with the notation, as the song's
  ``score`` annotation (:func:`songleaf.model.score_link`). A recorded annotation
  wins over the rule, so it is how a choice is overridden.
- **What to draw**: a *snippet provider*, ``song -> ScoreSnippet | None``, is
  injected into :func:`songleaf.render.render_sheet` (``snippets=``) and never
  imported by it. :func:`abc_snippet` draws the short ABC notation recorded on
  the annotation with reportlab lines only: one voice, treble staff, notes,
  rests, accidentals, bar lines and chord names (no clef is drawn). With the ``score`` extra,
  :func:`songleaf.engrave.engraved_snippet` engraves ABC, MusicXML or MEI
  properly; :func:`default_provider` picks it when installed.
- **Where it goes**: the ``score`` layout option makes the renderer place the
  snippet as a row above its line; the font fit counts its height, so the
  lyrics shrink to make room.

ABC subset read by :func:`parse_abc`: notes ``A-G a-g`` with ``,`` / ``'``
octave marks, ``^`` ``_`` ``=`` accidentals, lengths ``2`` ``/2`` ``3/2`` ``/``
(the unit is an eighth note), rests ``z``, bar lines ``|`` ``||`` ``|]`` ``|:``
``:|``, and ``"G"`` chord names over the next note. A length that needs a tie
(``5``) is refused. Header lines (``K:G``), decorations (``!fermata!``) and
anything else (ties, slurs, spaces) are skipped.

>>> [(n.pitch, n.length) for n in parse_abc("C2 D/2 z |").notes]
[(28, 0.25), (29, 0.0625), (None, 0.125)]
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction

from songleaf.model import Annotation, Song, score_link

#: The length of an unmarked ABC note, as a fraction of a whole note.
UNIT_LENGTH = Fraction(1, 8)
#: The shortest and longest note lengths read, in whole notes.
MIN_LENGTH, MAX_LENGTH = Fraction(1, 64), Fraction(4)
#: Notations longer than this are refused: a snippet is a few bars.
MAX_NOTATION_CHARS = 400
#: The notation formats a score annotation may hold inline (all but ``abc`` need the ``score`` extra).
NOTATION_FORMATS = ("abc", "musicxml", "mei")
#: What a provider-less recorded snippet is noted as.
INLINE_SOURCE = "inline"

_LETTERS = "CDEFGAB"
_BOTTOM_LINE = 2 + 7 * 4  # E4, the treble staff's bottom line, as a diatonic number
_TOKEN_RE = re.compile(
    r'"(?P<chord>[^"]*)"'
    r"|(?P<accidental>\^{1,2}|_{1,2}|=)?(?P<letter>[A-Ga-g])(?P<octave>[,']*)"
    r"(?P<num>\d*)(?P<slashes>/*)(?P<den>\d*)"
    r"|(?P<rest>[zx])(?P<rnum>\d*)(?P<rslashes>/*)(?P<rden>\d*)"
    r"|(?P<bar>\|\]|\|\||:\||\|:|\|)"
)
_SKIPPED_RE = re.compile(r"^[ \t]*[A-Za-z]:.*$|![^!\n]*!|\+[^+\n]*\+", re.MULTILINE)
_ACCIDENTAL_SIGNS = {"^": "♯", "^^": "♯♯", "_": "♭", "__": "♭♭", "=": "♮"}


@dataclass(frozen=True)
class Note:
    """One note (``pitch`` a diatonic number, C4 = 28) or rest (``pitch`` None)."""

    pitch: int | None
    length: float  # in whole notes
    accidental: str = ""
    chord: str = ""


@dataclass(frozen=True)
class Bar:
    """A bar line (``kind``: ``|``, ``||``, ``|]``, ``|:`` or ``:|``)."""

    kind: str = "|"


@dataclass(frozen=True)
class Tune:
    """A parsed snippet: notes, rests and bar lines in order."""

    events: tuple

    @property
    def notes(self) -> list[Note]:
        return [e for e in self.events if isinstance(e, Note)]


def _length(num: str, slashes: str, den: str) -> Fraction:
    numerator = int(num) if num else 1
    if slashes:
        denominator = int(den) if den else 2 ** len(slashes)
    else:
        denominator = 1
    if numerator <= 0 or denominator <= 0:
        raise ValueError("A note length must be positive.")
    length = UNIT_LENGTH * Fraction(numerator, denominator)
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        raise ValueError(
            f"A note length must be between {MIN_LENGTH} and {MAX_LENGTH} whole notes."
        )
    plain = (
        length.numerator == 1
        or length.denominator == 1
        and length.numerator in (1, 2, 4)
    )
    dotted = length.numerator == 3 and length.denominator > 1
    if not (plain or dotted):
        raise ValueError(f"A length of {length} needs a tie: write it as two notes.")
    return length


def parse_abc(notation: str) -> Tune:
    """The notes, rests and bars of a short ABC *notation* (see the module docstring).

    Raises ``ValueError`` for an empty or over-long notation, or one with no note.
    """
    if len(notation) > MAX_NOTATION_CHARS:
        raise ValueError(
            f"A snippet is a few bars: at most {MAX_NOTATION_CHARS} characters."
        )
    events, chord = [], ""
    body = _SKIPPED_RE.sub(
        "", notation
    )  # header fields ("K:G") and decorations ("!fermata!")
    for match in _TOKEN_RE.finditer(body):
        group = match.groupdict()
        if group["chord"] is not None:
            chord = group["chord"].strip()
        elif group["letter"]:
            letter = group["letter"]
            octave = 4 if letter.isupper() else 5
            octave += group["octave"].count("'") - group["octave"].count(",")
            pitch = _LETTERS.index(letter.upper()) + 7 * octave
            length = _length(group["num"], group["slashes"], group["den"])
            events.append(Note(pitch, float(length), group["accidental"] or "", chord))
            chord = ""
        elif group["rest"]:
            length = _length(group["rnum"], group["rslashes"], group["rden"])
            events.append(Note(None, float(length), "", chord))
            chord = ""
        else:
            events.append(Bar(group["bar"]))
    if not any(isinstance(e, Note) for e in events):
        raise ValueError(
            "No note in the notation: write notes as ABC, as in 'G2 AB c2'."
        )
    return Tune(tuple(events))


# --- which stretch of the song -------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A stretch of a song's text and the rule that chose it."""

    start: int
    end: int
    rule: str


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


def choose_segment(song: Song) -> Segment | None:
    """The line a snippet goes with: the first line of the chorus, else the most repeated line, else the first.

    ``None`` for a song with no lyric line.
    """
    from songleaf.render import section_family

    lines = [line for line in song.lines() if line.text.strip()]
    if not lines:
        return None
    for section in song.of_kind("section"):
        if section_family(section.body.get("label", "")) == "chorus":
            for line in lines:
                if section.start <= line.start < max(section.end, section.start + 1):
                    return Segment(line.start, line.end, "chorus-first-line")
    counts: dict[str, int] = {}
    for line in lines:
        key = _words(line.text)
        if key:
            counts[key] = counts.get(key, 0) + 1
    most = max(counts.values(), default=0)
    if most >= 2:
        line = next(l for l in lines if counts.get(_words(l.text)) == most)
        return Segment(line.start, line.end, "most-repeated-line")
    return Segment(lines[0].start, lines[0].end, "first-line")


def segment_at_line(song: Song, line: int) -> Segment:
    """The 1-based lyric *line* (blank lines not counted) as a segment chosen by hand."""
    lines = [l for l in song.lines() if l.text.strip()]
    if not 1 <= line <= len(lines):
        raise ValueError(f"line must be between 1 and {len(lines)}, got {line}")
    chosen = lines[line - 1]
    return Segment(chosen.start, chosen.end, "chosen")


def mark_segment(
    song: Song,
    notation: str,
    *,
    segment: Segment | None = None,
    format: str = "abc",
) -> Song:
    """A copy of *song* whose one ``score`` annotation holds *notation* over *segment*.

    *segment* defaults to :func:`choose_segment`'s. Earlier ``score``
    annotations are replaced: the recorded one is what the sheet draws.
    """
    if format not in NOTATION_FORMATS:
        raise ValueError(f"format must be one of {NOTATION_FORMATS}, got {format!r}")
    if format == "abc":
        parse_abc(notation)  # refuse what the default provider could not draw
    elif not notation.strip():
        raise ValueError("The notation is empty.")
    segment = segment or choose_segment(song)
    if segment is None:
        raise ValueError("The song has no lyric line to put a snippet over.")
    link = score_link(
        segment.start,
        segment.end,
        source=INLINE_SOURCE,
        id="",
        format=format,
        notation=notation,
        rule=segment.rule,
    )
    kept = [a for a in song.annotations if not _is_recorded(a)]
    return replace(song, annotations=sorted([*kept, link], key=lambda a: a.start))


def _is_recorded(annotation: Annotation) -> bool:
    """A score annotation holding notation: what :func:`mark_segment` replaces (links stay)."""
    body = annotation.body
    return annotation.kind == "score" and (
        bool(body.get("notation")) or body.get("source") == INLINE_SOURCE
    )


def recorded_snippet(song: Song, *, format: str = "abc") -> Annotation | None:
    """The song's first ``score`` annotation carrying *format* notation, if any."""
    for annotation in song.of_kind("score"):
        body = annotation.body
        if body.get("format") == format and body.get("notation"):
            return annotation
    return None


# --- what to draw ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreSnippet:
    """A drawable snippet, sized in staff spaces, placed above the line holding ``start``.

    ``draw(canvas, left, bottom, space, *, color, font)`` draws it with its
    lower-left corner at ``(left, bottom)``, ``space`` points per staff space;
    it then takes ``width * space`` by ``height * space`` points.
    """

    width: float
    height: float
    draw: Callable = field(repr=False)
    start: int = 0


#: A snippet provider: what the sheet draws for a song, or ``None`` for no snippet.
SnippetProvider = Callable[[Song], "ScoreSnippet | None"]

# Engraving proportions, in staff spaces (the distance between two staff lines).
_HEAD_WIDTH, _HEAD_HEIGHT = 1.3, 1.0
_STEM = 3.3
_PAD = 0.8  # before the first note and after the last
_BAR_ADVANCE = 1.2
_ACCIDENTAL_ADVANCE = 1.1
_CHORD_ROOM = 2.2  # height of the chord-name row above the staff
_LINE_WIDTH, _STEM_WIDTH = 0.09, 0.11


def _advance(length: float) -> float:
    return 1.8 + 1.5 * math.sqrt(length / float(UNIT_LENGTH))


def _shape(length: float) -> tuple[bool, int, bool]:
    """``(filled, flags, dotted)`` for a length in whole notes."""
    base = 2.0 ** math.floor(math.log2(length) + 1e-9)
    dotted = abs(length - 1.5 * base) < 1e-9
    filled = base < 0.5
    flags = max(0, int(round(-math.log2(base))) - 2) if base < 0.25 else 0
    return filled, flags, dotted


def _position(pitch: int) -> int:
    """Half-spaces above the bottom staff line (0 = E4, 8 = F5)."""
    return pitch - _BOTTOM_LINE


def layout_tune(tune: Tune) -> ScoreSnippet:
    """A :class:`ScoreSnippet` drawing *tune* on one treble staff, with reportlab lines only."""
    placed, x = [], _PAD
    low, high = 0.0, 4.0
    for event in tune.events:
        if isinstance(event, Bar):
            placed.append((x + 0.2, event))
            x += _BAR_ADVANCE
            continue
        if event.accidental:
            x += _ACCIDENTAL_ADVANCE
        placed.append((x, event))
        if event.pitch is not None:
            y = _position(event.pitch) / 2
            up = _position(event.pitch) < 4
            low = min(low, y - _HEAD_HEIGHT / 2 - (0 if up else _STEM))
            high = max(high, y + _HEAD_HEIGHT / 2 + (_STEM if up else 0))
        x += _advance(event.length)
    chords = any(isinstance(e, Note) and e.chord for _, e in placed)
    top = high + (_CHORD_ROOM if chords else 0.6)
    width, height = x + _PAD, top - low + 0.6

    def draw(canvas, left, bottom, space, *, color="#333333", font="Helvetica"):
        from reportlab.lib.colors import HexColor

        ink = HexColor(color)
        origin = bottom + (0.6 - low) * space  # the bottom staff line
        to_x = lambda units: left + units * space  # noqa: E731
        to_y = lambda units: origin + units * space  # noqa: E731
        canvas.saveState()
        canvas.setStrokeColor(ink)
        canvas.setFillColor(ink)
        canvas.setLineWidth(_LINE_WIDTH * space)
        for k in range(5):
            canvas.line(to_x(0), to_y(k), to_x(width), to_y(k))
        canvas.line(to_x(0), to_y(0), to_x(0), to_y(4))
        for at, event in placed:
            if isinstance(event, Bar):
                canvas.setLineWidth(
                    (_LINE_WIDTH * (3 if event.kind in ("|]", "||") else 1.5)) * space
                )
                canvas.line(to_x(at), to_y(0), to_x(at), to_y(4))
                if ":" in event.kind:
                    dot_x = at - 0.5 if event.kind == ":|" else at + 0.5
                    for dot_y in (1.5, 2.5):
                        canvas.circle(
                            to_x(dot_x), to_y(dot_y), 0.18 * space, stroke=0, fill=1
                        )
                continue
            if event.chord:
                canvas.setFont(font, 1.5 * space)
                canvas.drawString(to_x(at), to_y(high + 0.8), event.chord)
            _draw_event(canvas, event, at, to_x, to_y, space, font)
        canvas.restoreState()

    return ScoreSnippet(width, height, draw)


def _draw_event(
    canvas, event: Note, at: float, to_x, to_y, space: float, font: str
) -> None:
    filled, flags, dotted = _shape(event.length)
    if (
        event.pitch is None
    ):  # a rest: a block for long ones, a slanted stroke for short ones
        if event.length >= 0.5:
            y = (
                2.5 if event.length >= 1 else 2
            )  # a whole rest hangs from a line, a half sits on one
            canvas.rect(
                to_x(at), to_y(y), _HEAD_WIDTH * space, 0.5 * space, stroke=0, fill=1
            )
        else:
            canvas.setLineWidth(_STEM_WIDTH * 1.5 * space)
            canvas.line(to_x(at + 0.3), to_y(3), to_x(at + 0.9), to_y(1.2))
        return
    position = _position(event.pitch)
    y = position / 2
    canvas.setLineWidth(_LINE_WIDTH * space)
    for ledger in [*range(-2, position - 1, -2), *range(10, position + 1, 2)]:
        canvas.line(
            to_x(at - 0.3),
            to_y(ledger / 2),
            to_x(at + _HEAD_WIDTH + 0.3),
            to_y(ledger / 2),
        )
    if event.accidental:
        canvas.setFont(font, 1.8 * space)
        canvas.drawString(
            to_x(at - _ACCIDENTAL_ADVANCE),
            to_y(y - 0.5),
            _ACCIDENTAL_SIGNS[event.accidental],
        )
    canvas.setLineWidth(_STEM_WIDTH * 1.4 * space)
    canvas.ellipse(
        to_x(at),
        to_y(y - _HEAD_HEIGHT / 2),
        to_x(at + _HEAD_WIDTH),
        to_y(y + _HEAD_HEIGHT / 2),
        stroke=1,
        fill=1 if filled else 0,
    )
    if dotted:
        canvas.circle(
            to_x(at + _HEAD_WIDTH + 0.45),
            to_y(y + (0.25 if position % 2 == 0 else 0)),
            0.16 * space,
            stroke=0,
            fill=1,
        )
    if event.length >= 1:  # a whole note has no stem
        return
    up = position < 4
    stem_x = at + (_HEAD_WIDTH if up else 0)
    end = y + (_STEM if up else -_STEM)
    canvas.setLineWidth(_STEM_WIDTH * space)
    canvas.line(to_x(stem_x), to_y(y), to_x(stem_x), to_y(end))
    for k in range(flags):
        tip = end - (k * 0.8 if up else -k * 0.8)
        canvas.line(
            to_x(stem_x),
            to_y(tip),
            to_x(stem_x + 0.9),
            to_y(tip - (1.4 if up else -1.4)),
        )


def abc_snippet(song: Song) -> ScoreSnippet | None:
    """The default provider: the ABC notation recorded on the song's ``score`` annotation, drawn.

    ``None`` when the song has no such annotation, or its notation cannot be read.
    """
    annotation = recorded_snippet(song, format="abc")
    if annotation is None:
        return None
    try:
        tune = parse_abc(annotation.body["notation"])
    except (ValueError, OverflowError):
        return None
    return replace(layout_tune(tune), start=annotation.start)


def first_snippet(providers: Sequence[SnippetProvider]) -> SnippetProvider:
    """A provider asking each of *providers* in turn: the first snippet wins."""

    def provider(song: Song) -> ScoreSnippet | None:
        for each in providers:
            found = each(song)
            if found is not None:
                return found
        return None

    return provider


def default_provider() -> SnippetProvider:
    """The provider a ``score`` sheet uses when none is injected.

    The engraved one (:func:`songleaf.engrave.engraved_snippet`) when the
    ``score`` extra is installed, falling back to :func:`abc_snippet`; else
    :func:`abc_snippet` alone.
    """
    from songleaf import engrave

    if engrave.available():
        return first_snippet([engrave.engraved_snippet, abc_snippet])
    return abc_snippet
