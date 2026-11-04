"""Web expansion: find a song on chord and lyrics sites, extract it, keep it locally.

When the local search finds nothing by title or artist (or when asked), songleaf asks a
list of web *sites*. Each site is a strategy with one interface:

- ``find(query, *, limit, fetch) -> list[Candidate]``: the site's own search;
- ``extract(candidate, *, fetch) -> Song``: one result, in songleaf's own format.

:func:`expand` ranks every site's candidates against the query, extracts the best one
that passes :func:`is_usable`, and writes it to the song store (seam 2) as
``web:<site>:<id>``, with the page URL, site and licence in its provenance.
:class:`StoredWebSource` (the ``web`` source among :func:`songleaf.sources.default_sources`)
searches those stored songs, so the next search for the same song is local and makes no
request.

The list of sites is configuration, not code. :data:`WEB_SITES` is the registry,
:data:`DEFAULT_WEB_SITES` the default list, ``$SONGLEAF_WEB_SITES`` (comma-separated
names) or ``sites=`` override it, and a new site is a new entry: a
:class:`ChartPageSite` (a search URL and a result-link pattern) for most chord sites, or
any object with ``name``, ``license``, ``chords``, ``find`` and ``extract``. Why each
site is or is not in the default list is in ``misc/docs/sources.md``.

Every request goes through ``fetch`` (``url -> text``). The default is
:func:`polite_fetch`: :mod:`scraped.acquire` on its plain urllib transport, robots.txt
enforced, one request per second per host at most, and a User-Agent that says what it
is (no browser disguise). It needs the ``online`` extra (``pip install songleaf[online]``).

Lyrics and charts are copyrighted: what this module fetches is kept in the reader's own
data directory, for personal use, and never belongs in a repository.

>>> site_names("lrclib, chordie")
['lrclib', 'chordie']
>>> web_key("lrclib", "123")
'web:lrclib:123'
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Protocol, runtime_checkable
from urllib.parse import quote_plus, urljoin, urlsplit

from songleaf.model import Song

log = logging.getLogger(__name__)

#: ``url -> text``: how this module reaches the network (inject it to test or to cache).
Fetch = Callable[[str], str]

#: The environment variable choosing the web mode (one of :data:`WEB_MODES`).
WEB_MODE_ENVVAR = "SONGLEAF_WEB_SEARCH"
#: The environment variable listing the sites to ask, comma-separated (see :data:`WEB_SITES`).
WEB_SITES_ENVVAR = "SONGLEAF_WEB_SITES"
#: ``fallback``: only when the local search has no title or artist match; ``always``: every
#: search; ``off``: never.
WEB_MODES = ("fallback", "always", "off")
DEFAULT_WEB_MODE = "fallback"
#: The source name of songs found on the web: their keys are ``web:<site>:<id>``.
WEB_SOURCE = "web"
#: What every request says it is.
USER_AGENT = "songleaf (+https://github.com/thorwhalen/songleaf)"
#: Seconds between two requests to one host, at least (a site's Crawl-delay wins when longer).
MIN_INTERVAL_SECONDS = 1.0
#: Seconds before one request gives up.
TIMEOUT_SECONDS = 20.0
#: Characters of a fetched page kept at most (a chart page is a few hundred KB).
MAX_PAGE_CHARS = 3_000_000
#: How close a candidate's title and artist must be to the query (0-1) to be considered.
MIN_CLOSENESS = 0.6
#: Added to a candidate's closeness when its site gives chords, not lyrics alone.
CHORDS_BONUS = 0.1
#: Results asked of each site: all of them are ranked, so this is not the number kept.
RESULTS_PER_SITE = 20
#: Candidates extracted at most before giving up on a query.
MAX_EXTRACTIONS = 3
#: A usable song has at least this many lyric lines...
MIN_LYRIC_LINES = 4
#: ...and, from a site that gives chords, at least this many chords.
MIN_CHORDS = 4
#: Characters of a candidate id hashed from its URL (sites with no id of their own).
URL_ID_CHARS = 12


class OnlineUnavailable(RuntimeError):
    """The web expansion cannot run here (the ``online`` extra is not installed)."""


class FetchFailed(RuntimeError):
    """A request did not return a page (an HTTP error, a block, a challenge)."""


def web_key(site: str, song_id: str) -> str:
    """The store key of a song found on ``site``: ``web:<site>:<id>``."""
    return f"{WEB_SOURCE}:{site}:{song_id}"


@dataclass(frozen=True)
class Candidate:
    """One search result on a site: what :meth:`WebSite.extract` turns into a song.

    ``payload`` carries what the search already returned (an API that answers with the
    lyrics, say), so extracting it needs no second request. ``license`` overrides the
    site's for this one result (a site that searches other hosts knows each one's).
    """

    site: str
    id: str
    title: str
    artist: str = ""
    url: str = ""
    payload: Mapping = field(default_factory=dict, compare=False, repr=False)
    license: str = ""

    @property
    def key(self) -> str:
        return web_key(self.site, self.id)


@runtime_checkable
class WebSite(Protocol):
    """A site songleaf may search: its own search, and one result as a :class:`Song`."""

    name: str
    license: str
    chords: bool  # whether its songs carry chords (lyrics-only sites rank lower)

    def find(self, query: str, *, limit: int, fetch: Fetch) -> list[Candidate]: ...

    def extract(self, candidate: Candidate, *, fetch: Fetch) -> Song: ...


# --------------------------------------------------------------------------------------
# Sites


@dataclass(frozen=True)
class LrclibSite:
    """LRCLIB (lrclib.net): an open lyrics API, made for automated clients. Lyrics, no chords.

    One search request answers with the lyrics, so extracting a result costs nothing more.
    Synced lyrics, when there are any, become ``time`` annotations (see
    :func:`songleaf.timing.with_lrc`).
    """

    name: str = "lrclib"
    license: str = "personal"
    chords: bool = False
    base_url: str = "https://lrclib.net"

    def find(self, query: str, *, limit: int, fetch: Fetch) -> list[Candidate]:
        records = json.loads(fetch(f"{self.base_url}/api/search?q={quote_plus(query)}"))
        candidates = []
        for record in records if isinstance(records, list) else ():
            if not isinstance(record, Mapping) or record.get("id") in (None, ""):
                continue  # one odd record does not drop the others
            lyrics = record.get("plainLyrics")
            if record.get("instrumental") or not (
                isinstance(lyrics, str) and lyrics.strip()
            ):
                continue
            candidates.append(self._candidate(record))
        return candidates[:limit]

    def _candidate(self, record: Mapping) -> Candidate:
        return Candidate(
            site=self.name,
            id=str(record["id"]),
            title=str(record.get("trackName") or ""),
            artist=str(record.get("artistName") or ""),
            url=f"{self.base_url}/api/get/{record['id']}",
            payload=record,
        )

    def extract(self, candidate: Candidate, *, fetch: Fetch) -> Song:
        from songleaf.parse import parse_chords_over_lyrics
        from songleaf.timing import with_lrc

        record = candidate.payload or json.loads(fetch(candidate.url))
        meta = {"title": candidate.title, "artist": candidate.artist}
        if record.get("albumName"):
            meta["album"] = str(record["albumName"])
        song = parse_chords_over_lyrics(str(record.get("plainLyrics") or ""), meta=meta)
        synced = record.get("syncedLyrics")
        return with_lrc(song, synced, source=self.name) if synced else song


@dataclass(frozen=True)
class ChartPageSite:
    """A chord site with a search page and one chart per page: most of them.

    Args:
        name: Registry name, and the ``<site>`` of its keys.
        search_url: The search page, ``{query}`` standing for the URL-quoted query.
        result_link: A regex over the search page with named groups ``url`` (the
            result's href, relative or absolute) and ``label`` (the link's inner HTML).
        label_separator: Splits a label's text into title and artist (title first).
        license: The licence tag stored with every song from here.
        chords: Whether its pages carry chords.
    """

    name: str
    search_url: str
    result_link: str
    label_separator: str = r"\s*\xa0+\s*| - "
    license: str = "personal"
    chords: bool = True

    def find(self, query: str, *, limit: int, fetch: Fetch) -> list[Candidate]:
        page_url = self.search_url.format(query=quote_plus(query))
        page = fetch(page_url)
        found: dict[str, Candidate] = {}
        for match in re.finditer(self.result_link, page, re.DOTALL | re.IGNORECASE):
            url = urljoin(page_url, _html.unescape(match.group("url")))
            if url in found or not _same_site(url, page_url):
                continue
            title, artist = self._title_and_artist(match.group("label"))
            if title:
                found[url] = Candidate(self.name, url_id(url), title, artist, url)
            if len(found) >= limit:
                break
        return list(found.values())

    def _title_and_artist(self, label: str) -> tuple[str, str]:
        text = _html.unescape(re.sub(r"<[^>]+>", " ", label)).strip()
        title, _, artist = (
            part.strip() for part in _split_once(self.label_separator, text)
        )
        return title, artist

    def extract(self, candidate: Candidate, *, fetch: Fetch) -> Song:
        from songleaf.importers import import_song

        text = chart_text(fetch(candidate.url))
        if not text:
            raise ValueError(f"No chord chart found on {candidate.url}")
        return import_song(text, title=candidate.title, artist=candidate.artist).song


def _split_once(pattern: str, text: str) -> tuple[str, str, str]:
    parts = re.split(f"({pattern})", text, maxsplit=1)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else (text, "", "")


def _same_site(url: str, page_url: str) -> bool:
    """Whether ``url`` is an https page on the host of ``page_url`` (results never leave it)."""
    a, b = urlsplit(url), urlsplit(page_url)
    return a.scheme == "https" and a.hostname == b.hostname


def url_id(url: str) -> str:
    """A short, stable id for a page with no id of its own (a hash of its URL)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:URL_ID_CHARS]


#: Chordie (chordie.com): a chord search engine. Its robots.txt invites every robot and it
#: publishes no terms, but many of its pages re-host other sites' charts (some of which
#: forbid stored copies), so it is not in the default list (see misc/docs/sources.md).
CHORDIE = ChartPageSite(
    name="chordie",
    search_url="https://www.chordie.com/result.php?q={query}",
    result_link=r'<a[^>]+href="(?P<url>/(?:chord|song)\.pere/[^"]+)"[^>]*>(?P<label>.*?)</a>',
)

#: Every site songleaf knows, by name. A new site is a new entry.
WEB_SITES: dict[str, WebSite] = {"lrclib": LrclibSite(), "chordie": CHORDIE}
#: The sites asked when none are configured: those whose terms allow automated access.
DEFAULT_WEB_SITES = ("lrclib",)


def site_names(spec: str) -> list[str]:
    """The site names in a comma-separated list (blanks dropped)."""
    return [name.strip() for name in spec.split(",") if name.strip()]


def web_sites(
    sites: str | Sequence | None = None, *, registry: Mapping[str, WebSite] = WEB_SITES
) -> tuple:
    """The sites to ask: ``sites`` (names, comma-separated or a list, or site objects),
    else ``$SONGLEAF_WEB_SITES``, else :data:`DEFAULT_WEB_SITES`."""
    if not sites:
        sites = os.environ.get(WEB_SITES_ENVVAR, "") or DEFAULT_WEB_SITES
    if isinstance(sites, str):
        sites = site_names(sites)
    resolved = []
    for site in sites:
        if isinstance(site, str):
            if site not in registry:
                raise ValueError(
                    f"No web site named {site!r} (known: {', '.join(registry)})"
                )
            site = registry[site]
        resolved.append(site)
    return tuple(resolved)


def web_mode(mode: str = "") -> str:
    """The web mode: ``mode``, else ``$SONGLEAF_WEB_SEARCH``, else :data:`DEFAULT_WEB_MODE`."""
    mode = (
        (mode or os.environ.get(WEB_MODE_ENVVAR, "") or DEFAULT_WEB_MODE)
        .strip()
        .lower()
    )
    if mode not in WEB_MODES:
        raise ValueError(f"The web mode is one of {', '.join(WEB_MODES)}, not {mode!r}")
    return mode


# --------------------------------------------------------------------------------------
# Fetching


@lru_cache(maxsize=1)
def _polite_fetcher():
    try:
        from scraped.acquire import (
            HttpFetcher,
            Politeness,
            RobotsPolicy,
            UrllibTransport,
        )
        from scraped.acquire.fetchers.http import robots_reader
    except ImportError as error:
        raise OnlineUnavailable(
            "Searching the web needs the online extra: pip install 'songleaf[online]'"
            f" (it could not import scraped: {error})"
        ) from error
    transport = (
        UrllibTransport()
    )  # plain HTTP: songleaf does not pretend to be a browser
    return HttpFetcher(
        transport=transport,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        robots=RobotsPolicy(
            get_robots_txt=robots_reader(transport), user_agent=USER_AGENT
        ),
        politeness=Politeness(min_interval=MIN_INTERVAL_SECONDS),
    )


def polite_fetch(url: str) -> str:
    """The text at ``url``: robots.txt obeyed, paced per host, honest User-Agent.

    Raises :class:`OnlineUnavailable` without the ``online`` extra, scraped's
    ``RobotsDisallowed`` when robots.txt forbids the URL, and :class:`FetchFailed` for a
    response that is not a page.
    """
    if urlsplit(url).scheme != "https":
        raise FetchFailed(f"Only https URLs are fetched, not {url!r}")
    fetcher = _polite_fetcher()  # raises OnlineUnavailable without the extra
    from scraped.acquire import Request

    capture = fetcher(Request(url))
    if not capture.ok:
        raise FetchFailed(f"{url} answered {capture.response.status}")
    return capture.text()[:MAX_PAGE_CHARS]


# --------------------------------------------------------------------------------------
# Extraction


_BLOCK_RE = re.compile(
    r"<(pre|textarea)\b[^>]*>(.*?)</\1\s*>", re.DOTALL | re.IGNORECASE
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def text_blocks(page: str) -> list[str]:
    """The preformatted text of a page (``<pre>`` and ``<textarea>`` elements), unescaped."""
    blocks = []
    for match in _BLOCK_RE.finditer(page):
        text = _TAG_RE.sub("", _BR_RE.sub("\n", match.group(2)))
        text = _html.unescape(text).replace("\r\n", "\n").replace("\xa0", " ")
        if text.strip():
            blocks.append(text.strip("\n"))
    return blocks


def chart_counts(song: Song) -> tuple[int, int]:
    """``(lyric lines, chords)`` of a song: what :func:`chart_text` and :func:`is_usable` weigh."""
    lyric_lines = sum(
        1 for line in song.lines() if re.search(r"[^\W\d_]{2}", line.text)
    )
    return lyric_lines, len(song.of_kind("chord"))


def chart_text(page: str) -> str:
    """The chord chart in a chord site's page: of its text blocks, the one that reads best.

    Each ``<pre>`` / ``<textarea>`` is parsed as a song (the importers detect ChordPro,
    Ultimate Guitar markup, OpenSong or chords over lyrics), and the block with the most
    lyric lines and chords together wins; one with no lyrics never does. ``""`` when no
    block holds a chart.
    """
    from songleaf.importers import import_song

    best, best_score = "", 0
    for block in text_blocks(page):
        try:
            lines, chords = chart_counts(import_song(block).song)
        except Exception:  # noqa: BLE001 - one odd block (too long, unparsable) is skipped
            continue
        score = lines + chords if lines else 0
        if score > best_score:
            best, best_score = block, score
    return best


def is_usable(
    song: Song,
    *,
    chords: bool,
    min_lyric_lines: int = MIN_LYRIC_LINES,
    min_chords: int = MIN_CHORDS,
) -> bool:
    """Whether an extracted song is worth keeping: enough lyrics, and chords if promised."""
    lines, found = chart_counts(song)
    return lines >= min_lyric_lines and (found >= min_chords or not chords)


# --------------------------------------------------------------------------------------
# Search, pick, persist


#: A word of the query and a word of a label are the same word from this fuzzy ratio (0-100),
#: for words of :data:`songleaf.match.TYPO_MIN_LENGTH` letters or more.
SAME_WORD_RATIO = 85


def _same_word(a: str, b: str) -> bool:
    from rapidfuzz import fuzz

    from songleaf.match import TYPO_MIN_LENGTH

    if a == b:
        return True
    if min(len(a), len(b)) < TYPO_MIN_LENGTH:
        return False
    return a.startswith(b) or b.startswith(a) or fuzz.ratio(a, b) >= SAME_WORD_RATIO


def _share(words: list[str], others: list[str]) -> float:
    """The fraction of ``words`` that are (typo-tolerantly) among ``others``."""
    if not words:
        return 0.0
    return sum(any(_same_word(w, o) for o in others) for w in words) / len(words)


def closeness(query: str, candidate: Candidate) -> float:
    """How well a candidate names the song the query asks for, 0-1, word by word.

    The smaller of two shares: the query's words found in the candidate's title and
    artist, and the title's words found in the query. Both must be high: a candidate
    whose title is one word of a long query (*Dream* for "silver morning dream river
    song") scores low, and so does a query that names only part of the title. A word
    of four letters or more forgives a typo or an inflection (``rivers``/``river``).

    >>> c = Candidate("s", "1", "Birds of a Feather", "Billie Eilish")
    >>> closeness("birds of a feather billie eilish", c), closeness("birds of a feather", c)
    (1.0, 1.0)
    >>> closeness("silver morning dream river song", Candidate("s", "2", "Dream", "Rivers"))
    0.4
    """
    from songleaf.match import query_words

    asked = query_words(query)
    title = query_words(candidate.title)
    label = title + query_words(candidate.artist)
    return round(min(_share(asked, label), _share(title, asked)), 4)


def find_online(
    query: str,
    *,
    sites: str | Sequence | None = None,
    fetch: Fetch | None = None,
    limit: int = RESULTS_PER_SITE,
    min_closeness: float = MIN_CLOSENESS,
    chords_bonus: float = CHORDS_BONUS,
) -> list[tuple[float, Candidate, WebSite]]:
    """Every site's candidates for ``query``, best first: ``(score, candidate, site)``.

    Each site is asked for ``limit`` results, in its own order, and all of them are
    ranked here: a site's first result is often not the cleanest one. Equal scores go
    to the title and artist with fewer words, then to the sites' order.

    The score is the :func:`closeness` of the candidate, plus ``chords_bonus`` for a
    site that gives chords; candidates below ``min_closeness`` are dropped, ties keep
    the sites' order. A site that fails (offline, robots.txt, a changed page) is logged
    and skipped.
    """
    fetch = fetch or polite_fetch
    ranked = []
    for order, site in enumerate(web_sites(sites)):
        try:
            candidates = site.find(query, limit=limit, fetch=fetch)
        except OnlineUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - one site down must not stop the others
            log.warning("songleaf: searching %s failed: %s", site.name, error)
            continue
        for rank, candidate in enumerate(candidates):
            near = closeness(query, candidate)
            if near >= min_closeness:
                score = near + (chords_bonus if site.chords else 0.0)
                # equal scores: the plainest label ("X" by "A", not "A - X (Official Video)")
                plain = len(re.findall(r"\w+", f"{candidate.title} {candidate.artist}"))
                ranked.append((score, plain, order, rank, candidate, site))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2], r[3]))
    return [(round(r[0], 4), r[4], r[5]) for r in ranked]


def _with_provenance(song: Song, candidate: Candidate, site: WebSite) -> Song:
    provenance = {
        "source": WEB_SOURCE,
        "id": f"{candidate.site}:{candidate.id}",
        "site": site.name,
        "url": candidate.url,
        "license": candidate.license or site.license,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta = {**song.meta}
    for name, value in (("title", candidate.title), ("artist", candidate.artist)):
        if value and meta.get(name, "Pasted song") == "Pasted song":
            meta[name] = value
    return replace(song, meta=meta, provenance=provenance)


@dataclass(frozen=True)
class Found:
    """The song :func:`expand` kept: its key, the song, and how it was found."""

    key: str
    song: Song
    score: float
    cached: bool  # already stored: no page was fetched for it

    def hit(self):
        """The :class:`~songleaf.sources.Hit` a search reports for it."""
        from songleaf.sources import Hit

        provenance = self.song.provenance
        return Hit(
            source=WEB_SOURCE,
            id=self.key.partition(":")[2],
            title=self.song.title,
            artist=self.song.artist,
            score=min(self.score, 1.0),
            meta={"site": provenance.get("site", ""), "url": provenance.get("url", "")},
        )


def expand(
    query: str,
    *,
    sites: str | Sequence | None = None,
    fetch: Fetch | None = None,
    store: MutableMapping | None = None,
    max_extractions: int = MAX_EXTRACTIONS,
    **find_kwargs,
) -> Found | None:
    """Find ``query`` on the web sites, keep the best usable result, and return it.

    Candidates are tried best first (:func:`find_online`); one already in ``store`` is
    returned as it is, without a request. Otherwise it is extracted, judged
    (:func:`is_usable`), given its provenance and stored under ``web:<site>:<id>``.
    At most ``max_extractions`` are extracted; ``None`` when none is usable.
    """
    from songleaf.store import song_store

    if not query.strip():
        return None
    store = song_store() if store is None else store
    fetch = fetch or polite_fetch
    ranked = find_online(query, sites=sites, fetch=fetch, **find_kwargs)
    tried = 0
    for score, candidate, site in ranked:
        if candidate.key in store:
            return Found(candidate.key, store[candidate.key], score, cached=True)
        if tried >= max_extractions:
            break
        tried += 1
        try:
            song = site.extract(candidate, fetch=fetch)
        except Exception as error:  # noqa: BLE001 - a bad page: try the next candidate
            log.warning("songleaf: reading %s failed: %s", candidate.url, error)
            continue
        if not is_usable(song, chords=site.chords):
            log.info("songleaf: %s is not a usable song, skipped", candidate.url)
            continue
        song = _with_provenance(song, candidate, site)
        store[candidate.key] = song
        return Found(candidate.key, song, score, cached=False)
    return None


# --------------------------------------------------------------------------------------
# The local source over what was found


class StoredWebSource:
    """The songs found on the web and kept in the song store: searched locally.

    A source like any other (``name`` ``"web"``, ``search``, ``search_tiers``, ``get``):
    it reads the ``web:`` keys of the store, so a song kept by :func:`expand` is found
    again with no request. Title and artist match word by word, as the corpus does
    (:class:`~songleaf.match.WordIndex`: the query inside the title and artist, or the
    title and artist inside the query, typos forgiven); lyrics hold every word.

    Each kept song is read once per process (title, artist, words): a search lists the
    store's keys and reads only the new ones. A file that cannot be read is logged and
    skipped, never fatal to a search.

    Args:
        store: The song store (default: :func:`songleaf.store.song_store`, resolved on
            each use, since the data root may move).
    """

    name = WEB_SOURCE

    def __init__(self, store: MutableMapping | None = None):
        self._store = store
        self._index: dict = {}  # (store id, key) -> (title, artist, lyric words, site)

    @property
    def store(self) -> MutableMapping:
        if self._store is None:
            from songleaf.store import song_store

            return song_store()
        return self._store

    def _store_id(self) -> str:
        if self._store is None:
            from songleaf.store import data_dir

            return data_dir("songs")
        return f"given:{id(self._store)}"

    def _entries(self) -> list[tuple[str, str, str, frozenset, str]]:
        """``(key, title, artist, lyric words, site)`` of every kept web song."""
        from songleaf.match import query_words

        store, where, prefix = self.store, self._store_id(), f"{WEB_SOURCE}:"
        keys = [key for key in store if key.startswith(prefix)]
        entries = []
        for key in keys:
            entry = self._index.get((where, key))
            if entry is None:
                try:
                    song = store[key]
                except Exception as error:  # noqa: BLE001 - one bad file must not stop search
                    log.warning("songleaf: skipping unreadable %s: %s", key, error)
                    continue
                entry = (
                    song.title,
                    song.artist,
                    frozenset(query_words(song.text)),
                    song.provenance.get("site", ""),
                )
                self._index[(where, key)] = entry
            entries.append((key, *entry))
        live = {(where, key) for key in keys}
        for gone in [k for k in self._index if k[0] == where and k not in live]:
            del self._index[gone]
        return entries

    def _hit(self, key: str, title: str, artist: str, score: float, site: str = ""):
        from songleaf.sources import Hit

        return Hit(
            source=self.name,
            id=key.partition(":")[2],
            title=title,
            artist=artist,
            score=round(score, 4),
            meta={"site": site} if site else {},
        )

    def search(
        self,
        query: str = "",
        *,
        title: str = "",
        artist: str = "",
        lyrics: str = "",
        limit: int = 10,
    ) -> list:
        """The kept web songs matching every given constraint, the most query words first."""
        from songleaf.match import covers, query_words, shared_words

        if not (query or title or artist or lyrics):
            return []

        def holds(needle, text):
            return covers(needle, text) or covers(text, needle)

        hits = []
        for key, song_title, song_artist, words, site in self._entries():
            label = f"{song_title} {song_artist}"
            if query and not holds(query, label):
                continue
            if title and not holds(title, song_title):
                continue
            if artist and not holds(artist, song_artist):
                continue
            if lyrics and not set(query_words(lyrics)) <= words:
                continue
            asked = " ".join(filter(None, (query, title, artist))) or lyrics
            score = shared_words(asked, label) / max(len(query_words(asked)), 1)
            hits.append(
                self._hit(key, song_title, song_artist, min(score, 1.0) or 1.0, site)
            )
        hits.sort(key=lambda hit: (-hit.score, hit.id))
        return hits[:limit]

    def search_tiers(self, query: str, *, limit: int = 10) -> dict:
        """The kept web songs by where ``query`` matched (see :func:`songleaf.sources.search_tiers`).

        One pass over the kept songs: a song whose title and artist hold the query (or
        are held by it) is a title match when its title shares a word with the query,
        else an artist match; otherwise a lyrics match when its lyrics hold every word.
        """
        from songleaf.match import covers, query_words, shared_words

        tiers = {"title": [], "artist": [], "lyrics": []}
        asked = query_words(query)
        if not asked:
            return tiers
        for key, song_title, song_artist, words, site in self._entries():
            label = f"{song_title} {song_artist}"
            share = shared_words(query, label) / len(asked)
            if covers(query, label) or covers(label, query):
                kind = "title" if shared_words(query, song_title) else "artist"
                tiers[kind].append(
                    self._hit(key, song_title, song_artist, share or 1.0, site)
                )
            elif set(asked) <= words:
                tiers["lyrics"].append(
                    self._hit(key, song_title, song_artist, 1.0, site)
                )
        for kind in tiers:
            tiers[kind] = sorted(tiers[kind], key=lambda h: (-h.score, h.id))[:limit]
        return tiers

    def get(self, song_id: str) -> Song:
        """The kept song ``web:<song_id>``."""
        from songleaf.sources import SongNotFound

        try:
            return self.store[f"{WEB_SOURCE}:{song_id}"]
        except (KeyError, ValueError):
            raise SongNotFound(
                f"No song {song_id!r} found on the web and kept here"
            ) from None
