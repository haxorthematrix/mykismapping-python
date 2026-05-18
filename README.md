# mykismapping-python

Python port of [kismapping](https://github.com/haxorthematrix/kismapping) — a
WiFi heatmap generator that consumes [Kismet](https://www.kismetwireless.net/)
captures and produces a heatmap, either as image/JSON files or served on a
Google Maps web page.

The Python port has been validated against the Haskell reference binary on
real captures: polygon vertices match to floating-point precision and PNG
output is pixel-identical modulo HSL→RGB rounding (max channel delta 1/255).
See [specifications.md](specifications.md) for the full validation log.

## Supported Kismet output

- `.kismet` — current SQLite-backed Kismet log database (KISMETDB schema
  versions 5 and up; legacy `db_version < 5` files have their integer lat/lon
  rescaled automatically).
- `.gpsxml` (paired with the corresponding `.netxml` in the same directory) —
  legacy XML format from older Kismet releases.

Mixed inputs in one run are fine — pass `-i` multiple times.

## Requirements

- **Python 3.10 or newer**. Developed against 3.14; the wheels for
  numpy / scipy / Pillow / lxml all support 3.10+.
- **A working C/C++ toolchain** if your platform doesn't have prebuilt
  wheels for one of the deps (numpy, scipy, Pillow, lxml). macOS users
  typically just need Xcode Command Line Tools (`xcode-select --install`).
  On Linux, the distro's `build-essential` / `gcc` is enough.
- About **300 MB free** for the virtualenv (numpy + scipy bring the bulk).
- No system Kismet install is needed — this tool only consumes Kismet's
  *output* files.

The runtime dependencies declared in `pyproject.toml`:

- `numpy` — vectorized math for the per-pixel render
- `scipy` — used by the cleanup pipeline
- `Pillow` — PNG encode
- `Flask` — web-server output mode
- `lxml` — streaming XML parser for `.gpsxml` / `.netxml`

## Install

Use a virtualenv. Modern macOS and most Linux distros mark the system
Python as "externally managed" (PEP 668) and will refuse a plain
`pip install` — a venv sidesteps that and keeps the project's deps off
your system Python.

    git clone https://github.com/haxorthematrix/mykismapping-python.git
    cd mykismapping-python
    python3 -m venv .venv
    source .venv/bin/activate          # use `.venv\Scripts\activate` on Windows
    pip install --upgrade pip
    pip install -e .

That installs a `kismapping` console script onto your PATH inside the
virtualenv. Confirm with:

    kismapping --help

To leave the virtualenv: `deactivate`. To use the script again later: re-run
`source .venv/bin/activate` first, or call `./.venv/bin/kismapping` directly.

If you'd rather not install, you can also run the module out of the checkout:

    .venv/bin/python -m kismapping --help

## Run

The CLI mirrors the Haskell binary. Required flags in every run:

- `-e ESSID` — repeat once per SSID you want on the map.
- `-i FILE` — repeat once per input file. The file extension picks the
  reader: `.kismet` (SQLite) or `.gpsxml` (XML).

Pick exactly one output mode:

- `-o DIRECTORY` — file mode. Writes `coords.json` (the bounds) plus
  `overlay.png` (image mode) or `overlay.json` (polygons mode).
- `-k APIKEY [-p PORT]` — web-server mode. Serves a Google Maps page at
  `http://127.0.0.1:<port>/` with the heatmap overlaid; default port 8080.
  Requires a [Google Maps JavaScript API key](https://developers.google.com/maps/documentation/javascript/get-api-key).

Optional:

- `-r RES` (default 2048) — image resolution; output PNG is RES×RES.
- `--polygons` — emit one polygon per BSSID instead of a raster image.
- `--min-points N` (default 4) — drop any AP seen at fewer than N distinct
  GPS positions. See the data-quality note in the upstream
  [README](https://github.com/haxorthematrix/kismapping#data-quality-and---min-points)
  before lowering this below 4.

### Examples

Render a heatmap PNG for a single ESSID and save it locally:

    kismapping -e MyAP -i capture.kismet -o ./output

Same input, polygons mode:

    kismapping -e MyAP -i capture.kismet --polygons -o ./output

Serve the map on `http://127.0.0.1:8080/`:

    kismapping -e MyAP -i capture.kismet -k YourGoogleMapsApiKey

Combine a current `.kismet` capture with a legacy `.gpsxml` run and lower
the per-AP-point threshold for sparse data:

    kismapping --min-points 2 \
      -e MyAP \
      -i new-capture.kismet \
      -i old-capture.gpsxml \
      -o ./output

## Validation

`scripts/compare.py` runs both this port and the Haskell binary against the
same input and reports the numerical/perceptual diff. Useful while
modifying anything in the pipeline:

    .venv/bin/python scripts/compare.py /path/to/capture.kismet ESSID1 ESSID2 \
        --res 512 \
        --haskell-bin /path/to/kismapping

## Status & open work

See [specifications.md](specifications.md) for what's done and what's
pending (unit-test coverage for the geometry/propagation math is the main
remaining gap).
