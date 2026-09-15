# songleaf.model

The linked-artifact model: a song is lyrics text plus standoff annotations.

A [`Song`](#songleaf.model.Song) keeps its lyrics as one plain string and everything else as
[`Annotation`](#songleaf.model.Annotation) records anchored on character offsets into that string.
The text is never marked up, so any number of annotation layers can coexist
and be added later without touching the lyrics (the standoff design of
`lacing`, over characters instead of seconds).

Kinds used so far:

- `"section"`: spans the section’s lines, `body={"label": "Chorus"}`. A
  label-only section (a bare `[Chorus]` marker meaning “repeat the chorus”) is
  empty (`start == end`), sits on an empty line of its own, and has
  `"marker": True` in its body.
- `"chord"`: a point (`start == end`) on the first character of the
  syllable the chord lands on, `body={"symbol": "G/B", "timing": "at"}`.
  `timing` is `"at"` (the chord sounds with that syllable, the default) or
  `"before"` (it sounds ahead of it). Chords of a line with no lyrics (an
  intro, an instrumental bar) sit, in order, on an empty line of the text.
- `"score"`: a link to a score snippet for `[start, end)`,
  `body={"source": ..., "id": ..., "url": ..., "format": ...}`.

```pycon
>>> song = Song("Hello there", [chord(0, "C"), chord(6, "G")], meta={"title": "Hi"})
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(0, 'C'), (6, 'G')]
>>> Song.from_dict(song.to_dict()) == song
True
```

### Module Attributes

| [`CHORD_TIMINGS`](#songleaf.model.CHORD_TIMINGS)   | When a chord sounds, relative to the syllable it is anchored on.   |
|------------------------------------------------------------------|--------------------------------------------------------------------|

### Functions

| [`chord`](#songleaf.model.chord)(at, symbol, \*[, timing])                    | A chord landing on the syllable that starts at offset `at`.     |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`score_link`](#songleaf.model.score_link)(start, end, \*, source, id[, url, ...]) | A link from `[start, end)` to a score snippet held by a source. |
| [`section`](#songleaf.model.section)(start, end, label)                         | A section (verse, chorus, ...) spanning `[start, end)`.         |

### Classes

| [`Annotation`](#songleaf.model.Annotation)(kind, start, end[, body])        | One annotation over `Song.text[start:end]`; a point when `start == end`.   |
|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`Line`](#songleaf.model.Line)(start, end, text)                      | One line of a song's text: `text == song.text[start:end]`.                 |
| [`Song`](#songleaf.model.Song)(text[, annotations, meta, provenance]) | Lyrics text plus annotations, metadata and provenance.                     |

### *class* songleaf.model.Annotation(kind, start, end, body=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One annotation over `Song.text[start:end]`; a point when `start == end`.

#### to_dict()

The JSON-ready form.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.model.CHORD_TIMINGS *= ('at', 'before')*

When a chord sounds, relative to the syllable it is anchored on.

### *class* songleaf.model.Line(start, end, text)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One line of a song’s text: `text == song.text[start:end]`.

### *class* songleaf.model.Song(text, annotations=<factory>, meta=<factory>, provenance=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Lyrics text plus annotations, metadata and provenance.

* **Parameters:**
  * **text** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The lyrics, lines separated by `"\n"`.
  * **annotations** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Annotation`](#songleaf.model.Annotation)]) – Standoff annotations over `text` (kept sorted by start).
  * **meta** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Descriptive fields: `title`, `artist`, `capo`, `key`, …
  * **provenance** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Where the song came from: `source`, `id`, `url`, `license`.

#### *classmethod* from_dict(data)

The inverse of [`to_dict()`](#songleaf.model.Song.to_dict).

* **Return type:**
  [`Song`](#songleaf.model.Song)

#### lines()

The lines of the text, with their offsets.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`Line`](#songleaf.model.Line)]

#### of_kind(kind)

The annotations of one kind, in text order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Annotation`](#songleaf.model.Annotation)]

#### to_dict()

The JSON-ready form (what the store persists).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.model.chord(at, symbol, , timing='at')

A chord landing on the syllable that starts at offset `at`.

* **Return type:**
  [`Annotation`](#songleaf.model.Annotation)

### songleaf.model.score_link(start, end, , source, id, url='', format='')

A link from `[start, end)` to a score snippet held by a source.

* **Return type:**
  [`Annotation`](#songleaf.model.Annotation)

### songleaf.model.section(start, end, label)

A section (verse, chorus, …) spanning `[start, end)`.

* **Return type:**
  [`Annotation`](#songleaf.model.Annotation)
