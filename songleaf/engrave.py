"""Score snippets engraved by Verovio: the ``score`` extra (``pip install songleaf[score]``).

The default snippet provider (:func:`songleaf.snippets.abc_snippet`) draws a
short ABC subset with reportlab lines. With this extra, :func:`engraved_snippet`
engraves the notation recorded on the song's ``score`` annotation properly
(clef, key and time signatures, beams, ties, chord names) from ABC (a body, or a
whole tune with its header), MusicXML or MEI: Verovio renders it to SVG, and
``svglib`` turns the SVG into a reportlab drawing placed on the sheet.

:func:`songleaf.snippets.default_provider` prefers this provider when the extra
is installed. Nothing here touches the network: the notation is the text stored
on the song.

Both libraries are LGPL-3.0 and only imported when a snippet is drawn.
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from importlib.util import find_spec

from songleaf.model import Song
from songleaf.snippets import ScoreSnippet

#: The notation formats Verovio reads here, as recorded in a score annotation's ``format``.
ENGRAVE_FORMATS = {"abc": "abc", "musicxml": "musicxml", "mei": "mei"}
#: Notation longer than this is not engraved (a snippet is a few bars).
MAX_ENGRAVE_CHARS = 200_000
#: Verovio's half staff space, in its units at scale 100 (its default).
VEROVIO_UNIT = 9
#: The header given to an ABC body with none: the same eighth-note unit as the subset.
ABC_HEADER = "X:1\nL:1/8\nK:C\n"
_ABC_FIELD_RE = re.compile(r"^[A-Za-z]:", re.MULTILINE)
_SVG_SIZE_RE = re.compile(r'<svg[^>]*\bwidth="([\d.]+)px"')


def available() -> bool:
    """Whether the ``score`` extra (verovio, svglib) is installed."""
    return find_spec("verovio") is not None and find_spec("svglib") is not None


def as_abc_tune(notation: str) -> str:
    """*notation* as a whole ABC tune: a body with no ``X:`` header gets :data:`ABC_HEADER`."""
    if re.search(r"^X:", notation, re.MULTILINE):
        return notation
    if _ABC_FIELD_RE.search(notation):  # some fields but no X: line
        return "X:1\n" + notation
    return ABC_HEADER + notation.strip() + "\n"


@lru_cache(maxsize=64)
def engrave_svg(notation: str, format: str = "abc") -> str:
    """The SVG of *notation* (``format``: a key of :data:`ENGRAVE_FORMATS`), cropped to the music."""
    import verovio

    if format not in ENGRAVE_FORMATS:
        raise ValueError(
            f"format must be one of {sorted(ENGRAVE_FORMATS)}, got {format!r}"
        )
    if len(notation) > MAX_ENGRAVE_CHARS:
        raise ValueError(
            f"The notation is too long to engrave ({len(notation)} characters)."
        )
    verovio.enableLog(False)
    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {
            "inputFrom": ENGRAVE_FORMATS[format],
            "adjustPageHeight": True,
            "adjustPageWidth": True,
            "breaks": "none",
            "header": "none",
            "footer": "none",
            "pageMarginTop": 0,
            "pageMarginBottom": 0,
            "pageMarginLeft": 0,
            "pageMarginRight": 0,
            "scale": 100,
            "unit": VEROVIO_UNIT,
        }
    )
    text = as_abc_tune(notation) if format == "abc" else notation
    if not toolkit.loadData(text) or toolkit.getPageCount() < 1:
        raise ValueError("Verovio could not read the notation.")
    return toolkit.renderToSVG(1)


def snippet_from_svg(svg: str, *, start: int = 0) -> ScoreSnippet:
    """A :class:`ScoreSnippet` drawing a Verovio *svg*, sized in its staff spaces."""
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(io.StringIO(svg))
    if drawing is None or not drawing.width:
        raise ValueError("The engraved SVG could not be read.")
    found = _SVG_SIZE_RE.search(svg)
    pixels = float(found.group(1)) if found else drawing.width
    per_space = (
        2 * VEROVIO_UNIT * drawing.width / pixels
    )  # drawing units per staff space

    def draw(canvas, left, bottom, space, *, color="#333333", font="Helvetica"):
        from reportlab.graphics import renderPDF

        canvas.saveState()
        canvas.translate(left, bottom)
        canvas.scale(space / per_space, space / per_space)
        renderPDF.draw(drawing, canvas, 0, 0)
        canvas.restoreState()

    return ScoreSnippet(
        drawing.width / per_space, drawing.height / per_space, draw, start
    )


def engraved_snippet(song: Song) -> ScoreSnippet | None:
    """The provider: the song's first ``score`` annotation with notation Verovio reads, engraved.

    ``None`` when there is none, or when it cannot be engraved (the sheet is then drawn without it).
    """
    for annotation in song.of_kind("score"):
        body = annotation.body
        notation, format = body.get("notation"), body.get("format", "")
        if not notation or format not in ENGRAVE_FORMATS:
            continue
        try:
            return snippet_from_svg(
                engrave_svg(notation, format), start=annotation.start
            )
        except (ValueError, RuntimeError):
            return None
    return None
