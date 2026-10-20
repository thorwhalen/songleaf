"""Play-along: a song's media links and line timings (songleaf#30).

- **Media** (:func:`with_media`): the song's recording on YouTube or Spotify, as ids
  in ``meta["media"]`` (``{"youtube": "dQw4w9WgXcQ"}``), checked against each
  service's id format so the page can embed a player without trusting free text.
- **Timings** (:func:`with_lrc`): an ``.lrc`` file (or LRCLIB's synced lyrics) gives
  a time per lyric line; :func:`align_lrc` matches its lines to the song's lines by
  word overlap (token F1, in order, skipping what does not match), and each matched
  line gets a ``"time"`` annotation: a point at the line's start,
  ``body={"ms": 61230, "source": "lrc"}``. **Only the times are kept, never the
  LRC's text**, so a song's lyrics stay the ones it was imported with.

The page then follows the recording: the line whose time has come scrolls into
view.

>>> from songleaf.model import Song
>>> song = Song("Paper boats on a stream\\ncarry the names of a dream")
>>> lrc = "[ar:Someone]\\n[00:12.50]Paper boats on the stream\\n[00:17.00]Carry the names of my dream"
>>> timed = with_lrc(song, lrc)
>>> [(a.start, a.body["ms"]) for a in timed.of_kind("time")]
[(0, 12500), (24, 17000)]
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import replace

from songleaf.model import Annotation, Song

#: ``[mm:ss]``, ``[mm:ss.xx]`` or ``[mm:ss:xx]`` (minutes may exceed 59).
_TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET_TAG = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]\s*$", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
MEDIA_IDS: dict[str, re.Pattern] = {
    "youtube": re.compile(r"[A-Za-z0-9_-]{11}"),
    "spotify": re.compile(r"[A-Za-z0-9]{22}"),  # a track id
}
DFLT_MIN_F1 = 0.5


def parse_lrc(text: str) -> list[tuple[int, str]]:
    """``(milliseconds, line text)`` per timed line of an LRC, sorted by time.

    A line with several time tags (a repeated chorus) appears once per tag; an
    ``[offset:+/-ms]`` tag shifts every time (positive: earlier, as the format says);
    metadata tags (``[ar:...]``) and untimed lines are skipped.
    """
    offset, timed = 0, []
    for raw in text.splitlines():
        line = raw.strip()
        m = _OFFSET_TAG.match(line)
        if m:
            offset = int(m.group(1))
            continue
        tags, pos = [], 0
        while (t := _TIME_TAG.match(line, pos)) is not None:
            minutes, seconds, frac = t.groups()
            ms = int(frac.ljust(3, "0")[:3]) if frac else 0
            tags.append((int(minutes) * 60 + int(seconds)) * 1000 + ms)
            pos = t.end()
        lyric = line[pos:].strip()
        timed += [(max(0, ms - offset), lyric) for ms in tags]
    return sorted(timed, key=lambda t: t[0])


def _tokens(text: str) -> Counter:
    return Counter(w.casefold() for w in _WORD.findall(text))


def token_f1(a: str, b: str) -> float:
    """Word-overlap F1 of two lines (case and punctuation ignored).

    >>> token_f1("Carry the names", "carry the NAMES of my dream")
    0.6667
    """
    ta, tb = _tokens(a), _tokens(b)
    common = sum((ta & tb).values())
    if not common:
        return 0.0
    precision, recall = common / sum(tb.values()), common / sum(ta.values())
    return round(2 * precision * recall / (precision + recall), 4)


def align_lrc(
    song: Song,
    lrc: list[tuple[int, str]],
    *,
    min_f1: float = DFLT_MIN_F1,
    lookahead: int = 4,
) -> list[tuple[int, int]]:
    """``(line start offset, ms)`` pairs: LRC lines matched in order to the song's lines.

    Each LRC line is matched to the best of the next ``lookahead`` unmatched song
    lines with lyrics, if its token F1 is at least ``min_f1``; an LRC line that
    matches none is skipped (an ad lib, a line the song does not have).
    """
    lines = [ln for ln in song.lines() if _tokens(ln.text)]
    pairs, cursor = [], 0
    for ms, text in lrc:
        if not _tokens(text):
            continue
        window = lines[cursor : cursor + lookahead]
        scored = [(token_f1(ln.text, text), k) for k, ln in enumerate(window)]
        best = max(scored, default=(0.0, 0), key=lambda s: (s[0], -s[1]))
        if best[0] >= min_f1:
            pairs.append((window[best[1]].start, ms))
            cursor += best[1] + 1
    return pairs


def with_lrc(song: Song, lrc_text: str, *, source: str = "lrc", **align_kwargs) -> Song:
    """``song`` with ``"time"`` annotations from an LRC (earlier ones replaced).

    Only the times are added; the LRC's text is used to align and then dropped.
    """
    pairs = align_lrc(song, parse_lrc(lrc_text), **align_kwargs)
    times = [
        Annotation("time", at, at, {"ms": ms, "source": source}) for at, ms in pairs
    ]
    kept = [a for a in song.annotations if a.kind != "time"]
    return replace(
        song, annotations=sorted(kept + times, key=lambda a: (a.start, a.end))
    )


def with_media(song: Song, **ids: str | None) -> Song:
    """``song`` with media ids set in ``meta["media"]`` (an empty id removes one).

    >>> from songleaf.model import Song
    >>> with_media(Song("la"), youtube="dQw4w9WgXcQ").meta["media"]
    {'youtube': 'dQw4w9WgXcQ'}
    """
    media = dict(song.meta.get("media") or {})
    for service, value in ids.items():
        if service not in MEDIA_IDS:
            raise ValueError(
                f"unknown media service {service!r}; known: {sorted(MEDIA_IDS)}"
            )
        if not value:
            media.pop(service, None)
        elif not MEDIA_IDS[service].fullmatch(value):
            raise ValueError(f"{value!r} is not a {service} id")
        else:
            media[service] = value
    meta = {k: v for k, v in song.meta.items() if k != "media"}
    return replace(song, meta={**meta, **({"media": media} if media else {})})


#: ``(url, params) -> JSON``: how :func:`fetch_lrclib` reaches the network (inject it).
GetJson = Callable[[str, Mapping[str, str]], object]
LRCLIB_URL = "https://lrclib.net/api/get"


def _http_get_json(url: str, params: Mapping[str, str]):
    import json
    import urllib.parse
    import urllib.request

    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "songleaf (https://github.com/thorwhalen/songleaf)"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.load(response)


def fetch_lrclib(
    title: str,
    artist: str,
    *,
    duration_s: int | None = None,
    get_json: GetJson | None = None,
) -> str | None:
    """LRCLIB's synced lyrics (LRC text) for a song, or None. Use it with
    :func:`with_lrc`, which keeps the times only."""
    params = {"track_name": title, "artist_name": artist}
    if duration_s:
        params["duration"] = str(duration_s)
    try:
        found = (get_json or _http_get_json)(LRCLIB_URL, params)
    except Exception:  # noqa: BLE001 - not found (404) or offline: no timings
        return None
    synced = found.get("syncedLyrics") if isinstance(found, Mapping) else None
    return synced or None
