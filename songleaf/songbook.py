"""A songbook: several songs in one PDF, with a table of contents, page numbers and bookmarks.

``render_songbook(songs, output)`` renders each song through the same renderer
a single sheet uses (so each is at its fitted size), puts a table of contents
in front, stamps "page n of N" at the foot of every page and adds one PDF
bookmark per song. The renderer is a seam, as in :func:`songleaf.tools.sheet`.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence

from songleaf.model import Song
from songleaf.render import make_renderer

DFLT_TOC_TITLE = "Songbook"
DFLT_FOOTER_SIZE = 8.0
DFLT_TOC_SIZE = 12.0
DFLT_TOC_MARGIN = 56.0
DFLT_FOOTER_MARGIN = 20.0


def render_songbook(
    songs: Sequence[tuple[str, Song]],
    output,
    *,
    title: str = DFLT_TOC_TITLE,
    renderer: Callable | None = None,
    page_size="A4",
    toc_size: float = DFLT_TOC_SIZE,
    footer_size: float = DFLT_FOOTER_SIZE,
) -> dict:
    """Render ``songs`` (``(key, song)`` pairs, in set-list order) as one PDF to ``output``.

    ``output`` is a path or a binary file object. ``renderer`` is a
    ``(song, output) -> dict`` renderer (default: the dense layout). Returns
    ``{"path", "title", "pages", "songs": [{"key", "title", "artist", "page"}]}``
    where ``page`` is the song's first page in the book.
    """
    from pypdf import PdfReader, PdfWriter

    if not songs:
        raise ValueError("A songbook needs at least one song")
    renderer = renderer or make_renderer("dense", page_size=page_size)
    parts = []
    for key, song in songs:
        buffer = io.BytesIO()
        renderer(song, buffer)
        parts.append(PdfReader(io.BytesIO(buffer.getvalue())))
    entries = [
        {"key": key, "title": song.title, "artist": song.artist} for key, song in songs
    ]
    # The TOC may run to several pages; its length decides where the songs start.
    toc_pages = 1
    while True:
        starts, at = [], toc_pages + 1
        for part in parts:
            starts.append(at)
            at += len(part.pages)
        toc = _toc_pdf(
            title,
            [{**e, "page": s} for e, s in zip(entries, starts)],
            page_size=page_size,
            size=toc_size,
        )
        if len(toc.pages) == toc_pages:
            break
        toc_pages = len(toc.pages)
    writer = PdfWriter()
    for page in toc.pages:
        writer.add_page(page)
    for part in parts:
        for page in part.pages:
            writer.add_page(page)
    total = len(writer.pages)
    stamps = _footer_pdf(total, page_size=page_size, size=footer_size)
    for page, stamp in zip(writer.pages, stamps.pages):
        page.merge_page(stamp)
    writer.add_outline_item(title, 0)
    for entry, start in zip(entries, starts):
        label = " - ".join(filter(None, (entry["artist"], entry["title"])))
        writer.add_outline_item(label or entry["key"], start - 1)
    if hasattr(output, "write"):
        writer.write(output)
        path = None
    else:
        with open(output, "wb") as file:
            writer.write(file)
        path = str(output)
    return {
        "path": path,
        "title": title,
        "pages": total,
        "songs": [{**e, "page": s} for e, s in zip(entries, starts)],
    }


def _canvas(page_size):
    from reportlab.pdfgen.canvas import Canvas

    from songleaf.render import _page_dimensions

    buffer = io.BytesIO()
    dims = _page_dimensions(page_size)
    return buffer, Canvas(buffer, pagesize=dims), dims


def _toc_pdf(title: str, rows: list[dict], *, page_size, size: float):
    from pypdf import PdfReader

    buffer, canvas, (width, height) = _canvas(page_size)
    margin, lead = DFLT_TOC_MARGIN, size * 1.6

    def heading():
        canvas.setFont("Helvetica-Bold", size * 1.8)
        canvas.drawString(margin, height - margin, title)
        canvas.setFont("Helvetica", size)
        return height - margin - size * 3

    y = heading()
    for row in rows:
        if y < margin:
            canvas.showPage()
            y = heading()
        label = " - ".join(filter(None, (row["title"], row["artist"]))) or row["key"]
        number = str(row["page"])
        room = width - 2 * margin - canvas.stringWidth(number, "Helvetica", size) - 12
        while label and canvas.stringWidth(label, "Helvetica", size) > room:
            label = label.rstrip("…")[:-1] + "…"
        canvas.drawString(margin, y, label)
        canvas.drawRightString(width - margin, y, number)
        y -= lead
    canvas.showPage()
    canvas.save()
    return PdfReader(io.BytesIO(buffer.getvalue()))


def _footer_pdf(total: int, *, page_size, size: float):
    from pypdf import PdfReader

    buffer, canvas, (width, _) = _canvas(page_size)
    canvas.setFont("Helvetica", size)
    for n in range(1, total + 1):
        canvas.drawCentredString(width / 2, DFLT_FOOTER_MARGIN / 2, f"{n} / {total}")
        canvas.showPage()
    canvas.save()
    return PdfReader(io.BytesIO(buffer.getvalue()))
