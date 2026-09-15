"""Where songs persist: a ``MutableMapping`` of songs, JSON files by default.

Data lives under ``~/.local/share/songleaf/<kind>/`` (``songs/`` for the store,
``sheets/`` for rendered PDFs); ``SONGLEAF_DATA_DIR`` overrides the root.
Keys are song keys (``"<source>:<id>"``). Each song is one JSON file named after
its key, percent-encoded so that any key is a safe file name, and two keys that
differ only in letter case never share a file on a case-insensitive file system.

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
from urllib.parse import unquote

from songleaf.model import Song

#: Environment variable overriding the data root.
DATA_DIR_ENVVAR = "SONGLEAF_DATA_DIR"
_SUFFIX = ".json"
_LITERAL = frozenset(b"abcdefghijklmnopqrstuvwxyz0123456789-_.")
_MAX_FILE_NAME = 255


def data_dir(kind: str) -> str:
    """The directory holding one kind of data (created if missing)."""
    root = os.environ.get(DATA_DIR_ENVVAR) or os.path.join(
        os.path.expanduser("~"), ".local", "share", "songleaf"
    )
    path = os.path.join(root, kind)
    os.makedirs(path, exist_ok=True)
    return path


def file_name_of_key(key: str) -> str:
    """The file name a song key is stored under.

    Every byte but lowercase ASCII letters, digits and ``-_.`` is percent-encoded
    (uppercase letters included), so the name is safe everywhere and distinct from
    every other key's name even when letter case is ignored.

    >>> file_name_of_key("kaggle_chords:0"), file_name_of_key("src:Abc")
    ('kaggle_chords%3A0.json', 'src%3A%41bc.json')
    """
    name = "".join(
        chr(byte) if byte in _LITERAL else f"%{byte:02X}"
        for byte in key.encode("utf-8")
    )
    name += _SUFFIX
    if len(name) > _MAX_FILE_NAME:
        raise ValueError(
            f"The song key {key[:40]!r}... is too long to store "
            f"({len(name)} characters as a file name; the limit is {_MAX_FILE_NAME})"
        )
    return name


def _key_of_file_name(name: str) -> str:
    return unquote(name[: -len(_SUFFIX)])


def _is_song_file(name: str) -> bool:
    return name.endswith(_SUFFIX) and "/" not in name and os.sep not in name


def song_store(rootdir: str | None = None) -> MutableMapping[str, Song]:
    """Songs as JSON files in ``rootdir`` (default: the ``songs`` data dir)."""
    from dol import Files, filt_iter, wrap_kvs

    rootdir = rootdir or data_dir("songs")
    os.makedirs(rootdir, exist_ok=True)
    return wrap_kvs(
        filt_iter(Files(rootdir), filt=_is_song_file),
        key_of_id=_key_of_file_name,
        id_of_key=file_name_of_key,
        obj_of_data=lambda data: Song.from_dict(_json_loads(data)),
        data_of_obj=lambda song: _json_dumps(song.to_dict()),
    )


def _json_loads(data: bytes) -> dict:
    import json

    return json.loads(data.decode("utf-8"))


def _json_dumps(obj: dict) -> bytes:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
