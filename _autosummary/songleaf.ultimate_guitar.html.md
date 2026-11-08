# songleaf.ultimate_guitar

Ultimate Guitar: community chord charts the reader opened themselves (songleaf#28).

A community “Chords” or “Tabs” page on ultimate-guitar.com carries its chart in
the page’s store (`.js-store`’s `data-content`, or `window.UGAPP.store`):
`page.data.tab_view.wiki_tab.content`, in `[ch]`/`[tab]` markup, with the
tab’s `song_name`, `artist_name`, `tonality_name` and the view’s `capo`.

“Official” and “Pro” pages are refused: their content lives in UG’s own player,
behind its subscription, and songleaf does not circumvent content protection
(terms of service, section 6.2). [`refusal()`](#songleaf.ultimate_guitar.refusal) says why, in words a reader
understands; the bookmarklet (`data/web/bookmarklet.js`) applies the same rule
in the browser, and [`songleaf.importers.import_song()`](songleaf.importers.html.md#songleaf.importers.import_song) applies it to every
import that names a UG URL.

Three routes, in the order songleaf prefers them (the terms are in
`misc/docs/sources.md`):

1. paste the chart into the page (no contact with UG at all);
2. the bookmarklet, run in the reader’s own browser on a page they opened: it
   reads the chart from that page and hands it to songleaf’s import form, where
   the reader confirms it;
3. [`UltimateGuitarURLSource`](#songleaf.ultimate_guitar.UltimateGuitarURLSource), which fetches one URL per call. It is for a
   local command line only: off unless `SONGLEAF_UG_URL=1` is set, never in
   [`songleaf.sources.default_sources()`](songleaf.sources.html.md#songleaf.sources.default_sources), never behind an HTTP route, and it
   > never searches.

All UG-derived songs carry `provenance.license = "personal"`.

```pycon
>>> refusal("https://tabs.ultimate-guitar.com/tab/invented/song-official-123")[:22]
'This is an official or'
>>> refusal("https://tabs.ultimate-guitar.com/tab/invented/song-chords-123")
''
>>> ug_key("https://tabs.ultimate-guitar.com/tab/invented/song-chords-123")
'ug:123'
```

### Module Attributes

| [`SITE_NAME`](#songleaf.ultimate_guitar.SITE_NAME)             | The site's name in a song's provenance (`provenance.site`), by every route.                                              |
|------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`URL_SOURCE_ENVVAR`](#songleaf.ultimate_guitar.URL_SOURCE_ENVVAR)     | The environment variable that turns on [`UltimateGuitarURLSource`](#songleaf.ultimate_guitar.UltimateGuitarURLSource) (`"1"`). |
| [`REFUSED_TYPES`](#songleaf.ultimate_guitar.REFUSED_TYPES)         | Tab types whose page has no text chart songleaf may read (UG's own player, or video).                                    |
| [`USER_AGENT`](#songleaf.ultimate_guitar.USER_AGENT)            | What a request for a page says it is (UG scores bots; songleaf does not pretend to be a browser).                        |
| [`FETCH_TIMEOUT_SECONDS`](#songleaf.ultimate_guitar.FETCH_TIMEOUT_SECONDS) | Seconds before a page fetch gives up.                                                                                    |
| [`MAX_PAGE_BYTES`](#songleaf.ultimate_guitar.MAX_PAGE_BYTES)        | Bytes read from a page at most (a chart page is a few hundred KB).                                                       |

### Functions

| [`chart_from_html`](#songleaf.ultimate_guitar.chart_from_html)(page, \*[, url])   | The chart in a UG page's HTML (its `.js-store` element); see [`chart_from_store()`](#songleaf.ultimate_guitar.chart_from_store).   |
|-------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| [`chart_from_store`](#songleaf.ultimate_guitar.chart_from_store)(store, \*[, url]) | The chart in a UG page's store: `{"id", "text", "title", "artist", "key", "capo", "type", "url"}`.                                  |
| [`fetch_page`](#songleaf.ultimate_guitar.fetch_page)(url)                    | The HTML at *url*: one honest request, no retries, no browser disguise.                                                             |
| [`is_ultimate_guitar_url`](#songleaf.ultimate_guitar.is_ultimate_guitar_url)(url)        | Whether *url* is on ultimate-guitar.com (any subdomain).                                                                            |
| [`refusal`](#songleaf.ultimate_guitar.refusal)([url, tab_type])           | Why songleaf will not read this UG page, or `""` when it may.                                                                       |
| [`safe_page_url`](#songleaf.ultimate_guitar.safe_page_url)(url)                 | *url*, rebuilt from its parts, if it is a plain https URL on ultimate-guitar.com.                                                   |
| [`tab_id`](#songleaf.ultimate_guitar.tab_id)(url)                        | The tab's numeric id from a UG URL (`.../song-chords-123` -> `"123"`), or `""`.                                                     |
| [`ug_key`](#songleaf.ultimate_guitar.ug_key)(url)                        | The store key of a UG chart (`ug:<id>`), or `""` when *url* names none.                                                             |
| [`url_source_enabled`](#songleaf.ultimate_guitar.url_source_enabled)()               | Whether this process may fetch UG pages (`SONGLEAF_UG_URL=1`).                                                                      |

### Classes

| [`UltimateGuitarURLSource`](#songleaf.ultimate_guitar.UltimateGuitarURLSource)(\*[, fetch, enabled])   | One UG chord page, by URL: local command line only, off by default.   |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|

### Exceptions

| [`RefusedPage`](#songleaf.ultimate_guitar.RefusedPage)   | A UG page songleaf will not read (official or Pro content, or no text chart).   |
|----------------------------------------------------------------|---------------------------------------------------------------------------------|

### songleaf.ultimate_guitar.FETCH_TIMEOUT_SECONDS *= 20*

Seconds before a page fetch gives up.

### songleaf.ultimate_guitar.MAX_PAGE_BYTES *= 5000000*

Bytes read from a page at most (a chart page is a few hundred KB).

### songleaf.ultimate_guitar.REFUSED_TYPES *= frozenset({'official', 'power', 'pro', 'video'})*

Tab types whose page has no text chart songleaf may read (UG’s own player, or video).

### *exception* songleaf.ultimate_guitar.RefusedPage

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A UG page songleaf will not read (official or Pro content, or no text chart).

### songleaf.ultimate_guitar.SITE_NAME *= 'ultimate-guitar'*

The site’s name in a song’s provenance (`provenance.site`), by every route.

### songleaf.ultimate_guitar.URL_SOURCE_ENVVAR *= 'SONGLEAF_UG_URL'*

The environment variable that turns on [`UltimateGuitarURLSource`](#songleaf.ultimate_guitar.UltimateGuitarURLSource) (`"1"`).

### songleaf.ultimate_guitar.USER_AGENT *= 'songleaf (personal, one page per request)'*

What a request for a page says it is (UG scores bots; songleaf does not pretend to be a browser).

### *class* songleaf.ultimate_guitar.UltimateGuitarURLSource(\*, fetch=<function fetch_page>, enabled=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One UG chord page, by URL: local command line only, off by default.

It never searches ([`search()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.search) and [`find()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.find) return nothing) and is never
among [`songleaf.sources.default_sources()`](songleaf.sources.html.md#songleaf.sources.default_sources). [`get()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.get) fetches the one page
it is given, refuses official and Pro pages, and returns the chart as a
[`Song`](songleaf.model.html.md#songleaf.model.Song) keyed `ug:<id>` (see [`ug_key()`](#songleaf.ultimate_guitar.ug_key)).

It is also the `ug` entry of [`songleaf.online.WEB_SITES`](songleaf.online.html.md#songleaf.online.WEB_SITES), for
[`songleaf.online.import_url()`](songleaf.online.html.md#songleaf.online.import_url): [`candidate_for()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.candidate_for) claims a UG URL,
[`extract()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.extract) reads it. Its `fetch` is the one an import uses unless the
caller gives another (one plain request that stays on UG).

* **Parameters:**
  * **fetch** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – `url -> html`; the default makes one plain HTTPS request.
  * **enabled** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Whether fetching is allowed; defaults to `SONGLEAF_UG_URL=1`,
    read when asked (so a process can turn it on after import).

#### candidate_for(url)

The page at a UG *url*, to [`extract()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.extract) (`None` for another host).

Raises `ValueError` when the URL is not plain, and [`RefusedPage`](#songleaf.ultimate_guitar.RefusedPage) for
an official or Pro page. Whether fetching is on is checked by [`extract()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.extract),
so a page already kept is still found while it is off.

#### extract(candidate, , fetch=None)

The chart of a [`candidate_for()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.candidate_for) page as a song (`ValueError` when off).

#### find(query, , limit=0, fetch=None)

Nothing, as [`search()`](#songleaf.ultimate_guitar.UltimateGuitarURLSource.search): a web search never asks UG.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

#### get(url)

The chart at *url* as a song (raises [`RefusedPage`](#songleaf.ultimate_guitar.RefusedPage), or `ValueError` when off).

#### search(\*args, \*\*kwargs)

Nothing: this source reads the one page it is given and never searches UG.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### songleaf.ultimate_guitar.chart_from_html(page, , url='')

The chart in a UG page’s HTML (its `.js-store` element); see [`chart_from_store()`](#songleaf.ultimate_guitar.chart_from_store).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.ultimate_guitar.chart_from_store(store, , url='')

The chart in a UG page’s store: `{"id", "text", "title", "artist", "key", "capo", "type", "url"}`.

Raises [`RefusedPage`](#songleaf.ultimate_guitar.RefusedPage) for an official or Pro page, or one with no text chart.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.ultimate_guitar.fetch_page(url)

The HTML at *url*: one honest request, no retries, no browser disguise.

Only https ultimate-guitar.com URLs are fetched, and a redirect anywhere else is refused.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.ultimate_guitar.is_ultimate_guitar_url(url)

Whether *url* is on ultimate-guitar.com (any subdomain).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### songleaf.ultimate_guitar.refusal(url='', , tab_type='')

Why songleaf will not read this UG page, or `""` when it may.

Only URLs on ultimate-guitar.com are judged; any other URL gets `""`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.ultimate_guitar.safe_page_url(url)

*url*, rebuilt from its parts, if it is a plain https URL on ultimate-guitar.com.

Raises `ValueError` otherwise: another scheme or host, user info, backslashes,
whitespace or control characters (where URL parsers disagree).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.ultimate_guitar.tab_id(url)

The tab’s numeric id from a UG URL (`.../song-chords-123` -> `"123"`), or `""`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.ultimate_guitar.ug_key(url)

The store key of a UG chart (`ug:<id>`), or `""` when *url* names none.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.ultimate_guitar.url_source_enabled()

Whether this process may fetch UG pages (`SONGLEAF_UG_URL=1`).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
