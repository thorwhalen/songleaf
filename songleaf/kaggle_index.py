"""A search index of the Kaggle corpus: the same songs and keys, without the corpus in memory.

:class:`~songleaf.sources.KaggleChordsSource` holds the whole corpus as a
DataFrame: about 1.1 GB per process, 1.6 GB once a lyrics search has run, and
every web worker holds its own copy. :func:`build_kaggle_index` writes it once
to one SQLite file beside the zip (``datasets/chords-and-lyrics/``): titles,
artists, popularity, each chart zlib-compressed, and an FTS5 table of the
charts' words. :class:`KaggleChordsIndex` reads that file. It keeps only the
titles, artists and popularity in memory (for fuzzy matching, a few tens of MB)
and answers lyrics searches and song lookups from disk.

Search results are the same as the DataFrame source's: the ranking code is
shared, and only where the data comes from differs.

>>> import pandas as pd, tempfile, os
>>> corpus = pd.DataFrame({
...     "Unnamed: 0": [1, 2], "artist_name": ["The Band", "Other"],
...     "song_name": ["Paper Boats", "Quiet Road"], "lang": ["en", "en"],
...     "popularity": [3, 1], "chords&lyrics": ["G\\nPaper boats drift", "C\\nquiet road"],
... })
>>> path = os.path.join(tempfile.mkdtemp(), "index.sqlite")
>>> build_kaggle_index(path=path, loader=lambda: corpus)["songs"]
2
>>> [hit.key for hit in KaggleChordsIndex(path).search(lyrics="boats")]
['kaggle_chords:1']
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import zlib
from contextlib import closing
from functools import cached_property
from pathlib import Path

from songleaf.sources import (
    KAGGLE_CHORDS_ZIP,
    KaggleChordsSource,
    SourceUnavailable,
    _load_kaggle_corpus,
)
from songleaf.store import data_dir

#: The index's file name, beside the corpus zip under ``datasets/``.
KAGGLE_INDEX_NAME = "chords-and-lyrics.sqlite"
_SCHEMA = """
CREATE TABLE songs (
    row INTEGER PRIMARY KEY,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    lang TEXT NOT NULL,
    popularity REAL NOT NULL,
    chart BLOB NOT NULL
);
CREATE VIRTUAL TABLE chart_words USING fts5(
    chart, content='', tokenize='unicode61 remove_diacritics 0'
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def kaggle_index_path() -> str:
    """Where the index lives: beside the corpus zip, under the data root."""
    folder = os.path.join(data_dir("datasets"), os.path.dirname(KAGGLE_CHORDS_ZIP))
    return os.path.join(folder, KAGGLE_INDEX_NAME)


def build_kaggle_index(
    *, path: str | None = None, loader=None, batch_size: int = 5000
) -> dict:
    """Write the index of the Kaggle corpus (``loader``: as for ``KaggleChordsSource``).

    Loading the corpus takes the memory the index exists to avoid, so run this
    once, apart from any server (``songleaf build-index``). The file is written
    beside the target and moved into place when complete, so a reader never
    sees half an index.
    """
    path = path or kaggle_index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    started = time.time()
    df = (loader or _load_kaggle_corpus)().reset_index(drop=True)
    columns = KaggleChordsSource.columns
    building = path + ".building"
    if os.path.exists(building):
        os.remove(building)
    with closing(sqlite3.connect(building)) as conn:
        conn.executescript(_SCHEMA)
        rows = zip(*(df[name].tolist() for name in columns))
        batch = []
        for row, (song_id, artist, title, chart, lang, popularity) in enumerate(rows):
            chart = chart if isinstance(chart, str) else ""
            batch.append(
                (
                    row,
                    str(song_id),
                    _text_or_empty(title),
                    _text_or_empty(artist),
                    str(lang),
                    _number_or_zero(popularity),
                    chart,
                )
            )
            if len(batch) >= batch_size:
                _insert(conn, batch)
                batch = []
        _insert(conn, batch)
        conn.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("songs", str(len(df))), ("built_at", time.strftime("%Y-%m-%d %H:%M:%S"))],
        )
        conn.execute("INSERT INTO chart_words(chart_words) VALUES ('optimize')")
        conn.commit()
    os.replace(building, path)
    return {
        "path": path,
        "songs": len(df),
        "megabytes": round(os.path.getsize(path) / 1e6, 1),
        "seconds": round(time.time() - started, 1),
    }


def _text_or_empty(value) -> str:
    return "" if value is None or value != value else str(value)  # NaN != NaN


def _number_or_zero(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if number != number else number


def _insert(conn, batch: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO songs VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(*fields[:-1], zlib.compress(fields[-1].encode("utf-8"))) for fields in batch],
    )
    conn.executemany(
        "INSERT INTO chart_words(rowid, chart) VALUES (?, ?)",
        [(fields[0], fields[-1]) for fields in batch],
    )


class KaggleChordsIndex(KaggleChordsSource):
    """The Kaggle corpus read from its index (:func:`build_kaggle_index`).

    The same ``name`` and ids as :class:`KaggleChordsSource`, so song keys and
    stored songs carry over. Only the columns fuzzy matching needs are held in
    memory; charts and lyrics matches come from the file.
    """

    def __init__(self, path: str | None = None, *, min_score: float = 70):
        super().__init__(loader=self._no_dataframe, min_score=min_score)
        self.path = path or kaggle_index_path()
        self._columns_lock = threading.Lock()
        self._columns_loaded = None

    @staticmethod
    def _no_dataframe():
        raise AssertionError("KaggleChordsIndex never loads the corpus DataFrame")

    def _connect(self):
        if not os.path.isfile(self.path):
            raise SourceUnavailable(
                f"No search index at {self.path}: run `songleaf build-index` "
                "where the corpus zip is"
            )
        # read-only, one connection per call: safe across threads
        return closing(sqlite3.connect(f"{Path(self.path).as_uri()}?mode=ro", uri=True))

    @property
    def _columns(self) -> dict[str, list]:
        """ids, titles, artists, langs and popularity, in row order, loaded once."""
        if self._columns_loaded is None:
            with self._columns_lock:
                if self._columns_loaded is None:
                    with self._connect() as conn:
                        rows = conn.execute(
                            "SELECT id, title, artist, lang, popularity "
                            "FROM songs ORDER BY row"
                        ).fetchall()
                    names = ("ids", "titles", "artists", "langs", "popularity")
                    self._columns_loaded = dict(zip(names, map(list, zip(*rows))))
        return self._columns_loaded

    @cached_property
    def _ids(self) -> list[str]:
        return self._columns.get("ids", [])

    @cached_property
    def _titles(self) -> list[str]:
        return self._columns.get("titles", [])

    @cached_property
    def _artists(self) -> list[str]:
        return self._columns.get("artists", [])

    @cached_property
    def _langs(self) -> list[str]:
        return self._columns.get("langs", [])

    @cached_property
    def _popularity(self) -> list[float]:
        return self._columns.get("popularity", [])

    def _containing(self, words: str) -> dict[int, float]:
        from rapidfuzz import utils

        tokens = utils.default_process(words).split()
        if not tokens:
            return {}
        match = " ".join('"{}"'.format(token.replace('"', '""')) for token in tokens)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT rowid FROM chart_words WHERE chart_words MATCH ?", (match,)
            ).fetchall()
        return {row: 100.0 for (row,) in rows}

    def _text(self, row: int) -> str:
        with self._connect() as conn:
            found = conn.execute(
                "SELECT chart FROM songs WHERE row = ?", (row,)
            ).fetchone()
        return zlib.decompress(found[0]).decode("utf-8") if found else ""
