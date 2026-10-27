"""What a chord does in its song's key, so that sheets can shade chords by function.

The chord-symbol logic lives in :mod:`chordsym`; this module re-exports it (the
older import path) and adds :func:`transpose` for a whole :class:`Song`.

The key is estimated from the chords alone (a key given in a chart often names
the sounding key while the chords are written for a capo), and each chord is
then the ``"tonic"``, ``"diatonic"`` (another chord of the key), or ``"outside"``
the key (borrowed, secondary dominant, chromatic).

>>> key = estimate_key(["G", "D", "Em", "C", "G", "D", "G"])
>>> key
Key(tonic=7, minor=False)
>>> [chord_function(symbol, key) for symbol in ["G", "Em", "C", "Bb", "N.C."]]
['tonic', 'diatonic', 'diatonic', 'outside', None]
>>> estimate_key(["Am", "Dm", "E7", "Am"])
Key(tonic=9, minor=True)
"""

from __future__ import annotations

from chordsym import (  # noqa: F401  (re-exported)
    Key,
    chord_function,
    estimate_key,
    key_name,
    parse_chord,
    transpose_chord,
    transposition_table,
    uses_flats,
)


def transpose(song, semitones: int):
    """A copy of ``song`` with every chord moved by ``semitones``, spelled for the new key."""
    from dataclasses import replace

    if semitones % 12 == 0:
        return song
    chords = song.of_kind("chord")
    table = transposition_table([a.body["symbol"] for a in chords], semitones)["chords"]
    annotations = [
        replace(a, body={**a.body, "symbol": table[a.body["symbol"]]})
        if a.kind == "chord"
        else a
        for a in song.annotations
    ]
    return replace(
        song, annotations=annotations, meta={**song.meta, "transposed": semitones}
    )
