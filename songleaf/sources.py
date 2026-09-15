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

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from functools import cached_property, lru_cache

from songleaf.model import Song

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
