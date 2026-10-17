"""The web surface, through FastAPI's test client, over the synthetic source."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from songleaf import sources as sources_module  # noqa: E402
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
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SUNG_CHORDS_AND_LYRICS_ZIP", raising=False)

    def no_corpus():
        raise sources_module.SourceUnavailable(
            "Put the zip at datasets/chords-and-lyrics/"
        )

    source = sources_module.KaggleChordsSource(loader=no_corpus)
    client = TestClient(
        mk_app(sources=[source], store=song_store(str(tmp_path / "songs")))
    )
    response = client.get("/search", params={"q": "anything"})
    assert (
        response.status_code == 503
        and "datasets/chords-and-lyrics" in response.json()["detail"]
    )


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
