"""The web surface: a JSON API over :mod:`songleaf.tools`, the sheet as a PDF, and the page.

``mk_app()`` is a FastAPI app; mount it anywhere (``/api/songleaf`` on
apps.thorwhalen.com). Its routes:

- ``GET /search?q=&artist=&lyrics=&limit=``: hits, best first (``tools.search``)
- ``GET /songs``: the stored songs, with title and artist
- ``GET /layouts``: the layout options a sheet can combine
- ``GET /sheet?key=&layout=``: render the sheet; its title, artist, font size and pages
- ``GET /sheet.pdf?key=&layout=``: the sheet itself
- ``GET /sheet.png?key=&layout=&page=``: one page of it as an image, for browsers that
  show no PDF inline (Android's)
- ``GET /ui/app.js``, ``GET /ui/style.css``: the page's script and style

The page is a two-path shell (:func:`page_shell`) that loads its script and
style from ``/ui/``, so it changes with this package, not with the host. The app
carries no authentication: the host gates it.

A rendered sheet is kept in memory (the last ``sheet_cache_size``), so the page's
three requests for one sheet render it once.

Requires ``pip install songleaf[web]`` (FastAPI, pypdfium2). Importing :mod:`songleaf` does
not import this module.
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
from functools import lru_cache
from importlib.resources import files
from urllib.parse import quote

from songleaf import tools
from songleaf.render import LAYOUT_OPTIONS, layout_spec
from songleaf.sources import SourceUnavailable

#: Failures a request can cause, and the HTTP status each becomes.
ERROR_STATUS = {LookupError: 404, ValueError: 400, SourceUnavailable: 503}
_UI_FILES = {"app.js": "text/javascript", "style.css": "text/css"}
_MAX_LIMIT = 50
_PRIVATE_CACHE = {"Cache-Control": "private, max-age=300"}


def mk_app(
    *,
    sources=None,
    store=None,
    title: str = "songleaf",
    sheet_cache_size: int = 32,
    image_scale: float = 2.0,
):
    """The FastAPI app. ``sources`` and ``store`` are the seams of :mod:`songleaf.tools`.

    ``image_scale`` is pixels per PDF point for ``/sheet.png`` (2: an A4 page is
    1190 pixels wide, sharp on a phone).
    """
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse, Response

    app = FastAPI(title=title)
    # The default source loads its corpus on first use; two first requests at
    # once would load it twice. Serialising calls costs nothing at this scale.
    corpus_lock = threading.Lock()

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
        if not (q or title or artist or lyrics).strip():
            return []
        with corpus_lock:
            return tools.search(
                q, title=title, artist=artist, lyrics=lyrics, limit=limit,
                sources=sources,
            )  # fmt: skip

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
        return {"default": "dense", "options": options}

    @lru_cache(maxsize=sheet_cache_size)
    def rendered(key: str, layout: str) -> tuple[bytes, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "sheet.pdf")
            with corpus_lock:
                result = tools.sheet(
                    key, output=output, layout=layout, sources=sources, store=store
                )
            with open(output, "rb") as file:
                pdf = file.read()
        name = " - ".join(filter(None, (result["artist"], result["title"]))) or "sheet"
        info = {
            "key": result["key"],
            "title": result["title"],
            "artist": result["artist"],
            "layout": layout,
            "font_size": result.get("font_size"),
            "pages": result.get("pages", 1),
            "file_name": name + ".pdf",
        }
        return pdf, info

    def sheet_of(key: str, layout: str) -> tuple[bytes, dict]:
        return rendered(key, layout_spec(layout))  # one cache entry per spelling

    @app.get("/sheet")
    def sheet(key: str, layout: str = "dense") -> dict:
        return sheet_of(key, layout)[1]

    @app.get("/sheet.pdf")
    def sheet_pdf(key: str, layout: str = "dense"):
        pdf, info = sheet_of(key, layout)
        disposition = f"inline; filename*=UTF-8''{quote(info['file_name'])}"
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition, **_PRIVATE_CACHE},
        )

    @app.get("/sheet.png")
    def sheet_png(key: str, layout: str = "dense", page: int = Query(1, ge=1)):
        pdf, info = sheet_of(key, layout)
        if page > info["pages"]:
            raise LookupError(f"The sheet has {info['pages']} page(s), not {page}")
        return Response(
            pdf_page_png(pdf, page, scale=image_scale),
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
    rows = [
        {"key": key, "title": store[key].title, "artist": store[key].artist}
        for key in store
    ]
    return sorted(rows, key=lambda row: (row["artist"].lower(), row["title"].lower()))


def page_shell(*, api: str, base: str = "", title: str = "songleaf") -> str:
    """The page's HTML: where the page lives (``base``) and where :func:`mk_app` is mounted (``api``).

    >>> "/api/songleaf/ui/app.js" in page_shell(api="/api/songleaf", base="/songleaf")
    True
    """
    config = {"api": api.rstrip("/"), "base": base.rstrip("/"), "title": title}
    config_js = ", ".join(f'{k}: "{v}"' for k, v in config.items())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<!-- songleaf page shell, from songleaf.web.page_shell: the script and style load from the API,
     so they upgrade with the package. -->
<script>window.SONGLEAF = {{ {config_js} }};</script>
<link rel="stylesheet" href="{config["api"]}/ui/style.css">
</head>
<body>
<main id="app" aria-live="polite"><p class="muted">Loading…</p></main>
<script src="{config["api"]}/ui/app.js"></script>
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
