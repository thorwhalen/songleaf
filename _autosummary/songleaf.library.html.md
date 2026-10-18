# songleaf.library

The library’s lists: which stored songs are in which lists, shared by everyone using it.

The page calls them *lists*; the model and the stored file keep the name zodal-groups gives
them (groups), so this module and `groups.json` say “groups”.

The groups are a zodal-groups snapshot (`{"nodes": [...], "edges": [...]}`: songs and
groups are nodes, a membership is an edge from a group to a song or to another group). The
page edits them with zodal-groups and saves the whole snapshot; this module keeps it as one
JSON document under the data root (`library/groups.json`) with a revision number.

A save names the revision it was made from. If the document has moved on since (someone
else saved), the save is refused with [`RevisionConflict`](#songleaf.library.RevisionConflict), which carries the current
document, so no one’s change is silently overwritten.

```pycon
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
```

### Module Attributes

| [`MAX_BYTES`](#songleaf.library.MAX_BYTES)   | thousands of songs fit many times over.   |
|--------------------------------------------------------------|-------------------------------------------|

### Functions

| [`checked_snapshot`](#songleaf.library.checked_snapshot)(snapshot)                       | `snapshot` if it has the shape of a zodal-groups snapshot, else `ValueError`.                    |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| [`drop_item`](#songleaf.library.drop_item)(item, \*[, root])                      | Take `item` (a song key) out of every group; returns the document, saved if it changed.          |
| [`file_lock`](#songleaf.library.file_lock)(path)                                  | One writer of `path` at a time: threads of this process, and other processes where fcntl exists. |
| [`list_members`](#songleaf.library.list_members)(snapshot, list_id)                  | The songs in a list or in any list inside it, each once, in the order they were added.           |
| [`list_names`](#songleaf.library.list_names)(snapshot)                             | `{id: name}` of every list (group) in a snapshot: its nodes, and every edge's parent.            |
| [`lists_matching`](#songleaf.library.lists_matching)(query, snapshot)                  | The lists whose name the query names, best first: `[{"id", "name", "spans"}]`.                   |
| [`read_groups`](#songleaf.library.read_groups)(\*[, root])                          | `{"revision", "snapshot"}`: the current groups, revision 0 when there are none.                  |
| [`save_groups`](#songleaf.library.save_groups)(snapshot, \*, revision[, root, ...]) | Replace the groups with `snapshot`, made from `revision`; returns the new document.              |
| [`write_json_atomically`](#songleaf.library.write_json_atomically)(path, document)            | Write `document` to `path` so that readers see the old file or the new one, never half.          |

### Exceptions

| [`RevisionConflict`](#songleaf.library.RevisionConflict)(current)   | The groups changed since the revision a save was made from.   |
|------------------------------------------------------------------------------|---------------------------------------------------------------|

### songleaf.library.MAX_BYTES *= 2000000*

thousands of songs fit many times over.

* **Type:**
  The largest groups document accepted, in bytes

### *exception* songleaf.library.RevisionConflict(current)

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

The groups changed since the revision a save was made from.

### songleaf.library.checked_snapshot(snapshot)

`snapshot` if it has the shape of a zodal-groups snapshot, else `ValueError`.

The checks are zodal-groups’ own read-path rules (`parseSnapshot`: non-empty string
ids, unique node and edge ids, every edge with a parent, a child and a kind), plus no
self-loop and no cycle, so a page can always load what was saved. The profile’s other
rules are zodal-groups’, applied where the edit is made.

```pycon
>>> edge = {"id": "e", "parent": "a", "child": "a", "kind": "contains"}
>>> checked_snapshot({"nodes": [], "edges": [edge]})
Traceback (most recent call last):
...
ValueError: edges[0]: a group cannot contain itself ('a')
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.library.drop_item(item, , root=None)

Take `item` (a song key) out of every group; returns the document, saved if it changed.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.library.file_lock(path)

One writer of `path` at a time: threads of this process, and other processes where fcntl exists.

### songleaf.library.list_members(snapshot, list_id)

The songs in a list or in any list inside it, each once, in the order they were added.

```pycon
>>> snap = {"nodes": [], "edges": [
...     {"id": "1", "parent": "Campfire", "child": "x:1", "kind": "contains"},
...     {"id": "2", "parent": "Campfire", "child": "Slow", "kind": "contains"},
...     {"id": "3", "parent": "Slow", "child": "x:2", "kind": "contains"},
...     {"id": "4", "parent": "Slow", "child": "x:1", "kind": "contains"}]}
>>> list_members(snap, "Campfire")
['x:1', 'x:2']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.library.list_names(snapshot)

`{id: name}` of every list (group) in a snapshot: its nodes, and every edge’s parent.

```pycon
>>> list_names({"nodes": [{"id": "a", "label": "Campfire"}],
...             "edges": [{"id": "e", "parent": "b", "child": "x:1", "kind": "contains"}]})
{'a': 'Campfire', 'b': 'b'}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.library.lists_matching(query, snapshot)

The lists whose name the query names, best first: `[{"id", "name", "spans"}]`.

A list matches when every word of the query starts a word of its name (`"camp"`
finds Campfire, `"to le"` finds To learn; a one-letter word must be a whole word), or
when the whole name, four letters or more, is the query give or take one typo (a
letter added, dropped, changed or two swapped). So a short name (`Fun`) is not found
by every query that holds it (`funeral`, `funk`). `spans` are the matched parts
of the name.

```pycon
>>> snap = {"nodes": [{"id": "Campfire"}, {"id": "To learn"}, {"id": "Fun"}], "edges": []}
>>> [m["id"] for m in lists_matching("camp", snap)]
['Campfire']
>>> [m["id"] for m in lists_matching("campfier", snap)], lists_matching("funk", snap)
(['Campfire'], [])
>>> lists_matching("t", snap)
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### songleaf.library.read_groups(, root=None)

`{"revision", "snapshot"}`: the current groups, revision 0 when there are none.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.library.save_groups(snapshot, , revision, root=None, keep_item=None)

Replace the groups with `snapshot`, made from `revision`; returns the new document.

`keep_item(id) -> bool`, when given, decides whether a member that is not a group (an
item: a song key) may stay; memberships of the others are dropped (a song deleted while
a page that still showed it was saving). Raises [`RevisionConflict`](#songleaf.library.RevisionConflict) when the
stored revision is not `revision`, and `ValueError` when `snapshot` is not a
snapshot or `revision` not a whole number.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.library.write_json_atomically(path, document)

Write `document` to `path` so that readers see the old file or the new one, never half.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
