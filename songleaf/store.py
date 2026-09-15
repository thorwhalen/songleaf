"""Where songs persist: a ``MutableMapping`` of songs, JSON files by default.

Data lives under ``~/.local/share/songleaf/<kind>/`` (``songs/`` for the store,
``sheets/`` for rendered PDFs); ``SONGLEAF_DATA_DIR`` overrides the root.
Keys are song keys (``"<source>:<id>"``); each song is one JSON file named
after its percent-encoded key, so any key is a safe file name.

>>> import tempfile
>>> from songleaf.model import Song
>>> songs = song_store(tempfile.mkdtemp())
>>> songs["demo:1"] = Song("la la la", meta={"title": "Demo"})
>>> list(songs), songs["demo:1"].title
(['demo:1'], 'Demo')
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from urllib.parse import quote, unquote

from songleaf.model import Song

#: Environment variable overriding the data root.
DATA_DIR_ENVVAR = "SONGLEAF_DATA_DIR"
_SUFFIX = ".json"


def data_dir(kind: str) -> str:
    """The directory holding one kind of data (created if missing)."""
    root = os.environ.get(DATA_DIR_ENVVAR) or os.path.join(
        os.path.expanduser("~"), ".local", "share", "songleaf"
    )
    path = os.path.join(root, kind)
    os.makedirs(path, exist_ok=True)
    return path


def song_store(rootdir: str | None = None) -> MutableMapping[str, Song]:
    """Songs as JSON files in ``rootdir`` (default: the ``songs`` data dir)."""
    from dol import Files, filt_iter, wrap_kvs

    rootdir = rootdir or data_dir("songs")
    os.makedirs(rootdir, exist_ok=True)
    files = filt_iter(Files(rootdir), filt=lambda name: name.endswith(_SUFFIX))
    return wrap_kvs(
        files,
        key_of_id=lambda name: unquote(name[: -len(_SUFFIX)]),
        id_of_key=lambda key: quote(key, safe="") + _SUFFIX,
        obj_of_data=lambda data: Song.from_dict(_json_loads(data)),
        data_of_obj=lambda song: _json_dumps(song.to_dict()),
    )


def _json_loads(data: bytes) -> dict:
    import json

    return json.loads(data.decode("utf-8"))


def _json_dumps(obj: dict) -> bytes:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
