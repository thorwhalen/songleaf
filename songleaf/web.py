"""The web surface: a JSON API over :mod:`songleaf.tools`, the sheet as a PDF, and the page.

``mk_app()`` is a FastAPI app; mount it anywhere (``/api/songleaf`` on
apps.thorwhalen.com). Its routes:

- ``GET /search?q=&artist=&lyrics=&limit=``: hits, best first (``tools.search``)
- ``GET /songs``: the stored songs, with title and artist
- ``GET /layouts``: the layout options a sheet can combine, and the default colours
- ``GET /song?key=``: the song as JSON (``tools.song``): text, chords, sections, its
  key and a chord table for every key it can move to; the page draws it as text
- ``GET /sheet?key=&...``: render the sheet; its title, artist, font size and pages
- ``GET /sheet.pdf?key=&...``: the sheet itself
- ``GET /sheet.png?key=&...&page=``: one page of it as an image, for browsers that
  show no PDF inline (Android's)

The sheet routes take the parameters of :class:`SheetRequest`: ``layout``,
``transpose`` (semitones), ``scale`` (of the size that fills the page), and the
colours, opacities and chord size the page's reader uses.
- ``GET /ui/app.js``, ``GET /ui/style.css``: the page's script and style

The page is a two-path shell (:func:`page_shell`) that loads its script and
style from ``/ui/``, so it changes with this package, not with the host. The app
carries no authentication: the host gates it.

A rendered sheet and its page images are kept in memory (the last
``sheet_cache_size`` of each), so the page's requests for one sheet render it once.

Only what a request can get wrong becomes a 4xx: an unknown song (404), a bad
layout or page (400, 404). A corpus that is not on the machine is a 503 saying
where to put it. Anything else is a bug and stays a 500.

Requires ``pip install songleaf[web]`` (FastAPI, pypdfium2). Importing :mod:`songleaf` does
not import this module.
"""

from __future__ import annotations

import html
import io
import json
import os
import tempfile
import re
import threading
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib.resources import files
from urllib.parse import quote

from songleaf import tools
from songleaf.render import (
    LAYOUT_OPTIONS,
    DenseStyle,
    layout_named,
    layout_spec,
    make_renderer,
    on_paper,
)
from songleaf.sources import SongNotFound, SourceUnavailable

#: Failures a request can cause, and the HTTP status each becomes. Nothing broader:
#: a KeyError or ValueError from a bug must not read as "not found" or "your fault".
ERROR_STATUS = {SongNotFound: 404, SourceUnavailable: 503}
_UI_FILES = {"app.js": "text/javascript", "style.css": "text/css"}
_MAX_LIMIT = 50
_PRIVATE_CACHE = {"Cache-Control": "private, max-age=300"}
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
#: Allowed ranges of the numeric sheet parameters: (low, high).
SHEET_LIMITS = {
    "transpose": (-11, 11),
    "scale": (0.3, 3.0),
    "lyric_alpha": (0.0, 1.0),
    "chord_alpha": (0.0, 1.0),
    "chord_scale": (0.3, 1.5),
}


@dataclass(frozen=True)
class SheetRequest:
    """What a sheet is made from: the song, its layout and the reader's look.

    Empty colours and a zero ``chord_scale`` keep the layout's own. Opacities are
    blended onto white paper. Frozen, so it is also the render cache's key.
    """

    key: str
    layout: str = "dense"
    transpose: int = 0
    scale: float = 1.0
    lyric_color: str = ""
    lyric_alpha: float = 1.0
    chord_color: str = ""
    chord_alpha: float = 1.0
    chord_scale: float = 0.0

    def checked(self) -> SheetRequest:
        """This request in its one spelling, or ``ValueError`` naming what is wrong."""
        for name, (low, high) in SHEET_LIMITS.items():
            value = getattr(self, name)
            if name == "chord_scale" and value == 0:
                continue
            if not low <= value <= high:
                raise ValueError(f"{name} goes from {low:g} to {high:g}, got {value:g}")
        for name in ("lyric_color", "chord_color"):
            if getattr(self, name) and not _COLOR_RE.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} is #rrggbb, got {getattr(self, name)!r}")
        return replace(
            self,
            layout=layout_spec(self.layout),
            lyric_color=self.lyric_color.lower(),
            chord_color=self.chord_color.lower(),
        )

    def renderer(self):
        """The ``(song, output) -> dict`` renderer this request describes."""
        layout = layout_named(self.layout)
        style, base = {}, DenseStyle()
        if self.lyric_color or self.lyric_alpha < 1:
            style["lyric_color"] = on_paper(
                self.lyric_color or base.lyric_color, self.lyric_alpha
            )
        if self.chord_color or self.chord_alpha < 1:
            style["chord_color"] = on_paper(
                self.chord_color or base.chord_color, self.chord_alpha
            )
        if self.chord_scale:
            style["chord_scale"] = self.chord_scale
        layout = replace(layout, style=replace(layout.style, **style))
        return make_renderer(layout, scale=self.scale)


def mk_app(
    *,
    sources=None,
    store=None,
    title: str = "songleaf",
    sheet_cache_size: int = 32,
    image_cache_size: int = 8,
    image_scale: float = 2.0,
):
    """The FastAPI app. ``sources`` and ``store`` are the seams of :mod:`songleaf.tools`.

    ``image_scale`` is pixels per PDF point for ``/sheet.png`` (2: an A4 page is
    1190 pixels wide, sharp on a phone).
    """
    from fastapi import Depends, FastAPI, HTTPException, Query
    from fastapi.responses import JSONResponse, Response

    app = FastAPI(title=title)
    pdfium_lock = threading.Lock()  # pdfium is not thread-safe; reportlab needs none

    for error_type, status in ERROR_STATUS.items():

        def handler(request, error, status=status):
            return JSONResponse({"detail": str(error)}, status_code=status)

        app.add_exception_handler(error_type, handler)

    @app.get("/search")
    def search(
        q: str = "",
        title: str = "",
        artist: str = "",
        lyrics: str = "",
        limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    ) -> list[dict]:
        q, title, artist, lyrics = (text.strip() for text in (q, title, artist, lyrics))
        if not (q or title or artist or lyrics):
            return []
        return tools.search(
            q, title=title, artist=artist, lyrics=lyrics, limit=limit, sources=sources
        )

    @app.get("/songs")
    def songs() -> list[dict]:
        return stored_songs(store=store)

    @app.get("/layouts")
    def layouts() -> dict:
        # ``sets``: what an option changes; two that change the same thing exclude each other
        options = [
            {"name": name, "sets": sorted(changes)}
            for name, changes in LAYOUT_OPTIONS.items()
            if name != "dense"
        ]
        base = DenseStyle()
        style = {
            "lyric_color": base.lyric_color,
            "chord_color": base.chord_color,
            "chord_scale": base.chord_scale,
        }
        return {
            "default": "dense",
            "options": options,
            "style": style,
            "limits": SHEET_LIMITS,
        }

    @app.get("/song")
    def song(key: str) -> dict:
        return tools.song(key, sources=sources, store=store)

    @lru_cache(maxsize=sheet_cache_size)
    def rendered(request: SheetRequest) -> tuple[bytes, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "sheet.pdf")
            result = tools.sheet(
                request.key,
                output=output,
                transpose=request.transpose,
                renderer=request.renderer(),
                sources=sources,
                store=store,
            )
            with open(output, "rb") as file:
                pdf = file.read()
        name = " - ".join(filter(None, (result["artist"], result["title"]))) or "sheet"
        if request.transpose:
            name += f" ({request.transpose:+d})"
        info = {
            **asdict(request),
            "key": result["key"],
            "title": result["title"],
            "artist": result["artist"],
            "font_size": result.get("font_size"),
            "pages": result.get("pages", 1),
            "file_name": name + ".pdf",
        }
        return pdf, info

    def sheet_of(request: SheetRequest) -> tuple[bytes, dict]:
        try:
            request = request.checked()  # one spelling, so one cache entry
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return rendered(request)

    @lru_cache(maxsize=image_cache_size)  # PNGs are ~10x a PDF's size: keep fewer
    def page_image(request: SheetRequest, page: int) -> bytes:
        pdf, _ = rendered(request)
        with pdfium_lock:
            return pdf_page_png(pdf, page, scale=image_scale)

    @app.get("/sheet")
    def sheet(request: SheetRequest = Depends()) -> dict:
        return sheet_of(request)[1]

    @app.get("/sheet.pdf")
    def sheet_pdf(request: SheetRequest = Depends()):
        pdf, info = sheet_of(request)
        disposition = f"inline; filename*=UTF-8''{quote(info['file_name'], safe='')}"
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition, **_PRIVATE_CACHE},
        )

    @app.get("/sheet.png")
    def sheet_png(request: SheetRequest = Depends(), page: int = Query(1, ge=1)):
        _, info = sheet_of(request)
        if page > info["pages"]:
            raise HTTPException(
                404, f"The sheet has {info['pages']} page(s), not {page}"
            )
        return Response(
            page_image(request.checked(), page),
            media_type="image/png",
            headers=_PRIVATE_CACHE,
        )

    @app.get("/ui/{name}")
    def ui(name: str):
        if name not in _UI_FILES:
            return JSONResponse({"detail": f"No UI file {name!r}"}, status_code=404)
        body = files("songleaf").joinpath("data", "web", name).read_bytes()
        return Response(body, media_type=_UI_FILES[name])

    return app


def stored_songs(*, store=None) -> list[dict]:
    """Every stored song as ``{key, title, artist}``, by artist then title."""
    from songleaf.store import song_store

    store = song_store() if store is None else store
    rows = []
    for key in store:
        song = store[key]
        rows.append({"key": key, "title": song.title, "artist": song.artist})
    return sorted(rows, key=lambda row: (row["artist"].lower(), row["title"].lower()))


def page_shell(*, api: str, base: str = "", title: str = "songleaf") -> str:
    """The page's HTML: where the page lives (``base``) and where :func:`mk_app` is mounted (``api``).

    >>> "/api/songleaf/ui/app.js" in page_shell(api="/api/songleaf", base="/songleaf")
    True
    """
    config = {"api": api.rstrip("/"), "base": base.rstrip("/"), "title": title}
    config_js = json.dumps(config).replace(
        "<", "\\u003c"
    )  # no "</script>" can close it
    api_attr, title_text = html.escape(config["api"]), html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>{title_text}</title>
<!-- songleaf page shell, from songleaf.web.page_shell: the script and style load from the API,
     so they upgrade with the package. -->
<script>window.SONGLEAF = {config_js};</script>
<link rel="stylesheet" href="{api_attr}/ui/style.css">
</head>
<body>
<main id="app" aria-live="polite"><p class="muted">Loading…</p></main>
<script src="{api_attr}/ui/app.js"></script>
</body>
</html>
"""


def pdf_page_png(pdf: bytes, page: int = 1, *, scale: float = 2.0) -> bytes:
    """One page (from 1) of a PDF as PNG bytes, ``scale`` pixels per point."""
    import pypdfium2

    buffer = io.BytesIO()
    document = pypdfium2.PdfDocument(pdf)
    try:
        image = document[page - 1].render(scale=scale).to_pil()
        image.save(buffer, format="PNG", optimize=True)
    finally:
        document.close()
    return buffer.getvalue()
