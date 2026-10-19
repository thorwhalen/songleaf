# songleaf.datasets

Where the `datasets` data kind lives: local files by default, S3 by configuration.

The corpus files (`chords-and-lyrics/...`) are addressed by their path relative
to the `datasets` kind. ADR-0024 makes the S3 key mirror the local layout, so a
store over disk (`dol.Files`) and a store over S3 (`s3dol`) hold the same
relative keys, and [`dataset_path()`](#songleaf.datasets.dataset_path) is the one place that turns a key into a
real file (SQLite and zip readers need one).

Configuration (environment; `SONGLEAF_DATA_DIR` always wins, so a pinned local
root is never overridden by S3):

- `SONGLEAF_DATASETS_URI`: `s3://bucket/prefix` of the `datasets` kind
  (for example `s3://tw-apps/thorwhalen/songleaf/datasets`). Unset means local.
- `SONGLEAF_S3_PROFILE`: the AWS profile to read with (optional).
- `SONGLEAF_CACHE_DIR`: where S3 objects are cached (default
  `~/.cache/songleaf/datasets`).

### Functions

| [`dataset_path`](#songleaf.datasets.dataset_path)(key, \*[, location])        | The path of a real file for the dataset `key` (relative path), cached if remote.   |
|-------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`datasets_store`](#songleaf.datasets.datasets_store)(\*[, location, readonly]) | The `datasets` kind as a `MutableMapping[str, bytes]` keyed by relative path.      |
| [`s3_location`](#songleaf.datasets.s3_location)([environ])                   | The configured S3 home of the datasets, or `None` when they are local.             |

### Classes

| [`S3Location`](#songleaf.datasets.S3Location)(bucket, prefix[, profile])   |    |
|------------------------------------------------------------------------------------------|----|

### *class* songleaf.datasets.S3Location(bucket, prefix, profile=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

### songleaf.datasets.dataset_path(key, , location=None)

The path of a real file for the dataset `key` (relative path), cached if remote.

Local: `<data root>/datasets/<key>` (it may not exist). On S3: the object is
downloaded once to the cache (a missing object leaves no file, so the path
does not exist) and the cached path is returned; an object whose size changed
on S3 is fetched again.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.datasets.datasets_store(, location=None, readonly=True)

The `datasets` kind as a `MutableMapping[str, bytes]` keyed by relative path.

`dol.Files` over the local folder unless S3 is configured (or `location`
is given), then `s3dol` (the `s3` extra).

### songleaf.datasets.s3_location(environ=None)

The configured S3 home of the datasets, or `None` when they are local.

```pycon
>>> s3_location({"SONGLEAF_DATASETS_URI": "s3://b/x/datasets"})
S3Location(bucket='b', prefix='x/datasets/', profile=None)
>>> s3_location({})
```

* **Return type:**
  [`S3Location`](#songleaf.datasets.S3Location) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
