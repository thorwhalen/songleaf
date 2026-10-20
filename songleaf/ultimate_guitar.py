"""Ultimate Guitar: community chord charts the reader opened themselves (songleaf#28).

A community "Chords" or "Tabs" page on ultimate-guitar.com carries its chart in
the page's store (``.js-store``'s ``data-content``, or ``window.UGAPP.store``):
``page.data.tab_view.wiki_tab.content``, in ``[ch]``/``[tab]`` markup, with the
tab's ``song_name``, ``artist_name``, ``tonality_name`` and the view's ``capo``.

"Official" and "Pro" pages are refused: their content lives in UG's own player,
behind its subscription, and songleaf does not circumvent content protection
(terms of service, section 6.2). :func:`refusal` says why, in words a reader
understands; the bookmarklet (``data/web/bookmarklet.js``) applies the same rule
in the browser, and :func:`songleaf.importers.import_song` applies it to every
import that names a UG URL.

Three routes, in the order songleaf prefers them (the terms are in
``misc/docs/sources.md``):

1. paste the chart into the page (no contact with UG at all);
2. the bookmarklet, run in the reader's own browser on a page they opened: it
   reads the chart from that page and hands it to songleaf's import form, where
   the reader confirms it;
3. :class:`UltimateGuitarURLSource`, which fetches one URL per call. It is for a
   local command line only: off unless ``SONGLEAF_UG_URL=1`` is set, never in
   :func:`songleaf.sources.default_sources`, never behind an HTTP route, and it
   never searches.

All UG-derived songs carry ``provenance.license = "personal"``.

>>> refusal("https://tabs.ultimate-guitar.com/tab/invented/song-official-123")[:22]
'This is an official or'
>>> refusal("https://tabs.ultimate-guitar.com/tab/invented/song-chords-123")
''
>>> ug_key("https://tabs.ultimate-guitar.com/tab/invented/song-chords-123")
'ug:123'
"""

from __future__ import annotations

import html as _html
import json
import os
import re
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

#: The environment variable that turns on :class:`UltimateGuitarURLSource` (``"1"``).
URL_SOURCE_ENVVAR = "SONGLEAF_UG_URL"
#: Tab types whose page has no text chart songleaf may read (UG's own player, or video).
REFUSED_TYPES = frozenset({"official", "pro", "power", "video"})
#: What a request for a page says it is (UG scores bots; songleaf does not pretend to be a browser).
USER_AGENT = "songleaf (personal, one page per request)"
#: Seconds before a page fetch gives up.
FETCH_TIMEOUT_SECONDS = 20
#: Bytes read from a page at most (a chart page is a few hundred KB).
MAX_PAGE_BYTES = 5_000_000

_HOST_RE = re.compile(r"(^|\.)ultimate-guitar\.com$", re.IGNORECASE)
_OFFICIAL_PATH_RE = re.compile(r"-official-\d+|/pro/|/official/", re.IGNORECASE)
_ID_RE = re.compile(r"-(\d+)/?$")
_JS_STORE_RE = re.compile(
    r"""class=["'][^"']*\bjs-store\b[^"']*["'][^>]*?data-content=(["'])(.*?)\1""",
    re.DOTALL,
)
REFUSAL_OFFICIAL = (
    "This is an official or Pro tab: Ultimate Guitar serves it only in its own"
    " player, and songleaf does not copy it from there. Open a community"
    " 'Chords' version of the song instead."
)
REFUSAL_NO_CHART = (
    "This page has no text chord chart for songleaf to read. Open a community"
    " 'Chords' or 'Tabs' page."
)


class RefusedPage(ValueError):
    """A UG page songleaf will not read (official or Pro content, or no text chart)."""


def is_ultimate_guitar_url(url: str) -> bool:
    """Whether *url* is on ultimate-guitar.com (any subdomain)."""
    host = urlsplit(url.strip()).hostname or ""
    return bool(_HOST_RE.search(host))


def refusal(url: str = "", *, tab_type: str = "") -> str:
    """Why songleaf will not read this UG page, or ``""`` when it may.

    Only URLs on ultimate-guitar.com are judged; any other URL gets ``""``.
    """
    if tab_type.strip().lower() in REFUSED_TYPES:
        return REFUSAL_OFFICIAL
    if url and is_ultimate_guitar_url(url):
        if _OFFICIAL_PATH_RE.search(urlsplit(url.strip()).path):
            return REFUSAL_OFFICIAL
    return ""


def tab_id(url: str) -> str:
    """The tab's numeric id from a UG URL (``.../song-chords-123`` -> ``"123"``), or ``""``."""
    if not is_ultimate_guitar_url(url):
        return ""
    match = _ID_RE.search(urlsplit(url.strip()).path)
    return match.group(1) if match else ""


def ug_key(url: str) -> str:
    """The store key of a UG chart (``ug:<id>``), or ``""`` when *url* names none."""
    found = tab_id(url)
    return f"ug:{found}" if found else ""


def _page_data(store: Mapping) -> Mapping:
    # ``.js-store`` holds ``{"store": {"page": ...}}``; ``window.UGAPP.store`` is ``{"page": ...}``
    inner = store.get("store", store)
    page = inner.get("page") if isinstance(inner, Mapping) else None
    data = page.get("data") if isinstance(page, Mapping) else None
    return data if isinstance(data, Mapping) else {}


def chart_from_store(store: Mapping, *, url: str = "") -> dict:
    """The chart in a UG page's store: ``{"id", "text", "title", "artist", "key", "capo", "type", "url"}``.

    Raises :class:`RefusedPage` for an official or Pro page, or one with no text chart.
    """
    data = _page_data(store)
    tab = data.get("tab") or {}
    view = data.get("tab_view") or {}
    tab_type = str(tab.get("type") or "")
    url = url or str(tab.get("tab_url") or "")
    why = refusal(url, tab_type=tab_type)
    if why:
        raise RefusedPage(why)
    content = (view.get("wiki_tab") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RefusedPage(REFUSAL_NO_CHART)
    capo = (view.get("meta") or {}).get("capo") or ""
    return {
        "id": str(tab.get("id") or tab_id(url)),
        "text": content,
        "title": str(tab.get("song_name") or ""),
        "artist": str(tab.get("artist_name") or ""),
        "key": str(tab.get("tonality_name") or ""),
        "capo": str(capo) if capo else "",
        "type": tab_type,
        "url": url,
    }


def chart_from_html(page: str, *, url: str = "") -> dict:
    """The chart in a UG page's HTML (its ``.js-store`` element); see :func:`chart_from_store`."""
    found = _JS_STORE_RE.search(page)
    if not found:
        raise RefusedPage(REFUSAL_NO_CHART)
    try:
        store = json.loads(_html.unescape(found.group(2)))
    except ValueError as error:
        raise RefusedPage(REFUSAL_NO_CHART) from error
    return chart_from_store(store, url=url)


def fetch_page(url: str) -> str:
    """The HTML at *url*: one honest request, no retries, no browser disguise."""
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310 (https only, checked)
        return response.read(MAX_PAGE_BYTES).decode("utf-8", "replace")


def url_source_enabled() -> bool:
    """Whether this process may fetch UG pages (``SONGLEAF_UG_URL=1``)."""
    return os.environ.get(URL_SOURCE_ENVVAR, "") == "1"


class UltimateGuitarURLSource:
    """One UG chord page, by URL: local command line only, off by default.

    It never searches (:meth:`search` returns nothing) and is never among
    :func:`songleaf.sources.default_sources`. :meth:`get` fetches the one page
    it is given, refuses official and Pro pages, and returns the chart as a
    :class:`~songleaf.model.Song` keyed ``ug:<id>`` (see :func:`ug_key`).

    Args:
        fetch: ``url -> html``; the default makes one plain HTTPS request.
        enabled: Whether fetching is allowed; defaults to ``SONGLEAF_UG_URL=1``.
    """

    name = "ug"

    def __init__(
        self,
        *,
        fetch: Callable[[str], str] = fetch_page,
        enabled: bool | None = None,
    ):
        self._fetch = fetch
        self.enabled = url_source_enabled() if enabled is None else enabled

    def search(self, *args, **kwargs) -> list:
        """Nothing: this source reads the one page it is given and never searches UG."""
        return []

    def get(self, url: str):
        """The chart at *url* as a song (raises :class:`RefusedPage`, or ``ValueError`` when off)."""
        from songleaf.importers import import_song

        if not self.enabled:
            raise ValueError(
                "Fetching Ultimate Guitar pages is off. Paste the chart, or use the"
                " bookmarklet from the page you opened; on your own machine,"
                f" {URL_SOURCE_ENVVAR}=1 turns this on."
            )
        if urlsplit(url.strip()).scheme != "https" or not is_ultimate_guitar_url(url):
            raise ValueError(f"Not an https ultimate-guitar.com URL: {url!r}")
        why = refusal(url)
        if why:
            raise RefusedPage(why)
        chart = chart_from_html(self._fetch(url.strip()), url=url.strip())
        return import_song(
            chart["text"],
            title=chart["title"],
            artist=chart["artist"],
            url=chart["url"],
            key=chart["key"],
            capo=chart["capo"],
            format="ultimate-guitar",
        ).song
