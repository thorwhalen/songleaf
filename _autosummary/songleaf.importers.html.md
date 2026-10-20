# songleaf.importers

Turn pasted text into a [`Song`](songleaf.model.html.md#songleaf.model.Song): a registry of format importers.

Each [`Importer`](#songleaf.importers.Importer) is a strategy: `detect(text)` says whether the text is
in its format, `parse(text, meta=, provenance=)` builds the song. The registry
[`IMPORTERS`](#songleaf.importers.IMPORTERS) is tried in order and the first match wins; the last one
(plain chords-over-lyrics) matches anything, so `import_text()` always
answers. A new format is a new [`Importer`](#songleaf.importers.Importer) in the registry, or one passed
as `importers=`.

- `ultimate-guitar`: `[ch]G[/ch]` / `[tab]...[/tab]` markup, stripped to
  columns, then parsed as chords-over-lyrics (`[Verse 1]` headers become
  sections).
- `chordpro`: `{directive}` lines or `[G]` chords inline in the lyrics.
- `opensong`: lines prefixed `.` (chords), \`\` \`\` (lyrics), `;` (comment),
  `[V1]`-style section tags.
- `chords-over-lyrics`: the fallback.

songleaf never contacts the site the text came from.

```pycon
>>> import_song("[ch]G[/ch]    [ch]D[/ch]\nPaper boats drift").format
'ultimate-guitar'
```

### Module Attributes

| [`PASTE_PROVENANCE`](#songleaf.importers.PASTE_PROVENANCE)   | Provenance recorded for every pasted song (`url` is added when known).   |
|---------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`KEY_HASH_CHARS`](#songleaf.importers.KEY_HASH_CHARS)     | Characters of the text hashed into the `paste:<hash>` key.               |
| [`MAX_META_CHARS`](#songleaf.importers.MAX_META_CHARS)     | Characters a given `key` or `capo` may have at most (`"F#m"`, `"2"`).    |
| [`MAX_PASTE_CHARS`](#songleaf.importers.MAX_PASTE_CHARS)    | Pasted text longer than this is refused (a chord chart is a few KB).     |
| [`IMPORTERS`](#songleaf.importers.IMPORTERS)          | Tried in order; the last one accepts anything.                           |

### Functions

| [`detect_format`](#songleaf.importers.detect_format)(text, \*[, importers])             | The name of the first importer that recognises *text*.                        |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| `format_names`([importers])                                                                       |                                                                               |
| [`import_song`](#songleaf.importers.import_song)(text, \*[, title, artist, url, ...]) | Parse pasted *text* with the first importer that recognises it (or *format*). |
| [`paste_key`](#songleaf.importers.paste_key)(text)                                  | The store key of pasted *text*: `paste:<hash>` (the same text, the same key). |

### Classes

| [`Imported`](#songleaf.importers.Imported)(key, format, song)   | A parsed paste: the song, its key and the format that read it.   |
|--------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`Importer`](#songleaf.importers.Importer)(name, detect, parse) | One text format: how to recognise it and how to read it.         |

### songleaf.importers.IMPORTERS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Importer](#songleaf.importers.Importer), ...]* *= (Importer(name='ultimate-guitar', detect=<function <lambda>>, parse=<function \_parse_ultimate_guitar>), Importer(name='chordpro', detect=<function \_is_chordpro>, parse=<function parse_chordpro>), Importer(name='opensong', detect=<function <lambda>>, parse=<function \_parse_opensong>), Importer(name='chords-over-lyrics', detect=<function <lambda>>, parse=<function parse_chords_over_lyrics>))*

Tried in order; the last one accepts anything.

### *class* songleaf.importers.Imported(key, format, song)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed paste: the song, its key and the format that read it.

### *class* songleaf.importers.Importer(name, detect, parse)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One text format: how to recognise it and how to read it.

### songleaf.importers.KEY_HASH_CHARS *= 12*

Characters of the text hashed into the `paste:<hash>` key.

### songleaf.importers.MAX_META_CHARS *= 20*

Characters a given `key` or `capo` may have at most (`"F#m"`, `"2"`).

### songleaf.importers.MAX_PASTE_CHARS *= 200000*

Pasted text longer than this is refused (a chord chart is a few KB).

### songleaf.importers.PASTE_PROVENANCE *= {'license': 'personal', 'source': 'paste'}*

Provenance recorded for every pasted song (`url` is added when known).

### songleaf.importers.detect_format(text, \*, importers=(Importer(name='ultimate-guitar', detect=<function <lambda>>, parse=<function \_parse_ultimate_guitar>), Importer(name='chordpro', detect=<function \_is_chordpro>, parse=<function parse_chordpro>), Importer(name='opensong', detect=<function <lambda>>, parse=<function \_parse_opensong>), Importer(name='chords-over-lyrics', detect=<function <lambda>>, parse=<function parse_chords_over_lyrics>)))

The name of the first importer that recognises *text*.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### songleaf.importers.import_song(text, \*, title='', artist='', url='', key='', capo='', format='', importers=(Importer(name='ultimate-guitar', detect=<function <lambda>>, parse=<function \_parse_ultimate_guitar>), Importer(name='chordpro', detect=<function \_is_chordpro>, parse=<function parse_chordpro>), Importer(name='opensong', detect=<function <lambda>>, parse=<function \_parse_opensong>), Importer(name='chords-over-lyrics', detect=<function <lambda>>, parse=<function parse_chords_over_lyrics>)))

Parse pasted *text* with the first importer that recognises it (or *format*).

`title`/`artist`/`key`/`capo` given here win over those in the text.
A `url` on ultimate-guitar.com is checked first (official and Pro pages are
refused, see [`songleaf.ultimate_guitar`](songleaf.ultimate_guitar.html.md#module-songleaf.ultimate_guitar)), keys the song `ug:<id>`
instead of `paste:<hash>`, and is noted as `provenance.site`.

* **Return type:**
  [`Imported`](#songleaf.importers.Imported)

### songleaf.importers.paste_key(text)

The store key of pasted *text*: `paste:<hash>` (the same text, the same key).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
