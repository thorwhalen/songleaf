"""The one-command test, runnable in CI: query to a one-page PDF, through a synthetic source.

The same path on the real corpus is ``tests/test_real_corpus.py`` (local only).
"""

import pytest

from songleaf import sources as sources_module
from songleaf import tools
from songleaf.__main__ import main
from songleaf.store import song_store


def test_a_query_becomes_a_one_page_pdf(memory_source, page_count, tmp_path):
    store = song_store(str(tmp_path / "songs"))
    result = tools.sheet(
        "paper boats",
        output=str(tmp_path / "sheet.pdf"),
        sources=[memory_source],
        store=store,
    )
    assert (result["key"], result["title"], result["pages"]) == (
        "memory:1",
        "Paper Boats",
        1,
    )
    assert page_count((tmp_path / "sheet.pdf").read_bytes()) == 1
    assert tools.songs(store=store) == ["memory:1"]
    # a stored song renders by key, with no source at all
    again = tools.sheet(
        "memory:1", output=str(tmp_path / "again.pdf"), sources=[], store=store
    )
    assert again["font_size"] == result["font_size"]


def test_sheets_go_to_the_data_dir_by_default(memory_source, tmp_path, monkeypatch):
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    result = tools.sheet("paper boats", sources=[memory_source])
    assert result["path"] == str(
        tmp_path / "sheets" / "the-invented-band-paper-boats.pdf"
    )


def test_no_match_is_a_lookup_error(memory_source):
    with pytest.raises(LookupError):
        tools.sheet("no such song", sources=[memory_source])
    with pytest.raises(LookupError):
        tools.sheet("paper boats", pick=2, sources=[memory_source])


def run_cli(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    out, err = capsys.readouterr()
    return exit_info.value.code, out, err


def test_the_cli_makes_a_sheet(memory_source, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sources_module, "default_sources", lambda: (memory_source,))
    code, out, _ = run_cli(
        ["sheet", "paper boats", "--output", str(tmp_path / "cli.pdf")], capsys
    )
    assert code == 0 and "memory:1" in out
    assert (tmp_path / "cli.pdf").exists()
    code, out, _ = run_cli(["songs"], capsys)
    assert code == 0 and "memory:1" in out


def test_the_cli_hides_the_seams(capsys):
    code, out, _ = run_cli(["sheet", "--help"], capsys)
    assert code == 0 and "--output" in out
    assert "--store" not in out and "--sources" not in out and "--renderer" not in out


def test_the_cli_reports_no_match_in_one_line(memory_source, monkeypatch, capsys):
    monkeypatch.setattr(sources_module, "default_sources", lambda: (memory_source,))
    code, _, err = run_cli(["sheet", "no such song"], capsys)
    assert code == 1 and "No song" in err and "Traceback" not in err
