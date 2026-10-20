# songleaf.snippets

Score snippets on the sheet (songleaf#12): which stretch of a song, and a small staff for it.

A snippet is a few bars of notation drawn above one line of the lyrics, for a
sense of the melody or the rhythm. Three parts, each replaceable:

- **Which stretch**: [`choose_segment()`](#songleaf.snippets.choose_segment) picks a line by rule (the first line
  of the chorus, else the most repeated line, else the first line), and
  [`mark_segment()`](#songleaf.snippets.mark_segment) records the choice, with the notation, as the song’s
  > `score` annotation ([`songleaf.model.score_link()`](songleaf.model.html.md#songleaf.model.score_link)). A recorded annotation
  > wins over the rule, so it is how a choice is overridden.
- **What to draw**: a *snippet provider*, `song -> ScoreSnippet | None`, is
  injected into [`songleaf.render.render_sheet()`](songleaf.render.html.md#songleaf.render.render_sheet) (`snippets=`) and never
  imported by it. [`abc_snippet()`](#songleaf.snippets.abc_snippet) draws the short ABC notation recorded on
  the annotation with reportlab lines only: one voice, treble staff, notes,
  rests, accidentals, bar lines and chord names (no clef is drawn). With the `score` extra,
  [`songleaf.engrave.engraved_snippet()`](songleaf.engrave.html.md#songleaf.engrave.engraved_snippet) engraves ABC, MusicXML or MEI
  > properly; [`default_provider()`](#songleaf.snippets.default_provider) picks it when installed.
- **Where it goes**: the `score` layout option makes the renderer place the
  snippet as a row above its line; the font fit counts its height, so the
  lyrics shrink to make room.

ABC subset read by [`parse_abc()`](#songleaf.snippets.parse_abc): notes `A-G a-g` with `,` / `'`
octave marks, `^` `_` `=` accidentals, lengths `2` `/2` `3/2` `/`
(the unit is an eighth note), rests `z`, bar lines `|` `||` `|]` `|:`
`:|`, and `"G"` chord names over the next note. A length that needs a tie
(`5`) is refused. Header lines (`K:G`), decorations (`!fermata!`) and
anything else (ties, slurs, spaces) are skipped.

```pycon
>>> [(n.pitch, n.length) for n in parse_abc("C2 D/2 z |").notes]
[(28, 0.25), (29, 0.0625), (None, 0.125)]
```

### Module Attributes

| [`UNIT_LENGTH`](#songleaf.snippets.UNIT_LENGTH)        | The length of an unmarked ABC note, as a fraction of a whole note.                              |
|---------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`MIN_LENGTH`](#songleaf.snippets.MIN_LENGTH)         | The shortest and longest note lengths read, in whole notes.                                     |
| [`MAX_LENGTH`](#songleaf.snippets.MAX_LENGTH)         | The shortest and longest note lengths read, in whole notes.                                     |
| [`MAX_NOTATION_CHARS`](#songleaf.snippets.MAX_NOTATION_CHARS) | a snippet is a few bars.                                                                        |
| [`NOTATION_FORMATS`](#songleaf.snippets.NOTATION_FORMATS)   | The notation formats a score annotation may hold inline (all but `abc` need the `score` extra). |
| [`INLINE_SOURCE`](#songleaf.snippets.INLINE_SOURCE)      | What a provider-less recorded snippet is noted as.                                              |
| [`SnippetProvider`](#songleaf.snippets.SnippetProvider)    | what the sheet draws for a song, or `None` for no snippet.                                      |

### Functions

| [`abc_snippet`](#songleaf.snippets.abc_snippet)(song)                                | The default provider: the ABC notation recorded on the song's `score` annotation, drawn.                                       |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| [`choose_segment`](#songleaf.snippets.choose_segment)(song)                             | The line a snippet goes with: the first line of the chorus, else the most repeated line, else the first.                       |
| [`default_provider`](#songleaf.snippets.default_provider)()                               | The provider a `score` sheet uses when none is injected.                                                                       |
| [`first_snippet`](#songleaf.snippets.first_snippet)(providers)                         | A provider asking each of *providers* in turn: the first snippet wins.                                                         |
| [`layout_tune`](#songleaf.snippets.layout_tune)(tune)                                | A [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet) drawing *tune* on one treble staff, with reportlab lines only. |
| [`mark_segment`](#songleaf.snippets.mark_segment)(song, notation, \*[, segment, ...]) | A copy of *song* whose one `score` annotation holds *notation* over *segment*.                                                 |
| [`parse_abc`](#songleaf.snippets.parse_abc)(notation)                              | The notes, rests and bars of a short ABC *notation* (see the module docstring).                                                |
| [`recorded_snippet`](#songleaf.snippets.recorded_snippet)(song, \*[, format])             | The song's first `score` annotation carrying *format* notation, if any.                                                        |
| [`segment_at_line`](#songleaf.snippets.segment_at_line)(song, line)                      | The 1-based lyric *line* (blank lines not counted) as a segment chosen by hand.                                                |

### Classes

| [`Bar`](#songleaf.snippets.Bar)([kind])                                | A bar line (`kind`: `|`, `||`, `|]`, `|:` or `:|`).                               |
|---------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`Note`](#songleaf.snippets.Note)(pitch, length[, accidental, chord])   | One note (`pitch` a diatonic number, C4 = 28) or rest (`pitch` None).             |
| [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet)(width, height, draw[, start]) | A drawable snippet, sized in staff spaces, placed above the line holding `start`. |
| [`Segment`](#songleaf.snippets.Segment)(start, end, rule)                  | A stretch of a song's text and the rule that chose it.                            |
| [`Tune`](#songleaf.snippets.Tune)(events)                               | A parsed snippet: notes, rests and bar lines in order.                            |

### *class* songleaf.snippets.Bar(kind='|')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A bar line (`kind`: `|`, `||`, `|]`, `|:` or `:|`).

### songleaf.snippets.INLINE_SOURCE *= 'inline'*

What a provider-less recorded snippet is noted as.

### songleaf.snippets.MAX_LENGTH *= Fraction(4, 1)*

The shortest and longest note lengths read, in whole notes.

### songleaf.snippets.MAX_NOTATION_CHARS *= 400*

a snippet is a few bars.

* **Type:**
  Notations longer than this are refused

### songleaf.snippets.MIN_LENGTH *= Fraction(1, 64)*

The shortest and longest note lengths read, in whole notes.

### songleaf.snippets.NOTATION_FORMATS *= ('abc', 'musicxml', 'mei')*

The notation formats a score annotation may hold inline (all but `abc` need the `score` extra).

### *class* songleaf.snippets.Note(pitch, length, accidental='', chord='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One note (`pitch` a diatonic number, C4 = 28) or rest (`pitch` None).

### *class* songleaf.snippets.ScoreSnippet(width, height, draw, start=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A drawable snippet, sized in staff spaces, placed above the line holding `start`.

`draw(canvas, left, bottom, space, *, color, font)` draws it with its
lower-left corner at `(left, bottom)`, `space` points per staff space;
it then takes `width * space` by `height * space` points.

### *class* songleaf.snippets.Segment(start, end, rule)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A stretch of a song’s text and the rule that chose it.

### songleaf.snippets.SnippetProvider

what the sheet draws for a song, or `None` for no snippet.

* **Type:**
  A snippet provider

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Song`](songleaf.model.html.md#songleaf.model.Song)], ScoreSnippet | None]

### *class* songleaf.snippets.Tune(events)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed snippet: notes, rests and bar lines in order.

### songleaf.snippets.UNIT_LENGTH *= Fraction(1, 8)*

The length of an unmarked ABC note, as a fraction of a whole note.

### songleaf.snippets.abc_snippet(song)

The default provider: the ABC notation recorded on the song’s `score` annotation, drawn.

`None` when the song has no such annotation, or its notation cannot be read.

* **Return type:**
  [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.snippets.choose_segment(song)

The line a snippet goes with: the first line of the chorus, else the most repeated line, else the first.

`None` for a song with no lyric line.

* **Return type:**
  [`Segment`](#songleaf.snippets.Segment) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.snippets.default_provider()

The provider a `score` sheet uses when none is injected.

The engraved one ([`songleaf.engrave.engraved_snippet()`](songleaf.engrave.html.md#songleaf.engrave.engraved_snippet)) when the
`score` extra is installed, falling back to [`abc_snippet()`](#songleaf.snippets.abc_snippet); else
[`abc_snippet()`](#songleaf.snippets.abc_snippet) alone.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Song`](songleaf.model.html.md#songleaf.model.Song)], [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### songleaf.snippets.first_snippet(providers)

A provider asking each of *providers* in turn: the first snippet wins.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`Song`](songleaf.model.html.md#songleaf.model.Song)], [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### songleaf.snippets.layout_tune(tune)

A [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet) drawing *tune* on one treble staff, with reportlab lines only.

* **Return type:**
  [`ScoreSnippet`](#songleaf.snippets.ScoreSnippet)

### songleaf.snippets.mark_segment(song, notation, , segment=None, format='abc')

A copy of *song* whose one `score` annotation holds *notation* over *segment*.

*segment* defaults to [`choose_segment()`](#songleaf.snippets.choose_segment)’s. Earlier `score`
annotations are replaced: the recorded one is what the sheet draws.

* **Return type:**
  [`Song`](songleaf.model.html.md#songleaf.model.Song)

### songleaf.snippets.parse_abc(notation)

The notes, rests and bars of a short ABC *notation* (see the module docstring).

Raises `ValueError` for an empty or over-long notation, or one with no note.

* **Return type:**
  [`Tune`](#songleaf.snippets.Tune)

### songleaf.snippets.recorded_snippet(song, , format='abc')

The song’s first `score` annotation carrying *format* notation, if any.

* **Return type:**
  [`Annotation`](songleaf.model.html.md#songleaf.model.Annotation) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.snippets.segment_at_line(song, line)

The 1-based lyric *line* (blank lines not counted) as a segment chosen by hand.

* **Return type:**
  [`Segment`](#songleaf.snippets.Segment)
