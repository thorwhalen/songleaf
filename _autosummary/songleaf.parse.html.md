# songleaf.parse

Parse chords-over-lyrics text into a [`Song`](songleaf.model.html.md#songleaf.model.Song).

This is the format most chord sites use, and the one in the Kaggle corpus: a
line of chord symbols, column-aligned over the lyric line it belongs to.

- Each chord is anchored on the syllable under it (a chord over a space moves
  to the start of the next syllable).
- A chord line with no lyric line under it (an intro, a solo) becomes an empty
  text line carrying its chords in order.
- Section headers (`Verse 1:`, `[Chorus]`, `Intro 2x: G D`) become
  section annotations; a header with no lines of its own is a *marker*
  (`{"marker": True}`), usually meaning “play that section again”.
- `Capo`, `Key`/`Tom` and `Tuning` lines become metadata.
- Tablature and decoration lines (`e|--3--|`, `=====`) are dropped.

```pycon
>>> song = parse_chords_over_lyrics("Verse 1:\nC       G\nHello there my friend")
>>> song.text
'Hello there my friend'
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(0, 'C'), (8, 'G')]
>>> song.of_kind("section")[0].body["label"]
'Verse 1'
```

### Functions

| [`is_chord_line`](#songleaf.parse.is_chord_line)(line)                            | True if every token is a chord or chord-line filler, and at least one is a chord.   |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`is_chord_token`](#songleaf.parse.is_chord_token)(token)                          | True if `token` reads as a chord symbol (`G`, `F#m7b5`, `E7(#9)`, `C/G`).           |
| [`parse_chords_over_lyrics`](#songleaf.parse.parse_chords_over_lyrics)(raw, \*[, meta, ...]) | Parse chords-over-lyrics text into a `Song`.                                        |

### songleaf.parse.is_chord_line(line)

True if every token is a chord or chord-line filler, and at least one is a chord.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_chord_line("G   D/F#   Em  (x2)")
True
>>> is_chord_line("Bad Dad")
False
```

### songleaf.parse.is_chord_token(token)

True if `token` reads as a chord symbol (`G`, `F#m7b5`, `E7(#9)`, `C/G`).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### songleaf.parse.parse_chords_over_lyrics(raw, , meta=None, provenance=None)

Parse chords-over-lyrics text into a `Song`.

* **Parameters:**
  * **raw** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The chord chart, chord lines column-aligned over lyric lines.
  * **meta** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Metadata to start from (`title`, `artist`, …); `capo`,
    `key` and `tuning` found in the text are added to it.
  * **provenance** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Where the text came from, stored as is.
* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)
