# songleaf

Dense, readable one-page song sheets: lyrics and chords on one A4 page, with the lyrics as large as will fit.

```bash
pip install songleaf
python -m songleaf sheet "wonderwall oasis"    # -> a one-page PDF in ~/.local/share/songleaf/sheets/
```

The default source is the Kaggle *chords-and-lyrics* corpus (about 135,000 songs), read from a local copy of its zip (see [Sources](#sources)).

## What the sheet looks like

- **One page, largest type that fits.** The lyric font size is found by search for each song. On 1,500 randomly sampled corpus songs, the median came out around 22 pt, and 1,498 of the 1,500 fit on one page. A song that cannot fit at the minimum size spills onto a second page.
- **Chords take no line of their own.** They are smaller and blue, start over the syllable they land on, and overlap the tops of the letters of their lyric line.
- **Lines share rows.** Consecutive lines of a paragraph are packed onto one row, separated by a light `/`. A blank line or a new section starts a new row.
- **Small labels.** Sections are grey prefixes (`V1`, `Ch`, `Br`); title, artist, capo and key are one small line at the top.

## Command line

```bash
python -m songleaf search "wonderwall oasis"              # fuzzy: typos and word order don't matter
python -m songleaf search --artist oasis --lyrics "roads winding"
python -m songleaf sheet "wonderwall oasis" --output wonderwall.pdf
python -m songleaf sheet "wonderwall oasis" --pick 2      # the second-best match
python -m songleaf songs                                  # songs already stored
python -m songleaf sheet kaggle_chords:1234               # a song by its key: no search
python -m songleaf sheet kaggle_chords:1234 --refresh     # fetch it again from its source
```

The `songleaf` console script is the same command.

## Python

```python
import songleaf

hits = songleaf.search("wonderwall oasis")
song = songleaf.get_song(hits[0].key)  # a Song: lyrics text + annotations
songleaf.render_dense_a4(song, "wonderwall.pdf")  # {'font_size': ..., 'pages': 1, ...}

songleaf.sheet("wonderwall oasis")  # search, store and render in one call
```

## The song model

A `Song` is lyrics text plus *standoff* annotations anchored on character offsets, so annotation layers never touch the text:

- `section`: spans its lines, `{"label": "Chorus"}`;
- `chord`: a point on the first character of the syllable the chord lands on, `{"symbol": "G/B", "timing": "at"}` (`"before"` marks a chord that sounds ahead of that syllable);
- `score`: a link from a stretch of lyrics to a score snippet, `{"source", "id", "url", "format"}`.

Metadata (title, artist, capo, key) and provenance (source, id, url, licence) travel with the song, and `Song.to_dict()` is its JSON form.

```python
from songleaf import Song, chord, section, parse_chords_over_lyrics

song = Song(
    "Paper boats drift", [section(0, 17, "Verse 1"), chord(0, "G"), chord(6, "D")]
)
song = parse_chords_over_lyrics(
    "G     D\nPaper boats drift"
)  # the same chords, from a chart
```

## Storage

Songs are kept in a `MutableMapping` (`songleaf.song_store()`): one JSON file per song under `~/.local/share/songleaf/songs/`. Rendered sheets go to `~/.local/share/songleaf/sheets/`. Set `SONGLEAF_DATA_DIR` to move both.

## Sources

`KaggleChordsSource` reads the [chords-and-lyrics dataset](https://www.kaggle.com/datasets/eitanbentora/chords-and-lyrics-dataset) through `sung`. It needs a local copy of the zip: point `SUNG_CHORDS_AND_LYRICS_ZIP` at it, or keep it where `haggle` downloads it (`$HAGGLE_ROOTDIR/zips/eitanbentora/chords-and-lyrics-dataset.zip`). Without a local copy, `sung` downloads it from Kaggle, which needs Kaggle credentials. The corpus was scraped from a chords site, so keep it to personal use.

Loading the corpus takes about five seconds on the first search in a process.

## Extending

Three keyword arguments are the extension points, on `sheet` (and `search` for sources):

- `sources=`: objects with a `name`, `search(query, *, title, artist, lyrics, limit)` returning `Hit`s, and `get(song_id)` returning a `Song`;
- `store=`: any `MutableMapping[str, Song]` (a `dict` works);
- `renderer=`: any `(song, output) -> dict` function.

```python
songleaf.sheet("paper boats", sources=[my_source], store={}, renderer=my_renderer)
```
