"""A search index of the Kaggle corpus: the same songs and keys, without the corpus in memory.

:class:`~songleaf.sources.KaggleChordsSource` holds the whole corpus as a
DataFrame: about 1.1 GB per process, 1.6 GB once a lyrics search has run, and
every web worker holds its own copy. :func:`build_kaggle_index` writes it once
to one SQLite file beside the zip (``datasets/chords-and-lyrics/``): titles,
artists, popularity, each chart zlib-compressed, and an FTS5 table of the
charts' words. :class:`KaggleChordsIndex` reads that file. It keeps only the
titles, artists and popularity in memory (for fuzzy matching, a few tens of MB)
and answers lyrics searches and song lookups from disk.

Search results are the DataFrame source's: the ranking code is shared, and only
where the data comes from differs. The one difference is how lyrics split into
words: FTS5's tokenizer treats ``_`` as a separator and does not compose
decomposed accents, where the DataFrame source's regular expression does the
opposite. Rebuilding the index while a server runs is safe: a process that
notices the file changed reloads it.

The file format, its writing and its raw reads belong to ``sung.chords_index``
(stdlib only, so reading the index never imports pandas); this module adds where
songleaf keeps the file and the ranking shared with the DataFrame source.

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
import threading
from functools import cached_property

from sung import chords_index

from songleaf.sources import (
    KAGGLE_CHORDS_ZIP,
    KaggleChordsSource,
    SourceUnavailable,
    _load_kaggle_corpus,
)
from songleaf.datasets import dataset_path
from songleaf.store import data_dir

#: The index's file name, beside the corpus zip under ``datasets/``.
KAGGLE_INDEX_NAME = chords_index.INDEX_NAME


def _index_key() -> str:
    return (
        KAGGLE_CHORDS_ZIP.replace(os.sep, "/").rsplit("/", 1)[0]
        + "/"
        + KAGGLE_INDEX_NAME
    )


def kaggle_index_path() -> str:
    """Where the index is read from: beside the corpus zip under the data root.

    When the datasets live on S3 (``songleaf.datasets``), this is the cached
    download of the index (fetched on first use), a real file for SQLite.
    """
    return dataset_path(_index_key())


def _local_index_path() -> str:
    """Where a build writes the index: always the local data root (upload it after)."""
    folder = os.path.join(data_dir("datasets"), os.path.dirname(KAGGLE_CHORDS_ZIP))
    return os.path.join(folder, KAGGLE_INDEX_NAME)


def build_kaggle_index(
    *, path: str | None = None, loader=None, batch_size: int = 5000
) -> dict:
    """Write the index of the Kaggle corpus (``loader``: as for ``KaggleChordsSource``).

    Loading the corpus takes the memory the index exists to avoid, so run this
    once, apart from any server (``songleaf build-index``). The index format and
    its writing are ``sung.chords_index``'s; this picks the corpus and the path.
    """
    df = (loader or _load_kaggle_corpus)().reset_index(drop=True)
    return chords_index.build_chords_index(
        path or _local_index_path(),
        rows=zip(*(df[name].tolist() for name in KaggleChordsSource.columns)),
        batch_size=batch_size,
    )


class KaggleChordsIndex(KaggleChordsSource):
    """The Kaggle corpus read from its index (:func:`build_kaggle_index`).

    The same ``name`` and ids as :class:`KaggleChordsSource`, so song keys and
    stored songs carry over. Only the columns fuzzy matching needs are held in
    memory; charts and lyrics matches come from the file.
    """

    def __init__(self, path: str | None = None, *, min_score: float = 70):
        super().__init__(loader=self._no_dataframe, min_score=min_score)
        self.path = os.path.abspath(path or kaggle_index_path())
        self._columns_lock = threading.Lock()
        self._columns_loaded = None
        self._loaded_version = None  # (mtime, size) of the file the columns came from

    @staticmethod
    def _no_dataframe():
        raise AssertionError("KaggleChordsIndex never loads the corpus DataFrame")

    def _read(self, read, *args):
        """``read(path, *args)`` from ``sung.chords_index``; no file is a ``SourceUnavailable``."""
        try:
            return read(self.path, *args)
        except FileNotFoundError as error:
            raise SourceUnavailable(
                f"No search index at {self.path}: run `songleaf build-index` "
                "where the corpus zip is"
            ) from error

    _CACHED = (
        "_ids",
        "_titles",
        "_artists",
        "_langs",
        "_popularity",
        "_labels",
        "_row_of_id",
        "_title_words",
        "_artist_words",
    )

    def _version(self):
        return chords_index.index_version(self.path)

    def _reload_if_rebuilt(self) -> None:
        """Drop what was read from an index file that has since been rebuilt."""
        if self._loaded_version is not None and self._version() != self._loaded_version:
            with self._columns_lock:
                self._columns_loaded, self._loaded_version = None, None
                for name in self._CACHED:
                    self.__dict__.pop(name, None)

    def search(self, query: str = "", **constraints):
        self._reload_if_rebuilt()
        return super().search(query, **constraints)

    def search_tiers(self, query: str, *, limit: int = 10):
        self._reload_if_rebuilt()
        return super().search_tiers(query, limit=limit)

    def get(self, song_id: str):
        self._reload_if_rebuilt()
        return super().get(song_id)

    @property
    def _columns(self) -> dict[str, list]:
        """ids, titles, artists, langs and popularity, in row order, loaded once per file."""
        if self._columns_loaded is None:
            with self._columns_lock:
                if self._columns_loaded is None:
                    self._loaded_version = self._version()
                    self._columns_loaded = self._read(chords_index.read_columns)
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
        rows = self._read(chords_index.rows_with_words, tokens)
        return dict.fromkeys(rows, 100.0)

    def _text(self, row: int) -> str:
        return self._read(chords_index.read_chart, row)
