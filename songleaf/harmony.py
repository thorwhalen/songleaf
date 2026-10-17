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


# --- transposition ----------------------------------------------------------------

_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
#: Keys whose signatures use flats (as tonic pitch classes): F Bb Eb Ab Db Gb, d g c f bb eb.
_FLAT_MAJOR_TONICS = frozenset({5, 10, 3, 8, 1, 6})
_FLAT_MINOR_TONICS = frozenset({2, 7, 0, 5, 10, 3})
#: The bass is only a final ``/note`` (``D/F#``); a slash inside the extension (``C6/9``,
#: ``Bm5-/7``) belongs to the chord's suffix.
_TRANSPOSABLE_RE = re.compile(
    r"(?P<lead>[*.(\s]*)(?P<root>[A-G][#b]?)(?P<rest>.*?)"
    r"(?:/(?P<bass>[A-G][#b]?)(?P<tail>[^/A-Za-z0-9#]*))?",
    re.DOTALL,
)


def _pitch_class(name: str) -> int:
    return (_PITCH_CLASSES[name[0]] + _ACCIDENTALS[name[1:]]) % 12


def uses_flats(key: Key | None) -> bool:
    """Whether chords in ``key`` are spelled with flats (Bb, Eb) rather than sharps.

    >>> uses_flats(Key(5)), uses_flats(Key(7)), uses_flats(Key(2, minor=True)), uses_flats(None)
    (True, False, True, False)
    """
    if key is None:
        return False
    return key.tonic in (_FLAT_MINOR_TONICS if key.minor else _FLAT_MAJOR_TONICS)


def key_name(key: Key, *, flats: bool | None = None) -> str:
    """``"G"``, ``"Bb"``, ``"F#m"``: the key spelled as its tonic chord.

    >>> key_name(Key(10)), key_name(Key(6, minor=True)), key_name(Key(6, minor=True), flats=True)
    ('Bb', 'F#m', 'Gbm')
    """
    flats = uses_flats(key) if flats is None else flats
    return (_FLAT_NAMES if flats else _SHARP_NAMES)[key.tonic] + (
        "m" if key.minor else ""
    )


def transpose_chord(symbol: str, semitones: int, *, flats: bool = False) -> str:
    """``symbol`` moved by ``semitones``: root and bass move, the rest is kept as written.

    ``flats`` spells moved notes with flats (choose it from the target key with
    :func:`uses_flats`). What is not a chord comes back unchanged.

    >>> transpose_chord("G", 2), transpose_chord("F#m7", 1), transpose_chord("C/E", 3, flats=True)
    ('A', 'Gm7', 'Eb/G')
    >>> transpose_chord("Bbmaj7", -1, flats=True), transpose_chord("N.C.", 4), transpose_chord("Am", 0)
    ('Amaj7', 'N.C.', 'Am')
    >>> [transpose_chord(c, 2) for c in ("D7/9", "Bm5-/7", "C6/9", "C(4/9)", "(Em7)", "Am7/G)")]
    ['E7/9', 'C#m5-/7', 'D6/9', 'D(4/9)', '(F#m7)', 'Bm7/A)']
    """
    if semitones % 12 == 0 or parse_chord(symbol) is None:
        return symbol
    match = _TRANSPOSABLE_RE.fullmatch(symbol)
    if match is None:
        return symbol
    names = _FLAT_NAMES if flats else _SHARP_NAMES

    def moved(name: str) -> str:
        return names[(_pitch_class(name) + semitones) % 12]

    parts = match.groupdict()
    out = parts["lead"] + moved(parts["root"]) + parts["rest"]
    if parts["bass"]:
        out += "/" + moved(parts["bass"]) + (parts["tail"] or "")
    return out


def transposition_table(
    symbols: Iterable[str], semitones: int, *, key: Key | None = None
) -> dict:
    """The chords of a song moved by ``semitones``, spelled for the new key.

    ``symbols`` are the song's chords in order (they give the key when ``key`` is
    not given). Returns ``{"semitones", "key", "chords"}``: the new key's name
    (``""`` when there are no chords) and ``{original: transposed}`` over the
    distinct chords, in order of first appearance.

    >>> transposition_table(["G", "D", "Em", "C", "G"], 3)
    {'semitones': 3, 'key': 'Bb', 'chords': {'G': 'Bb', 'D': 'F', 'Em': 'Gm', 'C': 'Eb'}}
    """
    symbols = list(symbols)
    key = key or estimate_key(symbols)
    target = Key((key.tonic + semitones) % 12, key.minor) if key else None
    flats = uses_flats(target)
    chords = {
        symbol: transpose_chord(symbol, semitones, flats=flats)
        for symbol in dict.fromkeys(symbols)
    }
    return {
        "semitones": semitones,
        "key": key_name(target) if target else "",
        "chords": chords,
    }


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
