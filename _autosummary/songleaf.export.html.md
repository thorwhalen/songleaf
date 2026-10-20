# songleaf.export

Export a song as ChordPro or as plain text (chords over lyrics), transposition applied.

ChordPro is the fleet’s text interchange: Songbook Pro, OnSong and the ChordPro app read it.
[`to_chordpro()`](#songleaf.export.to_chordpro) writes what [`songleaf.chordpro.parse_chordpro()`](songleaf.chordpro.html.md#songleaf.chordpro.parse_chordpro) reads, so a song
survives the round trip (text, chords, sections, `title`/`artist`/`key`/`capo`/`tempo`).
A chord that sounds ahead of its syllable (`timing="before"`) has no ChordPro spelling; the
song carries it in the namespaced directive `{x_songleaf_before: ...}`, which other apps ignore.

[`to_text()`](#songleaf.export.to_text) is the monospaced form: each line of lyrics with its chords on the line above,
a `[Label]` line at each section. It is for reading and pasting; it does not carry timing.

```pycon
>>> from songleaf.model import Song, chord, section
>>> song = Song("Paper boats drift", [chord(6, "G"), chord(12, "D"), section(0, 17, "Chorus")],
...             meta={"title": "Paper Boats"})
>>> print(to_chordpro(song), end="")
{title: Paper Boats}
{start_of_chorus: Chorus}
Paper [G]boats [D]drift
{end_of_chorus}
>>> print(to_text(song), end="")
Paper Boats

[Chorus]
      G     D
Paper boats drift
```

### Module Attributes

| [`FORMATS`](#songleaf.export.FORMATS)   | name -> (function, file extension, media type).   |
|------------------------------------------------------------|---------------------------------------------------|

### Functions

| [`to_chordpro`](#songleaf.export.to_chordpro)(song, \*[, transpose])   | The song as ChordPro text, every chord moved by `transpose` semitones.           |
|---------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`to_text`](#songleaf.export.to_text)(song, \*[, transpose])       | The song as plain text: chords above their syllables, `[Label]` at each section. |

### songleaf.export.FORMATS *= {'chordpro': (<function to_chordpro>, 'cho', 'text/plain; charset=utf-8'), 'text': (<function to_text>, 'txt', 'text/plain; charset=utf-8')}*

name -> (function, file extension, media type).

* **Type:**
  Export formats

### songleaf.export.to_chordpro(song, , transpose=0)

The song as ChordPro text, every chord moved by `transpose` semitones.

Metadata become directives, sections `start_of_*`/`end_of_*` environments carrying
their label, chords go inline in brackets at the syllable they land on.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.export.to_text(song, , transpose=0)

The song as plain text: chords above their syllables, `[Label]` at each section.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
