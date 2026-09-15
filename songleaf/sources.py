"""Where songs are found: sources, and a search that composes them.

A *source* is any object with a ``name``, a
``search(query, *, title, artist, lyrics, limit) -> list[Hit]`` method and a
``get(song_id) -> Song`` method. :func:`search` and :func:`get_song` take
several through ``sources=``; the default is the Kaggle chords-and-lyrics
corpus, read through ``sung``.

A hit's :attr:`Hit.key` (``"<source>:<id>"``) names the song everywhere: it is
what :func:`get_song` resolves and what the store is keyed by.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from functools import cached_property, lru_cache

from songleaf.model import Song, score_link
from songleaf.store import data_dir

KAGGLE_CHORDS_URL = (
    "https://www.kaggle.com/datasets/eitanbentora/chords-and-lyrics-dataset"
)
#: Lines of the chords site's page left in the corpus, not part of any song:
#: "hide this tab" (in ~9% of songs) and obfuscated e-mail addresses.
_KAGGLE_SITE_NOISE = re.compile(
    r"^[ \t]*(?:(?:hide|show) this tab|\[email[^\]\n]*protected\])[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Hit:
    """One search result: a song a source can :meth:`get`."""

    source: str
    id: str
    title: str
    artist: str = ""
    score: float = 0.0  # relevance in [0, 1]
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """``"<source>:<id>"``, the song's name for :func:`get_song` and the store."""
        return f"{self.source}:{self.id}"

    def to_dict(self) -> dict:
        """The JSON-ready form."""
        return {"key": self.key, **asdict(self)}


def _load_kaggle_corpus():
    from sung.chords_and_lyrics import get_lyrics_and_chords_dataset

    try:
        return get_lyrics_and_chords_dataset(usecols=KaggleChordsSource.columns)
    except Exception as error:
        raise RuntimeError(
            "Could not load the Kaggle chords-and-lyrics corpus. Point "
            "SUNG_CHORDS_AND_LYRICS_ZIP at a local copy of "
            f"chords-and-lyrics-dataset.zip (from {KAGGLE_CHORDS_URL}). Without "
            "one, sung downloads it through haggle, which needs `pip install haggle` "
            f"and Kaggle credentials. (The loader said: {error})"
        ) from error


class KaggleChordsSource:
    """The Kaggle *chords-and-lyrics* corpus (~135K songs, chords over lyrics).

    Read through ``sung`` from a local copy of the zip, with no Kaggle
    credentials needed when that copy exists. The corpus was scraped from a
    chords site: personal use only (licence tag ``gray``).

    Title and artist are matched fuzzily (typos, punctuation and word order
    do not matter); lyrics must contain every word of the ``lyrics`` query as a
    whole word. Lyrics matches are not ranked beyond popularity.

    Args:
        loader: ``() -> pandas.DataFrame`` with :attr:`columns`. Defaults to
            sung's loader of the local corpus zip.
        min_score: Fuzzy-match cutoff, 0-100.
    """

    name = "kaggle_chords"
    license = "gray"
    columns = (
        "Unnamed: 0",
        "artist_name",
        "song_name",
        "chords&lyrics",
        "lang",
        "popularity",
    )

    def __init__(self, *, loader=None, min_score: float = 70):
        self._loader = loader or _load_kaggle_corpus
        self.min_score = min_score

    @cached_property
    def _df(self):
        return self._loader().reset_index(drop=True)

    @cached_property
    def _titles(self) -> list[str]:
        return self._df["song_name"].fillna("").astype(str).tolist()

    @cached_property
    def _artists(self) -> list[str]:
        return self._df["artist_name"].fillna("").astype(str).tolist()

    @cached_property
    def _labels(self) -> list[str]:
        return [f"{t} {a}" for t, a in zip(self._titles, self._artists)]

    @cached_property
    def _popularity(self) -> list[float]:
        return self._df["popularity"].fillna(0).astype(float).tolist()

    @cached_property
    def _row_of_id(self) -> dict[str, int]:
        return {str(v): i for i, v in enumerate(self._df["Unnamed: 0"])}

    @cached_property
    def _plain_lyrics(self):
        text = self._df["chords&lyrics"].fillna("").astype(str).str.lower()
        return text.str.replace(r"[^\w\s]+", " ", regex=True)

    def _fuzzy(self, needle: str, choices: list[str]) -> dict[int, float]:
        from rapidfuzz import fuzz, process, utils

        matches = process.extract(
            needle,
            choices,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            score_cutoff=self.min_score,
            limit=None,
        )
        return {index: score for _, score, index in matches}

    def _containing(self, words: str) -> dict[int, float]:
        from rapidfuzz import utils

        mask = None
        for word in utils.default_process(words).split():
            pattern = rf"\b{re.escape(word)}\b"
            has = self._plain_lyrics.str.contains(pattern, regex=True)
            mask = has if mask is None else mask & has
        if mask is None:
            return {}
        return {int(i): 100.0 for i in mask[mask].index}

    def search(
        self,
        query: str = "",
        *,
        title: str = "",
        artist: str = "",
        lyrics: str = "",
        limit: int = 10,
    ) -> list[Hit]:
        """Songs matching every given constraint, best first."""
        scores = []
        if query:
            scores.append(self._fuzzy(query, self._labels))
        if title:
            scores.append(self._fuzzy(title, self._titles))
        if artist:
            scores.append(self._fuzzy(artist, self._artists))
        if lyrics:
            scores.append(self._containing(lyrics))
        if not scores:
            return []
        rows = set(scores[0]).intersection(*scores[1:])

        def relevance(row):
            return sum(s[row] for s in scores) / len(scores)

        ranked = sorted(rows, key=lambda r: (-relevance(r), -self._popularity[r]))
        return [self._hit(row, relevance(row)) for row in ranked[:limit]]

    def _hit(self, row: int, score: float) -> Hit:
        record = self._df.iloc[row]
        return Hit(
            source=self.name,
            id=str(record["Unnamed: 0"]),
            title=self._titles[row],
            artist=self._artists[row],
            score=round(score / 100, 4),
            meta={"lang": str(record["lang"]), "popularity": self._popularity[row]},
        )

    def get(self, song_id: str) -> Song:
        """The song with this id, parsed into a :class:`Song`."""
        from songleaf.parse import parse_chords_over_lyrics

        try:
            row = self._row_of_id[str(song_id)]
        except KeyError:
            raise KeyError(f"No song with id {song_id!r} in {self.name}") from None
        record = self._df.iloc[row]
        text = record["chords&lyrics"]
        return parse_chords_over_lyrics(
            _KAGGLE_SITE_NOISE.sub("", text) if isinstance(text, str) else "",
            meta={
                "title": self._titles[row],
                "artist": self._artists[row],
                "lang": str(record["lang"]),
            },
            provenance={
                "source": self.name,
                "id": str(song_id),
                "url": KAGGLE_CHORDS_URL,
                "license": self.license,
            },
        )


#: Text files parsed as chords-over-lyrics charts (same format as the Kaggle
#: corpus) -- what a chords/tabs site's own "download" or "export" gives you.
_TEXT_EXTS = frozenset({".txt", ".cho", ".chopro", ".crd", ".pro"})
#: Score/tab files with no lyrics to parse: attached as a bare score link.
_SCORE_EXTS = {
    ".gp": "guitarpro",
    ".gpx": "guitarpro",
    ".gp3": "guitarpro",
    ".gp4": "guitarpro",
    ".gp5": "guitarpro",
    ".musicxml": "musicxml",
    ".mxl": "musicxml",
    ".mscz": "musescore",
    ".mid": "midi",
    ".midi": "midi",
    ".pdf": "pdf",
}


def _title_and_artist(stem: str) -> tuple[str, str]:
    """``"Artist - Title"`` splits; anything else is a bare title."""
    artist, sep, title = stem.partition(" - ")
    return (title, artist) if sep else (stem, "")


class LocalFolderSource:
    """A folder of files you exported yourself, indexed and searched by name.

    For files a chords/tab site lets a paying user export -- Ultimate Guitar's
    Guitar Pro/PDF downloads, MuseScore's MusicXML/MSCZ/MIDI/PDF exports -- with
    no automated route into either site (songleaf#5, songleaf#6): the user
    exports the file through the site as usual and drops it here. No network
    calls, no login; this only reads what is already on disk.

    Text files (``.txt``, ``.cho``, ``.chopro``, ``.crd``, ``.pro``) are parsed
    as chords-over-lyrics charts, the same format as the Kaggle corpus. Files
    with no lyrics to parse (Guitar Pro, MusicXML, MSCZ, MIDI, PDF) become a
    :class:`~songleaf.model.Song` with empty text and one
    :func:`~songleaf.model.score_link` annotation pointing at the file, so a
    renderer can still show it as an attached score snippet.

    A file is named ``"Artist - Title.ext"`` (the artist part is optional; a
    plain ``"Title.ext"`` works too).

    Args:
        root: Directory to index (searched recursively). Defaults to the
            ``imports`` data dir (``~/.local/share/songleaf/imports/``,
            moved by ``SONGLEAF_DATA_DIR``).
        name: Registry name (default ``"local_folder"``).

    >>> import tempfile, pathlib
    >>> root = tempfile.mkdtemp()
    >>> _ = (pathlib.Path(root) / "Nobody - Paper Boats.txt").write_text(
    ...     "C\\nla la la"
    ... )
    >>> local = LocalFolderSource(root)
    >>> hit = local.search("paper boats")[0]
    >>> (hit.title, hit.artist)
    ('Paper Boats', 'Nobody')
    >>> local.get(hit.id).of_kind("chord")[0].body["symbol"]
    'C'
    """

    def __init__(self, root: str | None = None, *, name: str = "local_folder"):
        self.name = name
        self.root = os.path.expanduser(root) if root else data_dir("imports")

    def _entries(self) -> list[dict]:
        entries = []
        for dirpath, _dirs, files in os.walk(self.root):
            for fname in files:
                stem, ext = os.path.splitext(fname)
                fmt = _SCORE_EXTS.get(ext.lower())
                is_text = ext.lower() in _TEXT_EXTS
                if fmt is None and not is_text:
                    continue
                title, artist = _title_and_artist(stem)
                path = os.path.join(dirpath, fname)
                entries.append(
                    {
                        "id": os.path.relpath(path, self.root),
                        "path": path,
                        "title": title,
                        "artist": artist,
                        "format": fmt or "text",
                        "is_text": is_text,
                    }
                )
        return entries

    def search(
        self,
        query: str = "",
        *,
        title: str = "",
        artist: str = "",
        lyrics: str = "",
        limit: int = 10,
    ) -> list[Hit]:
        """Substring-match the query/title/artist against each file's name."""
        needles = [n.lower() for n in (query, title, artist) if n]
        hits = []
        for entry in self._entries():
            haystack = f"{entry['title']} {entry['artist']}".lower()
            if not all(n in haystack for n in needles):
                continue
            if lyrics:
                if not entry["is_text"]:
                    continue
                with open(entry["path"], encoding="utf-8", errors="ignore") as file:
                    if lyrics.lower() not in file.read().lower():
                        continue
            hits.append(
                Hit(
                    source=self.name,
                    id=entry["id"],
                    title=entry["title"] or entry["id"],
                    artist=entry["artist"],
                    score=1.0,
                    meta={"format": entry["format"]},
                )
            )
        return hits[:limit]

    def get(self, song_id: str) -> Song:
        """The song at this relative path, parsed if it's a chart, else score-linked."""
        from songleaf.parse import parse_chords_over_lyrics

        path = os.path.join(self.root, song_id)
        if not os.path.isfile(path):
            raise KeyError(f"No file at {song_id!r} under {self.root}")
        stem, ext = os.path.splitext(os.path.basename(song_id))
        title, artist = _title_and_artist(stem)
        provenance = {
            "source": self.name,
            "id": song_id,
            "url": path,
            "license": "unknown",
        }
        if ext.lower() in _TEXT_EXTS:
            with open(path, encoding="utf-8", errors="ignore") as file:
                return parse_chords_over_lyrics(
                    file.read(),
                    meta={"title": title, "artist": artist},
                    provenance=provenance,
                )
        fmt = _SCORE_EXTS.get(ext.lower(), "")
        return Song(
            text="",
            annotations=[
                score_link(0, 0, source=self.name, id=song_id, url=path, format=fmt)
            ],
            meta={"title": title, "artist": artist},
            provenance=provenance,
        )


@lru_cache(maxsize=1)
def default_sources() -> tuple:
    """The sources used when none are given, built once per process."""
    return (KaggleChordsSource(),)


def search(
    query: str = "",
    *,
    title: str = "",
    artist: str = "",
    lyrics: str = "",
    limit: int = 10,
    sources: Sequence | None = None,
) -> list[Hit]:
    """Search every source and merge the hits, best first.

    >>> search("paper boats", sources=[])
    []
    """
    sources = default_sources() if sources is None else sources
    hits = [
        hit
        for source in sources
        for hit in source.search(
            query, title=title, artist=artist, lyrics=lyrics, limit=limit
        )
    ]
    return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def get_song(key: str, *, sources: Sequence | None = None) -> Song:
    """The song named by ``key`` (``"<source>:<id>"``), from the source of that name."""
    sources = default_sources() if sources is None else sources
    name, sep, song_id = key.partition(":")
    if not sep:
        raise KeyError(f"A song key looks like '<source>:<id>', got {key!r}")
    for source in sources:
        if source.name == name:
            return source.get(song_id)
    raise KeyError(f"No source named {name!r} (sources: {[s.name for s in sources]})")
