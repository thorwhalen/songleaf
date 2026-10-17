# songleaf.web

The web surface: a JSON API over [`songleaf.tools`](songleaf.tools.html.md#module-songleaf.tools), the sheet as a PDF, and the page.

`mk_app()` is a FastAPI app; mount it anywhere (`/api/songleaf` on
apps.thorwhalen.com). Its routes:

- `GET /search?q=&artist=&lyrics=&limit=`: hits, best first (`tools.search`)
- `GET /songs`: the stored songs, with title and artist
- `GET /layouts`: the layout options a sheet can combine, and the default colours
- `GET /song?key=`: the song as JSON (`tools.song`): text, chords, sections, its
  key and a chord table for every key it can move to; the page draws it as text
- `GET /sheet?key=&...`: render the sheet; its title, artist, font size and pages
- `GET /sheet.pdf?key=&...`: the sheet itself
- `GET /sheet.png?key=&...&page=`: one page of it as an image, for browsers that
  show no PDF inline (Android’s)

The sheet routes take the parameters of [`SheetRequest`](#songleaf.web.SheetRequest): `layout`,
`transpose` (semitones), `scale` (of the size that fills the page), and the
colours, opacities and chord size the page’s reader uses.

- `GET /ui/app.js`, `GET /ui/style.css`: the page’s script and style

The page is a two-path shell ([`page_shell()`](#songleaf.web.page_shell)) that loads its script and
style from `/ui/`, so it changes with this package, not with the host. The app
carries no authentication: the host gates it.

A rendered sheet and its page images are kept in memory (the last
`sheet_cache_size` of each), so the page’s requests for one sheet render it once.

Only what a request can get wrong becomes a 4xx: an unknown song (404), a bad
layout or page (400, 404). A corpus that is not on the machine is a 503 saying
where to put it. Anything else is a bug and stays a 500.

Requires `pip install songleaf[web]` (FastAPI, pypdfium2). Importing [`songleaf`](songleaf.html.md#module-songleaf) does
not import this module.

### Module Attributes

| [`ERROR_STATUS`](#songleaf.web.ERROR_STATUS)   | Failures a request can cause, and the HTTP status each becomes.   |
|-----------------------------------------------------------------|-------------------------------------------------------------------|
| [`SHEET_LIMITS`](#songleaf.web.SHEET_LIMITS)   | (low, high).                                                      |

### Functions

| [`mk_app`](#songleaf.web.mk_app)(\*[, sources, store, title, ...])   | The FastAPI app.                                                                                                                       |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| [`page_shell`](#songleaf.web.page_shell)(\*, api[, base, title])         | The page's HTML: where the page lives (`base`) and where [`mk_app()`](#songleaf.web.mk_app) is mounted (`api`). |
| [`pdf_page_png`](#songleaf.web.pdf_page_png)(pdf[, page, scale])           | One page (from 1) of a PDF as PNG bytes, `scale` pixels per point.                                                                     |
| [`stored_songs`](#songleaf.web.stored_songs)(\*[, store])                  | Every stored song as `{key, title, artist}`, by artist then title.                                                                     |

### Classes

| [`SheetRequest`](#songleaf.web.SheetRequest)(key[, layout, transpose, ...])   | What a sheet is made from: the song, its layout and the reader's look.   |
|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### songleaf.web.ERROR_STATUS *= {<class 'songleaf.sources.SongNotFound'>: 404, <class 'songleaf.sources.SourceUnavailable'>: 503}*

Failures a request can cause, and the HTTP status each becomes. Nothing broader:
a KeyError or ValueError from a bug must not read as “not found” or “your fault”.

### songleaf.web.SHEET_LIMITS *= {'chord_alpha': (0.0, 1.0), 'chord_scale': (0.3, 1.5), 'lyric_alpha': (0.0, 1.0), 'scale': (0.3, 3.0), 'transpose': (-11, 11)}*

(low, high).

* **Type:**
  Allowed ranges of the numeric sheet parameters

### *class* songleaf.web.SheetRequest(key, layout='dense', transpose=0, scale=1.0, lyric_color='', lyric_alpha=1.0, chord_color='', chord_alpha=1.0, chord_scale=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a sheet is made from: the song, its layout and the reader’s look.

Empty colours and a zero `chord_scale` keep the layout’s own. Opacities are
blended onto white paper. Frozen, so it is also the render cache’s key.

#### checked()

This request in its one spelling, or `ValueError` naming what is wrong.

* **Return type:**
  [`SheetRequest`](#songleaf.web.SheetRequest)

#### renderer()

The `(song, output) -> dict` renderer this request describes.

### songleaf.web.mk_app(, sources=None, store=None, title='songleaf', sheet_cache_size=32, image_cache_size=8, image_scale=2.0)

The FastAPI app. `sources` and `store` are the seams of [`songleaf.tools`](songleaf.tools.html.md#module-songleaf.tools).

`image_scale` is pixels per PDF point for `/sheet.png` (2: an A4 page is
1190 pixels wide, sharp on a phone).

### songleaf.web.page_shell(, api, base='', title='songleaf')

The page’s HTML: where the page lives (`base`) and where [`mk_app()`](#songleaf.web.mk_app) is mounted (`api`).

```pycon
>>> "/api/songleaf/ui/app.js" in page_shell(api="/api/songleaf", base="/songleaf")
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.web.pdf_page_png(pdf, page=1, , scale=2.0)

One page (from 1) of a PDF as PNG bytes, `scale` pixels per point.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### songleaf.web.stored_songs(, store=None)

Every stored song as `{key, title, artist}`, by artist then title.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
