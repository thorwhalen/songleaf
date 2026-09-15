# songleaf.store

Where songs persist: a `MutableMapping` of songs, JSON files by default.

Data lives under `~/.local/share/songleaf/<kind>/` (`songs/` for the store,
`sheets/` for rendered PDFs); `SONGLEAF_DATA_DIR` overrides the root.
Keys are song keys (`"<source>:<id>"`). Each song is one JSON file named after
its key, percent-encoded so that any key is a safe file name, and two keys that
differ only in letter case never share a file on a case-insensitive file system.

```pycon
>>> import tempfile
>>> from songleaf.model import Song
>>> songs = song_store(tempfile.mkdtemp())
>>> songs["demo:1"] = Song("la la la", meta={"title": "Demo"})
>>> list(songs), songs["demo:1"].title
(['demo:1'], 'Demo')
```

### Module Attributes

| [`DATA_DIR_ENVVAR`](#songleaf.store.DATA_DIR_ENVVAR)   | Environment variable overriding the data root.   |
|--------------------------------------------------------------------|--------------------------------------------------|

### Functions

| [`data_dir`](#songleaf.store.data_dir)(kind)        | The directory holding one kind of data (created if missing).      |
|------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`file_name_of_key`](#songleaf.store.file_name_of_key)(key) | The file name a song key is stored under.                         |
| [`song_store`](#songleaf.store.song_store)([rootdir]) | Songs as JSON files in `rootdir` (default: the `songs` data dir). |

### songleaf.store.DATA_DIR_ENVVAR *= 'SONGLEAF_DATA_DIR'*

Environment variable overriding the data root.

### songleaf.store.data_dir(kind)

The directory holding one kind of data (created if missing).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.store.file_name_of_key(key)

The file name a song key is stored under.

Every byte but lowercase ASCII letters, digits and `-_.` is percent-encoded
(uppercase letters included), so the name is safe everywhere and distinct from
every other key’s name even when letter case is ignored.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> file_name_of_key("kaggle_chords:0"), file_name_of_key("src:Abc")
('kaggle_chords%3A0.json', 'src%3A%41bc.json')
```

### songleaf.store.song_store(rootdir=None)

Songs as JSON files in `rootdir` (default: the `songs` data dir).

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Song`](songleaf.model.html.md#songleaf.model.Song)]
