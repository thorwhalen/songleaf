"""Viewed: each viewer's songs by last opened, kept by the server, apart from the lists."""

import os

import pytest

from songleaf import tools
from songleaf.library import read_groups, save_groups
from songleaf.viewed import MAX_VIEWS, read_viewed, record_view, viewer_file_stem

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from songleaf.store import song_store  # noqa: E402
from songleaf.web import mk_app  # noqa: E402


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / "root")


@pytest.fixture
def store(tmp_path, memory_source):
    songs = song_store(str(tmp_path / "songs"))
    for song_id in ("1", "2"):
        songs[f"memory:{song_id}"] = memory_source.get(song_id)
    return songs


def test_the_latest_view_comes_first_and_a_new_view_moves_a_song_up(store, root):
    tools.view("memory:1", store=store, library_root=root, at=100.0)
    tools.view("memory:2", store=store, library_root=root, at=200.0)
    assert [v["key"] for v in tools.viewed(store=store, library_root=root)] == [
        "memory:2",
        "memory:1",
    ]
    tools.view("memory:1", store=store, library_root=root, at=300.0)
    rows = tools.viewed(store=store, library_root=root)
    assert [v["key"] for v in rows] == ["memory:1", "memory:2"]
    assert rows[0]["title"] == "Paper Boats" and rows[0]["viewed_at"] == 300.0


def test_removing_from_viewed_keeps_the_song_and_its_lists(store, root):
    tools.view("memory:1", store=store, library_root=root)
    edge = {"id": "e", "parent": "Campfire", "child": "memory:1", "kind": "contains"}
    save_groups({"nodes": [], "edges": [edge]}, revision=0, root=root)
    result = tools.unview("memory:1", library_root=root)
    assert result["removed"] and result["viewed_at"]
    assert tools.viewed(store=store, library_root=root) == []
    assert "memory:1" in store
    assert read_groups(root=root)["snapshot"]["edges"] == [edge]
    assert tools.unview("memory:1", library_root=root)["removed"] is False


def test_an_undo_puts_a_song_back_where_it_was(store, root):
    tools.view("memory:1", store=store, library_root=root, at=100.0)
    tools.view("memory:2", store=store, library_root=root, at=200.0)
    at = tools.unview("memory:1", library_root=root)["viewed_at"]
    tools.view("memory:1", store=store, library_root=root, at=at)
    assert [v["key"] for v in tools.viewed(store=store, library_root=root)] == [
        "memory:2",
        "memory:1",
    ]


def test_only_stored_songs_are_viewed_and_a_deleted_one_leaves(store, root):
    with pytest.raises(KeyError):
        tools.view("memory:404", store=store, library_root=root)
    tools.view("memory:1", store=store, library_root=root)
    tools.view("memory:1", user="other", store=store, library_root=root)
    tools.forget("memory:1", store=store, library_root=root)
    assert tools.viewed(store=store, library_root=root) == []
    assert tools.viewed(user="other", store=store, library_root=root) == []


def test_each_viewer_has_a_list_and_the_file_never_names_them(store, root):
    tools.view("memory:1", user="person-a", store=store, library_root=root)
    tools.view("memory:2", user="person-b", store=store, library_root=root)
    assert [
        v["key"] for v in tools.viewed(user="person-a", store=store, library_root=root)
    ] == ["memory:1"]
    assert [
        v["key"] for v in tools.viewed(user="person-b", store=store, library_root=root)
    ] == ["memory:2"]
    assert tools.viewed(store=store, library_root=root) == []  # no one: the shared list
    folder = os.path.join(root, "library", "viewed")
    files = [
        n for n in os.listdir(folder) if n.endswith(".json")
    ]  # beside each: its lock
    for name in os.listdir(folder):
        assert "person" not in name
        if not name.endswith(".json"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as file:
            assert "person" not in file.read()
    assert sorted(files) == sorted(
        viewer_file_stem(u) + ".json" for u in ("person-a", "person-b")
    )


def test_the_list_keeps_the_most_recent(root):
    for i in range(MAX_VIEWS + 3):
        record_view(f"x:{i}", root=root, at=float(i))
    views = read_viewed(root=root)
    assert len(views) == MAX_VIEWS and views[0]["key"] == f"x:{MAX_VIEWS + 2}"


class _AsUser:
    """Plays the platform: sets request.state.user_id from a test header, as enlace_auth would from a session."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            user = headers.get(b"x-test-session", b"").decode() or None
            scope.setdefault("state", {})["user_id"] = user
        await self.app(scope, receive, send)


@pytest.fixture
def client(memory_source, store, root):
    return TestClient(
        _AsUser(mk_app(sources=[memory_source], store=store, library_root=root))
    )


def test_the_web_viewed_list_is_per_viewer(client):
    a, b = {"x-test-session": "a"}, {"x-test-session": "b"}
    assert (
        client.post("/viewed", params={"key": "memory:1"}, headers=a).status_code == 200
    )
    assert (
        client.post("/viewed", params={"key": "memory:2"}, headers=b).status_code == 200
    )
    assert [v["key"] for v in client.get("/viewed", headers=a).json()] == ["memory:1"]
    assert [v["key"] for v in client.get("/viewed", headers=b).json()] == ["memory:2"]
    assert client.get("/viewed").json() == []  # no identity: the list everyone shares


def test_the_web_remove_and_undo(client):
    me = {"x-test-session": "a"}
    client.post("/viewed", params={"key": "memory:1", "at": 100}, headers=me)
    client.post("/viewed", params={"key": "memory:2", "at": 200}, headers=me)
    removed = client.delete("/viewed", params={"key": "memory:1"}, headers=me).json()
    assert removed["viewed_at"] == 100
    assert (
        client.delete("/viewed", params={"key": "memory:1"}, headers=me).status_code
        == 404
    )
    client.post(
        "/viewed", params={"key": "memory:1", "at": removed["viewed_at"]}, headers=me
    )
    assert [v["key"] for v in client.get("/viewed", headers=me).json()] == [
        "memory:2",
        "memory:1",
    ]


def test_the_web_refuses_what_it_cannot_record(client):
    assert client.post("/viewed", params={"key": "memory:404"}).status_code == 404
    assert (
        client.post("/viewed", params={"key": "memory:1", "at": -1}).status_code == 422
    )
    assert (
        client.post("/viewed", params={"key": "memory:1", "at": 4e12}).status_code
        == 400
    )


def test_identity_comes_from_the_host_never_from_a_header(client):
    # a client's own identity header is not who it is: only request.state counts
    client.post("/viewed", params={"key": "memory:1"}, headers={"x-user-id": "a"})
    assert [v["key"] for v in client.get("/viewed").json()] == ["memory:1"]
    assert client.get("/viewed", headers={"x-test-session": "a"}).json() == []
