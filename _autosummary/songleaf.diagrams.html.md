# songleaf.diagrams

Chord diagrams for the sheet: piano keys or guitar shapes (songleaf#13).

The chords a song uses ([`song_chords()`](#songleaf.diagrams.song_chords), in order of first use) are drawn as a strip
of small diagrams. Both kinds come from the chord’s pitch classes alone
([`chord_tones()`](#songleaf.diagrams.chord_tones)), so no fingering table is needed, and none has to be licensed:

- **piano**: a two-octave keyboard with the chord’s notes marked, in close position
  from the bass;
- **guitar**: a shape in standard tuning found by search ([`guitar_shape()`](#songleaf.diagrams.guitar_shape)): the
  lowest sounding string plays the bass (the root, or the slash bass), every chord
  tone sounds, the fret span is at most four frets and four fingers (notes at the
  lowest fret share one barre finger, unless an open string lies under the barre),
  and fewer muted strings, lower positions, fewer fingers and no open string between
  fretted ones are preferred.

The layout reserves the strip’s height before it fits the font size, so the lyrics
shrink to make room ([`strip_height()`](#songleaf.diagrams.strip_height)); [`draw_strip()`](#songleaf.diagrams.draw_strip) draws it.

```pycon
>>> chord_tones("Cmaj7"), chord_tones("Am/G"), chord_tones("F#m7b5")
((0, 4, 7, 11), (7, 9, 0, 4), (6, 9, 0, 4))
>>> guitar_shape("C"), guitar_shape("E"), guitar_shape("G")
((None, 3, 2, 0, 1, 0), (0, 2, 2, 1, 0, 0), (3, 2, 0, 0, 0, 3))
```

### Module Attributes

| [`STANDARD_TUNING`](#songleaf.diagrams.STANDARD_TUNING)   | Standard guitar tuning, low to high, as pitch classes (E A D G B E).   |
|--------------------------------------------------------------------|------------------------------------------------------------------------|

### Functions

| [`chord_tones`](#songleaf.diagrams.chord_tones)(symbol)                              | The chord's pitch classes, bass first (the root, or the bass of a slash chord).                                           |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`draw_strip`](#songleaf.diagrams.draw_strip)(canvas, symbols, kind, \*, left, ...) | Draw the diagrams in rows, left to right, the strip's bottom at `bottom`.                                                 |
| [`guitar_shape`](#songleaf.diagrams.guitar_shape)(symbol, \*[, tuning, max_fret])     | Frets per string, low to high (`None` = not played), or None if none is found.                                            |
| [`song_chords`](#songleaf.diagrams.song_chords)(song)                                | The distinct chord symbols of `song` that [`chord_tones()`](#songleaf.diagrams.chord_tones) reads, in order. |
| [`strip_height`](#songleaf.diagrams.strip_height)(n, kind, size, width, \*[, style])  | The height a strip of `n` diagrams takes across `width` (0 for none).                                                     |

### Classes

| [`DiagramStyle`](#songleaf.diagrams.DiagramStyle)([piano_width, piano_height, ...])   | Sizes of a diagram, in units of the lyric font size, and its colours.   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### *class* songleaf.diagrams.DiagramStyle(piano_width=4.2, piano_height=1.5, guitar_width=1.9, guitar_height=2.2, label_scale=0.6, gap=0.7, line_color='#555555', mark_color='#222222', black_key_color='#444444')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Sizes of a diagram, in units of the lyric font size, and its colours.

### songleaf.diagrams.STANDARD_TUNING *= (4, 9, 2, 7, 11, 4)*

Standard guitar tuning, low to high, as pitch classes (E A D G B E).

### songleaf.diagrams.chord_tones(symbol)

The chord’s pitch classes, bass first (the root, or the bass of a slash chord).

Triads by quality (`m`, `dim`, `aug`/`+`, `sus2`, `sus4`, `5`), then
sevenths (`7`, `maj7`, `dim7`, `m7b5`), sixths and added ninths. `None`
for what [`songleaf.harmony.parse_chord()`](songleaf.harmony.html.md#songleaf.harmony.parse_chord) does not read as a chord.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.diagrams.draw_strip(canvas, symbols, kind, , left, bottom, width, size, font, style=DiagramStyle(piano_width=4.2, piano_height=1.5, guitar_width=1.9, guitar_height=2.2, label_scale=0.6, gap=0.7, line_color='#555555', mark_color='#222222', black_key_color='#444444'))

Draw the diagrams in rows, left to right, the strip’s bottom at `bottom`.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.diagrams.guitar_shape(symbol, , tuning=(4, 9, 2, 7, 11, 4), max_fret=12)

Frets per string, low to high (`None` = not played), or None if none is found.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.diagrams.song_chords(song)

The distinct chord symbols of `song` that [`chord_tones()`](#songleaf.diagrams.chord_tones) reads, in order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.diagrams.strip_height(n, kind, size, width, , style=DiagramStyle(piano_width=4.2, piano_height=1.5, guitar_width=1.9, guitar_height=2.2, label_scale=0.6, gap=0.7, line_color='#555555', mark_color='#222222', black_key_color='#444444'))

The height a strip of `n` diagrams takes across `width` (0 for none).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)
