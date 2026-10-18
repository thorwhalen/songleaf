"""Each viewer's *Viewed* list: the songs they opened, the most recent first.

Kept on the server, one JSON document per viewer under the data root
(``library/viewed/<viewer>.json``: ``{"views": {song key: seconds since the epoch}}``).
A viewer is whoever the host says is asking (the platform's user id, under enlace); the
file is named after a hash of that id (:func:`viewer_file_stem`), so no identity is
written to disk in the clear. With no identity (a local run, or a host with no login),
everyone shares one list, ``anyone``.

Viewed is not a list of the library: it is never in ``groups.json``, a song leaves it
without leaving any list, and leaving it does not delete the song.

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
"""

from __future__ import annotations

import hashlib
import json
import os
import time

from songleaf.library import file_lock, write_json_atomically
from songleaf.store import data_dir

#: The file stem of the list everyone shares when the host names no viewer.
ANYONE = "anyone"
#: The most songs one Viewed list keeps; opening one more forgets the least recent.
MAX_VIEWS = 2000
_HASH_SALT = (
    "songleaf-viewed\0"  # a viewer's file is named after this hashed with their id
)
_FOLDER = "viewed"


def viewer_file_stem(user: str | None) -> str:
    """The file name (without ``.json``) of ``user``'s list: a hash of the id, never the id.

    >>> viewer_file_stem(None), viewer_file_stem("")
    ('anyone', 'anyone')
    >>> stem = viewer_file_stem("user-1234")
    >>> stem.startswith("u-") and len(stem) == 34 and "1234" not in stem
    True
    >>> stem == viewer_file_stem("user-1234") != viewer_file_stem("other")
    True
    """
    if not user:
        return ANYONE
    digest = hashlib.sha256((_HASH_SALT + str(user)).encode("utf-8")).hexdigest()
    return "u-" + digest[:32]


def read_viewed(*, user: str | None = None, root: str | None = None) -> list[dict]:
    """``user``'s Viewed list, the most recent first: ``[{"key", "viewed_at"}]``."""
    views = _read(_path(user, root))
    ranked = sorted(views.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"key": key, "viewed_at": at} for key, at in ranked]


def record_view(
    key: str,
    *,
    user: str | None = None,
    at: float | None = None,
    root: str | None = None,
) -> float:
    """Put ``key`` at the top of ``user``'s Viewed list (or at time ``at``); returns the time used.

    ``at`` puts a song back where it was (an undo of :func:`remove_view`).
    """
    at = time.time() if at is None else float(at)
    path = _path(user, root)
    with file_lock(path):
        views = _read(path)
        views[key] = at
        if len(views) > MAX_VIEWS:
            kept = sorted(views.items(), key=lambda kv: -kv[1])[:MAX_VIEWS]
            views = dict(kept)
        write_json_atomically(path, {"views": views})
    return at


def remove_view(
    key: str, *, user: str | None = None, root: str | None = None
) -> float | None:
    """Take ``key`` out of ``user``'s Viewed list; returns when it was viewed, ``None`` if it was not there."""
    path = _path(user, root)
    with file_lock(path):
        views = _read(path)
        at = views.pop(key, None)
        if at is not None:
            write_json_atomically(path, {"views": views})
    return at


def drop_everywhere(key: str, *, root: str | None = None) -> int:
    """Take ``key`` out of every viewer's list (the song was deleted); returns how many held it.

    >>> import tempfile
    >>> root = tempfile.mkdtemp()
    >>> _ = record_view("x:1", root=root); _ = record_view("x:1", user="b", root=root)
    >>> drop_everywhere("x:1", root=root), read_viewed(user="b", root=root)
    (2, [])
    """
    folder = _folder(root)
    dropped = 0
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            path = os.path.join(folder, name)
            with file_lock(path):
                views = _read(path)
                if views.pop(key, None) is not None:
                    write_json_atomically(path, {"views": views})
                    dropped += 1
    return dropped


def _folder(root: str | None) -> str:
    folder = (
        os.path.join(root, "library", _FOLDER)
        if root
        else os.path.join(data_dir("library"), _FOLDER)
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def _path(user: str | None, root: str | None) -> str:
    return os.path.join(_folder(root), viewer_file_stem(user) + ".json")


def _read(path: str) -> dict[str, float]:
    try:
        with open(path, encoding="utf-8") as file:
            document = json.load(file)
    except FileNotFoundError:
        return {}
    except (
        OSError,
        ValueError,
    ):  # unreadable or not JSON: start that viewer's list afresh
        return {}
    if not isinstance(document, dict) or not isinstance(document.get("views"), dict):
        return {}
    return {
        str(key): float(at)
        for key, at in document["views"].items()
        if isinstance(at, (int, float)) and not isinstance(at, bool) and at == at
    }
