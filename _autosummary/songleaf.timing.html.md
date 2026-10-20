# songleaf.timing

Play-along: a song’s media links and line timings (songleaf#30).

- **Media** ([`with_media()`](#songleaf.timing.with_media)): the song’s recording on YouTube or Spotify, as ids
  in `meta["media"]` (`{"youtube": "dQw4w9WgXcQ"}`), checked against each
  service’s id format so the page can embed a player without trusting free text.
- **Timings** ([`with_lrc()`](#songleaf.timing.with_lrc)): an `.lrc` file (or LRCLIB’s synced lyrics) gives
  a time per lyric line; [`align_lrc()`](#songleaf.timing.align_lrc) matches its lines to the song’s lines by
  word overlap (token F1, in order, skipping what does not match), and each matched
  line gets a `"time"` annotation: a point at the line’s start,
  `body={"ms": 61230, "source": "lrc"}`. \*\*Only the times are kept, never the
  LRC’s text\*\*, so a song’s lyrics stay the ones it was imported with.

The page then follows the recording: the line whose time has come scrolls into
view.

```pycon
>>> from songleaf.model import Song
>>> song = Song("Paper boats on a stream\ncarry the names of a dream")
>>> lrc = "[ar:Someone]\n[00:12.50]Paper boats on the stream\n[00:17.00]Carry the names of my dream"
>>> timed = with_lrc(song, lrc)
>>> [(a.start, a.body["ms"]) for a in timed.of_kind("time")]
[(0, 12500), (24, 17000)]
```

### Module Attributes

| [`GetJson`](#songleaf.timing.GetJson)   | how [`fetch_lrclib()`](#songleaf.timing.fetch_lrclib) reaches the network (inject it).   |
|------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|

### Functions

| [`align_lrc`](#songleaf.timing.align_lrc)(song, lrc, \*[, min_f1, lookahead])      | `(line start offset, ms)` pairs: LRC lines matched in order to the song's lines.   |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`fetch_lrclib`](#songleaf.timing.fetch_lrclib)(title, artist, \*[, duration_s, ...]) | LRCLIB's synced lyrics (LRC text) for a song, or None.                             |
| [`parse_lrc`](#songleaf.timing.parse_lrc)(text)                                    | `(milliseconds, line text)` per timed line of an LRC, sorted by time.              |
| [`token_f1`](#songleaf.timing.token_f1)(a, b)                                     | Word-overlap F1 of two lines (case and punctuation ignored).                       |
| [`with_lrc`](#songleaf.timing.with_lrc)(song, lrc_text, \*[, source])             | `song` with `"time"` annotations from an LRC (earlier ones replaced).              |
| [`with_media`](#songleaf.timing.with_media)(song, \*\*ids)                          | `song` with media ids set in `meta["media"]` (an empty id removes one).            |

### songleaf.timing.GetJson

how [`fetch_lrclib()`](#songleaf.timing.fetch_lrclib) reaches the network (inject it).

* **Type:**
  `(url, params) -> JSON`

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]], [`object`](https://docs.python.org/3/builtins/functions.html#object)]

### songleaf.timing.align_lrc(song, lrc, , min_f1=0.5, lookahead=4)

`(line start offset, ms)` pairs: LRC lines matched in order to the song’s lines.

Each LRC line is matched to the best of the next `lookahead` unmatched song
lines with lyrics, if its token F1 is at least `min_f1`; an LRC line that
matches none is skipped (an ad lib, a line the song does not have).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]]

### songleaf.timing.fetch_lrclib(title, artist, , duration_s=None, get_json=None)

LRCLIB’s synced lyrics (LRC text) for a song, or None. Use it with
[`with_lrc()`](#songleaf.timing.with_lrc), which keeps the times only.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.timing.parse_lrc(text)

`(milliseconds, line text)` per timed line of an LRC, sorted by time.

A line with several time tags (a repeated chorus) appears once per tag; an
`[offset:+/-ms]` tag shifts every time (positive: earlier, as the format says);
metadata tags (`[ar:...]`) and untimed lines are skipped.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### songleaf.timing.token_f1(a, b)

Word-overlap F1 of two lines (case and punctuation ignored).

```pycon
>>> token_f1("Carry the names", "carry the NAMES of my dream")
0.6667
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.timing.with_lrc(song, lrc_text, , source='lrc', \*\*align_kwargs)

`song` with `"time"` annotations from an LRC (earlier ones replaced).

Only the times are added; the LRC’s text is used to align and then dropped.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.timing.with_media(song, \*\*ids)

`song` with media ids set in `meta["media"]` (an empty id removes one).

```pycon
>>> from songleaf.model import Song
>>> with_media(Song("la"), youtube="dQw4w9WgXcQ").meta["media"]
{'youtube': 'dQw4w9WgXcQ'}
```

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)
