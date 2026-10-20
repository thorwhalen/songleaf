"""Pasted-text importers: format detection, parsing, keys and the tool/CLI."""

import pytest

from songleaf import tools
from songleaf.importers import IMPORTERS, Importer, detect_format, import_song, paste_key
from songleaf.store import song_store

UG = (
    "[Verse 1]\n"
    "[ch]G[/ch]          [ch]D[/ch]\n"
    "Paper boats on a silver stream\n"
    "[ch]Em[/ch]\n"
    "carry the names\n"
)
CHORDPRO = "{title: Paper Boats}\n{artist: The Invented Band}\nPaper [G]boats on a [D]stream\n"
OPENSONG = ";comment\n[V1]\n.G          D\n Paper boats on a stream\n"
PLAIN = "Verse 1\nG          D\nPaper boats on a stream\n"


@pytest.mark.parametrize(
    "text, name",
    [
        (UG, "ultimate-guitar"),
        (CHORDPRO, "chordpro"),
        (OPENSONG, "opensong"),
        (PLAIN, "chords-over-lyrics"),
    ],
)
def test_detection(text, name):
    assert detect_format(text) == name


def test_ultimate_guitar_markup_becomes_columns_and_sections():
    song = import_song(UG, title="T", artist="A", url="https://example.org/x").song
    assert song.text == "Paper boats on a silver stream\ncarry the names"
    assert [(a.start, a.body["symbol"]) for a in song.of_kind("chord")] == [
        (0, "G"), (12, "D"), (31, "Em"),
    ]
    assert song.of_kind("section")[0].body["label"] == "Verse 1"
    assert song.provenance == {
        "source": "paste", "license": "personal", "url": "https://example.org/x",
    }
    assert (song.title, song.artist) == ("T", "A")


def test_chordpro_metadata_and_overrides():
    imported = import_song(CHORDPRO)
    assert imported.song.artist == "The Invented Band"
    assert import_song(CHORDPRO, artist="Other").song.artist == "Other"


def test_opensong_chords_anchor_on_lyrics():
    song = import_song(OPENSONG).song
    assert song.text == "Paper boats on a stream"
    assert [a.body["symbol"] for a in song.of_kind("chord")] == ["G", "D"]
    assert song.of_kind("section")[0].body["label"] == "Verse 1"


def test_key_is_stable_and_whitespace_insensitive():
    assert paste_key("a  b\n") == paste_key("a b")
    assert paste_key("a").startswith("paste:")


def test_errors():
    with pytest.raises(ValueError, match="empty"):
        import_song("  \n")
    with pytest.raises(ValueError, match="Unknown format"):
        import_song(PLAIN, format="nope")


def test_registry_is_extensible():
    custom = Importer("custom", lambda t: t.startswith("@@"), lambda t, **kw: IMPORTERS[-1].parse(t[2:], **kw))
    assert import_song("@@" + PLAIN, importers=(custom, *IMPORTERS)).format == "custom"


def test_tool_stores_and_the_song_is_usable(tmp_path):
    store = song_store(str(tmp_path / "songs"))
    info = tools.import_text(UG, title="Paper Boats", store=store)
    assert info["format"] == "ultimate-guitar" and info["chords"] == 3
    assert tools.song(info["key"], store=store)["chords"] == ["G", "D", "Em"]
    assert tools.import_text(UG, store=store)["key"] == info["key"]  # idempotent
