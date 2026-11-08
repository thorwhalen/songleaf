"""The page's "Search the web" control (songleaf#62): ``/web`` and ``/search?web=always``.

The web is a fake LRCLIB answering with an invented song: no test reaches the network.
"""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from songleaf.online import StoredWebSource  # noqa: E402
from songleaf.web import mk_app  # noqa: E402

LYRICS = "\n".join(
    [
        "Lanterns drift where the willows lean",
        "past the mill and the meadow green",
        "sing it slow, sing it low",
        "let the river know",
    ]
)
RECORDS = [{"id": 31, "trackName": "Willow Lanterns", "artistName": "The Invented Band",
            "instrumental": False, "plainLyrics": LYRICS}]


@pytest.fixture
def asked():
    return []


@pytest.fixture
def fetch(asked):
    def fetch(url):
        asked.append(url)
        assert url.startswith("https://lrclib.net/api/search")
        return json.dumps(RECORDS)

    return fetch


def test_the_default_app_never_searches_the_web(memory_source):
    client = TestClient(mk_app(sources=[memory_source], store={}))
    assert client.get("/web").json() == {
        "available": False, "sites": ["LRCLIB"], "reason": "off in this app"}
    response = client.get("/search", params={"q": "willow lanterns", "web": "always"})
    assert response.status_code == 403


def test_a_search_on_request_keeps_the_song_and_says_where_it_came_from(
    memory_source, fetch, asked, monkeypatch
):
    monkeypatch.delenv("SONGLEAF_WEB_SITES", raising=False)
    store = {}
    sources = [StoredWebSource(store), memory_source]
    client = TestClient(
        mk_app(sources=sources, store=store, web_on_request=True, fetch=fetch)
    )
    assert client.get("/web").json() == {"available": True, "sites": ["LRCLIB"], "reason": ""}
    assert client.get("/search", params={"q": "willow lanterns"}).json() == []
    assert asked == []  # typing never goes online, even in an app that may
    rows = client.get("/search", params={"q": "willow lanterns", "web": "always"}).json()
    web = [row for row in rows if row["match"] == "web"]
    assert [row["key"] for row in web] == ["web:lrclib:31"]
    assert web[0]["meta"]["site"] == "lrclib" and web[0]["meta"]["url"]
    assert len(asked) == 1 and "web:lrclib:31" in store
    again = client.get("/search", params={"q": "willow lanterns"}).json()
    assert [(row["key"], row["meta"].get("site")) for row in again] == [
        ("web:lrclib:31", "lrclib")]  # found locally from then on, with its origin
    assert len(asked) == 1


def test_only_always_is_a_web_mode_a_request_may_ask_for(memory_source, fetch):
    client = TestClient(mk_app(sources=[memory_source], store={}, web_on_request=True, fetch=fetch))
    for mode in ("fallback", "off", "sometimes"):
        assert client.get("/search", params={"q": "x", "web": mode}).status_code == 422
