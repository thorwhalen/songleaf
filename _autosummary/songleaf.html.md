# songleaf

songleaf: dense, readable one-page song sheets from searchable sources.

Find a song, keep it as lyrics plus anchored annotations (sections, chords,
provenance, score links), and render it onto one A4 page with the lyrics as
large as will fit.

```pycon
>>> import songleaf
>>> song = songleaf.parse_chords_over_lyrics("C       G\nHello there my friend")
>>> [a.body["symbol"] for a in song.of_kind("chord")]
['C', 'G']
```

From a query to a PDF, on the Kaggle chords-and-lyrics corpus:

```default
songleaf.sheet("wonderwall oasis")   # -> {'path': '.../sheets/oasis-wonderwall.pdf', ...}
```

or `python -m songleaf sheet "wonderwall oasis"`.

### Functions

| [`chord`](#songleaf.chord)(at, symbol, \*[, timing])                    | A chord landing on the syllable that starts at offset `at`.                                 |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`fit_font_size`](#songleaf.fit_font_size)(song, \*[, page_size, margin, ...])  | The largest lyric font size at which `song` fits one page.                                  |
| [`get_song`](#songleaf.get_song)(key, \*[, sources])                       | The song named by `key` (`"<source>:<id>"`), from the source of that name.                  |
| [`parse_chords_over_lyrics`](#songleaf.parse_chords_over_lyrics)(raw, \*[, meta, ...])     | Parse chords-over-lyrics text into a [`Song`](#songleaf.Song). |
| [`render_dense_a4`](#songleaf.render_dense_a4)(song, output, \*[, ...])           | Render `song` as a PDF to `output` (a path or a binary file object).                        |
| [`score_link`](#songleaf.score_link)(start, end, \*, source, id[, url, ...]) | A link from `[start, end)` to a score snippet held by a source.                             |
| [`search`](#songleaf.search)([query, title, artist, lyrics, ...])        | Search every source and merge the hits, best first.                                         |
| [`section`](#songleaf.section)(start, end, label)                         | A section (verse, chorus, ...) spanning `[start, end)`.                                     |
| [`sheet`](#songleaf.sheet)(query, \*[, output, pick, refresh, ...])     | Make a one-page song sheet (PDF) for the best match of `query`.                             |
| [`song_store`](#songleaf.song_store)([rootdir])                              | Songs as JSON files in `rootdir` (default: the `songs` data dir).                           |
| [`songs`](#songleaf.songs)(\*[, store])                                 | The keys of the stored songs.                                                               |

### Classes

| [`Annotation`](#songleaf.Annotation)(kind, start, end[, body])          | One annotation over `Song.text[start:end]`; a point when `start == end`.   |
|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`DenseStyle`](#songleaf.DenseStyle)([lyric_font, chord_font, ...])     | Typography of the dense layout.                                            |
| [`Hit`](#songleaf.Hit)(source, id, title[, artist, score, meta]) | One search result: a song a source can `get()`.                            |
| [`KaggleChordsSource`](#songleaf.KaggleChordsSource)(\*[, loader, min_score])   | The Kaggle *chords-and-lyrics* corpus (~135K songs, chords over lyrics).   |
| [`Song`](#songleaf.Song)(text[, annotations, meta, provenance])   | Lyrics text plus annotations, metadata and provenance.                     |

### *class* songleaf.Annotation(kind, start, end, body=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One annotation over `Song.text[start:end]`; a point when `start == end`.

#### to_dict()

The JSON-ready form.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* songleaf.DenseStyle(lyric_font='Helvetica', chord_font='Helvetica-Bold', label_font='Helvetica-Bold', title_font='Helvetica-Bold', lyric_color='#000000', chord_color='#3b73c4', label_color='#8c8c8c', separator_color='#a6a6a6', title_color='#595959', chord_scale=0.62, label_scale=0.5, title_scale=0.6, chord_rise=0.56, ascent=0.72, descent=0.21, row_gap=0.06, paragraph_gap=0.3, separator=' / ', chord_gap=0.3, bare_chord_gap=0.9, label_gap=0.4)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Typography of the dense layout. Lengths are fractions of the lyric font size.

### *class* songleaf.Hit(source, id, title, artist='', score=0.0, meta=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One search result: a song a source can `get()`.

#### *property* key *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"<source>:<id>"`, the song’s name for [`get_song()`](#songleaf.get_song) and the store.

#### to_dict()

The JSON-ready form.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* songleaf.KaggleChordsSource(, loader=None, min_score=70)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The Kaggle *chords-and-lyrics* corpus (~135K songs, chords over lyrics).

Read through `sung` from a local copy of the zip, with no Kaggle
credentials needed when that copy exists. The corpus was scraped from a
chords site: personal use only (licence tag `gray`).

Title and artist are matched fuzzily (typos, punctuation and word order
do not matter); lyrics must contain every word of the `lyrics` query as a
whole word. Lyrics matches are not ranked beyond popularity.

* **Parameters:**
  * **loader** – `() -> pandas.DataFrame` with `columns`. Defaults to
    sung’s loader of the local corpus zip.
  * **min_score** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Fuzzy-match cutoff, 0-100.

#### get(song_id)

The song with this id, parsed into a [`Song`](#songleaf.Song).

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

#### search(query='', , title='', artist='', lyrics='', limit=10)

Songs matching every given constraint, best first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](songleaf.sources.html.md#songleaf.sources.Hit)]

### *class* songleaf.Song(text, annotations=<factory>, meta=<factory>, provenance=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Lyrics text plus annotations, metadata and provenance.

* **Parameters:**
  * **text** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The lyrics, lines separated by `"\n"`.
  * **annotations** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Annotation`](songleaf.model.html.md#songleaf.model.Annotation)]) – Standoff annotations over `text` (kept sorted by start).
  * **meta** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Descriptive fields: `title`, `artist`, `capo`, `key`, …
  * **provenance** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Where the song came from: `source`, `id`, `url`, `license`.

#### *classmethod* from_dict(data)

The inverse of [`to_dict()`](#songleaf.Song.to_dict).

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

#### lines()

The lines of the text, with their offsets.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`Line`](songleaf.model.html.md#songleaf.model.Line)]

#### of_kind(kind)

The annotations of one kind, in text order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Annotation`](songleaf.model.html.md#songleaf.model.Annotation)]

#### to_dict()

The JSON-ready form (what the store persists).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.chord(at, symbol, , timing='at')

A chord landing on the syllable that starts at offset `at`.

* **Return type:**
  [`Annotation`](songleaf.model.html.md#songleaf.model.Annotation)

### songleaf.fit_font_size(song, , page_size='A4', margin=14.0, style=None, min_font_size=6.0, max_font_size=72.0, precision=0.05)

The largest lyric font size at which `song` fits one page.

`min_font_size` if even that does not fit (the song then needs more pages).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.get_song(key, , sources=None)

The song named by `key` (`"<source>:<id>"`), from the source of that name.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.parse_chords_over_lyrics(raw, , meta=None, provenance=None)

Parse chords-over-lyrics text into a [`Song`](#songleaf.Song).

* **Parameters:**
  * **raw** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The chord chart, chord lines column-aligned over lyric lines.
  * **meta** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Metadata to start from (`title`, `artist`, …); `capo`,
    `key` and `tuning` found in the text are added to it.
  * **provenance** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Where the text came from, stored as is.
* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.render_dense_a4(song, output, , page_size='A4', margin=14.0, style=None, min_font_size=6.0, max_font_size=72.0)

Render `song` as a PDF to `output` (a path or a binary file object).

Returns `{"path", "font_size", "pages", "rows"}`; `path` is `None`
when `output` is a file object.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.score_link(start, end, , source, id, url='', format='')

A link from `[start, end)` to a score snippet held by a source.

* **Return type:**
  [`Annotation`](songleaf.model.html.md#songleaf.model.Annotation)

### songleaf.search(query='', , title='', artist='', lyrics='', limit=10, sources=None)

Search every source and merge the hits, best first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](songleaf.sources.html.md#songleaf.sources.Hit)]

```pycon
>>> search("paper boats", sources=[])
[]
```

### songleaf.section(start, end, label)

A section (verse, chorus, …) spanning `[start, end)`.

* **Return type:**
  [`Annotation`](songleaf.model.html.md#songleaf.model.Annotation)

### songleaf.sheet(query, , output='', pick=1, refresh=False, sources=None, store=None, renderer=None)

Make a one-page song sheet (PDF) for the best match of `query`.

`query` may also be a song key, as `search` and `songs` show them
(`kaggle_chords:1234`): a stored song renders without searching, and the
key of a known source is fetched from it directly. `pick` chooses the n-th
best match instead of the best. The song is saved to the store; `refresh`
fetches it from its source again, replacing the stored copy. The PDF goes to
`output`, by default the `sheets` data directory.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.song_store(rootdir=None)

Songs as JSON files in `rootdir` (default: the `songs` data dir).

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Song`](songleaf.model.html.md#songleaf.model.Song)]

### songleaf.songs(, store=None)

The keys of the stored songs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### Modules

| [`model`](songleaf.model.html.md#module-songleaf.model)     | The linked-artifact model: a song is lyrics text plus standoff annotations.                                     |
|----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| [`parse`](songleaf.parse.html.md#module-songleaf.parse)     | Parse chords-over-lyrics text into a [`Song`](songleaf.model.html.md#songleaf.model.Song). |
| [`render`](songleaf.render.html.md#module-songleaf.render)   | Render a song onto one dense A4 page, with the lyrics as large as will fit.                                     |
| [`sources`](songleaf.sources.html.md#module-songleaf.sources) | Where songs are found: sources, and a search that composes them.                                                |
| [`store`](songleaf.store.html.md#module-songleaf.store)     | Where songs persist: a `MutableMapping` of songs, JSON files by default.                                        |
| [`tools`](songleaf.tools.html.md#module-songleaf.tools)     | The single source of truth for every surface: plain functions, flat arguments, JSON-ready results.              |
