# songleaf.viewed

Each viewer’s *Viewed* list: the songs they opened, the most recent first.

Kept on the server, one JSON document per viewer under the data root
(`library/viewed/<viewer>.json`: `{"views": {song key: seconds since the epoch}}`).
A viewer is whoever the host says is asking (the platform’s user id, under enlace); the
file is named after a hash of that id ([`viewer_file_stem()`](#songleaf.viewed.viewer_file_stem)), so no identity is
written to disk in the clear. With no identity (a local run, or a host with no login),
everyone shares one list, `anyone`.

Viewed is not a list of the library: it is never in `groups.json`, a song leaves it
without leaving any list, and leaving it does not delete the song.

```pycon
>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> _ = record_view("x:1", root=root, at=100.0)
>>> _ = record_view("x:2", root=root, at=200.0)
>>> [v["key"] for v in read_viewed(root=root)]
['x:2', 'x:1']
>>> remove_view("x:2", root=root)
200.0
>>> [v["key"] for v in read_viewed(root=root)], read_viewed(user="someone", root=root)
(['x:1'], [])
```

### Module Attributes

| [`ANYONE`](#songleaf.viewed.ANYONE)    | The file stem of the list everyone shares when the host names no viewer.         |
|------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`MAX_VIEWS`](#songleaf.viewed.MAX_VIEWS) | The most songs one Viewed list keeps; opening one more forgets the least recent. |

### Functions

| [`drop_everywhere`](#songleaf.viewed.drop_everywhere)(key, \*[, root])       | Take `key` out of every viewer's list (the song was deleted); returns how many held it.         |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`read_viewed`](#songleaf.viewed.read_viewed)(\*[, user, root])          | `user`'s Viewed list, the most recent first: `[{"key", "viewed_at"}]`.                          |
| [`record_view`](#songleaf.viewed.record_view)(key, \*[, user, at, root]) | Put `key` at the top of `user`'s Viewed list (or at time `at`); returns the time used.          |
| [`remove_view`](#songleaf.viewed.remove_view)(key, \*[, user, root])     | Take `key` out of `user`'s Viewed list; returns when it was viewed, `None` if it was not there. |
| [`viewer_file_stem`](#songleaf.viewed.viewer_file_stem)(user)                 | The file name (without `.json`) of `user`'s list: a hash of the id, never the id.               |

### songleaf.viewed.ANYONE *= 'anyone'*

The file stem of the list everyone shares when the host names no viewer.

### songleaf.viewed.MAX_VIEWS *= 2000*

The most songs one Viewed list keeps; opening one more forgets the least recent.

### songleaf.viewed.drop_everywhere(key, , root=None)

Take `key` out of every viewer’s list (the song was deleted); returns how many held it.

```pycon
>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> _ = record_view("x:1", root=root); _ = record_view("x:1", user="b", root=root)
>>> drop_everywhere("x:1", root=root), read_viewed(user="b", root=root)
(2, [])
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### songleaf.viewed.read_viewed(, user=None, root=None)

`user`’s Viewed list, the most recent first: `[{"key", "viewed_at"}]`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### songleaf.viewed.record_view(key, , user=None, at=None, root=None)

Put `key` at the top of `user`’s Viewed list (or at time `at`); returns the time used.

`at` puts a song back where it was (an undo of [`remove_view()`](#songleaf.viewed.remove_view)).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.viewed.remove_view(key, , user=None, root=None)

Take `key` out of `user`’s Viewed list; returns when it was viewed, `None` if it was not there.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.viewed.viewer_file_stem(user)

The file name (without `.json`) of `user`’s list: a hash of the id, never the id.

```pycon
>>> viewer_file_stem(None), viewer_file_stem("")
('anyone', 'anyone')
>>> stem = viewer_file_stem("user-1234")
>>> stem.startswith("u-") and len(stem) == 34 and "1234" not in stem
True
>>> stem == viewer_file_stem("user-1234") != viewer_file_stem("other")
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
