Seams: (1) `sources=` = the Kaggle chords-and-lyrics corpus via `sung` · (2) `store=` = JSON files under `~/.local/share/songleaf/songs/` · (3) `renderer=` = the dense one-page A4 PDF.
Surface built for v1: CLI (`python -m songleaf`, `cw` over `songleaf.tools`). Asked, not built: MCP, shipped skill, HTTP, frontend.
Rationale and which defaults are provisional: the "v1 architecture: seams and surfaces" Discussion.

# songleaf — dev map

## Seam table (decided before the first commit)

| # | Seam | v1 default (no new dependency) | Replacement you can point at |
|---|---|---|---|
| 1 | where songs are found: `sources=` on `search` / `sheet` | `KaggleChordsSource`: the Kaggle *chords-and-lyrics* corpus (~135K songs) read through `sung` from its local zip, fuzzy title/artist/lyrics match | `scoreseek.search` sources (`KaggleChordsSource`, `ChordonomiconSource`, thesession, …); the sources surveyed in songleaf#3 |
| 2 | where songs persist: `store=` | a `MutableMapping[str, Song]` of JSON files under `~/.local/share/songleaf/songs/` (`SONGLEAF_DATA_DIR` overrides the root), through `dol` | a `dict` (tests); `s3dol`; a `lacing` store once chords get audio timing |
| 3 | how a song becomes a sheet: `renderer=` on `sheet` | `render_dense_a4`: one A4 page, lyric font size maximised to fit, lines packed within a section, chords overlapping the top of the lyric line in a lighter shade (`reportlab`) | score snippets from `scoreseek`, chord diagrams, a TTF font (songleaf#9); audio/video renderers on the av side (`reelee`, `muvid`) |

Inside seam 3 (songleaf#4): `render_sheet(song, output, layout=...)` draws any `SheetLayout`. A layout composes two strategies plus options: `chords=` (a `ChordPlacement`: `"over"` = `OverChords`, `"inline"` = `InlineChords`), `packing=` (a packer from `songleaf/packing.py`: `"greedy"`, `"structured"`), `columns=`, `shading=` (colours from `songleaf/harmony.py`), `style=`. `layout_named("inline+two-column")` builds one from `LAYOUT_OPTIONS`; the CLI's `--layout` is that spec; `make_renderer(spec)` is what `sheet` passes to seam 3. A new layout is a new option in `LAYOUT_OPTIONS`, or a new strategy in `CHORD_PLACEMENTS` / `PACKERS`, not a new renderer function.

```
Surface for v1: CLI only (MCP/skill/HTTP/frontend: questions answered, not built)
NOT seams: fuzzy scorer (rapidfuzz WRatio), chords-over-lyrics parsing rules, style knobs (colours, chord scale, margins, page size: keyword args), store key encoding, CLI output format, rhyme/couplet break costs and the key estimate (keyword args)
```

Layout evaluation (local only, stats only): render every layout over the same random 2,000 corpus songs and compare the fitted font sizes; numbers are on songleaf#4. Keep real renders and CSVs under `~/.local/share/songleaf/`.

One-command test (the definition of v1; needs the corpus zip on disk, so it is local-only):

```bash
python -m songleaf sheet "10000 hours justin bieber"   # -> a one-page A4 PDF under ~/.local/share/songleaf/sheets/
```

`tests/test_smoke.py` runs the same path in CI with a synthetic in-memory source.

## Rules for working in this repo

- **No song text from any real source in the repo**: not in tests, fixtures, docs, issues or commit messages. The corpus is scraped. Tests use synthesized lyrics only.
- **No generated sheets in the repo.** PDFs go to the data root (`~/.local/share/songleaf/sheets/`) or a scratch dir.
- `songleaf/tools.py` is the SSOT for surfaces: flat, serialisable arguments in, JSON-ready dicts out. Dependency-injection parameters (`sources=`, `store=`, `renderer=`) live in the core modules and are hidden from the CLI.
- Importing `songleaf` must not import `sung`, `pandas`, `reportlab` or `cw`; they load when used.
- The linked-artifact model is a plain standoff model (`songleaf.model`), not a `lacing` store; see the Discussion for why and for the adapter plan.
