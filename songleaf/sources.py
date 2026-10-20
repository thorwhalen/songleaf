"""Where songs are found: sources, and a search that composes them.

A *source* is any object with a ``name``, a
``search(query, *, title, artist, lyrics, limit) -> list[Hit]`` method and a
``get(song_id) -> Song`` method that raises ``KeyError`` for an id it does not
have (:func:`get_song` reports that as :class:`SongNotFound`; a source that cannot
load its data at all raises :class:`SourceUnavailable`). :func:`search` and :func:`get_song` take
several through ``sources=``; the default is the Kaggle chords-and-lyrics
corpus, read through ``sung``.

A hit's :attr:`Hit.key` (``"<source>:<id>"``) names the song everywhere: it is
what :func:`get_song` resolves and what the store is keyed by.

:func:`search_tiers` is the one-field search: the songs whose title, artist or lyrics
match a query, each reported once, in the first of those that matches. A source may answer
it itself with a ``search_tiers(query, *, limit)`` method (the Kaggle sources do, in one
pass); any other source is asked three times through ``search``.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from functools import cached_property, lru_cache

from scoreseek.sources.local import (
    EXPORT_FORMATS,
    SCORE_FORMATS,
    scan_folder,
    title_and_artist,
)

from songleaf.model import Song, score_link
from songleaf.datasets import dataset_path
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


#: Where a copy of the corpus zip is found under the data root, before sung looks.
KAGGLE_CHORDS_ZIP = os.path.join("chords-and-lyrics", "chords-and-lyrics-dataset.zip")
_SUNG_ZIP_ENVVAR = "SUNG_CHORDS_AND_LYRICS_ZIP"


class SourceUnavailable(RuntimeError):
    """A source's data cannot be loaded here (a corpus that is not on this machine, say)."""


class SongNotFound(KeyError):
    """No song by that key, id or query. A ``KeyError``, so ``except KeyError`` still catches it."""

    def __str__(self) -> str:  # KeyError's own str() quotes the message
        return str(self.args[0]) if self.args else ""


def kaggle_chords_zip() -> str | None:
    """The corpus zip under the data root (``datasets/`` + :data:`KAGGLE_CHORDS_ZIP`), if there is one.

    ``$SUNG_CHORDS_AND_LYRICS_ZIP``, when set, wins: then this is ``None`` and
    sung reads the variable itself.
    """
    if os.environ.get(_SUNG_ZIP_ENVVAR):
        return None
    path = dataset_path(KAGGLE_CHORDS_ZIP)
    return path if os.path.isfile(path) else None


def _load_kaggle_corpus():
    try:
        from sung.chords_and_lyrics import get_lyrics_and_chords_dataset

        return get_lyrics_and_chords_dataset(
            zip_path=kaggle_chords_zip(), usecols=KaggleChordsSource.columns
        )
    except (ImportError, OSError) as error:  # no sung, no zip, no Kaggle access
        in_data_root = os.path.join(data_dir("datasets"), KAGGLE_CHORDS_ZIP)
        raise SourceUnavailable(
            "Could not load the Kaggle chords-and-lyrics corpus. Put a copy of "
            f"chords-and-lyrics-dataset.zip (from {KAGGLE_CHORDS_URL}) at "
            f"{in_data_root}, or point {_SUNG_ZIP_ENVVAR} at one. Without "
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
        self._load_lock = threading.Lock()
        self._loaded = None

    @property
    def _df(self):
        """The corpus, loaded once even when several threads ask for it first."""
        if self._loaded is None:
            with self._load_lock:
                if self._loaded is None:
                    self._loaded = self._loader().reset_index(drop=True)
        return self._loaded

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
    def _ids(self) -> list[str]:
        return [str(v) for v in self._df["Unnamed: 0"]]

    @cached_property
    def _langs(self) -> list[str]:
        return self._df["lang"].astype(str).tolist()

    @cached_property
    def _row_of_id(self) -> dict[str, int]:
        return {song_id: row for row, song_id in enumerate(self._ids)}

    def _text(self, row: int) -> str:
        """The chart (chords over lyrics) of one row."""
        text = self._df.iloc[row]["chords&lyrics"]
        return text if isinstance(text, str) else ""

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

    def search_tiers(self, query: str, *, limit: int = 10) -> dict[str, list[Hit]]:
        """The songs whose title, artist or lyrics match ``query``, by where they match.

        ``{"title": [...], "artist": [...], "lyrics": [...]}``, at most ``limit`` in each,
        best first. A song is in the first kind it matches, even when it ranks below the
        limit there, so a song is never shown as an artist match because more titles
        matched.

        Title and artist match word by word (:class:`~songleaf.match.WordIndex`): the query
        is inside the field (``"wonder"`` finds *Wonderwall*) or the field is inside the
        query (``"wonderwall oasis"`` finds the title *Wonderwall* and the artist *Oasis*),
        a word of four letters or more forgiving a typo; or every word of the query is in
        the title or in the artist (``"paper boats invented band"``). A song whose title
        holds a word of the query that its artist does not is a title match
        (``"wonderwall oasis"``: *Wonderwall (ver. 2)* by Oasis), otherwise an artist match. Within each kind, the songs whose
        title and artist together hold the most words of the query come first (so
        *Wonderwall* by Oasis leads), then the closest by fuzzy score (of the title, or of
        title and artist, whichever is closer; of the artist), then the most popular.
        Lyrics hold every word of the query, rank by popularity, and carry
        ``meta["snippet"]``: the line that matched, with its spans.
        """
        from songleaf.match import lyric_snippet, shared_words

        if not query.strip():
            return {"title": [], "artist": [], "lyrics": []}
        popularity = self._popularity
        title_rows, artist_rows = self._title_and_artist_rows(query)
        title_score = {
            row: max(score, label)
            for (row, score), label in zip(
                self._scores(query, self._titles, title_rows).items(),
                self._scores(query, self._labels, title_rows).values(),
            )
        }
        artist_score = self._scores(query, self._artists, artist_rows)
        labels = self._labels

        def best(scores):
            # the song whose title and artist hold the most query words, then the closest
            shared = {r: shared_words(query, labels[r]) for r in scores}
            ranked = sorted(
                scores, key=lambda r: (-shared[r], -scores[r], -popularity[r], r)
            )
            return [self._hit(r, scores[r]) for r in ranked[:limit]]

        lyric_rows = sorted(
            (
                r
                for r in self._containing(query)
                if r not in title_rows and r not in artist_rows
            ),
            key=lambda r: (-popularity[r], r),
        )[:limit]
        lyric_hits = []
        for row in lyric_rows:
            hit = self._hit(row, 100.0)
            text = _KAGGLE_SITE_NOISE.sub("", self._text(row))
            snippet = lyric_snippet(text, query)
            if snippet:
                hit.meta["snippet"] = snippet
            lyric_hits.append(hit)
        return {
            "title": best(title_score),
            "artist": best(artist_score),
            "lyrics": lyric_hits,
        }

    def _title_and_artist_rows(self, query: str) -> tuple[set[int], set[int]]:
        """The rows that are title matches, and those that are artist matches (none in both)."""
        from songleaf.match import MAX_QUERY_WORDS, query_words

        titles, artists = self._title_words, self._artist_words
        in_either, title_only = None, set()
        for word in query_words(query)[:MAX_QUERY_WORDS]:
            in_title, in_artist = titles.rows_with(word), artists.rows_with(word)
            either = in_title | in_artist
            in_either = either if in_either is None else in_either & either
            title_only |= in_title - in_artist
        # "wonderwall oasis", "paper boats invented band": every word is in the title or the
        # artist, and the title holds one the artist does not: a title match. "ed sheeran"
        # finds a song called Edge by its artist only.
        candidates = artists.matching(query) | (in_either or set())
        title_rows = titles.matching(query) | (candidates & title_only)
        return title_rows, candidates - title_rows

    @cached_property
    def _title_words(self):
        from songleaf.match import WordIndex

        return WordIndex(self._titles)

    @cached_property
    def _artist_words(self):
        from songleaf.match import WordIndex

        return WordIndex(self._artists)

    @staticmethod
    def _scores(query: str, texts: list[str], rows) -> dict[int, float]:
        """``{row: fuzzy score of query against texts[row]}`` for the given rows, in row order."""
        from rapidfuzz import fuzz, process, utils

        choices = {row: texts[row] for row in sorted(rows)}
        scored = process.extract(
            query,
            choices,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            limit=None,
        )
        found = {row: score for _, score, row in scored}
        return {row: found.get(row, 0.0) for row in choices}

    def _hit(self, row: int, score: float) -> Hit:
        return Hit(
            source=self.name,
            id=self._ids[row],
            title=self._titles[row],
            artist=self._artists[row],
            score=round(score / 100, 4),
            meta={"lang": self._langs[row], "popularity": self._popularity[row]},
        )

    def get(self, song_id: str) -> Song:
        """The song with this id, parsed into a :class:`Song`."""
        from songleaf.parse import parse_chords_over_lyrics

        try:
            row = self._row_of_id[str(song_id)]
        except KeyError:
            raise SongNotFound(f"No song with id {song_id!r} in {self.name}") from None
        return parse_chords_over_lyrics(
            _KAGGLE_SITE_NOISE.sub("", self._text(row)),
            meta={
                "title": self._titles[row],
                "artist": self._artists[row],
                "lang": self._langs[row],
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
#: The text extensions that hold ChordPro rather than chords-over-lyrics.
_CHORDPRO_EXTS = frozenset({".cho", ".chopro", ".crd", ".pro"})
#: Score/tab files with no lyrics to parse: attached as a bare score link. Labels
#: come from scoreseek's format tables (scoreseek#7).
_SCORE_FORMATS = {
    **EXPORT_FORMATS,
    **{ext: SCORE_FORMATS[ext] for ext in (".musicxml", ".mxl", ".mid", ".midi")},
}
#: Every file LocalFolderSource indexes: those plus the text charts it parses.
_FOLDER_FORMATS = {**_SCORE_FORMATS, **dict.fromkeys(_TEXT_EXTS, "text")}


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
        """The indexed files, through scoreseek's folder scan (scoreseek#7)."""
        return [
            {**entry, "is_text": entry["ext"] in _TEXT_EXTS}
            for entry in scan_folder(self.root, formats=_FOLDER_FORMATS)
        ]

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
        from songleaf.chordpro import parse_chordpro
        from songleaf.parse import parse_chords_over_lyrics

        path = os.path.realpath(os.path.join(self.root, song_id))
        inside = path.startswith(os.path.realpath(self.root) + os.sep)
        if not (inside and os.path.isfile(path)):  # an id never leaves the folder
            raise SongNotFound(f"No file at {song_id!r} under {self.root}")
        stem, ext = os.path.splitext(os.path.basename(song_id))
        title, artist = title_and_artist(stem)
        provenance = {
            "source": self.name,
            "id": song_id,
            "url": path,
            "license": "unknown",
        }
        if ext.lower() in _TEXT_EXTS:
            parse = (
                parse_chordpro
                if ext.lower() in _CHORDPRO_EXTS
                else parse_chords_over_lyrics
            )
            with open(path, encoding="utf-8", errors="ignore") as file:
                return parse(
                    file.read(),
                    meta={"title": title, "artist": artist},
                    provenance=provenance,
                )
        fmt = _SCORE_FORMATS.get(ext.lower(), "")
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
    """The sources used when none are given, built once per process.

    The Kaggle corpus is read from its search index when one has been built
    (``songleaf build-index``): the same songs and keys, in tens of MB rather
    than the GB the whole corpus takes in memory.
    """
    from songleaf.kaggle_index import KaggleChordsIndex, kaggle_index_path

    if os.path.isfile(kaggle_index_path()):
        return (KaggleChordsIndex(),)
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


#: The kinds of match :func:`search_tiers` reports, in order: a song is in the first that fits.
SONG_TIERS = ("title", "artist", "lyrics")


def search_tiers(
    query: str, *, limit: int = 10, sources: Sequence | None = None
) -> dict[str, list[Hit]]:
    """Every source's songs whose title, artist or lyrics match ``query``, by where they match.

    ``{"title": [...], "artist": [...], "lyrics": [...]}`` (:data:`SONG_TIERS`), at most
    ``limit`` in each; each song in the first kind it matches. Within a kind, each
    source's hits come in its own ranking, the sources in the order given.

    >>> search_tiers("paper boats", sources=[])
    {'title': [], 'artist': [], 'lyrics': []}
    """
    sources = default_sources() if sources is None else sources
    found = {kind: [] for kind in SONG_TIERS}
    for source in sources:
        if hasattr(source, "search_tiers"):
            tiers = source.search_tiers(query, limit=limit)
        else:
            tiers = _tiers_through_search(source, query, limit=limit)
        for kind in SONG_TIERS:
            found[kind].extend(tiers.get(kind, ()))
    seen: set[str] = set()
    for kind in SONG_TIERS:
        # each source ranks its own (a score alone is not its order); sources in the order given
        ranked = found[kind]
        found[kind] = [hit for hit in ranked if hit.key not in seen][:limit]
        seen.update(hit.key for hit in ranked)
    return found


def _tiers_through_search(source, query: str, *, limit: int) -> dict[str, list[Hit]]:
    """The tiers of a source with only ``search``: one call per field, plus the free query.

    The free query catches a source that reads no fields; each of its hits goes to the
    field it is closer to. A song past the limit of one kind may show up in a later one.
    """
    from rapidfuzz import fuzz, utils

    tiers = {
        "title": source.search(title=query, limit=limit),
        "artist": source.search(artist=query, limit=limit),
        "lyrics": source.search(lyrics=query, limit=limit),
    }
    known = {hit.key for hits in tiers.values() for hit in hits}

    def closeness(text):
        return fuzz.WRatio(query, text, processor=utils.default_process)

    for hit in source.search(query, limit=limit):
        if hit.key in known:
            continue
        kind = "title" if closeness(hit.title) >= closeness(hit.artist) else "artist"
        tiers[kind].append(hit)
    seen: set[str] = set()
    for kind in SONG_TIERS:
        tiers[kind] = [hit for hit in tiers[kind] if hit.key not in seen]
        seen.update(hit.key for hit in tiers[kind])
    return tiers


def get_song(key: str, *, sources: Sequence | None = None) -> Song:
    """The song named by ``key`` (``"<source>:<id>"``), from the source of that name."""
    sources = default_sources() if sources is None else sources
    name, sep, song_id = key.partition(":")
    if not sep:
        raise SongNotFound(f"A song key looks like '<source>:<id>', got {key!r}")
    for source in sources:
        if source.name == name:
            try:
                return source.get(song_id)
            except SongNotFound:
                raise
            except KeyError as error:  # the protocol: a source's get raises KeyError
                raise SongNotFound(f"No song with id {song_id!r} in {name}") from error
    raise SongNotFound(
        f"No source named {name!r} (sources: {[s.name for s in sources]})"
    )
