# songleaf.match

Where a query matched: the words it shares with a field, as spans to highlight, and the lyric line.

Pure text functions, no corpus and no I/O. The search tags each hit with the field it
matched ([`MATCH_KINDS`](#songleaf.match.MATCH_KINDS)); these say *where* in that field, so the page can mark the
matched part without tokenizing anything itself.

Words are runs of letters and digits, compared case-insensitively; a query word marks a
word of the text that it starts (`"wond"` marks `"Wonderwall"`), so a partly typed
word is shown too. A fuzzy match with a typo marks nothing, which is honest: the words
are not there.

```pycon
>>> word_spans("Paper Boats", "paper")
[[0, 5]]
>>> lyric_snippet("G       D\nPaper boats drift down\nC\nthe silver stream", "silver stream")
{'text': 'the silver stream', 'spans': [[4, 10], [11, 17]]}
```

### Module Attributes

| [`MATCH_KINDS`](#songleaf.match.MATCH_KINDS)       | a song in a list whose name matches, then title, artist and lyrics.                                                                                                     |
|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`TYPO_MIN_LENGTH`](#songleaf.match.TYPO_MIN_LENGTH)   | A query word this long or longer also finds the words one edit away (a letter added, dropped, changed, or two swapped); from `TWO_TYPOS_MIN_LENGTH` letters, two edits. |
| [`PREFIX_MIN_LENGTH`](#songleaf.match.PREFIX_MIN_LENGTH) | A query word shorter than this finds only itself, not every word it starts ("a").                                                                                       |
| [`MAX_QUERY_WORDS`](#songleaf.match.MAX_QUERY_WORDS)   | a pasted verse stops here.                                                                                                                                              |

### Functions

| [`lyric_snippet`](#songleaf.match.lyric_snippet)(text, query, \*[, width])   | The line of `text` holding the most words of `query` (whole words), with their spans.   |
|--------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`query_words`](#songleaf.match.query_words)(query)                        | The distinct words of a query, lowercased, in order; `10,000` is the word `10000`.      |
| [`shared_words`](#songleaf.match.shared_words)(query, text)                 | How many distinct words of `query` are words of `text`.                                 |
| [`word_spans`](#songleaf.match.word_spans)(text, query)                   | `[start, end]` of each word of `text` that a word of `query` starts, in order.          |

### Classes

| [`WordIndex`](#songleaf.match.WordIndex)(texts)   | Which of a list of texts (titles, say) hold which words, for matching a query word by word.   |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|

### songleaf.match.MATCH_KINDS *= ('list', 'title', 'artist', 'lyrics')*

a song in a list
whose name matches, then title, artist and lyrics. A song is reported once, in its first kind.

* **Type:**
  The kinds of match a search reports, in the order the page shows them

### songleaf.match.MAX_QUERY_WORDS *= 12*

a pasted verse stops here.

* **Type:**
  The words of a query that are matched against titles and artists

### songleaf.match.PREFIX_MIN_LENGTH *= 2*

A query word shorter than this finds only itself, not every word it starts (“a”).

### songleaf.match.TYPO_MIN_LENGTH *= 4*

A query word this long or longer also finds the words one edit away (a letter added,
dropped, changed, or two swapped); from `TWO_TYPOS_MIN_LENGTH` letters, two edits.

### *class* songleaf.match.WordIndex(texts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Which of a list of texts (titles, say) hold which words, for matching a query word by word.

A text matches a query when the query is *inside* it (every query word is a word of the
text, or starts one: `"paper bo"` finds *Paper Boats*) or the text is inside the query
(every word of the text is a word of the query, two at least: `"paper boats band"`
finds *Paper Boats*). In the first direction, a query word of [`TYPO_MIN_LENGTH`](#songleaf.match.TYPO_MIN_LENGTH) letters or more
also matches the words it is a typo of; in the second, the text’s words must be there as
typed, or every short title would be a typo of some word of a long query. Unlike a fuzzy score over the whole string, a word is never matched by
a piece of another word, so *As* is not a match for `"oasis"`.

Memory: one sorted vocabulary, one array of row numbers per text word, and one word
count per text, a few MB for 135K titles.

```pycon
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
```

#### matching(query)

The rows whose text holds the query, or is held by it, word by word.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

#### rows_with(word)

The rows holding `word` (a query word, lowercased), a word it starts, or one it is a typo of.

```pycon
>>> sorted(WordIndex(["Paper Boats", "Paperback", "Quiet"]).rows_with("paper"))
[0, 1]
```

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

### songleaf.match.lyric_snippet(text, query, , width=90)

The line of `text` holding the most words of `query` (whole words), with their spans.

Lyrics match on whole words (as the search does), so a span here is a whole word.
A line longer than `width` is cut around its first match, with `…` marking each
cut. `None` when no line holds any of the words.

```pycon
>>> lyric_snippet("la la\nno match here", "boats") is None
True
>>> long = "word " * 30 + "boats " + "word " * 30
>>> cut = lyric_snippet(long, "boats", width=30)
>>> cut["text"].startswith("…") and cut["text"].endswith("…"), len(cut["text"]) <= 32
(True, True)
>>> cut["text"][slice(*cut["spans"][0])]
'boats'
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.match.query_words(query)

The distinct words of a query, lowercased, in order; `10,000` is the word `10000`.

```pycon
>>> query_words("Paper  boats, PAPER!"), query_words("10,000 Hours")
(['paper', 'boats'], ['10000', 'hours'])
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### songleaf.match.shared_words(query, text)

How many distinct words of `query` are words of `text`.

```pycon
>>> shared_words("10000 hours justin bieber", "10,000 Hours Justin Bieber")
4
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### songleaf.match.word_spans(text, query)

`[start, end]` of each word of `text` that a word of `query` starts, in order.

```pycon
>>> word_spans("Wonderwall (Remastered)", "wonder rem")
[[0, 10], [12, 22]]
>>> word_spans("Quiet Road", "road quiet")
[[0, 5], [6, 10]]
>>> word_spans("Quiet Road", "")
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]]
