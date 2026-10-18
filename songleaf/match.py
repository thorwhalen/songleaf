"""Where a query matched: the words it shares with a field, as spans to highlight, and the lyric line.

Pure text functions, no corpus and no I/O. The search tags each hit with the field it
matched (:data:`MATCH_KINDS`); these say *where* in that field, so the page can mark the
matched part without tokenizing anything itself.

Words are runs of letters and digits, compared case-insensitively; a query word marks a
word of the text that it starts (``"wond"`` marks ``"Wonderwall"``), so a partly typed
word is shown too. A fuzzy match with a typo marks nothing, which is honest: the words
are not there.

>>> word_spans("Paper Boats", "paper")
[[0, 5]]
>>> lyric_snippet("G       D\\nPaper boats drift down\\nC\\nthe silver stream", "silver stream")
{'text': 'the silver stream', 'spans': [[4, 10], [11, 17]]}
"""

from __future__ import annotations

import re
from array import array
from bisect import bisect_left

#: The kinds of match a search reports, in the order the page shows them: a song in a list
#: whose name matches, then title, artist and lyrics. A song is reported once, in its first kind.
MATCH_KINDS = ("list", "title", "artist", "lyrics")
# A word: a number written with thousands separators ("10,000"), or a run of letters and digits.
_WORD = re.compile(r"\d{1,3}(?:[,.]\d{3})+(?!\d)|\w+", re.UNICODE)
_SEPARATORS = re.compile(r"[,.]")
_DEFAULT_SNIPPET_WIDTH = 90
#: A query word this long or longer also finds the words one edit away (a letter added,
#: dropped, changed, or two swapped); from :data:`TWO_TYPOS_MIN_LENGTH` letters, two edits.
TYPO_MIN_LENGTH = 4
TWO_TYPOS_MIN_LENGTH = 10
#: A query word shorter than this finds only itself, not every word it starts ("a").
PREFIX_MIN_LENGTH = 2
#: The words of a query that are matched against titles and artists: a pasted verse stops here.
MAX_QUERY_WORDS = 12


def query_words(query: str) -> list[str]:
    """The distinct words of a query, lowercased, in order; ``10,000`` is the word ``10000``.

    >>> query_words("Paper  boats, PAPER!"), query_words("10,000 Hours")
    (['paper', 'boats'], ['10000', 'hours'])
    """
    return list(dict.fromkeys(_normal(m.group()) for m in _WORD.finditer(query)))


def _normal(word: str) -> str:
    return _SEPARATORS.sub("", word.lower())


def shared_words(query: str, text: str) -> int:
    """How many distinct words of ``query`` are words of ``text``.

    >>> shared_words("10000 hours justin bieber", "10,000 Hours Justin Bieber")
    4
    """
    return len(set(query_words(query)) & set(query_words(text)))


def word_spans(text: str, query: str) -> list[list[int]]:
    """``[start, end]`` of each word of ``text`` that a word of ``query`` starts, in order.

    >>> word_spans("Wonderwall (Remastered)", "wonder rem")
    [[0, 10], [12, 22]]
    >>> word_spans("Quiet Road", "road quiet")
    [[0, 5], [6, 10]]
    >>> word_spans("Quiet Road", "")
    []
    """
    words = query_words(query)
    if not words:
        return []
    return [
        [m.start(), m.end()]
        for m in _WORD.finditer(text)
        if any(_normal(m.group()).startswith(w) for w in words)
    ]


def lyric_snippet(
    text: str, query: str, *, width: int = _DEFAULT_SNIPPET_WIDTH
) -> dict | None:
    """The line of ``text`` holding the most words of ``query`` (whole words), with their spans.

    Lyrics match on whole words (as the search does), so a span here is a whole word.
    A line longer than ``width`` is cut around its first match, with ``…`` marking each
    cut. ``None`` when no line holds any of the words.

    >>> lyric_snippet("la la\\nno match here", "boats") is None
    True
    >>> long = "word " * 30 + "boats " + "word " * 30
    >>> cut = lyric_snippet(long, "boats", width=30)
    >>> cut["text"].startswith("…") and cut["text"].endswith("…"), len(cut["text"]) <= 32
    (True, True)
    >>> cut["text"][slice(*cut["spans"][0])]
    'boats'
    """
    words = set(query_words(query))
    if not words:
        return None
    best, best_found = None, 0
    for line in text.splitlines():
        found = {_normal(m.group()) for m in _WORD.finditer(line)} & words
        if len(found) > best_found:
            best, best_found = line, len(found)
            if best_found == len(words):
                break
    if best is None:
        return None
    line = " ".join(best.split())  # the chart's alignment spaces go
    spans = [
        [m.start(), m.end()]
        for m in _WORD.finditer(line)
        if _normal(m.group()) in words
    ]
    if len(line) <= width:
        return {"text": line, "spans": spans}
    first = spans[0][0]
    start = max(0, min(first - width // 3, len(line) - width))
    end = start + width
    prefix = "…" if start else ""
    suffix = "…" if end < len(line) else ""
    shift = len(prefix) - start
    kept = [[a + shift, b + shift] for a, b in spans if a >= start and b <= end]
    return {"text": prefix + line[start:end] + suffix, "spans": kept}


class WordIndex:
    """Which of a list of texts (titles, say) hold which words, for matching a query word by word.

    A text matches a query when the query is *inside* it (every query word is a word of the
    text, or starts one: ``"paper bo"`` finds *Paper Boats*) or the text is inside the query
    (every word of the text is a word of the query, two at least: ``"paper boats band"``
    finds *Paper Boats*). In the first direction, a query word of :data:`TYPO_MIN_LENGTH` letters or more
    also matches the words it is a typo of; in the second, the text's words must be there as
    typed, or every short title would be a typo of some word of a long query. Unlike a fuzzy score over the whole string, a word is never matched by
    a piece of another word, so *As* is not a match for ``"oasis"``.

    Memory: one sorted vocabulary, one array of row numbers per text word, and one word
    count per text, a few MB for 135K titles.

    >>> titles = WordIndex(["Paper Boats", "Quiet Road", "Paper Moon", "As"])
    >>> sorted(titles.matching("paper"))
    [0, 2]
    >>> sorted(titles.matching("paper boats by the band")), sorted(titles.matching("papr boats"))
    ([0], [0])
    >>> sorted(WordIndex(["Scream"]).matching("silver stream"))  # one letter from "stream"
    []
    >>> sorted(WordIndex(["Day", "The Day"]).matching("is gonna be the day"))  # one word is not enough
    [1]
    >>> sorted(titles.matching("oasis")), sorted(titles.matching("qui"))
    ([], [1])
    """

    def __init__(self, texts):
        postings: dict[str, list[int]] = {}
        sizes = array("H")
        for row, text in enumerate(texts):
            words = set(query_words(text))
            sizes.append(min(len(words), 65535))
            for word in words:
                postings.setdefault(word, []).append(row)
        self._vocabulary = sorted(postings)
        self._rows = [array("i", postings[word]) for word in self._vocabulary]
        self._sizes = sizes

    def __len__(self) -> int:
        return len(self._sizes)

    def _ids(self, word: str, *, prefix: bool, typos: bool = True) -> list[int]:
        """Vocabulary positions of the words ``word`` finds: itself, (``typos``) its typos, and (``prefix``) the words it starts."""
        vocabulary = self._vocabulary
        found = set()
        start = bisect_left(vocabulary, word)
        if prefix and len(word) >= PREFIX_MIN_LENGTH:
            end = start
            while end < len(vocabulary) and vocabulary[end].startswith(word):
                end += 1
            found.update(range(start, end))
        elif start < len(vocabulary) and vocabulary[start] == word:
            found.add(start)
        if typos and len(word) >= TYPO_MIN_LENGTH:
            from rapidfuzz import process
            from rapidfuzz.distance import DamerauLevenshtein

            edits = 2 if len(word) >= TWO_TYPOS_MIN_LENGTH else 1
            for _, _, position in process.extract(
                word,
                vocabulary,
                scorer=DamerauLevenshtein.distance,
                score_cutoff=edits,
                limit=None,
            ):
                found.add(position)
        return sorted(found)

    def rows_with(self, word: str) -> set[int]:
        """The rows holding ``word`` (a query word, lowercased), a word it starts, or one it is a typo of.

        >>> sorted(WordIndex(["Paper Boats", "Paperback", "Quiet"]).rows_with("paper"))
        [0, 1]
        """
        rows = set()
        for position in self._ids(word, prefix=True):
            rows.update(self._rows[position])
        return rows

    def matching(self, query: str) -> set[int]:
        """The rows whose text holds the query, or is held by it, word by word."""
        words = query_words(query)[:MAX_QUERY_WORDS]
        if not words:
            return set()
        inside = None  # rows holding every query word (or a word it starts)
        exact_ids = (
            set()
        )  # vocabulary words some query word is: a whole text inside the query is exact
        for word in words:
            rows = self.rows_with(word)
            inside = rows if inside is None else inside & rows
            exact_ids.update(self._ids(word, prefix=False, typos=False))
        covered: dict[int, int] = {}  # row -> how many of its words the query holds
        for position in exact_ids:
            for row in self._rows[position]:
                covered[row] = covered.get(row, 0) + 1
        # a whole text inside a longer query must hold two of its words: one word ("Day",
        # "Be") is inside almost any line of lyrics typed as a query
        least = min(2, len(words))
        held = {
            row for row, n in covered.items() if n >= self._sizes[row] and n >= least
        }
        return (inside or set()) | held
