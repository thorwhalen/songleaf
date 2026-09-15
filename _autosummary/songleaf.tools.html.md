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

| [`search`](#songleaf.tools.search)([query, title, artist, lyrics, ...])    | Find songs: fuzzy title and artist (`query`), or by title, artist, or whole words of the lyrics.   |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| [`sheet`](#songleaf.tools.sheet)(query, \*[, output, pick, refresh, ...]) | Make a one-page song sheet (PDF) for the best match of `query`.                                    |
| [`songs`](#songleaf.tools.songs)(\*[, store])                             | The keys of the stored songs.                                                                      |

### songleaf.tools.TOOLS *= (<function search>, <function sheet>, <function songs>)*

Every operation, in the order the CLI lists them.

### songleaf.tools.search(query='', , title='', artist='', lyrics='', limit=10, sources=None)

Find songs: fuzzy title and artist (`query`), or by title, artist, or whole words of the lyrics.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### songleaf.tools.sheet(query, , output='', pick=1, refresh=False, sources=None, store=None, renderer=None)

Make a one-page song sheet (PDF) for the best match of `query`.

`query` may also be a song key, as `search` and `songs` show them
(`kaggle_chords:1234`): a stored song renders without searching, and the
key of a known source is fetched from it directly. `pick` chooses the n-th
best match instead of the best. The song is saved to the store; `refresh`
fetches it from its source again, replacing the stored copy. The PDF goes to
`output`, by default the `sheets` data directory.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.tools.songs(, store=None)

The keys of the stored songs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
