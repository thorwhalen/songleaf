# songleaf.sources

Where songs are found: sources, and a search that composes them.

A *source* is any object with a `name`, a
`search(query, *, title, artist, lyrics, limit) -> list[Hit]` method and a
`get(song_id) -> Song` method that raises `KeyError` for an id it does not
have ([`get_song()`](#songleaf.sources.get_song) reports that as [`SongNotFound`](#songleaf.sources.SongNotFound); a source that cannot
load its data at all raises [`SourceUnavailable`](#songleaf.sources.SourceUnavailable)). [`search()`](#songleaf.sources.search) and [`get_song()`](#songleaf.sources.get_song) take
several through `sources=`; the default is the Kaggle chords-and-lyrics
corpus, read through `sung`.

A hit’s [`Hit.key`](#songleaf.sources.Hit.key) (`"<source>:<id>"`) names the song everywhere: it is
what [`get_song()`](#songleaf.sources.get_song) resolves and what the store is keyed by.

[`search_tiers()`](#songleaf.sources.search_tiers) is the one-field search: the songs whose title, artist or lyrics
match a query, each reported once, in the first of those that matches. A source may answer
it itself with a `search_tiers(query, *, limit)` method (the Kaggle sources do, in one
pass); any other source is asked three times through `search`.

### Module Attributes

| [`KAGGLE_CHORDS_ZIP`](#songleaf.sources.KAGGLE_CHORDS_ZIP)   | Where a copy of the corpus zip is found under the data root, before sung looks.   |
|----------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`SONG_TIERS`](#songleaf.sources.SONG_TIERS)          | a song is in the first that fits.                                                 |

### Functions

| [`default_sources`](#songleaf.sources.default_sources)()                           | The sources used when none are given, built once per process.                                                                           |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`get_song`](#songleaf.sources.get_song)(key, \*[, sources])                | The song named by `key` (`"<source>:<id>"`), from the source of that name.                                                              |
| [`kaggle_chords_zip`](#songleaf.sources.kaggle_chords_zip)()                         | The corpus zip under the data root (`datasets/` + [`KAGGLE_CHORDS_ZIP`](#songleaf.sources.KAGGLE_CHORDS_ZIP)), if there is one. |
| [`search`](#songleaf.sources.search)([query, title, artist, lyrics, ...]) | Search every source and merge the hits, best first.                                                                                     |
| [`search_tiers`](#songleaf.sources.search_tiers)(query, \*[, limit, sources])   | Every source's songs whose title, artist or lyrics match `query`, by where they match.                                                  |

### Classes

| [`Hit`](#songleaf.sources.Hit)(source, id, title[, artist, score, meta])   | One search result: a song a source can `get()`.                          |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`KaggleChordsSource`](#songleaf.sources.KaggleChordsSource)(\*[, loader, min_score])     | The Kaggle *chords-and-lyrics* corpus (~135K songs, chords over lyrics). |
| [`LocalFolderSource`](#songleaf.sources.LocalFolderSource)([root, name])                 | A folder of files you exported yourself, indexed and searched by name.   |

### Exceptions

| [`SongNotFound`](#songleaf.sources.SongNotFound)      | No song by that key, id or query.                                                  |
|--------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`SourceUnavailable`](#songleaf.sources.SourceUnavailable) | A source's data cannot be loaded here (a corpus that is not on this machine, say). |

### *class* songleaf.sources.Hit(source, id, title, artist='', score=0.0, meta=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One search result: a song a source can `get()`.

#### *property* key *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"<source>:<id>"`, the song’s name for [`get_song()`](#songleaf.sources.get_song) and the store.

#### to_dict()

The JSON-ready form.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.sources.KAGGLE_CHORDS_ZIP *= 'chords-and-lyrics/chords-and-lyrics-dataset.zip'*

Where a copy of the corpus zip is found under the data root, before sung looks.

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

#### search_tiers(query, , limit=10)

The songs whose title, artist or lyrics match `query`, by where they match.

`{"title": [...], "artist": [...], "lyrics": [...]}`, at most `limit` in each,
best first. A song is in the first kind it matches, even when it ranks below the
limit there, so a song is never shown as an artist match because more titles
matched.

Title and artist match word by word ([`WordIndex`](songleaf.match.html.md#songleaf.match.WordIndex)): the query
is inside the field (`"wonder"` finds *Wonderwall*) or the field is inside the
query (`"wonderwall oasis"` finds the title *Wonderwall* and the artist *Oasis*),
a word of four letters or more forgiving a typo; or every word of the query is in
the title or in the artist (`"paper boats invented band"`). A song whose title
holds a word of the query that its artist does not is a title match
(`"wonderwall oasis"`: *Wonderwall (ver. 2)* by Oasis), otherwise an artist match. Within each kind, the songs whose
title and artist together hold the most words of the query come first (so
*Wonderwall* by Oasis leads), then the closest by fuzzy score (of the title, or of
title and artist, whichever is closer; of the artist), then the most popular.
Lyrics hold every word of the query, rank by popularity, and carry
`meta["snippet"]`: the line that matched, with its spans.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]]

### *class* songleaf.sources.LocalFolderSource(root=None, , name='local_folder')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A folder of files you exported yourself, indexed and searched by name.

For files a chords/tab site lets a paying user export – Ultimate Guitar’s
Guitar Pro/PDF downloads, MuseScore’s MusicXML/MSCZ/MIDI/PDF exports – with
no automated route into either site (songleaf#5, songleaf#6): the user
exports the file through the site as usual and drops it here. No network
calls, no login; this only reads what is already on disk.

Text files (`.txt`, `.cho`, `.chopro`, `.crd`, `.pro`) are parsed
as chords-over-lyrics charts, the same format as the Kaggle corpus. Files
with no lyrics to parse (Guitar Pro, MusicXML, MSCZ, MIDI, PDF) become a
[`Song`](songleaf.model.html.md#songleaf.model.Song) with empty text and one
[`score_link()`](songleaf.model.html.md#songleaf.model.score_link) annotation pointing at the file, so a
renderer can still show it as an attached score snippet.

A file is named `"Artist - Title.ext"` (the artist part is optional; a
plain `"Title.ext"` works too).

* **Parameters:**
  * **root** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Directory to index (searched recursively). Defaults to the
    `imports` data dir (`~/.local/share/songleaf/imports/`,
    moved by `SONGLEAF_DATA_DIR`).
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Registry name (default `"local_folder"`).

```pycon
>>> import tempfile, pathlib
>>> root = tempfile.mkdtemp()
>>> _ = (pathlib.Path(root) / "Nobody - Paper Boats.txt").write_text(
...     "C\nla la la"
... )
>>> local = LocalFolderSource(root)
>>> hit = local.search("paper boats")[0]
>>> (hit.title, hit.artist)
('Paper Boats', 'Nobody')
>>> local.get(hit.id).of_kind("chord")[0].body["symbol"]
'C'
```

#### get(song_id)

The song at this relative path, parsed if it’s a chart, else score-linked.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

#### search(query='', , title='', artist='', lyrics='', limit=10)

Substring-match the query/title/artist against each file’s name.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]

### songleaf.sources.SONG_TIERS *= ('title', 'artist', 'lyrics')*

a song is in the first that fits.

* **Type:**
  The kinds of match [`search_tiers()`](#songleaf.sources.search_tiers) reports, in order

### *exception* songleaf.sources.SongNotFound

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

No song by that key, id or query. A `KeyError`, so `except KeyError` still catches it.

### *exception* songleaf.sources.SourceUnavailable

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A source’s data cannot be loaded here (a corpus that is not on this machine, say).

### songleaf.sources.default_sources()

The sources used when none are given, built once per process.

The Kaggle corpus is read from its search index when one has been built
(`songleaf build-index`): the same songs and keys, in tens of MB rather
than the GB the whole corpus takes in memory.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### songleaf.sources.get_song(key, , sources=None)

The song named by `key` (`"<source>:<id>"`), from the source of that name.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.sources.kaggle_chords_zip()

The corpus zip under the data root (`datasets/` + [`KAGGLE_CHORDS_ZIP`](#songleaf.sources.KAGGLE_CHORDS_ZIP)), if there is one.

`$SUNG_CHORDS_AND_LYRICS_ZIP`, when set, wins: then this is `None` and
sung reads the variable itself.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.sources.search(query='', , title='', artist='', lyrics='', limit=10, sources=None)

Search every source and merge the hits, best first.

```pycon
>>> search("paper boats", sources=[])
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]

### songleaf.sources.search_tiers(query, , limit=10, sources=None)

Every source’s songs whose title, artist or lyrics match `query`, by where they match.

`{"title": [...], "artist": [...], "lyrics": [...]}` ([`SONG_TIERS`](#songleaf.sources.SONG_TIERS)), at most
`limit` in each; each song in the first kind it matches. Within a kind, each
source’s hits come in its own ranking, the sources in the order given.

```pycon
>>> search_tiers("paper boats", sources=[])
{'title': [], 'artist': [], 'lyrics': []}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Hit`](#songleaf.sources.Hit)]]
