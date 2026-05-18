# mykismapping-python — porting specification

A Python port of [kismapping](https://github.com/haxorthematrix/kismapping)
(Haskell). This document captures what needs to be ported, the reference
behavior to match, and the validation plan.

## Source of truth

The Haskell binary in the sibling `kismapping/` repo is the reference. For
every Python feature we add, we validate by running both binaries against the
same input and comparing output (numerical for coords/polygons, perceptual
for the rendered PNG).

The validation dataset is `~/Desktop/wardrive.kismet`:
- Kismet 2022.02.R1, KISMETDB `db_version = 8`
- 726 devices, 526 Wi-Fi APs, 4203 usable IEEE802.11 packets with GPS
- bbox: 28.4090,-81.4725 .. 28.4470,-81.4550 (I-Drive Orlando)

Known reference outputs from the Haskell binary:

| Run | `min-points` | bounds (coords.json) |
|---|---|---|
| `-e @Hyatt_WiFi -e @Hyatt_Colleague` | 2 | `west=-81.47011019586954, south=28.42774483272233, east=-81.46986020382961, north=28.428441731666666` |
| `-e osf -e osfl -e osfc -e osf_guest` | 4 | `west=-81.47141960821013, south=28.444806558263647, east=-81.4705952883352, north=28.446140792304348` |

## Scope

Port the full kismapping pipeline. The Haskell binary supports:

1. Input parsing
   - `.kismet` (SQLite) — current Kismet log database, schema versions 5+
     (REAL lat/lon) and pre-5 (integer ×100000), filter `phyname='IEEE802.11'
     AND lat != 0 AND lon != 0`
   - `.gpsxml` (paired with `.netxml`) — legacy XML format
   - Both readers contribute to a single `EssidMap = {essid -> {bssid -> {(lon,lat) -> [dbm_readings]}}}`

2. Data cleanup (`removeInvalidData`)
   - Per-AP: drop signal readings outside 95% CI around the mean falloff-distance
   - Filter: AP must have `>= min-points` distinct GPS positions (default 4,
     CLI-configurable via `--min-points`)
   - Per-cluster: drop entire APs whose convex-hull radius is outside 95% CI
     across all APs

3. Propagation model (`Propagation.hs`)
   - dB↔power: `power = 10^(db/10)`
   - power↔distance (unitless): `distance = sqrt(1/power)`
   - `strength(c, falloffDist, p)`: signal at p assuming AP at c with -75 dB
     falloff at distance `falloffDist`
   - `falloffDistance(falloff_db, a, b)`: meters from a to where signal
     would be `falloff_db`, extrapolated from two readings
   - `centerOf(points)`: trilateration as weighted centroid where each
     point's weight is its dB-derived distance estimate
   - `perimeter(falloff_db, points)`: angle-sorted ring of points where each
     measurement is extrapolated outward to the falloff dB

4. Rendering
   - `renderImage(resolution)`: per-pixel min-distance lookup across a
     quad-tree-subdivided region (`imageDivisionFactor = 7`, so 128 blocks),
     gradient lookup table of size `gradientResolution = 8192`, HSL-derived
     colors clamped to `[-75 dB, -40 dB]`
   - `renderPolygons`: one polygon per BSSID = `perimeter(-75)`, plus
     hardcoded fill/stroke styling

5. Output
   - File mode: `coords.json` (bounds), `overlay.png` (image), `overlay.json`
     (polygons)
   - Web mode: HTTP server with Google Maps page using the bundled
     `map.html` template, `${{KEY}}` replaced with API key

6. CLI (argparse-compatible UX)
   - `-e ESSID` (repeatable, required)
   - `-i FILE` (repeatable, required; extension determines reader)
   - `-r RES` (default 2048) or `--polygons`
   - `-k APIKEY [-p PORT]` (web mode) or `-o DIRECTORY` (file mode); exactly one required
   - `--min-points N` (default 4)

## Validation plan

For each milestone we run the Python build against `~/Desktop/wardrive.kismet`
and diff against the Haskell binary's output. Acceptance criteria are
case-by-case but generally:

- **Coords (bounds)**: agreement to within 1e-6 degrees. Slight floating-point
  drift is acceptable; large drift indicates an algorithm divergence.
- **Polygons**: same number of polygons, same set of paths to within 1e-6
  degrees (modulo path order, which depends on iteration order over a hash
  map and is allowed to vary).
- **PNG**: visual inspection at low resolution. Pixel-exact match is not
  expected because of independent floating-point chains; structural match
  (same clusters in same places, similar hot-spot intensity) is the bar.

## Non-goals (initial port)

- Match the Haskell binary's wall-clock performance. The Haskell binary uses
  `repa` for parallel image generation; the Python port will use vectorized
  numpy, which should be fast enough at 1024–2048 but is not the goal.
- Match the on-disk byte layout of `overlay.png` (different encoders).
- Match dependency footprint. We will use numpy/scipy/Pillow/Flask, which
  pull in many transitive deps.

## Progress

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

### Foundation
- [x] `mykismapping-python/` directory on Desktop
- [x] `specifications.md` (this file)
- [x] `pyproject.toml` with declared deps
- [x] `.gitignore`
- [x] `README.md` (initial)
- [x] Empty `kismapping/` package + tests dir
- [x] Init git, create remote `haxorthematrix/mykismapping-python`, first push

### Input parsing
- [x] `kismapping/input/kismet_sqlite.py` reads .kismet, returns EssidMap-equivalent
- [x] Validation: device count, packet count, AP-name JSON parsing match
  Haskell readings on `wardrive.kismet` — 726 devices / 526 Wi-Fi APs /
  4203 usable packets reproduced
- [x] `kismapping/input/kismet_xml.py` reads .gpsxml + .netxml (lxml streaming
  parser; munge_to_printable for non-ASCII ESSID matching)
- [x] Validation: Ames 2013 ISU-CARDINAL run vs Haskell — 5/5 polygons match,
  coord diff max 1.14e-13 deg

### Geometry & propagation
- [x] `kismapping/geometry.py`: Polar↔Euclidean (matches `fromPolar`/`toPolar`)
- [x] `kismapping/propagation.py`: `dbToPower`/`dbToDistance`/`strength`/`falloffDistance`/`centerOf`/`perimeter`
- [ ] Unit tests asserting parity with the Haskell formulas on a handful of canned inputs

### Cleanup
- [x] `kismapping/cleanup.py`: per-point outlier (95% CI on falloff distance),
  `min-points` filter, per-AP outlier (95% CI on convex-hull radius)
- [x] Validation: post-cleanup AP counts match Haskell on `wardrive.kismet`
  for `osf`/`Hyatt`/`Spectrum` configurations at both default and
  `--min-points 2`

### Rendering
- [x] `kismapping/render_polygon.py`: list of polygons matching Haskell `overlay.json`
- [x] Validation: polygon vertices match Haskell to floating-point precision
  (max delta `1.78e-14` deg across `osf` + `Hyatt mp=2` + `Spectrum mp=2`
  runs on `wardrive.kismet`)
- [x] `kismapping/render_image.py`: PNG raster. Required matching the
  Haskell pixel coordinate formula (`west + i * dLon / w`, *not* numpy's
  inclusive linspace) so pixels sample at the same geographic points.
- [x] Validation: 512×512 PNGs on `osf`/`Spectrum mp=2`/`Hyatt mp=2 @ 256`:
  identical bounds, max channel diff 1/255 — just HSL→RGB rounding noise.

### Output
- [x] `kismapping/output_file.py`: write coords.json + overlay.png/json
- [x] `kismapping/output_web.py`: Flask server with templated map.html.
  Endpoints `/`, `/coords`, `/config`, `/overlay.png` (image mode) or
  `/overlay.json` (polygon mode); ${{KEY}} substituted in the bundled HTML.
- [x] Bundle the same `map.html` template (copied verbatim from the Haskell
  project)

### CLI
- [x] `kismapping/cli.py`: argparse mirroring the Haskell flag set
- [x] `kismapping/__main__.py` so `python -m kismapping ...` works
- [x] Console script entry point so `kismapping ...` works after `pip install`

### Verification harness
- [x] `scripts/compare.py`: run both binaries on a given input, diff
  coords/polygons, perceptual-diff the PNGs
- [x] Final acceptance: `osf` (default mp), `Spectrum mp=2`, `@Hyatt mp=2`
  all pass — polygons match at FP precision, PNGs match within 1/255 per
  channel (HSL rounding only)
