# songleaf.render

Render a song onto one dense page, with the lyrics as large as will fit.

A [`SheetLayout`](#songleaf.render.SheetLayout) is one way of laying a song out: where the chords go
(`chords`), which lines share a row (`packing`), how many `columns`, and
whether sections, repeated lines and chord functions are `shading`-ed.
[`render_sheet()`](#songleaf.render.render_sheet) draws any layout, and [`render_dense_a4()`](#songleaf.render.render_dense_a4) is the v1
layout. A layout can be named by a spec that joins the options of
[`LAYOUT_OPTIONS`](#songleaf.render.LAYOUT_OPTIONS) with `+` ([`layout_named()`](#songleaf.render.layout_named)), and
[`make_renderer()`](#songleaf.render.make_renderer) turns a spec into the `(song, output) -> dict` function
that the `renderer=` seam of [`songleaf.tools.sheet()`](songleaf.tools.html.md#songleaf.tools.sheet) takes.

Every layout finds the largest lyric font size at which the whole song fits on
one page ([`fit_font_size()`](#songleaf.render.fit_font_size)), then draws it:

- consecutive lines of a paragraph share a row, separated by a light `/`: as
  many as fit (`packing="greedy"`), or breaking where the lyrics break
  (`"structured"`: between couplets and quatrains, not inside a rhyming pair
  or a repeat; see [`songleaf.packing`](songleaf.packing.html.md#module-songleaf.packing)). A blank line or a new section
  starts a new row, and a line too long for its column wraps at a space (inside
  a word only when a single word is wider than the column);
- `chords="over"`: chords ride on their lyric row, smaller and in a lighter
  colour, overlapping the letters instead of taking a line of their own. A chord
  starts over the syllable it lands on, and a `timing="before"` chord ends
  there. `DenseStyle.chord_rise` sets how deep they overlap: the tops of the
  letters by default, the words themselves with the `overlap` option;
- `chords="inline"`: chords sit in the lyric line itself, in a lighter colour,
  right before the syllable they land on. A chord that sounds before its
  syllable is preceded by a small marker (`DenseStyle.before_marker`);
- `columns=2`: the rows flow down two columns, under a full-width heading;
- `shading`: chorus-like sections get a light warm band and pre-chorus or
  bridge sections a light cool one, lines sung earlier in the song are set in
  dark grey, and chords are coloured by their function in the key estimated
  from the chords ([`songleaf.harmony`](songleaf.harmony.html.md#module-songleaf.harmony)): the tonic darker, the key’s other
  chords in the usual blue, chords outside the key in a warm accent;
- section labels are small grey prefixes (`V1`, `Ch`) on a section’s first row;
- only a song that cannot fit at `min_font_size` spills onto more pages.

Text is set in DejaVu Sans, a TrueType font bundled in `songleaf/data/fonts`
(Bitstream Vera licence, which allows embedding and redistribution; the licence
text is beside the files) and embedded in each PDF. It covers Latin Extended
(Turkish ş ğ ı), Greek, Cyrillic and more, where reportlab’s built-in Helvetica
stops at its single-byte cp1252 encoding (songleaf#9). If a bundled file cannot
be loaded, the matching Helvetica is used instead, with a warning. Emoji are
not covered by either.

```pycon
>>> short_label("Verse 1"), short_label("Pre-Chorus"), short_label("Coda")
('V1', 'Pre', 'Coda')
>>> layout = layout_named("inline+two-column")
>>> layout.chords, layout.columns, layout.packing
('inline', 2, 'greedy')
```

### Module Attributes

| [`DFLT_MARGIN`](#songleaf.render.DFLT_MARGIN)      | Page margin in points (5 mm), about the least a printer leaves blank anyway.                                                                                                              |
|-------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`FONTS_DIR`](#songleaf.render.FONTS_DIR)        | Where the bundled TrueType fonts live (with their licence).                                                                                                                               |
| [`BUNDLED_FONTS`](#songleaf.render.BUNDLED_FONTS)    | name -> (file in [`FONTS_DIR`](#songleaf.render.FONTS_DIR), standard font used when that file cannot be loaded).                                                         |
| [`CHORD_PLACEMENTS`](#songleaf.render.CHORD_PLACEMENTS) | The chord placements a [`SheetLayout`](#songleaf.render.SheetLayout) can name.                                                                                             |
| [`PACKERS`](#songleaf.render.PACKERS)          | The line packers a [`SheetLayout`](#songleaf.render.SheetLayout) can name (see [`songleaf.packing`](songleaf.packing.html.md#module-songleaf.packing)). |
| [`LAYOUT_OPTIONS`](#songleaf.render.LAYOUT_OPTIONS)   | What each option of a layout spec changes, from the v1 layout (`dense`).                                                                                                                  |

### Functions

| [`fit_font_size`](#songleaf.render.fit_font_size)(song, \*[, page_size, margin, ...])   | The largest lyric font size at which `song` fits one page in `layout` (default: v1's).                                                  |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`layout_named`](#songleaf.render.layout_named)(spec, \*[, style])                     | The layout of a spec: options of [`LAYOUT_OPTIONS`](#songleaf.render.LAYOUT_OPTIONS) joined by `+` (`"inline+two-column"`). |
| [`layout_spec`](#songleaf.render.layout_spec)(spec)                                   | The one spelling of a layout spec, for names: `"Dense"` -> `"dense"`.                                                                   |
| [`make_renderer`](#songleaf.render.make_renderer)([layout])                             | A `(song, output) -> dict` renderer for `layout`, the shape `sheet`'s `renderer=` takes.                                                |
| [`on_paper`](#songleaf.render.on_paper)(color[, alpha, paper])                     | `color` at opacity `alpha` over `paper`, as one opaque colour: what ink at that opacity shows.                                          |
| [`render_dense_a4`](#songleaf.render.render_dense_a4)(song, output, \*[, ...])            | Render `song` in the v1 layout as a PDF to `output` (a path or a binary file object).                                                   |
| [`render_sheet`](#songleaf.render.render_sheet)(song, output, \*[, layout, ...])       | Render `song` in `layout` (a [`SheetLayout`](#songleaf.render.SheetLayout) or a spec) as a PDF to `output`.              |
| [`section_family`](#songleaf.render.section_family)(label)                               | `"chorus"` for a chorus or refrain, `"bridge"` for a pre-chorus or bridge, else `""`.                                                   |
| [`short_label`](#songleaf.render.short_label)(label)                                  | A compact section label: `"Verse 1"` -> `"V1"`, `"Chorus x2"` -> `"Ch x2"`.                                                             |
| [`usable_font`](#songleaf.render.usable_font)(name)                                   | The reportlab font name to set `name` in, registering a bundled TTF once.                                                               |

### Classes

| [`ChordPlacement`](#songleaf.render.ChordPlacement)(\*args, \*\*kwargs)           | Where a piece's chords go relative to its lyrics: the strategy behind `SheetLayout.chords`.   |
|-----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| [`DenseStyle`](#songleaf.render.DenseStyle)([lyric_font, chord_font, ...])    | Typography of the dense layouts.                                                              |
| [`InlineChords`](#songleaf.render.InlineChords)(\*[, snap_to_syllables])        | Chords in the lyric line, right before their syllable; a chord-only line is a row of chords.  |
| [`OverChords`](#songleaf.render.OverChords)()                                 | Chords above their syllables, smaller and lighter, overlapping the lyric row by `chord_rise`. |
| [`SheetLayout`](#songleaf.render.SheetLayout)([chords, packing, columns, ...]) | One way to lay a song out on a page.                                                          |

### songleaf.render.BUNDLED_FONTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'DejaVuSans': ('DejaVuSans.ttf', 'Helvetica'), 'DejaVuSans-Bold': ('DejaVuSans-Bold.ttf', 'Helvetica-Bold')}*

name -> (file in [`FONTS_DIR`](#songleaf.render.FONTS_DIR), standard font used
when that file cannot be loaded). Any other name is passed to reportlab as is:
one of its standard fonts, or a TTF the caller registered with `pdfmetrics`.

* **Type:**
  Fonts songleaf ships

### songleaf.render.CHORD_PLACEMENTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [ChordPlacement](#songleaf.render.ChordPlacement)]* *= {'inline': InlineChords(snap_to_syllables=True), 'over': OverChords()}*

The chord placements a [`SheetLayout`](#songleaf.render.SheetLayout) can name.

### *class* songleaf.render.ChordPlacement(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Where a piece’s chords go relative to its lyrics: the strategy behind `SheetLayout.chords`.

#### extent(piece, size, style)

The width the piece takes, chords included (its label excluded).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

#### fitting_length(piece, available, size, style)

How many leading characters of the piece’s text fit in `available`.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

#### items(piece, x, size, style, paint)

What to draw for the piece, starting at `x`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[`_Item`]

### songleaf.render.DFLT_MARGIN *= 14.0*

Page margin in points (5 mm), about the least a printer leaves blank anyway.

### *class* songleaf.render.DenseStyle(lyric_font='DejaVuSans', chord_font='DejaVuSans-Bold', label_font='DejaVuSans-Bold', title_font='DejaVuSans-Bold', lyric_color='#000000', chord_color='#3b73c4', label_color='#8c8c8c', separator_color='#a6a6a6', title_color='#595959', chord_scale=0.62, label_scale=0.5, title_scale=0.6, chord_rise=0.56, chord_halo='', chord_halo_width=0.16, ascent=0.72, descent=0.21, row_gap=0.06, paragraph_gap=0.3, separator=' / ', chord_gap=0.3, bare_chord_gap=0.9, label_gap=0.4, inline_chord_scale=0.7, inline_chord_rise=0.2, inline_chord_pad=0.15, before_marker='‹', column_gap=0.8, column_rule_color='#d9d9d9', chorus_shade='#f3efe4', bridge_shade='#e8eef6', band_pad=0.12, repeat_color='#4d4d4d', tonic_chord_color='#1c4a91', outside_chord_color='#c0602a')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Typography of the dense layouts. Lengths are fractions of the lyric font size.

### songleaf.render.FONTS_DIR *= PosixPath('/home/runner/work/songleaf/songleaf/songleaf/data/fonts')*

Where the bundled TrueType fonts live (with their licence).

### *class* songleaf.render.InlineChords(, snap_to_syllables=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Chords in the lyric line, right before their syllable; a chord-only line is a row of chords.

* **Parameters:**
  **snap_to_syllables** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Show a chord that lands inside a word at the word’s
  or the syllable’s start (see `_syllable_start()`); the song’s
  annotations are not changed.

### songleaf.render.LAYOUT_OPTIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]* *= {'dense': {}, 'guitar': {'diagrams': 'guitar'}, 'inline': {'chords': 'inline'}, 'overlap': {'chords': 'over', 'style': {'chord_halo': '#ffffff', 'chord_rise': 0.42}}, 'packed': {'packing': 'structured'}, 'piano': {'diagrams': 'piano'}, 'shaded': {'shading': True}, 'two-column': {'columns': 2}}*

What each option of a layout spec changes, from the v1 layout (`dense`).

### *class* songleaf.render.OverChords

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Chords above their syllables, smaller and lighter, overlapping the lyric row by `chord_rise`.

### songleaf.render.PACKERS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)]* *= {'greedy': <function pack_greedy>, 'structured': <function pack_structured>}*

The line packers a [`SheetLayout`](#songleaf.render.SheetLayout) can name (see [`songleaf.packing`](songleaf.packing.html.md#module-songleaf.packing)).

### *class* songleaf.render.SheetLayout(chords='over', packing='greedy', columns=1, shading=False, diagrams=None, style=DenseStyle())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One way to lay a song out on a page.

* **Parameters:**
  * **chords** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`ChordPlacement`](#songleaf.render.ChordPlacement)) – Where chords go: `"over"` (overlapping the lyric row) or
    `"inline"` (in the line, before their syllable), or any
    [`ChordPlacement`](#songleaf.render.ChordPlacement).
  * **packing** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)) – Which lines share a row: `"greedy"` or `"structured"`, or
    any packer with the signature of [`songleaf.packing.pack_greedy()`](songleaf.packing.html.md#songleaf.packing.pack_greedy).
  * **columns** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Columns per page.
  * **shading** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Shade sections, repeated lines and chord functions.
  * **diagrams** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – `"piano"` or `"guitar"` draws the song’s chords as a strip
    of diagrams at the foot of the first page ([`songleaf.diagrams`](songleaf.diagrams.html.md#module-songleaf.diagrams));
    the lyrics shrink to make room. `None`: no diagrams.
  * **style** ([`DenseStyle`](#songleaf.render.DenseStyle)) – Typography and colours.

#### *property* packer *: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)*

The line packer.

#### *property* placement *: [ChordPlacement](#songleaf.render.ChordPlacement)*

The chord placement strategy.

### songleaf.render.fit_font_size(song, , page_size='A4', margin=14.0, style=None, layout=None, min_font_size=6.0, max_font_size=72.0, precision=0.05)

The largest lyric font size at which `song` fits one page in `layout` (default: v1’s).

`style`, if given, replaces the layout’s style. Returns `min_font_size`
if even that does not fit (the song then needs more pages).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.render.layout_named(spec, , style=None)

The layout of a spec: options of [`LAYOUT_OPTIONS`](#songleaf.render.LAYOUT_OPTIONS) joined by `+` (`"inline+two-column"`).

Options apply in order, over the v1 layout and `style` (default
[`DenseStyle`](#songleaf.render.DenseStyle)).

* **Return type:**
  [`SheetLayout`](#songleaf.render.SheetLayout)

### songleaf.render.layout_spec(spec)

The one spelling of a layout spec, for names: `"Dense"` -> `"dense"`.

```pycon
>>> layout_spec("2col + INLINE"), layout_spec("dense+"), layout_spec("inline+2col+inline")
('two-column+inline', 'dense', 'two-column+inline')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.render.make_renderer(layout='dense', \*\*render_options)

A `(song, output) -> dict` renderer for `layout`, the shape `sheet`’s `renderer=` takes.

`render_options` are passed to [`render_sheet()`](#songleaf.render.render_sheet) (`page_size`,
`margin`, …). A bad spec fails here, not at render time.

```pycon
>>> make_renderer("packed+shaded").keywords["layout"].packing
'structured'
```

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)

### songleaf.render.on_paper(color, alpha=1.0, , paper='#ffffff')

`color` at opacity `alpha` over `paper`, as one opaque colour: what ink at that opacity shows.

```pycon
>>> on_paper("#000000", 0.5), on_paper("#3b73c4"), on_paper("#ff0000", 0)
('#808080', '#3b73c4', '#ffffff')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.render.render_dense_a4(song, output, , page_size='A4', margin=14.0, style=None, min_font_size=6.0, max_font_size=72.0)

Render `song` in the v1 layout as a PDF to `output` (a path or a binary file object).

The same as [`render_sheet()`](#songleaf.render.render_sheet) with `layout="dense"`. Returns
`{"path", "font_size", "pages", "rows"}`; `path` is `None` when
`output` is a file object.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.render.render_sheet(song, output, , layout='dense', page_size='A4', margin=14.0, min_font_size=6.0, max_font_size=72.0, scale=1.0)

Render `song` in `layout` (a [`SheetLayout`](#songleaf.render.SheetLayout) or a spec) as a PDF to `output`.

The lyric font size is the largest that fits the song on one page, times
`scale`: `1` fills the page, `0.8` leaves room, `1.2` is larger type
that runs onto a second page. It never goes past `max_font_size`.

`output` is a path or a binary file object. Returns
`{"path", "font_size", "pages", "rows"}`; `path` is `None` when
`output` is a file object.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.render.section_family(label)

`"chorus"` for a chorus or refrain, `"bridge"` for a pre-chorus or bridge, else `""`.

```pycon
>>> section_family("Pre-Chorus"), section_family("Refrão 2"), section_family("Verse")
('bridge', 'chorus', '')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.render.short_label(label)

A compact section label: `"Verse 1"` -> `"V1"`, `"Chorus x2"` -> `"Ch x2"`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.render.usable_font(name)

The reportlab font name to set `name` in, registering a bundled TTF once.

A name in [`BUNDLED_FONTS`](#songleaf.render.BUNDLED_FONTS) is registered from [`FONTS_DIR`](#songleaf.render.FONTS_DIR) on first
use; if its file cannot be loaded, the paired standard font is returned and a
warning says so. Any other name is returned unchanged.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
