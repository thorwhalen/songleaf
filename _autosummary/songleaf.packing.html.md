# songleaf.packing

Line packing: which consecutive lines of a paragraph share a row.

A *packer* takes the widths of consecutive units (lines, or the parts of a
wrapped line), the row `width` and the `separator` width, and returns the
rows as `(start, stop)` index ranges, in order. It never reorders units, and a
unit wider than the row gets a row of its own.

- [`pack_greedy()`](#songleaf.packing.pack_greedy) puts as many units on each row as fit (the v1 packing).
- [`pack_structured()`](#songleaf.packing.pack_structured) finds the packing of least total cost: every row costs
  `row_cost`, and every break between rows costs what breaking the lyric there
  costs (`break_costs`, usually from [`line_break_costs()`](#songleaf.packing.line_break_costs)): nothing
  between quatrains, little between couplets, a lot inside a rhyming pair or
  between a line and its repeat.

A five-line verse where three lines fit on a row: greedy packing leaves a
couplet split across rows, structured packing does not, on as many rows.

```pycon
>>> verse = ["one", "two", "three", "four", "five"]
>>> pack_greedy([2] * 5, width=6.5, separator=0.25)
[(0, 3), (3, 5)]
>>> pack_structured([2] * 5, width=6.5, separator=0.25, break_costs=line_break_costs(verse))
[(0, 2), (2, 5)]
>>> rhyme_key("Paper boats on a silver stream"), rhyme_key("a morning dream")
('eam', 'eam')
```

### Functions

| [`line_break_costs`](#songleaf.packing.line_break_costs)(lines, \*[, ...])               | The cost of a row break after each line of a paragraph but the last.                          |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| [`pack_greedy`](#songleaf.packing.pack_greedy)(widths, \*, width, separator[, ...]) | As many units on each row as fit.                                                             |
| [`pack_structured`](#songleaf.packing.pack_structured)(widths, \*, width, separator)    | The rows of least `row_cost * rows + sum(break_costs at the breaks)`.                         |
| [`rhyme_key`](#songleaf.packing.rhyme_key)(line)                                  | The sound a line ends on, as letters: the last vowel group of its last word and what follows. |

### songleaf.packing.line_break_costs(lines, , between_quatrains=0.0, between_couplets=0.3, inside_couplet=1.0, rhyme=1.0, repeat=0.5)

The cost of a row break after each line of a paragraph but the last.

Counting from the paragraph’s first line, a break after every fourth line
costs `between_quatrains`, after every other even line
`between_couplets`, and after an odd line `inside_couplet`. A break
right before or after a rhyming pair costs no more than
`between_couplets` (so a pickup line shifts the couplets), a break
between two lines that rhyme costs `rhyme` more, and one between a line
and its repeat `repeat` more.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> line_break_costs(["a stream", "a dream", "go slow", "go low"])
[2.0, 0.3, 2.0]
>>> line_break_costs(["well", "a stream", "a dream", "go slow", "go slow"])
[0.3, 1.3, 0.3, 1.5]
```

### songleaf.packing.pack_greedy(widths, , width, separator, break_costs=())

As many units on each row as fit. `break_costs` is accepted and ignored.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]]

### songleaf.packing.pack_structured(widths, , width, separator, break_costs=(), row_cost=2.0)

The rows of least `row_cost * rows + sum(break_costs at the breaks)`.

`break_costs[k]` is the cost of a break between unit `k` and `k + 1`
(missing entries cost nothing). With every break free this uses as few rows
as [`pack_greedy()`](#songleaf.packing.pack_greedy), and ties go to the greedy packing.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]]

### songleaf.packing.rhyme_key(line)

The sound a line ends on, as letters: the last vowel group of its last word and what follows.

A silent final `e` is dropped first, so `love` and `above` share
`"ov"`. Accents are ignored, and a trailing note such as `(x2)` is skipped.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> rhyme_key("sing it low (x2)"), rhyme_key("Coração"), rhyme_key("")
('ow', 'ao', '')
```
