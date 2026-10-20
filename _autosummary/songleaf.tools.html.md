# songleaf.tools

The single source of truth for every surface: plain functions, flat arguments, JSON-ready results.

The CLI (`python -m songleaf`) is `cw` over [`TOOLS`](#songleaf.tools.TOOLS). Nothing here
knows about any surface. `sources`, `store` and `renderer` are the seams:
library callers pass them, the CLI hides them. Code that wants objects rather
than dicts uses [`songleaf.sources`](songleaf.sources.html.md#module-songleaf.sources), [`songleaf.store`](songleaf.store.html.md#module-songleaf.store) and
[`songleaf.render`](songleaf.render.html.md#module-songleaf.render) directly.

### Module Attributes

| [`TOOLS`](#songleaf.tools.TOOLS)   | Every operation, in the order the CLI lists them.   |
|----------------------------------------------------------|-----------------------------------------------------|

### Functions

| [`build_index`](#songleaf.tools.build_index)(\*[, path])                           | Build the search index of the Kaggle corpus, once, where the corpus zip is.                                |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`export`](#songleaf.tools.export)(query, \*[, format, transpose, ...])       | Export a song as ChordPro (`chordpro`) or plain text with chords over lyrics (`text`).                     |
| [`forget`](#songleaf.tools.forget)(key, \*[, store, library_root])            | Remove a song from the stored songs, from every list it was in, and from every Viewed list.                |
| [`import_file`](#songleaf.tools.import_file)([path, title, artist, url, ...])      | Read pasted song text from a file (`-`: standard input) and store it; see `import_text`.                   |
| [`import_text`](#songleaf.tools.import_text)(text, \*[, title, artist, url, ...])  | Store a song pasted from anywhere: Ultimate Guitar markup, ChordPro, OpenSong or plain chords over lyrics. |
| [`import_url`](#songleaf.tools.import_url)(url, \*[, refresh, store, source])     | Fetch one community Ultimate Guitar chord page and store its chart as `ug:<id>`.                           |
| [`media`](#songleaf.tools.media)(query, \*[, youtube, spotify, pick, ...])   | Link the song's recording: a YouTube video and/or a Spotify track, by id or link.                          |
| [`search`](#songleaf.tools.search)([query, title, artist, lyrics, ...])       | Find songs with one query: in your lists' names, then titles, artists and lyrics.                          |
| [`sheet`](#songleaf.tools.sheet)(query, \*[, output, pick, refresh, ...])    | Make a one-page song sheet (PDF) for the best match of `query`.                                            |
| [`snippet`](#songleaf.tools.snippet)(query, notation, \*[, line, format, ...]) | Put a score snippet over one line of a song; the `score` layout draws it on the sheet.                     |
| [`song`](#songleaf.tools.song)(query, \*[, pick, refresh, ...])             | The song itself as JSON: lyrics text, chords and sections, and every key it can move to.                   |
| [`songbook`](#songleaf.tools.songbook)(group, \*[, output, title, layout, ...]) | Render a list (group) of songs as one PDF: a table of contents, then every song at its fitted size.        |
| [`songs`](#songleaf.tools.songs)(\*[, store])                                | The keys of the stored songs.                                                                              |
| [`sync`](#songleaf.tools.sync)(query, \*[, lrc, lrclib, pick, store, ...])  | Time the song's lines from an LRC, so the page can scroll with the recording.                              |
| [`unview`](#songleaf.tools.unview)(key, \*[, user, library_root])             | Take a song out of `user`'s Viewed list.                                                                   |
| [`view`](#songleaf.tools.view)(key, \*[, user, at, store, library_root])    | Put a stored song at the top of `user`'s Viewed list: they just opened it.                                 |
| [`viewed`](#songleaf.tools.viewed)(\*[, user, store, library_root])           | The songs `user` opened, the most recent first: `key`, `title`, `artist`, `viewed_at`.                     |

### songleaf.tools.TOOLS *= (<function search>, <function sheet>, <function songbook>, <function song>, <function export>, <function songs>, <function import_file>, <function import_url>, <function viewed>, <function view>, <function unview>, <function forget>, <function build_index>, <function sync>, <function media>, <function snippet>)*

Every operation, in the order the CLI lists them.

### songleaf.tools.build_index(, path='')

Build the search index of the Kaggle corpus, once, where the corpus zip is.

Searching then reads the index instead of loading the whole corpus into
memory (tens of MB instead of over a GB per process). Run it again after
replacing the zip. `path` defaults to beside the zip under the data root.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.export(query, , format='chordpro', transpose=0, output='', pick=1, refresh=False, sources=None, store=None)

Export a song as ChordPro (`chordpro`) or plain text with chords over lyrics (`text`).

`query` is a song key or a search, as for `sheet`. `transpose` moves every chord
by that many semitones (the stored song keeps its chords). The result has the `text`;
with `output` set it is also written to that file, and `path` says where.
ChordPro is the fleet’s interchange (Songbook Pro, OnSong and the ChordPro app read it);
chords that sound before their syllable travel in the `x_songleaf_before` directive.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.forget(key, , store=None, library_root=None)

Remove a song from the stored songs, from every list it was in, and from every Viewed list.

It can be found and stored again by searching. Returns `{"key", "deleted"}`;
`deleted` is False when it was not stored.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.import_file(path='-', , title='', artist='', url='', format='', store=None)

Read pasted song text from a file (`-`: standard input) and store it; see `import_text`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.import_text(text, , title='', artist='', url='', key='', capo='', format='', store=None)

Store a song pasted from anywhere: Ultimate Guitar markup, ChordPro, OpenSong or plain chords over lyrics.

The format is detected (`format` forces one of `ultimate-guitar`,
`chordpro`, `opensong`, `chords-over-lyrics`). `url` is only
recorded as provenance: songleaf never contacts it (an official or Pro
Ultimate Guitar URL is refused). The song is stored under `paste:<hash>`
(the same text, the same key), or `ug:<id>` for an Ultimate Guitar URL,
and is then usable like any other: `sheet <key>`, `song <key>`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.import_url(url, , refresh=False, store=None, source=None)

Fetch one community Ultimate Guitar chord page and store its chart as `ug:<id>`.

Local command line only, and off unless `SONGLEAF_UG_URL=1` is set: prefer
pasting, or the bookmarklet run on the page you opened (see
`songleaf.ultimate_guitar`). Official and Pro pages are refused. A chart
already stored is not fetched again unless `refresh`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.media(query, , youtube='', spotify='', pick=1, store=None, sources=None)

Link the song’s recording: a YouTube video and/or a Spotify track, by id or link.

An id given as `""` is left as it is; `"-"` removes it. Returns
`{"key", "media"}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.search(query='', , title='', artist='', lyrics='', limit=10, list_songs=3, sources=None, store=None, library_root=None)

Find songs with one query: in your lists’ names, then titles, artists and lyrics.

With only `query`, every song comes once, tagged with where it matched (`match`):
`"list"` (the first `list_songs` stored songs of each list whose name the query
names; `list` and `list_name` say which, and the list’s other songs are found in
the later kinds as usual), then `"title"`, `"artist"` and `"lyrics"`, in that order,
at most `limit` of each, best first within each. A song that matches its title and
its lyrics is a title match only. `highlight` holds the matched words of the title and
artist (and of `list_name`) as `[start, end]` spans; a lyrics match carries
`snippet`, the line that matched, with its spans.

With `title`, `artist` or `lyrics`, it is a narrower search instead: songs that
match every field given (and `query`, fuzzily over title and artist), `match: ""`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### songleaf.tools.sheet(query, , output='', pick=1, refresh=False, layout='dense', transpose=0, scale=1.0, sources=None, store=None, renderer=None)

Make a one-page song sheet (PDF) for the best match of `query`.

`query` may also be a song key, as `search` and `songs` show them
(`kaggle_chords:1234`): a stored song renders without searching, and the
key of a known source is fetched from it directly. `pick` chooses the n-th
best match instead of the best. The song is saved to the store; `refresh`
fetches it from its source again, replacing the stored copy. The PDF goes to
`output`, by default the `sheets` data directory.

`layout` is `dense` (the default), or options joined with `+`:
`overlap` (chords over the words themselves), `inline` (chords in the
line, before their syllable), `packed` (rows break where the lyrics do),
`two-column`, `shaded` (sections, repeated lines and chord functions);
for example `inline+packed+two-column`. A `renderer` decides the layout
itself, so it does not go with `layout` or `scale`.

`transpose` moves every chord by that many semitones (spelled for the new
key); the stored song keeps its chords. `scale` multiplies the font size
that fills the page: `0.8` for smaller type, `1.2` for larger type over
more pages.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.snippet(query, notation, , line=0, format='abc', pick=1, store=None, sources=None)

Put a score snippet over one line of a song; the `score` layout draws it on the sheet.

`notation` is a few bars of ABC (`"G2 AB c2 | d4"`; the unit is an eighth
note). `line` is the 1-based lyric line it goes with; `0` lets the rule
choose (the first line of the chorus, else the most repeated line, else the
first). `format` may also be `musicxml` or `mei` (drawn with the
`score` extra only). Returns `{"key", "start", "end", "rule"}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.song(query, , pick=1, refresh=False, transpositions=6, sources=None, store=None)

The song itself as JSON: lyrics text, chords and sections, and every key it can move to.

`query` is a song key or a search, as for `sheet`; the song is stored
the same way. Besides the song’s own fields (`text`, `annotations`,
`meta`, `provenance`), the result has `chords` (the distinct chords,
in order of first appearance), `sections` (`{"start", "end", "label",
"family"}`, the family as the printed sheet shades it: `"chorus"`,
`"bridge"` or `""`), `song_key` (the estimated key, `""` with
no chords) and `transpositions`: one table per shift from
`-transpositions + 1` to `transpositions` semitones, each
`{"semitones", "key", "chords": {original: transposed}}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.songbook(group, , output='', title='', layout='dense', scale=1.0, library_root=None, sources=None, store=None, renderer=None)

Render a list (group) of songs as one PDF: a table of contents, then every song at its fitted size.

`group` is a list’s id or its name (the best match of the name). The
songs come in the order they were filed in the list, nested lists
included, so the list order is the set list. Page numbers are stamped on
every page and each song is a PDF bookmark. `title` defaults to the
list’s name. `layout` and `scale` are as for `sheet`. The PDF goes to
`output`, by default the `sheets` data directory.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.songs(, store=None)

The keys of the stored songs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.tools.sync(query, , lrc='', lrclib=False, pick=1, store=None, sources=None, get_json=None)

Time the song’s lines from an LRC, so the page can scroll with the recording.

`lrc` is the LRC text (an `.lrc` file’s content); with `lrclib` and no
`lrc`, LRCLIB is asked for the song’s synced lyrics. Only the times are stored
(`"time"` annotations), never the LRC’s text. Returns `{"key", "timed",
"lines"}`: how many lyric lines got a time, of how many.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.unview(key, , user='', library_root=None)

Take a song out of `user`’s Viewed list. It stays stored, and in its lists.

Returns `{"key", "removed", "viewed_at"}`: when it had been viewed, so the same
time can be given back to [`view()`](#songleaf.tools.view) to undo.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.view(key, , user='', at=0.0, store=None, library_root=None)

Put a stored song at the top of `user`’s Viewed list: they just opened it.

`at` (seconds since the epoch) records that time instead, which is how an undo puts
a song it took out back where it was. Returns `{"key", "viewed_at"}`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.viewed(, user='', store=None, library_root=None)

The songs `user` opened, the most recent first: `key`, `title`, `artist`, `viewed_at`.

`user` is who the host says is asking (no one: the list everyone shares). Songs no
longer stored are left out. `viewed_at` is in seconds since the epoch.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
