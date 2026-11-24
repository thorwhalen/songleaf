"""Measure songleaf's layouts and parser on a sample of the local Kaggle chords-and-lyrics corpus.

The evaluation behind songleaf#4, kept as a script so it can be rerun (songleaf#20, #42, #53).
It reads the corpus zip under songleaf's data root, renders every sampled song in every
layout, and records only ids and numbers: no song text leaves the machine, and nothing is
written inside the repo. Results go to ``<songleaf data root>/eval/``.

Measures:

- ``layouts``: the largest lyric font size at which each song fits one A4 page, per layout
  (:func:`songleaf.render.fit_font_size`), in the default font and, with ``--helvetica``, in
  the old Helvetica style too (songleaf#20). ``--score`` adds the ``score`` layouts, with one
  fixed reference snippet per song (songleaf#53).
- ``chordlines``: lines where at least 60% of the tokens are chords but the parser keeps the
  line as lyrics (songleaf#11, #42), as counts and token shapes only.

Usage (from a songleaf checkout)::

    python misc/eval/corpus_eval.py layouts --ids-from ~/.local/share/songleaf/eval/v1-2000-seed2.csv --helvetica --score
    python misc/eval/corpus_eval.py chordlines --ids-from ~/.local/share/songleaf/eval/v1-2000-seed2.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

#: The layouts of songleaf#4's table, in its order.
LAYOUTS = (
    "dense",
    "overlap",
    "inline",
    "packed",
    "shaded",
    "overlap+packed",
    "inline+packed",
    "two-column",
    "overlap+two-column",
    "inline+two-column",
    "packed+two-column",
    "inline+packed+two-column+shaded",
)
SCORE_LAYOUTS = ("score", "two-column+score")
#: One fixed two-bar phrase per song for the score layouts (songleaf#53): only its size matters.
REFERENCE_ABC = "X:1\nM:4/4\nL:1/8\nK:C\nCDEF GABc|c2B2 A2G2|"
HELVETICA = dict(lyric_font="Helvetica", chord_font="Helvetica-Bold", label_font="Helvetica-Bold", title_font="Helvetica-Bold")
CHORD_SHARE = 0.6


def _eval_dir() -> str:
    from songleaf.store import data_dir

    path = data_dir("eval")
    os.makedirs(path, exist_ok=True)
    return path


def _ids(path: str) -> list[str]:
    with open(os.path.expanduser(path)) as f:
        return list(dict.fromkeys(row["id"] for row in csv.DictReader(f)))


def _songs(ids):
    from songleaf.sources import KaggleChordsSource

    source = KaggleChordsSource()
    return [(i, source.get(i)) for i in ids]


def _fit_one(args):
    song_id, song, specs, helvetica, score = args
    from songleaf.render import DenseStyle, fit_font_size, layout_named

    rows = []
    styles = [("default", DenseStyle())] + ([("helvetica", DenseStyle(**HELVETICA))] if helvetica else [])
    scored = None
    if score:
        from songleaf.snippets import mark_segment

        try:
            scored = mark_segment(song, REFERENCE_ABC)
        except ValueError:  # no lyric line to put a snippet over: no score rows for this song
            pass
    for font, style in styles:
        for spec in specs + (SCORE_LAYOUTS if scored is not None else ()):
            target = scored if "score" in spec else song
            t0 = time.perf_counter()
            size = fit_font_size(target, layout=layout_named(spec, style=style))
            rows.append((song_id, font, spec, round(size, 2), round((time.perf_counter() - t0) * 1000, 1)))
    return rows


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def layouts(args):
    songs = _songs(_ids(args.ids_from))
    jobs = [(i, s, LAYOUTS, args.helvetica, args.score) for i, s in songs]
    with ProcessPoolExecutor(args.jobs) as pool:
        rows = [r for chunk in pool.map(_fit_one, jobs, chunksize=8) for r in chunk]
    out = os.path.join(_eval_dir(), args.out)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "font", "layout", "font_size", "ms"])
        w.writerows(rows)
    by = {}
    for song_id, font, spec, size, ms in rows:
        by.setdefault((font, spec), {})[song_id] = (size, ms)
    print(f"{len(songs)} songs; {out}")
    print("| font | layout | at min size (6 pt) | p10 | median | p90 | median vs dense | ms median |")
    print("|---|---|---|---|---|---|---|---|")
    for (font, spec), d in by.items():
        sizes = [v[0] for v in d.values()]
        dense = statistics.median(v[0] for k, v in by[(font, "dense")].items() if k in d)
        med = statistics.median(sizes)
        print(
            f"| {font} | `{spec}` | {sum(s <= 6.0 for s in sizes)} | {_pct(sizes, .1):.1f} | {med:.1f} | "
            f"{_pct(sizes, .9):.1f} | {100 * (med / dense - 1):+.1f}% | {statistics.median(v[1] for v in d.values()):.0f} |"
        )


def _shape(token: str) -> str:
    return re.sub(r"[a-z]+", "a", re.sub(r"[A-G]", "C", re.sub(r"\d+", "9", token)))


def chordlines(args):
    from songleaf.parse import _kind, is_chord_token
    from songleaf.sources import _KAGGLE_SITE_NOISE, KaggleChordsSource

    source = KaggleChordsSource()
    songs_hit, lines_hit, shapes = 0, 0, Counter()
    ids = _ids(args.ids_from)
    for song_id in ids:
        text = _KAGGLE_SITE_NOISE.sub("", source._text(source._row_of_id[song_id]))
        hit = 0
        for line in text.splitlines():
            tokens = line.split()
            if len(tokens) < 1 or _kind(line) != "lyric":
                continue
            chords = [t for t in tokens if is_chord_token(t)]
            if len(chords) / len(tokens) >= CHORD_SHARE:
                hit += 1
                shapes.update(_shape(t) for t in tokens if not is_chord_token(t))
        songs_hit += hit > 0
        lines_hit += hit
    print(f"{len(ids)} songs: {songs_hit} songs, {lines_hit} lines with >= {CHORD_SHARE:.0%} chord tokens kept as lyrics")
    print("blocking token shapes (C = a note letter, 9 = digits, a = lowercase run):", shapes.most_common(15))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("layouts")
    a.add_argument("--ids-from", required=True, help="a CSV with an `id` column (the #4 sample)")
    a.add_argument("--helvetica", action="store_true", help="also measure the old Helvetica style")
    a.add_argument("--score", action="store_true", help="also measure the score layouts")
    a.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a.add_argument("--out", default="layouts-remeasure.csv")
    a.set_defaults(func=layouts)
    c = sub.add_parser("chordlines")
    c.add_argument("--ids-from", required=True)
    c.set_defaults(func=chordlines)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
