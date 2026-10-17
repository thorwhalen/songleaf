"""The library's groups: which stored songs are in which groups, shared by everyone using it.

The groups are a zodal-groups snapshot (``{"nodes": [...], "edges": [...]}``: songs and
groups are nodes, a membership is an edge from a group to a song or to another group). The
page edits them with zodal-groups and saves the whole snapshot; this module keeps it as one
JSON document under the data root (``library/groups.json``) with a revision number.

A save names the revision it was made from. If the document has moved on since (someone
else saved), the save is refused with :class:`RevisionConflict`, which carries the current
document, so no one's change is silently overwritten.

>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> read_groups(root=root)
{'revision': 0, 'snapshot': {'nodes': [], 'edges': []}}
>>> snapshot = {"nodes": [{"id": "Family"}, {"id": "memory:1"}],
...             "edges": [{"id": "e1", "parent": "Family", "child": "memory:1",
...                        "kind": "contains"}]}
>>> save_groups(snapshot, revision=0, root=root)["revision"]
1
>>> drop_item("memory:1", root=root)["snapshot"]["edges"]
[]
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager

from songleaf.store import data_dir

#: The largest groups document accepted, in bytes: thousands of songs fit many times over.
MAX_BYTES = 2_000_000
_MAX_ID = 500  # characters in a node or edge id
_FILE = "groups.json"
_EMPTY = {"nodes": [], "edges": []}
_thread_lock = threading.Lock()


class RevisionConflict(Exception):
    """The groups changed since the revision a save was made from."""

    def __init__(self, current: dict):
        super().__init__(
            f"The groups changed since you loaded them (now at revision {current['revision']})"
        )
        self.current = current


def read_groups(*, root: str | None = None) -> dict:
    """``{"revision", "snapshot"}``: the current groups, revision 0 when there are none."""
    path = _path(root)
    try:
        with open(path, encoding="utf-8") as file:
            document = json.load(file)
    except FileNotFoundError:
        return {"revision": 0, "snapshot": dict(_EMPTY)}
    return {"revision": int(document["revision"]), "snapshot": document["snapshot"]}


def save_groups(
    snapshot: dict, *, revision: int, root: str | None = None, keep_item=None
) -> dict:
    """Replace the groups with ``snapshot``, made from ``revision``; returns the new document.

    ``keep_item(id) -> bool``, when given, decides whether a member that is not a group (an
    item: a song key) may stay; memberships of the others are dropped (a song deleted while
    a page that still showed it was saving). Raises :class:`RevisionConflict` when the
    stored revision is not ``revision``, and ``ValueError`` when ``snapshot`` is not a
    snapshot or ``revision`` not a whole number.
    """
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise ValueError(f"A revision is a whole number, got {revision!r}")
    snapshot = checked_snapshot(snapshot)
    if keep_item is not None:
        groups = {node["id"] for node in snapshot["nodes"]}
        snapshot["edges"] = [
            e
            for e in snapshot["edges"]
            if e["child"] in groups or keep_item(e["child"])
        ]
    with _locked(root):
        current = read_groups(root=root)
        if current["revision"] != revision:
            raise RevisionConflict(current)
        return _write({"revision": revision + 1, "snapshot": snapshot}, root)


def drop_item(item: str, *, root: str | None = None) -> dict:
    """Take ``item`` (a song key) out of every group; returns the document, saved if it changed."""
    with _locked(root):
        current = read_groups(root=root)
        snapshot = current["snapshot"]
        edges = [
            e
            for e in snapshot["edges"]
            if item not in (e.get("parent"), e.get("child"))
        ]
        nodes = [n for n in snapshot["nodes"] if n.get("id") != item]
        if len(edges) == len(snapshot["edges"]) and len(nodes) == len(
            snapshot["nodes"]
        ):
            return current
        pruned = {**snapshot, "nodes": nodes, "edges": edges}
        return _write({"revision": current["revision"] + 1, "snapshot": pruned}, root)


def checked_snapshot(snapshot) -> dict:
    """``snapshot`` if it has the shape of a zodal-groups snapshot, else ``ValueError``.

    The checks are zodal-groups' own read-path rules (``parseSnapshot``: non-empty string
    ids, unique node and edge ids, every edge with a parent, a child and a kind), plus no
    self-loop and no cycle, so a page can always load what was saved. The profile's other
    rules are zodal-groups', applied where the edit is made.

    >>> edge = {"id": "e", "parent": "a", "child": "a", "kind": "contains"}
    >>> checked_snapshot({"nodes": [], "edges": [edge]})
    Traceback (most recent call last):
    ...
    ValueError: edges[0]: a group cannot contain itself ('a')
    """
    if not isinstance(snapshot, dict):
        raise ValueError("A groups snapshot is an object with nodes and edges")
    nodes, edges = snapshot.get("nodes"), snapshot.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("A groups snapshot has a list of nodes and a list of edges")
    node_ids = set()
    for i, node in enumerate(nodes):
        if not (isinstance(node, dict) and _name(node.get("id"))):
            raise ValueError(
                f"nodes[{i}]: needs a non-empty string id, got {node!r:.80}"
            )
        if node["id"] in node_ids:
            raise ValueError(f"nodes[{i}]: duplicate node id {node['id']!r}")
        node_ids.add(node["id"])
    edge_ids, children = set(), {}
    fields = ("id", "parent", "child", "kind")
    for i, edge in enumerate(edges):
        if not (isinstance(edge, dict) and all(_name(edge.get(f)) for f in fields)):
            raise ValueError(
                f"edges[{i}]: needs non-empty string {', '.join(fields)}, got {edge!r:.80}"
            )
        if edge["id"] in edge_ids:
            raise ValueError(f"edges[{i}]: duplicate edge id {edge['id']!r}")
        if edge["parent"] == edge["child"]:
            raise ValueError(
                f"edges[{i}]: a group cannot contain itself ({edge['parent']!r})"
            )
        edge_ids.add(edge["id"])
        children.setdefault(edge["parent"], []).append(edge["child"])
    cycle = _a_cycle(children)
    if cycle:
        raise ValueError(
            f"The groups contain each other in a loop: {' > '.join(cycle)}"
        )
    size = len(json.dumps(snapshot))
    if size > MAX_BYTES:
        raise ValueError(f"The groups are {size} bytes; the limit is {MAX_BYTES}")
    return {"nodes": nodes, "edges": edges}


def _name(value) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= _MAX_ID


def _a_cycle(children: dict) -> list:
    """One loop of containment (``[a, b, a]``), or ``[]``: iterative DFS, no recursion limit."""
    state = {}  # node -> 1 while on the current path, 2 once done
    for start in children:
        if state.get(start):
            continue
        path, stack = [start], [(start, iter(children.get(start, ())))]
        state[start] = 1
        while stack:
            node, kids = stack[-1]
            child = next(kids, None)
            if child is None:
                stack.pop()
                path.pop()
                state[node] = 2
            elif state.get(child) == 1:
                return path[path.index(child) :] + [child]
            elif not state.get(child):
                state[child] = 1
                path.append(child)
                stack.append((child, iter(children.get(child, ()))))
    return []


def _path(root: str | None) -> str:
    folder = os.path.join(root, "library") if root else data_dir("library")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, _FILE)


def _write(document: dict, root: str | None) -> dict:
    path = _path(root)
    temporary = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(document, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(
        temporary, path
    )  # readers see the old document or the new one, never half
    return document


@contextmanager
def _locked(root: str | None):
    """One writer at a time: threads of this process, and other processes where fcntl exists."""
    with _thread_lock:
        try:
            import fcntl
        except ImportError:  # Windows: one process is all a local run has
            yield
            return
        with open(_path(root) + ".lock", "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
