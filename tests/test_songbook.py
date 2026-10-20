"""The songbook: a group of songs as one PDF with a table of contents and bookmarks."""

import io

import pytest
from pypdf import PdfReader

from songleaf import tools
from songleaf.library import save_groups
from songleaf.store import song_store

pytest.importorskip("reportlab")


def _group(root, *keys):
    edges = [
        {"id": f"e{i}", "parent": "Setlist", "child": k, "kind": "contains"}
        for i, k in enumerate(keys)
    ]
    save_groups({"nodes": [{"id": "Setlist"}], "edges": edges}, revision=0, root=str(root))


@pytest.fixture
def book(memory_source, tmp_path):
    _group(tmp_path / "lib", "memory:2", "memory:1")
    out = tmp_path / "book.pdf"
    result = tools.songbook(
        "setlist",  # a name, not the id's spelling
        output=str(out),
        library_root=str(tmp_path / "lib"),
        sources=[memory_source],
        store=song_store(str(tmp_path / "songs")),
    )
    return result, PdfReader(str(out))


def test_songs_follow_the_list_order_after_a_table_of_contents(book):
    result, reader = book
    assert [s["key"] for s in result["songs"]] == ["memory:2", "memory:1"]
    assert result["songs"][0]["page"] == 2  # page 1 is the contents
    assert len(reader.pages) == result["pages"]
    assert result["songs"][1]["page"] > result["songs"][0]["page"]
    toc_text = reader.pages[0].extract_text()
    assert "Quiet Road" in toc_text and "Paper Boats" in toc_text


def test_every_song_is_a_bookmark_and_every_page_is_numbered(book):
    result, reader = book
    titles = [item.title for item in reader.outline]
    assert titles[0] == "Setlist" and len(titles) == 3
    n = result["pages"]
    assert f"{n} / {n}" in reader.pages[-1].extract_text()


def test_an_unknown_or_empty_list_is_an_error(memory_source, tmp_path):
    kwargs = dict(library_root=str(tmp_path / "lib"), sources=[memory_source])
    with pytest.raises(LookupError):
        tools.songbook("nothing", output=str(tmp_path / "x.pdf"), **kwargs)


def test_the_web_route_serves_the_book(memory_source, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from songleaf.web import mk_app

    _group(tmp_path / "lib", "memory:1")
    client = TestClient(
        mk_app(
            sources=[memory_source],
            store=song_store(str(tmp_path / "songs")),
            library_root=str(tmp_path / "lib"),
        )
    )
    response = client.get("/songbook.pdf", params={"group": "Setlist"})
    assert response.status_code == 200
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 2
    assert client.get("/songbook.pdf", params={"group": "Nope"}).status_code == 404
    assert (
        client.get("/songbook.pdf", params={"group": "Setlist", "layout": "zz"}).status_code
        == 400
    )
