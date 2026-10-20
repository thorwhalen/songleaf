"""Export a song as ChordPro or as plain text (chords over lyrics), transposition applied.

ChordPro is the fleet's text interchange: Songbook Pro, OnSong and the ChordPro app read it.
:func:`to_chordpro` writes what :func:`songleaf.chordpro.parse_chordpro` reads, so a song
survives the round trip (text, chords, sections, ``title``/``artist``/``key``/``capo``/``tempo``).
A chord that sounds ahead of its syllable (``timing="before"``) has no ChordPro spelling; the
song carries it in the namespaced directive ``{x_songleaf_before: ...}``, which other apps ignore.

:func:`to_text` is the monospaced form: each line of lyrics with its chords on the line above,
a ``[Label]`` line at each section. It is for reading and pasting; it does not carry timing.

>>> from songleaf.model import Song, chord, section
>>> song = Song("Paper boats drift", [chord(6, "G"), chord(12, "D"), section(0, 17, "Chorus")],
...             meta={"title": "Paper Boats"})
>>> print(to_chordpro(song))
{title: Paper Boats}
{start_of_chorus: Chorus}
Paper [G]boats [D]drift
{end_of_chorus}
>>> print(to_text(song))
Paper Boats
<BLANKLINE>
[Chorus]
      G     D
Paper boats drift
"""

from __future__ import annotations

from songleaf.chordpro import BEFORE_DIRECTIVE
from songleaf.harmony import transpose as _transposed

__all__ = ["to_chordpro", "to_text", "FORMATS"]

#: ChordPro's directive for each metadata field, in the order they are written.
_META_DIRECTIVES = ("title", "artist", "key", "capo", "tempo")
#: Chord symbols are kept this far apart on a chords-over-lyrics line.
_CHORD_GAP = 1


def _environment(label: str) -> tuple[str, str]:
    """``(start, end)`` directive names for a section label."""
    lowered = label.lower()
    if lowered.startswith("chorus"):
        return "start_of_chorus", "end_of_chorus"
    if lowered.startswith("bridge"):
        return "start_of_bridge", "end_of_bridge"
    return "start_of_verse", "end_of_verse"


def _lines_with_chords(song):
    """``(start, end, text, [(offset in line, symbol, timing)])`` for each line of the song."""
    chords = song.of_kind("chord")
    for line in song.lines():
        own = [
            (a.start - line.start, a.body["symbol"], a.body.get("timing", "at"))
            for a in chords
            if line.start <= a.start <= line.end
        ]
        yield line, own


def _sections(song):
    """``(label, start, end, marker)`` in text order."""
    return [
        (a.body.get("label", ""), a.start, a.end, bool(a.body.get("marker")))
        for a in song.of_kind("section")
    ]


def to_chordpro(song, *, transpose: int = 0) -> str:
    """The song as ChordPro text, every chord moved by ``transpose`` semitones.

    Metadata become directives, sections ``start_of_*``/``end_of_*`` environments carrying
    their label, chords go inline in brackets at the syllable they land on.
    """
    if transpose:
        song = _transposed(song, transpose)
    out: list[str] = []
    for name in _META_DIRECTIVES:
        if song.meta.get(name) not in (None, ""):
            out.append(f"{{{name}: {song.meta[name]}}}")
    sections = sorted(_sections(song), key=lambda s: (s[1], not s[3]))
    opened: list[
        tuple[int, str]
    ] = []  # (end offset, end directive) of the open section
    ordinal = 0
    before: list[int] = []
    pending = iter(sections)
    upcoming = next(pending, None)
    for line, own in _lines_with_chords(song):
        while opened and line.start > opened[-1][0]:
            out.append("{" + opened.pop()[1] + "}")
        while upcoming and upcoming[1] == line.start and (upcoming[3] or not opened):
            label, _, end, marker = upcoming
            start_name, end_name = _environment(label)
            out.append(f"{{{start_name}: {label}}}")
            if marker:
                out.append("{" + end_name + "}")
            else:
                opened.append((end, end_name))
            upcoming = next(pending, None)
            if marker:
                break
        if (
            any(s[3] and s[1] == line.start for s in sections)
            and not line.text
            and not own
        ):
            continue  # the empty line a label-only section sits on
        if not line.text:
            out.append(" ".join(f"[{symbol}]" for _, symbol, _ in own))
        else:
            text = line.text
            for offset, symbol, _ in sorted(own, key=lambda c: -c[0]):
                text = text[:offset] + f"[{symbol}]" + text[offset:]
            out.append(text)
        for _, _, timing in own:
            if timing == "before":
                before.append(ordinal)
            ordinal += 1
    out.extend("{" + end + "}" for _, end in reversed(opened))
    if before:
        out.append(f"{{{BEFORE_DIRECTIVE}: {', '.join(map(str, before))}}}")
    return "\n".join(out) + "\n"


def _chord_row(own, text: str) -> str:
    """Chord symbols at their columns, pushed right so none touches the one before."""
    row = ""
    for offset, symbol, _ in sorted(own):
        column = max(offset, len(row) + _CHORD_GAP if row else 0)
        row = row.ljust(column) + symbol
    return row


def to_text(song, *, transpose: int = 0) -> str:
    """The song as plain text: chords above their syllables, ``[Label]`` at each section."""
    if transpose:
        song = _transposed(song, transpose)
    out: list[str] = []
    heading = " - ".join(filter(None, (song.title, song.artist)))
    if heading:
        out += [heading, ""]
    starts = {}
    for label, start, _, marker in _sections(song):
        starts.setdefault(start, []).append((label, marker))
    for line, own in _lines_with_chords(song):
        labels = starts.get(line.start, [])
        out.extend(f"[{label}]" for label, _ in labels)
        if any(marker for _, marker in labels) and not line.text and not own:
            continue
        if not line.text:
            out.append("  ".join(symbol for _, symbol, _ in own))
            continue
        if own:
            out.append(_chord_row(own, line.text))
        out.append(line.text)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


#: Export formats: name -> (function, file extension, media type).
FORMATS = {
    "chordpro": (to_chordpro, "cho", "text/plain; charset=utf-8"),
    "text": (to_text, "txt", "text/plain; charset=utf-8"),
}
