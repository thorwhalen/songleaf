# songleaf.kaggle_index

A search index of the Kaggle corpus: the same songs and keys, without the corpus in memory.

[`KaggleChordsSource`](songleaf.sources.html.md#songleaf.sources.KaggleChordsSource) holds the whole corpus as a
DataFrame: about 1.1 GB per process, 1.6 GB once a lyrics search has run, and
every web worker holds its own copy. [`build_kaggle_index()`](#songleaf.kaggle_index.build_kaggle_index) writes it once
to one SQLite file beside the zip (`datasets/chords-and-lyrics/`): titles,
artists, popularity, each chart zlib-compressed, and an FTS5 table of the
charts’ words. [`KaggleChordsIndex`](#songleaf.kaggle_index.KaggleChordsIndex) reads that file. It keeps only the
titles, artists and popularity in memory (for fuzzy matching, a few tens of MB)
and answers lyrics searches and song lookups from disk.

Search results are the DataFrame source’s: the ranking code is shared, and only
where the data comes from differs. The one difference is how lyrics split into
words: FTS5’s tokenizer treats `_` as a separator and does not compose
decomposed accents, where the DataFrame source’s regular expression does the
opposite. Rebuilding the index while a server runs is safe: a process that
notices the file changed reloads it.

```pycon
>>> import pandas as pd, tempfile, os
>>> corpus = pd.DataFrame({
...     "Unnamed: 0": [1, 2], "artist_name": ["The Band", "Other"],
...     "song_name": ["Paper Boats", "Quiet Road"], "lang": ["en", "en"],
...     "popularity": [3, 1], "chords&lyrics": ["G\nPaper boats drift", "C\nquiet road"],
... })
>>> path = os.path.join(tempfile.mkdtemp(), "index.sqlite")
>>> build_kaggle_index(path=path, loader=lambda: corpus)["songs"]
2
>>> [hit.key for hit in KaggleChordsIndex(path).search(lyrics="boats")]
['kaggle_chords:1']
```

### Module Attributes

| [`KAGGLE_INDEX_NAME`](#songleaf.kaggle_index.KAGGLE_INDEX_NAME)   | The index's file name, beside the corpus zip under `datasets/`.   |
|----------------------------------------------------------------------|-------------------------------------------------------------------|

### Functions

| [`build_kaggle_index`](#songleaf.kaggle_index.build_kaggle_index)(\*[, path, loader, batch_size])   | Write the index of the Kaggle corpus (`loader`: as for `KaggleChordsSource`).   |
|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`kaggle_index_path`](#songleaf.kaggle_index.kaggle_index_path)()                                  | Where the index lives: beside the corpus zip, under the data root.              |

### Classes

| [`KaggleChordsIndex`](#songleaf.kaggle_index.KaggleChordsIndex)([path, min_score])   | The Kaggle corpus read from its index ([`build_kaggle_index()`](#songleaf.kaggle_index.build_kaggle_index)).   |
|-----------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|

### songleaf.kaggle_index.KAGGLE_INDEX_NAME *= 'chords-and-lyrics.sqlite'*

The index’s file name, beside the corpus zip under `datasets/`.

### *class* songleaf.kaggle_index.KaggleChordsIndex(path=None, , min_score=70)

Bases: [`KaggleChordsSource`](songleaf.sources.html.md#songleaf.sources.KaggleChordsSource)

The Kaggle corpus read from its index ([`build_kaggle_index()`](#songleaf.kaggle_index.build_kaggle_index)).

The same `name` and ids as `KaggleChordsSource`, so song keys and
stored songs carry over. Only the columns fuzzy matching needs are held in
memory; charts and lyrics matches come from the file.

#### get(song_id)

The song with this id, parsed into a `Song`.

#### search(query='', \*\*constraints)

Songs matching every given constraint, best first.

### songleaf.kaggle_index.build_kaggle_index(, path=None, loader=None, batch_size=5000)

Write the index of the Kaggle corpus (`loader`: as for `KaggleChordsSource`).

Loading the corpus takes the memory the index exists to avoid, so run this
once, apart from any server (`songleaf build-index`). The file is written
beside the target and moved into place when complete, so a reader never
sees half an index.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.kaggle_index.kaggle_index_path()

Where the index lives: beside the corpus zip, under the data root.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
