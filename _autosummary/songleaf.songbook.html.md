# songleaf.songbook

A songbook: several songs in one PDF, with a table of contents, page numbers and bookmarks.

`render_songbook(songs, output)` renders each song through the same renderer
a single sheet uses (so each is at its fitted size), puts a table of contents
in front, stamps “page n of N” at the foot of every page and adds one PDF
bookmark per song. The renderer is a seam, as in [`songleaf.tools.sheet()`](songleaf.tools.html.md#songleaf.tools.sheet).

### Functions

| [`render_songbook`](#songleaf.songbook.render_songbook)(songs, output, \*[, title, ...])   | Render `songs` (`(key, song)` pairs, in set-list order) as one PDF to `output`.   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|

### songleaf.songbook.render_songbook(songs, output, , title='Songbook', renderer=None, page_size='A4', toc_size=12.0, footer_size=8.0)

Render `songs` (`(key, song)` pairs, in set-list order) as one PDF to `output`.

`output` is a path or a binary file object. `renderer` is a
`(song, output) -> dict` renderer (default: the dense layout). Returns
`{"path", "title", "pages", "songs": [{"key", "title", "artist", "page"}]}`
where `page` is the song’s first page in the book.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
