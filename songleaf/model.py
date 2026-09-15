"""The linked-artifact model: a song is lyrics text plus standoff annotations.

A :class:`Song` keeps its lyrics as one plain string and everything else as
:class:`Annotation` records anchored on character offsets into that string.
The text is never marked up, so any number of annotation layers can coexist
and be added later without touching the lyrics (the standoff design of
``lacing``, over characters instead of seconds).

Kinds used so far:

- ``"section"``: spans the section's lines, ``body={"label": "Chorus"}``. A
  label-only section (a bare ``[Chorus]`` marker meaning "repeat the chorus") is
  empty (``start == end``) and sits on an empty line of its own.
- ``"chord"``: a point (``start == end``) on the first character of the
  syllable the chord lands on, ``body={"symbol": "G/B", "timing": "at"}``.
  ``timing`` is ``"at"`` (the chord sounds with that syllable, the default) or
  ``"before"`` (it sounds ahead of it). Chords of a line with no lyrics (an
  intro, an instrumental bar) sit, in order, on an empty line of the text.
- ``"score"``: a link to a score snippet for ``[start, end)``,
  ``body={"source": ..., "id": ..., "url": ..., "format": ...}``.

>>> song = Song("Hello there", [chord(0, "C"), chord(6, "G")], meta={"title": "Hi"})
>>> [(a.start, a.body["symbol"]) for a in song.of_kind("chord")]
[(0, 'C'), (6, 'G')]
>>> Song.from_dict(song.to_dict()) == song
True
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

#: When a chord sounds, relative to the syllable it is anchored on.
CHORD_TIMINGS = ("at", "before")


@dataclass(frozen=True)
class Annotation:
    """One annotation over ``Song.text[start:end]``; a point when ``start == end``."""

    kind: str
    start: int
    end: int
    body: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if not 0 <= self.start <= self.end:
            raise ValueError(
                f"An annotation needs 0 <= start <= end, got [{self.start}, {self.end})"
            )

    def to_dict(self) -> dict:
        """The JSON-ready form."""
        return {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "body": dict(self.body),
        }


def chord(at: int, symbol: str, *, timing: str = "at") -> Annotation:
    """A chord landing on the syllable that starts at offset ``at``."""
    if timing not in CHORD_TIMINGS:
        raise ValueError(f"timing must be one of {CHORD_TIMINGS}, got {timing!r}")
    return Annotation("chord", at, at, {"symbol": symbol, "timing": timing})


def section(start: int, end: int, label: str) -> Annotation:
    """A section (verse, chorus, ...) spanning ``[start, end)``."""
    return Annotation("section", start, end, {"label": label})


def score_link(
    start: int, end: int, *, source: str, id: str, url: str = "", format: str = ""
) -> Annotation:
    """A link from ``[start, end)`` to a score snippet held by a source."""
    body = {"source": source, "id": id, "url": url, "format": format}
    return Annotation("score", start, end, body)


@dataclass(frozen=True)
class Line:
    """One line of a song's text: ``text == song.text[start:end]``."""

    start: int
    end: int
    text: str


@dataclass
class Song:
    """Lyrics text plus annotations, metadata and provenance.

    Args:
        text: The lyrics, lines separated by ``"\\n"``.
        annotations: Standoff annotations over ``text`` (kept sorted by start).
        meta: Descriptive fields: ``title``, ``artist``, ``capo``, ``key``, ...
        provenance: Where the song came from: ``source``, ``id``, ``url``, ``license``.
    """

    text: str
    annotations: list[Annotation] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        for annotation in self.annotations:
            if annotation.end > len(self.text):
                raise ValueError(
                    f"{annotation} ends past the text (length {len(self.text)})"
                )
        # A stable sort: annotations sharing an offset keep their given order.
        self.annotations = sorted(self.annotations, key=lambda a: a.start)

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def artist(self) -> str:
        return self.meta.get("artist", "")

    def of_kind(self, kind: str) -> list[Annotation]:
        """The annotations of one kind, in text order."""
        return [a for a in self.annotations if a.kind == kind]

    def lines(self) -> Iterator[Line]:
        """The lines of the text, with their offsets."""
        start = 0
        for text in self.text.split("\n"):
            yield Line(start, start + len(text), text)
            start += len(text) + 1

    def to_dict(self) -> dict:
        """The JSON-ready form (what the store persists)."""
        return {
            "text": self.text,
            "annotations": [a.to_dict() for a in self.annotations],
            "meta": dict(self.meta),
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> Song:
        """The inverse of :meth:`to_dict`."""
        return cls(
            text=data["text"],
            annotations=[Annotation(**a) for a in data.get("annotations", ())],
            meta=dict(data.get("meta", {})),
            provenance=dict(data.get("provenance", {})),
        )
