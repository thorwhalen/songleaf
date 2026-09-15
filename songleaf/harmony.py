"""What a chord does in its song's key, so that sheets can shade chords by function.

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

import re
from collections.abc import Iterable
from dataclasses import dataclass

_ROOT_RE = re.compile(r"[*.(\s]*([A-G])([#b]?)(.*)", re.DOTALL)
_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTALS = {"#": 1, "b": -1, "": 0}
_DIMINISHED_RE = re.compile(r"(?:dim|°|º|ø|m(?:in)?7?\(?b5)")
_POWER_RE = re.compile(r"5(?!\d)")

# Qualities each scale degree (semitones above the tonic) takes in a key.
_MAJOR_KEY = {
    0: {"major"},
    2: {"minor"},
    4: {"minor"},
    5: {"major"},
    7: {"major"},
    9: {"minor"},
    11: {"diminished", "minor"},
}
_MINOR_KEY = {
    0: {"minor"},
    2: {"diminished", "minor"},
    3: {"major"},
    5: {"minor"},
    7: {"minor", "major"},  # the harmonic-minor V is at home in a minor key
    8: {"major"},
    10: {"major"},
}
_TONIC_WEIGHT, _DIATONIC_WEIGHT, _ENDS_WEIGHT = 2.0, 1.0, 2.0


@dataclass(frozen=True)
class Key:
    """A key: its tonic as a pitch class (C = 0, C# = 1, ... B = 11), major or minor."""

    tonic: int
    minor: bool = False


def parse_chord(symbol: str) -> tuple[int, str] | None:
    """``(root pitch class, quality)``, or None for what is not a chord.

    The quality is ``"major"``, ``"minor"``, ``"diminished"``, or ``"open"`` (a
    suspended or power chord, which has no third). A bass note is ignored. What
    the chart parser would not read as a chord (``is_chord_token``) is not one.

    >>> parse_chord("F#m7"), parse_chord("Bbmaj7/D"), parse_chord("A7sus4"), parse_chord("Bm7b5")
    ((6, 'minor'), (10, 'major'), (9, 'open'), (11, 'diminished'))
    >>> parse_chord("C-7"), parse_chord("Bridge")
    ((0, 'minor'), None)
    """
    from songleaf.parse import is_chord_token

    symbol = symbol.strip()
    match = _ROOT_RE.fullmatch(symbol)
    if not (match and is_chord_token(symbol)):
        return None
    letter, accidental, rest = match.groups()
    root = (_PITCH_CLASSES[letter] + _ACCIDENTALS[accidental]) % 12
    if rest.startswith(("maj", "M")):
        quality = "major"
    elif _DIMINISHED_RE.match(rest):
        quality = "diminished"
    elif rest.startswith(("min", "m", "-")):  # "C-7" is jazz for Cm7
        quality = "minor"
    elif "sus" in rest or _POWER_RE.match(rest):
        quality = "open"
    else:
        quality = "major"
    return root, quality


def _function(parsed: tuple[int, str], key: Key) -> str:
    root, quality = parsed
    degree = (root - key.tonic) % 12
    qualities = (_MINOR_KEY if key.minor else _MAJOR_KEY).get(degree)
    if qualities is None or (quality != "open" and quality not in qualities):
        return "outside"
    return "tonic" if degree == 0 else "diatonic"


def chord_function(symbol: str, key: Key) -> str | None:
    """``"tonic"``, ``"diatonic"`` or ``"outside"`` in ``key``; None if ``symbol`` is not a chord."""
    parsed = parse_chord(symbol)
    return None if parsed is None else _function(parsed, key)


def estimate_key(symbols: Iterable[str]) -> Key | None:
    """The key that best explains a song's chords, in order; None if there are no chords.

    Each chord scores for a key when it belongs to it, and more when it is its
    tonic; a song that starts or ends on a key's tonic chord scores extra for
    that key. Ties go to the major key, and to the lower tonic.
    """
    chords = [parsed for parsed in map(parse_chord, symbols) if parsed]
    if not chords:
        return None
    weights = {"tonic": _TONIC_WEIGHT, "diatonic": _DIATONIC_WEIGHT, "outside": 0.0}
    best, best_score = None, float("-inf")
    for tonic in range(12):
        for minor in (False, True):
            key = Key(tonic, minor)
            score = sum(weights[_function(parsed, key)] for parsed in chords)
            score += _ENDS_WEIGHT * sum(
                _function(parsed, key) == "tonic" for parsed in (chords[0], chords[-1])
            )
            if score > best_score:
                best, best_score = key, score
    return best
