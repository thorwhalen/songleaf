# songleaf.engrave

Score snippets engraved by Verovio: the `score` extra (`pip install songleaf[score]`).

The default snippet provider ([`songleaf.snippets.abc_snippet()`](songleaf.snippets.html.md#songleaf.snippets.abc_snippet)) draws a
short ABC subset with reportlab lines. With this extra, [`engraved_snippet()`](#songleaf.engrave.engraved_snippet)
engraves the notation recorded on the song’s `score` annotation properly
(clef, key and time signatures, beams, ties, chord names) from ABC (a body, or a
whole tune with its header), MusicXML or MEI: Verovio renders it to SVG, and
`svglib` turns the SVG into a reportlab drawing placed on the sheet.

[`songleaf.snippets.default_provider()`](songleaf.snippets.html.md#songleaf.snippets.default_provider) prefers this provider when the extra
is installed. Nothing here touches the network: the notation is the text stored
on the song.

Both libraries are LGPL-3.0 and only imported when a snippet is drawn.

### Module Attributes

| [`ENGRAVE_FORMATS`](#songleaf.engrave.ENGRAVE_FORMATS)   | The notation formats Verovio reads here, as recorded in a score annotation's `format`.   |
|--------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`MAX_ENGRAVE_CHARS`](#songleaf.engrave.MAX_ENGRAVE_CHARS) | Notation longer than this is not engraved (a snippet is a few bars).                     |
| [`VEROVIO_UNIT`](#songleaf.engrave.VEROVIO_UNIT)      | Verovio's half staff space, in its units at scale 100 (its default).                     |
| [`ABC_HEADER`](#songleaf.engrave.ABC_HEADER)        | the same eighth-note unit as the subset.                                                 |

### Functions

| [`as_abc_tune`](#songleaf.engrave.as_abc_tune)(notation)              | *notation* as a whole ABC tune: a body with no `X:` header gets [`ABC_HEADER`](#songleaf.engrave.ABC_HEADER).       |
|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| [`available`](#songleaf.engrave.available)()                        | Whether the `score` extra (verovio, svglib) is installed.                                                                          |
| [`engrave_svg`](#songleaf.engrave.engrave_svg)(notation[, format])    | The SVG of *notation* (`format`: a key of [`ENGRAVE_FORMATS`](#songleaf.engrave.ENGRAVE_FORMATS)), cropped to the music. |
| [`engraved_snippet`](#songleaf.engrave.engraved_snippet)(song)             | The provider: the song's first `score` annotation with notation Verovio reads, engraved.                                           |
| [`snippet_from_svg`](#songleaf.engrave.snippet_from_svg)(svg, \*[, start]) | A `ScoreSnippet` drawing a Verovio *svg*, sized in its staff spaces.                                                               |

### songleaf.engrave.ABC_HEADER *= 'X:1\\nL:1/8\\nK:C\\n'*

the same eighth-note unit as the subset.

* **Type:**
  The header given to an ABC body with none

### songleaf.engrave.ENGRAVE_FORMATS *= {'abc': 'abc', 'mei': 'mei', 'musicxml': 'musicxml'}*

The notation formats Verovio reads here, as recorded in a score annotation’s `format`.

### songleaf.engrave.MAX_ENGRAVE_CHARS *= 200000*

Notation longer than this is not engraved (a snippet is a few bars).

### songleaf.engrave.VEROVIO_UNIT *= 9*

Verovio’s half staff space, in its units at scale 100 (its default).

### songleaf.engrave.as_abc_tune(notation)

*notation* as a whole ABC tune: a body with no `X:` header gets [`ABC_HEADER`](#songleaf.engrave.ABC_HEADER).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.engrave.available()

Whether the `score` extra (verovio, svglib) is installed.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### songleaf.engrave.engrave_svg(notation, format='abc')

The SVG of *notation* (`format`: a key of [`ENGRAVE_FORMATS`](#songleaf.engrave.ENGRAVE_FORMATS)), cropped to the music.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.engrave.engraved_snippet(song)

The provider: the song’s first `score` annotation with notation Verovio reads, engraved.

`None` when there is none, or when it cannot be engraved (the sheet is then drawn without it).

* **Return type:**
  [`ScoreSnippet`](songleaf.snippets.html.md#songleaf.snippets.ScoreSnippet) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.engrave.snippet_from_svg(svg, , start=0)

A `ScoreSnippet` drawing a Verovio *svg*, sized in its staff spaces.

* **Return type:**
  [`ScoreSnippet`](songleaf.snippets.html.md#songleaf.snippets.ScoreSnippet)
