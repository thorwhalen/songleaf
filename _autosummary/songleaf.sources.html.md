# songleaf.sources

Where songs are found: sources, and a search that composes them.

A *source* is any object with a `name`, a
`search(query, *, title, artist, lyrics, limit) -> list[Hit]` method and a
`get(song_id) -> Song` method. [`search()`](#songleaf.sources.search) and [`get_song()`](#songleaf.sources.get_song) take
several through `sources=`; the default is the Kaggle chords-and-lyrics
corpus, read through `sung`.

A hit’s [`Hit.key`](#songleaf.sources.Hit.key) (`"<source>:<id>"`) names the song everywhere: it is
what [`get_song()`](#songleaf.sources.get_song) resolves and what the store is keyed by.

### Functions

| [`default_sources`](#songleaf.sources.default_sources)()                           | The sources used when none are given, built once per process.              |
|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`get_song`](#songleaf.sources.get_song)(key, \*[, sources])                | The song named by `key` (`"<source>:<id>"`), from the source of that name. |
| [`search`](#songleaf.sources.search)([query, title, artist, lyrics, ...]) | Search every source and merge the hits, best first.                        |

### Classes

| [`Hit`](#songleaf.sources.Hit)(source, id, title[, artist, score, meta])   | One search result: a song a source can `get()`.                          |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`KaggleChordsSource`](#songleaf.sources.KaggleChordsSource)(\*[, loader, min_score])     | The Kaggle *chords-and-lyrics* corpus (~135K songs, chords over lyrics). |

### *class* songleaf.sources.Hit(source, id, title, artist='', score=0.0, meta=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One search result: a song a source can `get()`.

#### *property* key *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"<source>:<id>"`, the song’s name for [`get_song()`](#songleaf.sources.get_song) and the store.

#### to_dict()

The JSON-ready form.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### *class* songleaf.sources.KaggleChordsSource(, loader=None, min_score=70)

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

The song with this id, parsed into a `Song`.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

#### search(query='', , title='', artist='', lyrics='', limit=10)

Songs matching every given constraint, best first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]

### songleaf.sources.default_sources()

The sources used when none are given, built once per process.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### songleaf.sources.get_song(key, , sources=None)

The song named by `key` (`"<source>:<id>"`), from the source of that name.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.sources.search(query='', , title='', artist='', lyrics='', limit=10, sources=None)

Search every source and merge the hits, best first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]

```pycon
>>> search("paper boats", sources=[])
[]
```
