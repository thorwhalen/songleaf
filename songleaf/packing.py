"""Line packing: which consecutive lines of a paragraph share a row.

A *packer* takes the widths of consecutive units (lines, or the parts of a
wrapped line), the row ``width`` and the ``separator`` width, and returns the
rows as ``(start, stop)`` index ranges, in order. It never reorders units, and a
unit wider than the row gets a row of its own.

- :func:`pack_greedy` puts as many units on each row as fit (the v1 packing).
- :func:`pack_structured` finds the packing of least total cost: every row costs
  ``row_cost``, and every break between rows costs what breaking the lyric there
  costs (``break_costs``, usually from :func:`line_break_costs`): nothing
  between quatrains, little between couplets, a lot inside a rhyming pair or
  between a line and its repeat.

A five-line verse where three lines fit on a row: greedy packing leaves a
couplet split across rows, structured packing does not, on as many rows.

>>> verse = ["one", "two", "three", "four", "five"]
>>> pack_greedy([2] * 5, width=6.5, separator=0.25)
[(0, 3), (3, 5)]
>>> pack_structured([2] * 5, width=6.5, separator=0.25, break_costs=line_break_costs(verse))
[(0, 2), (2, 5)]
>>> rhyme_key("Paper boats on a silver stream"), rhyme_key("a morning dream")
('eam', 'eam')
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from functools import lru_cache

_VOWELS = "aeiouy"
_TRAILING_NOTE_RE = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*$")  # "(x2)", "[repeat]"
_EPSILON = 1e-9


def pack_greedy(
    widths: Sequence[float],
    *,
    width: float,
    separator: float,
    break_costs: Sequence[float] = (),
) -> list[tuple[int, int]]:
    """As many units on each row as fit. ``break_costs`` is accepted and ignored."""
    rows, start, used = [], 0, 0.0
    for index, unit in enumerate(widths):
        if index > start and used + separator + unit <= width:
            used += separator + unit
            continue
        if index > start:
            rows.append((start, index))
        start, used = index, unit
    if widths:
        rows.append((start, len(widths)))
    return rows


def pack_structured(
    widths: Sequence[float],
    *,
    width: float,
    separator: float,
    break_costs: Sequence[float] = (),
    row_cost: float = 2.0,
) -> list[tuple[int, int]]:
    """The rows of least ``row_cost * rows + sum(break_costs at the breaks)``.

    ``break_costs[k]`` is the cost of a break between unit ``k`` and ``k + 1``
    (missing entries cost nothing). With every break free this uses as few rows
    as :func:`pack_greedy`, and ties go to the greedy packing.
    """
    n = len(widths)
    if not n:
        return []

    def cost_of_break_after(k):
        return break_costs[k] if k < len(break_costs) else 0.0

    best = [0.0] + [float("inf")] * n
    first_of_last_row = [0] * (n + 1)
    for stop in range(1, n + 1):
        used = 0.0
        for start in range(stop - 1, -1, -1):
            used += widths[start] + (separator if start < stop - 1 else 0.0)
            if start < stop - 1 and used > width:
                break
            cost = best[start] + row_cost
            if stop < n:
                cost += cost_of_break_after(stop - 1)
            if cost < best[stop] - _EPSILON:
                best[stop], first_of_last_row[stop] = cost, start
    rows, stop = [], n
    while stop:
        start = first_of_last_row[stop]
        rows.append((start, stop))
        stop = start
    return rows[::-1]


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def rhyme_key(line: str) -> str:
    """The sound a line ends on, as letters: the last vowel group of its last word and what follows.

    A silent final ``e`` is dropped first, so ``love`` and ``above`` share
    ``"ov"``. Accents are ignored, and a trailing note such as ``(x2)`` is skipped.

    >>> rhyme_key("sing it low (x2)"), rhyme_key("Coração"), rhyme_key("")
    ('ow', 'ao', '')
    """
    words = re.findall(r"[^\W\d_]+", _plain(_TRAILING_NOTE_RE.sub("", line)))
    if not words:
        return ""
    word = words[-1]
    if len(word) > 2 and word.endswith("e") and word[-2] not in _VOWELS:
        word = word[:-1]
    match = re.search(rf"[{_VOWELS}]+[^{_VOWELS}]*$", word)
    return match.group() if match else word


def _words(line: str) -> str:
    return " ".join(re.findall(r"\w+", _plain(line)))


@lru_cache(maxsize=4096)
def _cached_break_costs(lines: tuple, costs: tuple) -> tuple:
    between_quatrains, between_couplets, inside_couplet, rhyme, repeat = costs
    keys = [rhyme_key(line) for line in lines]
    words = [_words(line) for line in lines]

    def rhymes(i, j):
        return bool(keys[i]) and keys[i] == keys[j]

    result = []
    for i in range(len(lines) - 1):
        count = i + 1  # lines before the break
        if count % 4 == 0:
            cost = between_quatrains
        elif count % 2 == 0:
            cost = between_couplets
        else:
            cost = inside_couplet
        pair_ends = i and rhymes(i - 1, i)
        pair_starts = i + 2 < len(lines) and rhymes(i + 1, i + 2)
        if (pair_ends or pair_starts) and not rhymes(i, i + 1):
            cost = min(cost, between_couplets)  # a rhyming pair ends or starts here
        if rhymes(i, i + 1):
            cost += rhyme
        if words[i] and words[i] == words[i + 1]:
            cost += repeat
        result.append(cost)
    return tuple(result)


def line_break_costs(
    lines: Sequence[str],
    *,
    between_quatrains: float = 0.0,
    between_couplets: float = 0.3,
    inside_couplet: float = 1.0,
    rhyme: float = 1.0,
    repeat: float = 0.5,
) -> list[float]:
    """The cost of a row break after each line of a paragraph but the last.

    Counting from the paragraph's first line, a break after every fourth line
    costs ``between_quatrains``, after every other even line
    ``between_couplets``, and after an odd line ``inside_couplet``. A break
    right before or after a rhyming pair costs no more than
    ``between_couplets`` (so a pickup line shifts the couplets), a break
    between two lines that rhyme costs ``rhyme`` more, and one between a line
    and its repeat ``repeat`` more.

    >>> line_break_costs(["a stream", "a dream", "go slow", "go low"])
    [2.0, 0.3, 2.0]
    >>> line_break_costs(["well", "a stream", "a dream", "go slow", "go slow"])
    [0.3, 1.3, 0.3, 1.5]
    """
    costs = (between_quatrains, between_couplets, inside_couplet, rhyme, repeat)
    return list(_cached_break_costs(tuple(lines), costs))
