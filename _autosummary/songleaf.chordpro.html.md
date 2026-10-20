# songleaf.chordpro

Parse ChordPro text into a [`Song`](songleaf.model.html.md#songleaf.model.Song).

ChordPro puts chords inline, in square brackets, at the syllable they land on
(`Paper [G]boats [D]drift`), and describes the song with `{directive: value}`
lines.

- `[X]` becomes a `chord` annotation at that character offset of the
  bracket-free lyric line; a line of chords only becomes an empty text line
  carrying its chords in order, as in [`songleaf.parse`](songleaf.parse.html.md#module-songleaf.parse).
- `{title}`, `{artist}`, `{key}`, `{capo}`, `{tempo}` (and their short
  forms) become metadata.
- `{soc}`/`{eoc}` (and verse, bridge, tab-less variants) and `{c: label}`
  comments become `section` annotations; a section with no lines of its own is
  a *marker* (`{"marker": True}`), as in [`songleaf.parse`](songleaf.parse.html.md#module-songleaf.parse).
- `# comments` and unknown directives are dropped.

```pycon
>>> song = parse_chordpro("{title: Paper Boats}\n{soc}\nPaper [G]boats [D]drift\n{eoc}")
>>> song.text
'Paper boats drift'
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(6, 'G'), (12, 'D')]
>>> song.meta["title"], song.of_kind("section")[0].body["label"]
('Paper Boats', 'Chorus')
```

### Functions

| [`parse_chordpro`](#songleaf.chordpro.parse_chordpro)(raw, \*[, meta, provenance])   | Parse ChordPro text into a `Song`.   |
|------------------------------------------------------------------------------------------------|--------------------------------------|

### songleaf.chordpro.parse_chordpro(raw, , meta=None, provenance=None)

Parse ChordPro text into a `Song`.

* **Parameters:**
  * **raw** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The ChordPro text.
  * **meta** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Metadata to start from; directives in the text override it.
  * **provenance** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Where the text came from, stored as is.
* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)
