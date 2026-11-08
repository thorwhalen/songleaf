# songleaf.online

Web expansion: find a song on chord and lyrics sites, extract it, keep it locally.

When the local search finds nothing by title or artist (or when asked), songleaf asks a
list of web *sites*. Each site is a strategy with one interface:

- `find(query, *, limit, fetch) -> list[Candidate]`: the site’s own search;
- `extract(candidate, *, fetch) -> Song`: one result, in songleaf’s own format.

[`expand()`](#songleaf.online.expand) ranks every site’s candidates against the query, extracts the best one
that passes [`is_usable()`](#songleaf.online.is_usable), and writes it to the song store (seam 2) as
`web:<site>:<id>`, with the page URL, site and licence in its provenance.
[`StoredWebSource`](#songleaf.online.StoredWebSource) (the `web` source among [`songleaf.sources.default_sources()`](songleaf.sources.html.md#songleaf.sources.default_sources))
searches those stored songs, so the next search for the same song is local and makes no
request.

The list of sites is configuration, not code. [`WEB_SITES`](#songleaf.online.WEB_SITES) is the registry,
[`DEFAULT_WEB_SITES`](#songleaf.online.DEFAULT_WEB_SITES) the default list, `$SONGLEAF_WEB_SITES` (comma-separated
names) or `sites=` override it, and a new site is a new entry: a
[`ChartPageSite`](#songleaf.online.ChartPageSite) (a search URL and a result-link pattern) for most chord sites, or
any object with `name`, `license`, `chords`, `find` and `extract`. Why each
site is or is not in the default list is in `misc/docs/sources.md`.

Every request goes through `fetch` (`url -> text`). The default is
[`polite_fetch()`](#songleaf.online.polite_fetch): `scraped.acquire` on its plain urllib transport, robots.txt
enforced, one request per second per host at most, and a User-Agent that says what it
is (no browser disguise). It needs the `online` extra (`pip install songleaf[online]`).

Lyrics and charts are copyrighted: what this module fetches is kept in the reader’s own
data directory, for personal use, and never belongs in a repository.

```pycon
>>> site_names("lrclib, chordie")
['lrclib', 'chordie']
>>> web_key("lrclib", "123")
'web:lrclib:123'
```

### Module Attributes

| [`Fetch`](#songleaf.online.Fetch)                | how this module reaches the network (inject it to test or to cache).                                                                                                                                                                    |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`WEB_MODE_ENVVAR`](#songleaf.online.WEB_MODE_ENVVAR)      | The environment variable choosing the web mode (one of [`WEB_MODES`](#songleaf.online.WEB_MODES)).                                                                                                                     |
| [`WEB_SITES_ENVVAR`](#songleaf.online.WEB_SITES_ENVVAR)     | The environment variable listing the sites to ask, comma-separated (see [`WEB_SITES`](#songleaf.online.WEB_SITES)).                                                                                                    |
| [`WEB_MODES`](#songleaf.online.WEB_MODES)            | every search; `off`: never.                                                                                                                                                                                                             |
| [`WEB_SOURCE`](#songleaf.online.WEB_SOURCE)           | their keys are `web:<site>:<id>`.                                                                                                                                                                                                       |
| [`USER_AGENT`](#songleaf.online.USER_AGENT)           | What every request says it is.                                                                                                                                                                                                          |
| [`MIN_INTERVAL_SECONDS`](#songleaf.online.MIN_INTERVAL_SECONDS) | Seconds between two requests to one host, at least (a site's Crawl-delay wins when longer).                                                                                                                                             |
| [`TIMEOUT_SECONDS`](#songleaf.online.TIMEOUT_SECONDS)      | Seconds before one request gives up.                                                                                                                                                                                                    |
| [`MAX_PAGE_CHARS`](#songleaf.online.MAX_PAGE_CHARS)       | Characters of a fetched page kept at most (a chart page is a few hundred KB).                                                                                                                                                           |
| [`MIN_CLOSENESS`](#songleaf.online.MIN_CLOSENESS)        | How close a candidate's title and artist must be to the query (0-1) to be considered.                                                                                                                                                   |
| [`CHORDS_BONUS`](#songleaf.online.CHORDS_BONUS)         | Added to a candidate's closeness when its site gives chords, not lyrics alone.                                                                                                                                                          |
| [`RESULTS_PER_SITE`](#songleaf.online.RESULTS_PER_SITE)     | all of them are ranked, so this is not the number kept.                                                                                                                                                                                 |
| [`MAX_EXTRACTIONS`](#songleaf.online.MAX_EXTRACTIONS)      | Candidates extracted at most before giving up on a query.                                                                                                                                                                               |
| [`MIN_LYRIC_LINES`](#songleaf.online.MIN_LYRIC_LINES)      | A usable song has at least this many lyric lines...                                                                                                                                                                                     |
| [`MIN_CHORDS`](#songleaf.online.MIN_CHORDS)           | ...and, from a site that gives chords, at least this many chords.                                                                                                                                                                       |
| [`URL_ID_CHARS`](#songleaf.online.URL_ID_CHARS)         | Characters of a candidate id hashed from its URL (sites with no id of their own).                                                                                                                                                       |
| [`MAX_LABEL_CHARS`](#songleaf.online.MAX_LABEL_CHARS)      | Characters of a title-and-artist label kept at most (a page's <title> can be anything).                                                                                                                                                 |
| [`CHORDIE`](#songleaf.online.CHORDIE)              | a chord search engine.                                                                                                                                                                                                                  |
| [`AZCHORDS`](#songleaf.online.AZCHORDS)             | chords over lyrics in `<pre id="content">`.                                                                                                                                                                                             |
| [`WEB_SITES`](#songleaf.online.WEB_SITES)            | Every site songleaf knows, by name.                                                                                                                                                                                                     |
| [`DEFAULT_WEB_SITES`](#songleaf.online.DEFAULT_WEB_SITES)    | those whose terms allow automated access.                                                                                                                                                                                               |
| [`SAME_WORD_RATIO`](#songleaf.online.SAME_WORD_RATIO)      | A word of the query and a word of a label are the same word from this fuzzy ratio (0-100), for words of [`songleaf.match.TYPO_MIN_LENGTH`](songleaf.match.html.md#songleaf.match.TYPO_MIN_LENGTH) letters or more. |
| [`KEPT_SOURCES`](#songleaf.online.KEPT_SOURCES)         | found on the web or imported by URL (`web:`), Ultimate Guitar charts (`ug:`), pasted songs (`paste:`).                                                                                                                                  |

### Functions

| [`canonical_url`](#songleaf.online.canonical_url)(url, site_url)                       | `url` as one spelling: https, the host as `site_url` spells it, no `#fragment`.                                                                                                     |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`chart_counts`](#songleaf.online.chart_counts)(song)                                 | `(lyric lines, chords)` of a song: what [`chart_text()`](#songleaf.online.chart_text) and [`is_usable()`](#songleaf.online.is_usable) weigh.       |
| [`chart_text`](#songleaf.online.chart_text)(page)                                   | The chord chart in a chord site's page: of its text blocks, the one that reads best.                                                                                                |
| [`closeness`](#songleaf.online.closeness)(query, candidate)                        | How well a candidate names the song the query asks for, 0-1, word by word.                                                                                                          |
| [`expand`](#songleaf.online.expand)(query, \*[, sites, fetch, store, ...])      | Find `query` on the web sites, keep the best usable result, and return it.                                                                                                          |
| [`find_online`](#songleaf.online.find_online)(query, \*[, sites, fetch, limit, ...]) | Every site's candidates for `query`, best first: `(score, candidate, site)`.                                                                                                        |
| [`import_url`](#songleaf.online.import_url)(url, \*[, sites, fetch, store, ...])    | Read the song page at `url` and keep it, like a song a search found.                                                                                                                |
| [`is_usable`](#songleaf.online.is_usable)(song, \*, chords[, ...])                 | Whether an extracted song is worth keeping: enough lyrics, and chords if promised.                                                                                                  |
| [`kept_keys`](#songleaf.online.kept_keys)(store, \*[, kinds])                      | The keys of `store` holding songs the reader brought in (see [`KEPT_SOURCES`](#songleaf.online.KEPT_SOURCES)).                                                        |
| [`label_of`](#songleaf.online.label_of)(site_name)                                | How a page names the site a kept song's provenance names (`""` for none).                                                                                                           |
| [`page_heading`](#songleaf.online.page_heading)(page)                                 | A song page's own label: its first `<h1>` (inner HTML), else [`page_title()`](#songleaf.online.page_title).                                                         |
| [`page_title`](#songleaf.online.page_title)(page)                                   | The song a page's `<title>` names (`title - artist`), without the site's words.                                                                                                     |
| [`polite_fetch`](#songleaf.online.polite_fetch)(url)                                  | The text at `url`: robots.txt obeyed, paced per host, honest User-Agent.                                                                                                            |
| [`site_for_url`](#songleaf.online.site_for_url)(url, \*[, sites])                     | The site that reads the page at `url`, and the page as a [`Candidate`](#songleaf.online.Candidate).                                                                |
| [`site_label`](#songleaf.online.site_label)(site)                                   | How a page names `site`: its `label` when it has one, else its name.                                                                                                                |
| [`site_names`](#songleaf.online.site_names)(spec)                                   | The site names in a comma-separated list (blanks dropped).                                                                                                                          |
| [`text_blocks`](#songleaf.online.text_blocks)(page)                                  | The preformatted text of a page (`<pre>` and `<textarea>` elements), unescaped.                                                                                                     |
| [`unavailable_reason`](#songleaf.online.unavailable_reason)()                               | Why this process cannot fetch with [`polite_fetch()`](#songleaf.online.polite_fetch) (no `online` extra), or `""`.                                                    |
| [`url_id`](#songleaf.online.url_id)(url)                                        | A short, stable id for a page with no id of its own (a hash of its URL).                                                                                                            |
| [`web_key`](#songleaf.online.web_key)(site, song_id)                             | The store key of a song found on `site`: `web:<site>:<id>`.                                                                                                                         |
| [`web_mode`](#songleaf.online.web_mode)([mode])                                   | The web mode: `mode`, else `$SONGLEAF_WEB_SEARCH`, else `DEFAULT_WEB_MODE`.                                                                                                         |
| [`web_sites`](#songleaf.online.web_sites)([sites, registry])                       | The sites to ask: `sites` (names, comma-separated or a list, or site objects), else `$SONGLEAF_WEB_SITES`, else [`DEFAULT_WEB_SITES`](#songleaf.online.DEFAULT_WEB_SITES). |

### Classes

| [`Candidate`](#songleaf.online.Candidate)(site, id, title[, artist, url, ...])   | One search result on a site: what `WebSite.extract()` turns into a song.                                          |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| [`ChartPageSite`](#songleaf.online.ChartPageSite)(name, search_url, result_link)     | A chord site with a search page and one chart per page: most of them.                                             |
| [`Found`](#songleaf.online.Found)(key, song, score, cached)                  | The song [`expand()`](#songleaf.online.expand) kept: its key, the song, and how it was found. |
| [`LrclibSite`](#songleaf.online.LrclibSite)([name, license, chords, ...])         | LRCLIB (lrclib.net): an open lyrics API, made for automated clients.                                              |
| [`StoredWebSource`](#songleaf.online.StoredWebSource)([store, kinds])                  | The songs the reader brought in and kept in the song store: searched locally.                                     |
| [`WebSite`](#songleaf.online.WebSite)(\*args, \*\*kwargs)                      | A site songleaf may search: its own search, and one result as a `Song`.                                           |

### Exceptions

| [`FetchFailed`](#songleaf.online.FetchFailed)       | A request did not return a page (an HTTP error, a block, a challenge).   |
|--------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`OnlineUnavailable`](#songleaf.online.OnlineUnavailable) | The web expansion cannot run here (the `online` extra is not installed). |

### songleaf.online.AZCHORDS *= ChartPageSite(name='azchords', search_url='', result_link='', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/[a-z0-9]/[a-z0-9]+-tabs-\\\\d+/[a-z0-9]+-tabs-\\\\d+\\\\.html$', home='https://www.azchords.com/', heading='title', label='AZChords')*

chords over lyrics in `<pre id="content">`. Its robots.txt
allows song pages; it publishes no terms beyond a footer limiting use to “private study,
scholarship, research”. Its search box is Google’s, so it only reads pages named by URL.

* **Type:**
  AZChords (azchords.com)

### songleaf.online.CHORDIE *= ChartPageSite(name='chordie', search_url='https://www.chordie.com/result.php?q={query}', result_link='<a[^>]+href="(?P<url>/(?:chord|song)\\\\.pere/[^"]+)"[^>]\*>(?P<label>.\*?)</a>', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/(?:chord|song)\\\\.pere/', home='', heading='h1', label='Chordie')*

a chord search engine. Its robots.txt invites every robot and it
publishes no terms, but many of its pages re-host other sites’ charts (some of which
forbid stored copies), so it is not in the default list (see misc/docs/sources.md).

* **Type:**
  Chordie (chordie.com)

### songleaf.online.CHORDS_BONUS *= 0.1*

Added to a candidate’s closeness when its site gives chords, not lyrics alone.

### *class* songleaf.online.Candidate(site, id, title, artist='', url='', payload=dict(), license='', store_key='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One search result on a site: what `WebSite.extract()` turns into a song.

`payload` carries what the search already returned (an API that answers with the
lyrics, say), so extracting it needs no second request. `license` overrides the
site’s for this one result (a site that searches other hosts knows each one’s).
`store_key` overrides the `web:<site>:<id>` key (Ultimate Guitar keeps `ug:<id>`).

### *class* songleaf.online.ChartPageSite(name, search_url, result_link, label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='', home='', heading='h1', label='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A chord site with a search page and one chart per page: most of them.

* **Parameters:**
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Registry name, and the `<site>` of its keys.
  * **search_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The search page, `{query}` standing for the URL-quoted query.
    `""` for a site with no search of its own: it then only reads pages
    named by URL ([`candidate_for()`](#songleaf.online.ChartPageSite.candidate_for)), on the host of `home`.
  * **result_link** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A regex over the search page with named groups `url` (the
    result’s href, relative or absolute) and `label` (the link’s inner HTML).
  * **label_separator** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Splits a label’s text into title and artist (title first).
  * **license** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The licence tag stored with every song from here.
  * **chords** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether its pages carry chords.
  * **page_path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A regex over the path of one of its song pages: a URL on its host
    whose path matches can be imported ([`candidate_for()`](#songleaf.online.ChartPageSite.candidate_for)). `""`: none.
  * **home** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The site’s root URL; its host is the site’s when `search_url` is `""`.
  * **heading** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where a page named by URL says its title and artist: `"h1"` (its first
    heading, else its `<title>`) or `"title"` (its `<title>`, for a site whose
    first heading is a breadcrumb, artist first).
  * **label** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – How a page names the site (`""`: its name).

#### candidate_for(url)

The song page at `url`, when it is one of this site’s (else `None`).

The URL is made canonical first ([`canonical_url()`](#songleaf.online.canonical_url)), as the search’s results
are, so a song found by a search and the same page imported by URL (with or
without `www.`, a `#fragment`, capitals in the host) are one song. Title and
artist come from the page itself (`extract()`).

* **Return type:**
  [`Candidate`](#songleaf.online.Candidate) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.online.DEFAULT_WEB_SITES *= ('lrclib',)*

those whose terms allow automated access.

* **Type:**
  The sites asked when none are configured

### songleaf.online.Fetch

how this module reaches the network (inject it to test or to cache).

* **Type:**
  `url -> text`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### *exception* songleaf.online.FetchFailed

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A request did not return a page (an HTTP error, a block, a challenge).

### *class* songleaf.online.Found(key, song, score, cached)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The song [`expand()`](#songleaf.online.expand) kept: its key, the song, and how it was found.

#### hit()

The [`Hit`](songleaf.sources.html.md#songleaf.sources.Hit) a search reports for it.

### songleaf.online.KEPT_SOURCES *= ('web', 'ug', 'paste')*

found on the web
or imported by URL (`web:`), Ultimate Guitar charts (`ug:`), pasted songs (`paste:`).

* **Type:**
  The kinds of stored song the reader brought in, and local search finds

### *class* songleaf.online.LrclibSite(name='lrclib', license='personal', chords=False, base_url='https://lrclib.net', label='LRCLIB')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

LRCLIB (lrclib.net): an open lyrics API, made for automated clients. Lyrics, no chords.

One search request answers with the lyrics, so extracting a result costs nothing more.
Synced lyrics, when there are any, become `time` annotations (see
[`songleaf.timing.with_lrc()`](songleaf.timing.html.md#songleaf.timing.with_lrc)).

### songleaf.online.MAX_EXTRACTIONS *= 3*

Candidates extracted at most before giving up on a query.

### songleaf.online.MAX_LABEL_CHARS *= 200*

Characters of a title-and-artist label kept at most (a page’s <title> can be anything).

### songleaf.online.MAX_PAGE_CHARS *= 3000000*

Characters of a fetched page kept at most (a chart page is a few hundred KB).

### songleaf.online.MIN_CHORDS *= 4*

…and, from a site that gives chords, at least this many chords.

### songleaf.online.MIN_CLOSENESS *= 0.6*

How close a candidate’s title and artist must be to the query (0-1) to be considered.

### songleaf.online.MIN_INTERVAL_SECONDS *= 1.0*

Seconds between two requests to one host, at least (a site’s Crawl-delay wins when longer).

### songleaf.online.MIN_LYRIC_LINES *= 4*

A usable song has at least this many lyric lines…

### *exception* songleaf.online.OnlineUnavailable

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The web expansion cannot run here (the `online` extra is not installed).

### songleaf.online.RESULTS_PER_SITE *= 20*

all of them are ranked, so this is not the number kept.

* **Type:**
  Results asked of each site

### songleaf.online.SAME_WORD_RATIO *= 85*

A word of the query and a word of a label are the same word from this fuzzy ratio (0-100),
for words of [`songleaf.match.TYPO_MIN_LENGTH`](songleaf.match.html.md#songleaf.match.TYPO_MIN_LENGTH) letters or more.

### *class* songleaf.online.StoredWebSource(store=None, , kinds=('web', 'ug', 'paste'))

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The songs the reader brought in and kept in the song store: searched locally.

A source like any other (`name` `"web"`, `search`, `search_tiers`, `get`):
it reads the store’s keys of the `kinds` the reader brought in (found on the web,
imported by URL, pasted), so a song kept by [`expand()`](#songleaf.online.expand), [`import_url()`](#songleaf.online.import_url) or a
paste is found again with no request. Each hit’s `source` is its key’s own prefix. Title and artist match word by word, as the corpus does
([`WordIndex`](songleaf.match.html.md#songleaf.match.WordIndex): the query inside the title and artist, or the
title and artist inside the query, typos forgiven); lyrics hold every word.

Each kept song is read once per process (title, artist, words): a search lists the
store’s keys and reads only the new ones. A file that cannot be read is logged and
skipped, never fatal to a search.

* **Parameters:**
  * **store** ([`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – The song store (default: [`songleaf.store.song_store()`](songleaf.store.html.md#songleaf.store.song_store), resolved on
    each use, since the data root may move).
  * **kinds** ([`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)) – The key prefixes searched (default [`KEPT_SOURCES`](#songleaf.online.KEPT_SOURCES)). Corpus songs
    cached in the store are not among them: their own source finds them.

#### get(song_id)

The kept song `web:<song_id>`.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

#### search(query='', , title='', artist='', lyrics='', limit=10)

The kept web songs matching every given constraint, the most query words first.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

#### search_tiers(query, , limit=10)

The kept web songs by where `query` matched (see [`songleaf.sources.search_tiers()`](songleaf.sources.html.md#songleaf.sources.search_tiers)).

One pass over the kept songs: a song whose title and artist hold the query (or
are held by it) is a title match when its title shares a word with the query,
else an artist match; otherwise a lyrics match when its lyrics hold every word.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.online.TIMEOUT_SECONDS *= 20.0*

Seconds before one request gives up.

### songleaf.online.URL_ID_CHARS *= 12*

Characters of a candidate id hashed from its URL (sites with no id of their own).

### songleaf.online.USER_AGENT *= 'songleaf (+https://github.com/thorwhalen/songleaf)'*

What every request says it is.

### songleaf.online.WEB_MODES *= ('fallback', 'always', 'off')*

every
search; `off`: never.

* **Type:**
  `fallback`
* **Type:**
  only when the local search has no title or artist match; `always`

### songleaf.online.WEB_MODE_ENVVAR *= 'SONGLEAF_WEB_SEARCH'*

The environment variable choosing the web mode (one of [`WEB_MODES`](#songleaf.online.WEB_MODES)).

### songleaf.online.WEB_SITES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [WebSite](#songleaf.online.WebSite)]* *= {'azchords': ChartPageSite(name='azchords', search_url='', result_link='', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/[a-z0-9]/[a-z0-9]+-tabs-\\\\d+/[a-z0-9]+-tabs-\\\\d+\\\\.html$', home='https://www.azchords.com/', heading='title', label='AZChords'), 'chordie': ChartPageSite(name='chordie', search_url='https://www.chordie.com/result.php?q={query}', result_link='<a[^>]+href="(?P<url>/(?:chord|song)\\\\.pere/[^"]+)"[^>]\*>(?P<label>.\*?)</a>', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/(?:chord|song)\\\\.pere/', home='', heading='h1', label='Chordie'), 'lrclib': LrclibSite(name='lrclib', license='personal', chords=False, base_url='https://lrclib.net', label='LRCLIB'), 'ug': <songleaf.ultimate_guitar.UltimateGuitarURLSource object>}*

Every site songleaf knows, by name. A new site is a new entry. `ug` never searches:
it only reads a page the reader names, and only when `SONGLEAF_UG_URL=1` (songleaf#28).

### songleaf.online.WEB_SITES_ENVVAR *= 'SONGLEAF_WEB_SITES'*

The environment variable listing the sites to ask, comma-separated (see [`WEB_SITES`](#songleaf.online.WEB_SITES)).

### songleaf.online.WEB_SOURCE *= 'web'*

their keys are `web:<site>:<id>`.

* **Type:**
  The source name of songs found on the web

### *class* songleaf.online.WebSite(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

A site songleaf may search: its own search, and one result as a `Song`.

### songleaf.online.canonical_url(url, site_url)

`url` as one spelling: https, the host as `site_url` spells it, no `#fragment`.

```pycon
>>> canonical_url("https://WWW.Chords.example/a.html#top", "https://chords.example/s")
'https://chords.example/a.html'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.chart_counts(song)

`(lyric lines, chords)` of a song: what [`chart_text()`](#songleaf.online.chart_text) and [`is_usable()`](#songleaf.online.is_usable) weigh.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

### songleaf.online.chart_text(page)

The chord chart in a chord site’s page: of its text blocks, the one that reads best.

Each `<pre>` / `<textarea>` is parsed as a song (the importers detect ChordPro,
Ultimate Guitar markup, OpenSong or chords over lyrics), and the block with the most
lyric lines and chords together wins; one with no lyrics never does. `""` when no
block holds a chart.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.closeness(query, candidate)

How well a candidate names the song the query asks for, 0-1, word by word.

The smaller of two shares: the query’s words found in the candidate’s title and
artist, and the title’s words found in the query. Both must be high: a candidate
whose title is one word of a long query (*Dream* for “silver morning dream river
song”) scores low, and so does a query that names only part of the title. A word
of four letters or more forgives a typo or an inflection (`rivers`/`river`).

```pycon
>>> c = Candidate("s", "1", "Birds of a Feather", "Billie Eilish")
>>> closeness("birds of a feather billie eilish", c), closeness("birds of a feather", c)
(1.0, 1.0)
>>> closeness("silver morning dream river song", Candidate("s", "2", "Dream", "Rivers"))
0.4
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.online.expand(query, , sites=None, fetch=None, store=None, max_extractions=3, \*\*find_kwargs)

Find `query` on the web sites, keep the best usable result, and return it.

Candidates are tried best first ([`find_online()`](#songleaf.online.find_online)); one already in `store` is
returned as it is, without a request. Otherwise it is extracted, judged
([`is_usable()`](#songleaf.online.is_usable)), given its provenance and stored under `web:<site>:<id>`.
At most `max_extractions` are extracted; `None` when none is usable.

* **Return type:**
  [`Found`](#songleaf.online.Found) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.online.find_online(query, , sites=None, fetch=None, limit=20, min_closeness=0.6, chords_bonus=0.1)

Every site’s candidates for `query`, best first: `(score, candidate, site)`.

Each site is asked for `limit` results, in its own order, and all of them are
ranked here: a site’s first result is often not the cleanest one. Equal scores go
to the title and artist with fewer words, then to the sites’ order.

The score is the [`closeness()`](#songleaf.online.closeness) of the candidate, plus `chords_bonus` for a
site that gives chords; candidates below `min_closeness` are dropped, ties keep
the sites’ order. A site that fails (offline, robots.txt, a changed page) is logged
and skipped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`Candidate`](#songleaf.online.Candidate), [`WebSite`](#songleaf.online.WebSite)]]

### songleaf.online.import_url(url, , sites=None, fetch=None, store=None, refresh=False)

Read the song page at `url` and keep it, like a song a search found.

The site is found by [`site_for_url()`](#songleaf.online.site_for_url); the song is stored under its key
(`web:<site>:<id>`, or `ug:<id>` for Ultimate Guitar) with its provenance, and
from then on found by local search ([`StoredWebSource`](#songleaf.online.StoredWebSource)). A page already kept
is not fetched again unless `refresh`. `fetch` defaults to the site’s own
(`site.fetch`) or [`polite_fetch()`](#songleaf.online.polite_fetch). Raises `ValueError` for a page with
neither lyrics nor chords (no [`is_usable()`](#songleaf.online.is_usable) bar: the reader chose this page).

* **Return type:**
  [`Found`](#songleaf.online.Found)

### songleaf.online.is_usable(song, , chords, min_lyric_lines=4, min_chords=4)

Whether an extracted song is worth keeping: enough lyrics, and chords if promised.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### songleaf.online.kept_keys(store, , kinds=('web', 'ug', 'paste'))

The keys of `store` holding songs the reader brought in (see [`KEPT_SOURCES`](#songleaf.online.KEPT_SOURCES)).

```pycon
>>> kept_keys({"web:lrclib:1": 0, "paste:ab": 0, "kaggle_chords:9": 0})
['web:lrclib:1', 'paste:ab']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.online.label_of(site_name)

How a page names the site a kept song’s provenance names (`""` for none).

A registry name, or the name a site writes in provenance (`site_name`: Ultimate
Guitar’s `ultimate-guitar`); an unknown name is shown as it is.

```pycon
>>> label_of("lrclib"), label_of("ultimate-guitar"), label_of("elsewhere"), label_of("")
('LRCLIB', 'Ultimate Guitar', 'elsewhere', '')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.page_heading(page)

A song page’s own label: its first `<h1>` (inner HTML), else [`page_title()`](#songleaf.online.page_title).

Chord sites title a song page as their search results label it (title, then
artist), so `ChartPageSite._title_and_artist()` splits either the same way.

```pycon
>>> page_heading("<title>x</title><h1>Paper Boats&nbsp;<a>Invented Band</a></h1>")
'Paper Boats&nbsp;<a>Invented Band</a>'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.page_title(page)

The song a page’s `<title>` names (`title - artist`), without the site’s words.

```pycon
>>> page_title("<title>Paper Boats - Invented Band chords | Some Site</title>")
'Paper Boats - Invented Band'
>>> page_title("<title>Paper Boats  Chords &ndash; Invented Band | Version #2</title>")
'Paper Boats - Invented Band'
>>> page_title("<title>Paper Boats Invented Band Chords and Lyrics for Guitar</title>")
'Paper Boats Invented Band'
>>> page_title("<title>Gentle Guitar Rain Chords - Invented Band | Version #1</title>")
'Gentle Guitar Rain - Invented Band'
```

The kind word that ends the song’s name is the first one followed only by \`\` - artist\`\`
or by the site’s own words: a “Guitar” inside the title does not cut it.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.polite_fetch(url)

The text at `url`: robots.txt obeyed, paced per host, honest User-Agent.

Raises [`OnlineUnavailable`](#songleaf.online.OnlineUnavailable) without the `online` extra, scraped’s
`RobotsDisallowed` when robots.txt forbids the URL, and [`FetchFailed`](#songleaf.online.FetchFailed) for a
response that is not a page.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.site_for_url(url, , sites=None)

The site that reads the page at `url`, and the page as a [`Candidate`](#songleaf.online.Candidate).

Every site with a `candidate_for` is asked, in order (default: all of
[`WEB_SITES`](#songleaf.online.WEB_SITES), whatever the search list says: naming a page is not a search).
No request is made. Raises `ValueError` when no site reads that URL, or when its
site refuses it (a URL that is not plain, an official Ultimate Guitar tab); whether
Ultimate Guitar fetching is on is checked when the page is read.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`WebSite`](#songleaf.online.WebSite), [`Candidate`](#songleaf.online.Candidate)]

### songleaf.online.site_label(site)

How a page names `site`: its `label` when it has one, else its name.

```pycon
>>> site_label(LrclibSite()), site_label(CHORDIE)
('LRCLIB', 'Chordie')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.site_names(spec)

The site names in a comma-separated list (blanks dropped).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.online.text_blocks(page)

The preformatted text of a page (`<pre>` and `<textarea>` elements), unescaped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.online.unavailable_reason()

Why this process cannot fetch with [`polite_fetch()`](#songleaf.online.polite_fetch) (no `online` extra), or `""`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.url_id(url)

A short, stable id for a page with no id of its own (a hash of its URL).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.web_key(site, song_id)

The store key of a song found on `site`: `web:<site>:<id>`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.web_mode(mode='')

The web mode: `mode`, else `$SONGLEAF_WEB_SEARCH`, else `DEFAULT_WEB_MODE`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.online.web_sites(sites=None, \*, registry={'azchords': ChartPageSite(name='azchords', search_url='', result_link='', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/[a-z0-9]/[a-z0-9]+-tabs-\\\\d+/[a-z0-9]+-tabs-\\\\d+\\\\.html$', home='https://www.azchords.com/', heading='title', label='AZChords'), 'chordie': ChartPageSite(name = 'chordie', search_url='https://www.chordie.com/result.php?q={query}', result_link='<a[^>]+href="(?P<url>/(?:chord|song)\\\\.pere/[^"]+)"[^>]\*>(?P<label>.\*?)</a>', label_separator='\\\\s\*\\\\xa0+\\\\s\*| - ', license='personal', chords=True, page_path='^/(?:chord|song)\\\\.pere/', home='', heading='h1', label='Chordie'), 'lrclib': LrclibSite(name = 'lrclib', license='personal', chords=False, base_url='https://lrclib.net', label='LRCLIB'), 'ug': <songleaf.ultimate_guitar.UltimateGuitarURLSource object>})

The sites to ask: `sites` (names, comma-separated or a list, or site objects),
else `$SONGLEAF_WEB_SITES`, else [`DEFAULT_WEB_SITES`](#songleaf.online.DEFAULT_WEB_SITES).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
