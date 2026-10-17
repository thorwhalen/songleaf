"""The web surface, through FastAPI's test client, over the synthetic source."""

import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from songleaf import sources as sources_module  # noqa: E402
from songleaf.parse import parse_chords_over_lyrics  # noqa: E402
from songleaf.store import song_store  # noqa: E402
from songleaf.web import mk_app, page_shell  # noqa: E402


@pytest.fixture
def client(memory_source, tmp_path):
    store = song_store(str(tmp_path / "songs"))
    return TestClient(mk_app(sources=[memory_source], store=store))


def test_search_finds_and_an_empty_query_finds_nothing(client):
    hits = client.get("/search", params={"q": "paper boats"}).json()
    assert [hit["key"] for hit in hits] == ["memory:1"]
    assert client.get("/search", params={"q": "  "}).json() == []


def test_the_sheet_is_a_one_page_pdf_and_the_song_is_stored(client, page_count):
    info = client.get("/sheet", params={"key": "memory:1"}).json()
    assert (info["title"], info["pages"], info["file_name"]) == (
        "Paper Boats",
        1,
        "The Invented Band - Paper Boats.pdf",
    )
    response = client.get("/sheet.pdf", params={"key": "memory:1"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Paper%20Boats.pdf" in response.headers["content-disposition"]
    assert page_count(response.content) == 1
    assert client.get("/songs").json() == [
        {"key": "memory:1", "title": "Paper Boats", "artist": "The Invented Band"}
    ]


def test_a_page_of_the_sheet_is_a_png(client):
    pytest.importorskip("pypdfium2")
    response = client.get("/sheet.png", params={"key": "memory:1"})
    assert response.status_code == 200 and response.content[:8] == b"\x89PNG\r\n\x1a\n"
    beyond = client.get("/sheet.png", params={"key": "memory:1", "page": 2})
    assert beyond.status_code == 404


def test_a_layout_spec_renders_and_a_bad_one_is_a_400(client):
    assert (
        client.get(
            "/sheet.pdf", params={"key": "memory:1", "layout": "inline+two-column"}
        ).status_code
        == 200
    )
    bad = client.get("/sheet.pdf", params={"key": "memory:1", "layout": "sideways"})
    assert bad.status_code == 400 and "sideways" in bad.json()["detail"]


def test_an_unknown_song_is_a_404(client):
    assert client.get("/sheet.pdf", params={"key": "memory:999"}).status_code == 404
    assert (
        client.get("/sheet.pdf", params={"key": "no such song at all"}).status_code
        == 404
    )


def test_a_missing_corpus_is_a_503_that_says_where_to_put_it(monkeypatch, tmp_path):
    # the real loader, with sung unimportable: what a server without the corpus sees
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SUNG_CHORDS_AND_LYRICS_ZIP", raising=False)
    monkeypatch.setitem(sys.modules, "sung.chords_and_lyrics", None)
    source = sources_module.KaggleChordsSource()
    store = song_store(str(tmp_path / "songs"))
    client = TestClient(mk_app(sources=[source], store=store))
    response = client.get("/search", params={"q": "anything"})
    assert response.status_code == 503
    assert (
        "datasets/chords-and-lyrics/chords-and-lyrics-dataset.zip"
        in (response.json()["detail"])
    )
    # a stored song still opens without the corpus
    store["kaggle_chords:7"] = parse_chords_over_lyrics("C\nla la", meta={"title": "T"})
    assert client.get("/sheet", params={"key": "kaggle_chords:7"}).status_code == 200


def test_whitespace_in_one_field_does_not_hide_another(tmp_path):
    calls = []

    class Spy:
        name = "spy"

        def search(self, query="", **fields):
            calls.append((query, fields))
            return []

    client = TestClient(mk_app(sources=[Spy()], store=song_store(str(tmp_path))))
    client.get("/search", params={"q": "  ", "title": " paper boats "})
    assert calls == [
        ("", {"title": "paper boats", "artist": "", "lyrics": "", "limit": 20})
    ]


def test_a_bug_is_a_500_not_a_404(memory_source, tmp_path):
    class BrokenStore(dict):
        def __getitem__(self, key):
            raise KeyError("a bug, not a missing song")

        def __contains__(self, key):
            return True

    app = mk_app(sources=[memory_source], store=BrokenStore())
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/sheet", params={"key": "memory:1"}).status_code == 500


def test_the_layout_comes_back_in_its_one_spelling(client):
    info = client.get("/sheet", params={"key": "memory:1", "layout": "2col+INLINE"})
    assert info.json()["layout"] == "two-column+inline"


def test_layouts_say_which_options_exclude_each_other(client):
    options = {o["name"]: o["sets"] for o in client.get("/layouts").json()["options"]}
    assert "dense" not in options
    assert "chords" in options["inline"] and "chords" in options["overlap"]


def test_the_page_loads_its_script_and_style_from_the_api(client):
    shell = page_shell(api="/api/songleaf/", base="/songleaf")
    assert (
        'src="/api/songleaf/ui/app.js"' in shell
        and 'href="/api/songleaf/ui/style.css"' in shell
    )
    assert (
        client.get("/ui/app.js").headers["content-type"].startswith("text/javascript")
    )
    assert client.get("/ui/style.css").status_code == 200
    assert client.get("/ui/secrets.txt").status_code == 404


def test_the_zip_under_the_data_root_is_found(monkeypatch, tmp_path):
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SUNG_CHORDS_AND_LYRICS_ZIP", raising=False)
    assert sources_module.kaggle_chords_zip() is None
    zip_path = tmp_path / "datasets" / sources_module.KAGGLE_CHORDS_ZIP
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"")
    assert sources_module.kaggle_chords_zip() == str(zip_path)
    monkeypatch.setenv("SUNG_CHORDS_AND_LYRICS_ZIP", "/elsewhere.zip")
    assert sources_module.kaggle_chords_zip() is None  # the explicit variable wins
