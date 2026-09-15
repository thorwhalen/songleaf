# songleaf.harmony

What a chord does in its song’s key, so that sheets can shade chords by function.

The key is estimated from the chords alone (a key given in a chart often names
the sounding key while the chords are written for a capo), and each chord is
then the `"tonic"`, `"diatonic"` (another chord of the key), or `"outside"`
the key (borrowed, secondary dominant, chromatic).

```pycon
>>> key = estimate_key(["G", "D", "Em", "C", "G", "D", "G"])
>>> key
Key(tonic=7, minor=False)
>>> [chord_function(symbol, key) for symbol in ["G", "Em", "C", "Bb", "N.C."]]
['tonic', 'diatonic', 'diatonic', 'outside', None]
>>> estimate_key(["Am", "Dm", "E7", "Am"])
Key(tonic=9, minor=True)
```

### Functions

| [`chord_function`](#songleaf.harmony.chord_function)(symbol, key)   | `"tonic"`, `"diatonic"` or `"outside"` in `key`; None if `symbol` is not a chord.   |
|--------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`estimate_key`](#songleaf.harmony.estimate_key)(symbols)         | The key that best explains a song's chords, in order; None if there are no chords.  |
| [`parse_chord`](#songleaf.harmony.parse_chord)(symbol)           | `(root pitch class, quality)`, or None for what is not a chord.                     |

### Classes

| [`Key`](#songleaf.harmony.Key)(tonic[, minor])   | A key: its tonic as a pitch class (C = 0, C# = 1, .   |
|------------------------------------------------------------------------|-------------------------------------------------------|

### *class* songleaf.harmony.Key(tonic, minor=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A key: its tonic as a pitch class (C = 0, C# = 1, … B = 11), major or minor.

### songleaf.harmony.chord_function(symbol, key)

`"tonic"`, `"diatonic"` or `"outside"` in `key`; None if `symbol` is not a chord.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.harmony.estimate_key(symbols)

The key that best explains a song’s chords, in order; None if there are no chords.

Each chord scores for a key when it belongs to it, and more when it is its
tonic; a song that starts or ends on a key’s tonic chord scores extra for
that key. Ties go to the major key, and to the lower tonic.

* **Return type:**
  [`Key`](#songleaf.harmony.Key) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### songleaf.harmony.parse_chord(symbol)

`(root pitch class, quality)`, or None for what is not a chord.

The quality is `"major"`, `"minor"`, `"diminished"`, or `"open"` (a
suspended or power chord, which has no third). A bass note is ignored. What
the chart parser would not read as a chord (`is_chord_token`) is not one.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> parse_chord("F#m7"), parse_chord("Bbmaj7/D"), parse_chord("A7sus4"), parse_chord("Bm7b5")
((6, 'minor'), (10, 'major'), (9, 'open'), (11, 'diminished'))
>>> parse_chord("C-7"), parse_chord("Bridge")
((0, 'minor'), None)
```
