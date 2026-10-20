"""Ultimate Guitar intake (songleaf#28): refusal rules, page parsing, the opt-in URL source,
the import route and the bookmarklet. Every chart here is synthetic."""

import html
import json
import shutil
import subprocess
from importlib.resources import files

import pytest

from songleaf import tools
from songleaf import ultimate_guitar as ug
from songleaf.importers import import_song

COMMUNITY = "https://tabs.ultimate-guitar.com/tab/the-invented-band/paper-boats-chords-424242"
OFFICIAL = "https://tabs.ultimate-guitar.com/tab/the-invented-band/paper-boats-official-5150"
PRO = "https://tabs.ultimate-guitar.com/pro/the-invented-band/paper-boats-9999"
CHART = "[Verse 1]\n[tab][ch]G[/ch]          [ch]D[/ch]\nPaper boats on a silver stream[/tab]\n"


def _store(*, kind="Chords", content=CHART, url=COMMUNITY, capo=2):
    return {
        "store": {
            "page": {
                "data": {
                    "tab": {
                        "id": 424242,
                        "type": kind,
                        "song_name": "Paper Boats",
                        "artist_name": "The Invented Band",
                        "tonality_name": "G",
                        "tab_url": url,
                    },
                    "tab_view": {"wiki_tab": {"content": content}, "meta": {"capo": capo}},
                }
            }
        }
    }


def _page(store):
    return f'<div class="js-store" data-content="{html.escape(json.dumps(store))}"></div>'


def test_refusal_rules():
    assert ug.refusal(COMMUNITY) == ""
    assert ug.refusal(OFFICIAL) == ug.REFUSAL_OFFICIAL
    assert ug.refusal(PRO) == ug.REFUSAL_OFFICIAL
    assert ug.refusal(COMMUNITY, tab_type="Official") == ug.REFUSAL_OFFICIAL
    assert ug.refusal("https://example.com/x-official-1") == ""  # only UG URLs are judged
    assert ug.ug_key(COMMUNITY) == "ug:424242"
    assert ug.ug_key("https://example.com/song-42") == ""
    assert not ug.is_ultimate_guitar_url("https://ultimate-guitar.com.example.org/tab/x-1")


def test_chart_from_a_page():
    chart = ug.chart_from_html(_page(_store()))
    assert chart["title"] == "Paper Boats" and chart["key"] == "G" and chart["capo"] == "2"
    assert chart["id"] == "424242" and chart["text"] == CHART
    ugapp = _store()["store"]  # window.UGAPP.store has no outer "store"
    assert ug.chart_from_store(ugapp)["artist"] == "The Invented Band"


@pytest.mark.parametrize(
    "store",
    [_store(kind="Official"), _store(kind="Pro"), _store(url=OFFICIAL), _store(content="")],
)
def test_official_pro_and_empty_pages_are_refused(store):
    with pytest.raises(ug.RefusedPage):
        ug.chart_from_html(_page(store))


def test_import_keys_by_tab_and_refuses_official_urls():
    imported = import_song(CHART, url=COMMUNITY, key="G", capo="2")
    assert imported.key == "ug:424242"
    assert imported.song.meta["key"] == "G" and imported.song.meta["capo"] == "2"
    provenance = imported.song.provenance
    assert provenance["license"] == "personal" and provenance["site"] == "ultimate-guitar"
    with pytest.raises(ValueError, match="official or Pro"):
        import_song(CHART, url=OFFICIAL)


def test_url_source_is_off_by_default_and_never_searches(monkeypatch):
    monkeypatch.delenv(ug.URL_SOURCE_ENVVAR, raising=False)
    source = ug.UltimateGuitarURLSource(fetch=lambda url: pytest.fail("fetched"))
    assert source.search("paper boats") == []
    with pytest.raises(ValueError, match="off"):
        source.get(COMMUNITY)


def test_url_source_is_not_a_default_or_web_source():
    import inspect

    from songleaf import sources

    web = files("songleaf").joinpath("web.py").read_text()
    assert "ultimate_guitar" not in inspect.getsource(sources.default_sources)
    assert "import_url" not in web and "UltimateGuitarURLSource" not in web


def test_import_url_fetches_once_then_reads_the_store():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return _page(_store())

    store = {}
    source = ug.UltimateGuitarURLSource(fetch=fetch, enabled=True)
    first = tools.import_url(COMMUNITY, store=store, source=source)
    again = tools.import_url(COMMUNITY, store=store, source=source)
    assert first["key"] == again["key"] == "ug:424242"
    assert (first["cached"], again["cached"]) == (False, True)
    assert fetched == [COMMUNITY]
    with pytest.raises(ug.RefusedPage):
        tools.import_url(OFFICIAL, store=store, source=source)
    for bad in [
        "http://tabs.ultimate-guitar.com/tab/x/y-chords-1",
        "https://evil.example\\@tabs.ultimate-guitar.com/tab/x/y-chords-1",
        "https://user@tabs.ultimate-guitar.com/tab/x/y-chords-1",
        "file:///etc/passwd",
    ]:
        with pytest.raises(ValueError, match="plain https"):
            source.get(bad)
        with pytest.raises(ValueError, match="plain https"):
            ug.fetch_page(bad)


def test_more_paid_url_forms_are_refused_and_meta_is_bounded():
    for form in ("pro", "power", "video", "guitar-pro"):
        url = f"https://tabs.ultimate-guitar.com/tab/the-invented-band/paper-boats-{form}-77"
        assert ug.refusal(url) == ug.REFUSAL_OFFICIAL
    with pytest.raises(ValueError, match="too long"):
        import_song(CHART, key="x" * 50)


def test_web_import_takes_key_and_capo_and_refuses_official(memory_source, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from songleaf.store import song_store
    from songleaf.web import mk_app

    client = TestClient(mk_app(sources=[memory_source], store=song_store(str(tmp_path))))
    body = {"text": CHART, "url": COMMUNITY, "key": "G", "capo": "2", "format": "ultimate-guitar"}
    info = client.post("/import", json=body).json()
    assert info["key"] == "ug:424242"
    refused = client.post("/import", json={**body, "url": OFFICIAL})
    assert refused.status_code == 400 and "official" in refused.json()["detail"]
    script = client.get("/ui/bookmarklet.js")
    assert script.status_code == 200 and "__SONGLEAF_PAGE__" in script.text


_HARNESS = r"""
const vm = require("vm");
const [code, host, path, storeJson] = process.argv.slice(1);
const out = { alerts: [], opened: [] };
const element = storeJson === "null" ? null : { getAttribute: () => storeJson };
const context = {
  document: { querySelector: () => element },
  window: {
    location: { hostname: host, pathname: path, origin: "https://" + host, assign: (u) => out.opened.push(u) },
    alert: (m) => out.alerts.push(m),
    open: (u) => { out.opened.push(u); return {}; },
  },
};
vm.runInNewContext(code.replace('"__SONGLEAF_PAGE__"', '"https://songleaf.invalid/"'), context);
console.log(JSON.stringify(out));
"""


def _run_bookmarklet(host, path, store):
    code = files("songleaf").joinpath("data", "web", "bookmarklet.js").read_text()
    result = subprocess.run(
        ["node", "-e", _HARNESS, code, host, path, json.dumps(store)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_bookmarklet_sends_community_charts_and_refuses_the_rest():
    host, path = "tabs.ultimate-guitar.com", "/tab/the-invented-band/paper-boats-chords-424242"
    out = _run_bookmarklet(host, path, _store())
    assert out["alerts"] == [] and len(out["opened"]) == 1
    target = out["opened"][0]
    assert target.startswith("https://songleaf.invalid/#import=")
    from urllib.parse import unquote

    chart = json.loads(unquote(target.split("#import=", 1)[1]))
    assert chart["text"] == CHART and chart["capo"] == "2" and chart["format"] == "ultimate-guitar"

    for args in [
        (host, path, _store(kind="Official")),
        (host, "/tab/the-invented-band/paper-boats-official-5150", _store()),
        (host, path, _store(content="")),
        ("example.com", path, _store()),
        (host, path, None),
    ]:
        out = _run_bookmarklet(*args)
        assert out["opened"] == [] and len(out["alerts"]) == 1
