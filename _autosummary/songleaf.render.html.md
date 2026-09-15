# songleaf.render

Render a song onto one dense A4 page, with the lyrics as large as will fit.

[`render_dense_a4()`](#songleaf.render.render_dense_a4) finds the largest lyric font size at which the whole
song fits on one page ([`fit_font_size()`](#songleaf.render.fit_font_size)), then draws it:

- consecutive lines of a paragraph are packed onto one row while they fit,
  separated by a light `/`; a blank line or a new section starts a new row,
  and a line too long for the page wraps at a space (inside a word only when
  a single word is wider than the page);
- chords ride on their lyric row, smaller and in a lighter colour, overlapping
  the tops of the letters instead of taking a line of their own; a chord starts
  over the syllable it lands on (a `timing="before"` chord ends there);
- section labels are small grey prefixes (`V1`, `Ch`) on the first row;
- only a song that cannot fit at `min_font_size` spills onto more pages.

Text is set in reportlab’s built-in Helvetica, which covers Latin-1.

```pycon
>>> short_label("Verse 1"), short_label("Pre-Chorus"), short_label("Coda")
('V1', 'Pre', 'Coda')
```

### Module Attributes

| [`DFLT_MARGIN`](#songleaf.render.DFLT_MARGIN)   | Page margin in points (5 mm), about the least a printer leaves blank anyway.   |
|----------------------------------------------------------------|--------------------------------------------------------------------------------|

### Functions

| [`fit_font_size`](#songleaf.render.fit_font_size)(song, \*[, page_size, margin, ...])   | The largest lyric font size at which `song` fits one page.                  |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`render_dense_a4`](#songleaf.render.render_dense_a4)(song, output, \*[, ...])            | Render `song` as a PDF to `output` (a path or a binary file object).        |
| [`short_label`](#songleaf.render.short_label)(label)                                  | A compact section label: `"Verse 1"` -> `"V1"`, `"Chorus x2"` -> `"Ch x2"`. |

### Classes

| [`DenseStyle`](#songleaf.render.DenseStyle)([lyric_font, chord_font, ...])   | Typography of the dense layout.   |
|----------------------------------------------------------------------------------------------|-----------------------------------|

### songleaf.render.DFLT_MARGIN *= 14.0*

Page margin in points (5 mm), about the least a printer leaves blank anyway.

### *class* songleaf.render.DenseStyle(lyric_font='Helvetica', chord_font='Helvetica-Bold', label_font='Helvetica-Bold', title_font='Helvetica-Bold', lyric_color='#000000', chord_color='#3b73c4', label_color='#8c8c8c', separator_color='#a6a6a6', title_color='#595959', chord_scale=0.62, label_scale=0.5, title_scale=0.6, chord_rise=0.56, ascent=0.72, descent=0.21, row_gap=0.06, paragraph_gap=0.3, separator=' / ', chord_gap=0.3, bare_chord_gap=0.9, label_gap=0.4)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Typography of the dense layout. Lengths are fractions of the lyric font size.

### songleaf.render.fit_font_size(song, , page_size='A4', margin=14.0, style=None, min_font_size=6.0, max_font_size=72.0, precision=0.05)

The largest lyric font size at which `song` fits one page.

`min_font_size` if even that does not fit (the song then needs more pages).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### songleaf.render.render_dense_a4(song, output, , page_size='A4', margin=14.0, style=None, min_font_size=6.0, max_font_size=72.0)

Render `song` as a PDF to `output` (a path or a binary file object).

Returns `{"path", "font_size", "pages", "rows"}`; `path` is `None`
when `output` is a file object.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### songleaf.render.short_label(label)

A compact section label: `"Verse 1"` -> `"V1"`, `"Chorus x2"` -> `"Ch x2"`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
