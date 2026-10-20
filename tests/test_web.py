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


def test_the_song_comes_with_a_chord_table_for_every_key(client):
    song = client.get("/song", params={"key": "memory:1"}).json()
    assert song["title"] == "Paper Boats" and song["text"].startswith("")
    assert song["chords"][:4] == ["G", "D", "Em", "C"] and song["song_key"] == "G"
    tables = {t["semitones"]: t for t in song["transpositions"]}
    assert sorted(tables) == list(range(-5, 7))
    assert tables[2]["key"] == "A" and tables[2]["chords"]["Em"] == "F#m"
    assert tables[3]["key"] == "Bb" and tables[3]["chords"]["D"] == "F"  # flats in Bb
    assert tables[0]["chords"]["G"] == "G"


def test_a_transposed_and_scaled_sheet(client):
    plain = client.get("/sheet", params={"key": "memory:1"}).json()
    moved = client.get(
        "/sheet", params={"key": "memory:1", "transpose": 2, "scale": 0.5}
    ).json()
    assert moved["transpose"] == 2 and "(+2)" in moved["file_name"]
    assert moved["font_size"] == pytest.approx(plain["font_size"] * 0.5, rel=0.01)
    png = client.get("/sheet.png", params={"key": "memory:1", "transpose": 2})
    assert png.status_code == 200


def test_sheet_colours_and_ranges_are_checked(client):
    ok = client.get(
        "/sheet",
        params={"key": "memory:1", "chord_color": "#ff0000", "chord_alpha": 0.5},
    )
    assert ok.status_code == 200
    for bad in (
        {"chord_color": "red"},
        {"lyric_alpha": 2},
        {"scale": 0},
        {"transpose": 40},
        {"chord_scale": 5},
    ):
        response = client.get("/sheet", params={"key": "memory:1", **bad})
        assert response.status_code == 400, bad


def test_layouts_carry_the_default_look(client):
    body = client.get("/layouts").json()
    assert (
        body["style"]["chord_color"].startswith("#")
        and 0 < body["style"]["chord_scale"] < 1
    )


def test_sections_carry_the_family_the_sheet_shades(client):
    sections = client.get("/song", params={"key": "memory:1"}).json()["sections"]
    families = {s["label"]: s["family"] for s in sections}
    assert families["Chorus"] == "chorus" and families["Verse 1"] == ""


def test_a_stored_song_can_be_deleted(client):
    client.get("/sheet", params={"key": "memory:1"})  # stores it
    assert [s["key"] for s in client.get("/songs").json()] == ["memory:1"]
    assert client.delete("/songs", params={"key": "memory:1"}).json()["deleted"]
    assert client.get("/songs").json() == []
    assert client.delete("/songs", params={"key": "memory:1"}).status_code == 404


def _edge(edge_id, parent, child):
    return {"id": edge_id, "parent": parent, "child": child, "kind": "contains"}


def test_groups_save_with_a_revision_and_refuse_a_stale_one(client):
    client.get("/sheet", params={"key": "memory:1"})  # stored: may be in a group
    empty = client.get("/groups").json()
    assert empty == {"revision": 0, "snapshot": {"nodes": [], "edges": []}}
    snapshot = {
        "nodes": [{"id": "Family"}],
        "edges": [_edge("e1", "Family", "memory:1")],
    }
    saved = client.put("/groups", json={"revision": 0, "snapshot": snapshot})
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert saved.json()["snapshot"]["edges"] == snapshot["edges"]
    stale = client.put(
        "/groups", json={"revision": 0, "snapshot": {"nodes": [], "edges": []}}
    )
    assert stale.status_code == 409 and stale.json()["current"]["revision"] == 1


def test_groups_refuse_what_a_page_could_not_load(client):
    def put(snapshot, revision=0):
        return client.put("/groups", json={"revision": revision, "snapshot": snapshot})

    loop = [_edge("a", "A", "B"), _edge("b", "B", "A")]
    for bad in (
        {"nodes": "x", "edges": []},
        {"nodes": [], "edges": [_edge("e", "A", "A")]},  # self-loop
        {"nodes": [], "edges": loop},  # cycle
        {
            "nodes": [],
            "edges": [_edge("e", "A", "B"), _edge("e", "A", "C")],
        },  # duplicate id
        {"nodes": [{"id": "A"}, {"id": "A"}], "edges": []},  # duplicate node
        {"nodes": [], "edges": [{"id": "e", "parent": "A", "child": "B"}]},  # no kind
    ):
        assert put(bad).status_code == 400, bad
    for revision in (0.5, True, "0"):
        assert put({"nodes": [], "edges": []}, revision).status_code == 400, revision
    assert client.put("/groups", content=b"[1, 2]").status_code == 400


def test_a_song_not_stored_is_dropped_from_groups_on_save(client):
    snapshot = {
        "nodes": [{"id": "Family"}, {"id": "Inner"}],
        "edges": [_edge("e1", "Family", "memory:9"), _edge("e2", "Family", "Inner")],
    }
    saved = client.put("/groups", json={"revision": 0, "snapshot": snapshot}).json()
    assert [e["child"] for e in saved["snapshot"]["edges"]] == ["Inner"]


def test_deleting_a_song_takes_it_out_of_its_groups(client):
    client.get("/sheet", params={"key": "memory:1"})
    snapshot = {
        "nodes": [{"id": "Family"}],
        "edges": [_edge("e1", "Family", "memory:1")],
    }
    client.put("/groups", json={"revision": 0, "snapshot": snapshot})
    client.delete("/songs", params={"key": "memory:1"})
    assert client.get("/groups").json()["snapshot"]["edges"] == []


def test_the_vendored_groups_bundle_is_served(client):
    js = client.get("/ui/vendor/zodal-groups.js")
    assert js.status_code == 200
    assert "defineGroups" in js.text and "renderTagMenu" in js.text
    assert client.get("/ui/vendor/other.js").status_code == 404
    assert client.get("/ui/vendor%2F..%2Fapp.js").status_code == 404


def test_layout_controls_name_every_option_once_in_plain_words(client):
    from songleaf.render import LAYOUT_OPTIONS

    body = client.get("/layouts").json()
    offered = [
        choice["option"]
        for control in body["controls"]
        for choice in control["choices"]
        if choice["option"]
    ]
    assert sorted(offered) == sorted(set(LAYOUT_OPTIONS) - {"dense"})
    for control in body["controls"]:
        assert control["label"] and all(c["label"] for c in control["choices"])
        # each control offers the default layout's own choice first
        assert control["choices"][0]["option"] == ""
    labels = {o["name"]: o["label"] for o in body["options"]}
    assert labels["packed"] == "Break at rhymes" and labels["two-column"] == "Two"


def test_options_in_one_control_set_the_same_thing(client):
    body = client.get("/layouts").json()
    sets = {o["name"]: set(o["sets"]) for o in body["options"]}
    for control in body["controls"]:
        names = [c["option"] for c in control["choices"] if c["option"]]
        common = set.intersection(*(sets[n] for n in names))
        assert common, control["name"]  # so the page's choices exclude each other


def test_every_ui_file_is_served(client):
    from songleaf.web import _UI_FILES

    for name, media_type in _UI_FILES.items():
        response = client.get(f"/ui/{name}")
        assert response.status_code == 200, name
        assert response.headers["content-type"].startswith(media_type)


def test_the_reader_settings_map_onto_real_layout_options(client):
    from songleaf.render import LAYOUT_OPTIONS

    mapping = client.get("/layouts").json()["from_reader"]
    assert set(mapping) == {"chordMode", "columns", "shade"}
    for by_value in mapping.values():
        assert set(by_value.values()) <= set(LAYOUT_OPTIONS) - {"dense"}


def test_import_stores_a_pasted_song_and_it_can_be_read(client):
    text = "{title: Paper Boats}\nPaper [G]boats on a [D]stream\n"
    info = client.post("/import", json={"text": text, "artist": "The Invented Band"}).json()
    assert info["key"].startswith("paste:") and info["format"] == "chordpro"
    song = client.get("/song", params={"key": info["key"]}).json()
    assert song["chords"] == ["G", "D"]
    assert song["provenance"]["source"] == "paste"
    assert song["artist"] == "The Invented Band"


def test_import_refuses_empty_text_and_non_strings(client):
    assert client.post("/import", json={"text": "  "}).status_code == 400
    assert client.post("/import", json={"text": 3}).status_code == 400


def test_a_song_downloads_as_chordpro_and_as_text(client):
    cho = client.get("/song.cho", params={"key": "memory:1", "transpose": 2})
    assert cho.status_code == 200 and "attachment" in cho.headers["content-disposition"]
    assert ".cho" in cho.headers["content-disposition"] and "%28%2B2%29" in cho.headers["content-disposition"]
    assert cho.text.startswith("{title: Paper Boats}")
    text = client.get("/song.txt", params={"key": "memory:1"})
    assert text.status_code == 200 and "Paper Boats" in text.text.splitlines()[0]
    assert client.get("/song.cho", params={"key": "memory:1", "transpose": 40}).status_code == 422


def test_media_links_a_recording_by_link_or_id(client):
    key = client.post("/import", json={"text": "G\nPaper boats on a stream\n"}).json()["key"]
    info = client.put("/media", json={"key": key, "youtube": "https://youtu.be/dQw4w9WgXcQ"}).json()
    assert info["media"] == {"youtube": "dQw4w9WgXcQ"}
    assert client.get("/song", params={"key": key}).json()["meta"]["media"]["youtube"] == "dQw4w9WgXcQ"
    assert client.put("/media", json={"key": key, "youtube": "-"}).json()["media"] == {}
    assert client.put("/media", json={"key": key, "spotify": "not an id"}).status_code == 400
    assert client.put("/media", json={"key": "paste:nothing", "youtube": "-"}).status_code == 404
    assert client.put("/media", json={"key": key, "youtube": 3}).status_code == 400


def test_sync_keeps_only_the_times(memory_source, tmp_path):
    asked = []

    def get_json(url, params):
        asked.append(params)
        return {"syncedLyrics": "[00:01.00]Paper boats on a stream\n[00:04.50]carry the names"}

    store = song_store(str(tmp_path / "songs"))
    client = TestClient(mk_app(sources=[memory_source], store=store, get_json=get_json))
    text = "G\nPaper boats on a stream\nD\ncarry the names\n"
    key = client.post("/import", json={"text": text, "title": "Paper Boats"}).json()["key"]
    info = client.post("/sync", json={"key": key, "lrc": "[00:02.00]Paper boats on a stream"}).json()
    assert info["timed"] == 1
    info = client.post("/sync", json={"key": key, "lrclib": True}).json()
    assert info["timed"] == 2 and asked[0]["track_name"] == "Paper Boats"
    song = client.get("/song", params={"key": key}).json()
    times = [a["body"]["ms"] for a in song["annotations"] if a["kind"] == "time"]
    assert times == [1000, 4500]
    assert song["text"] == "Paper boats on a stream\ncarry the names"  # the LRC's words are not kept
    unmatched = client.post("/sync", json={"key": key, "lrc": "[00:09.00]nothing like it at all"})
    assert unmatched.status_code == 400  # and the timings stay
    assert len([a for a in client.get("/song", params={"key": key}).json()["annotations"] if a["kind"] == "time"]) == 2
    assert client.post("/sync", json={"key": key}).status_code == 400
    assert client.post("/sync", json={"key": key, "lrc": "x" * 200_000}).status_code == 400
