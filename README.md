# mykismapping-python

Python port of [kismapping](https://github.com/haxorthematrix/kismapping) — a
WiFi heatmap generator that consumes [Kismet](https://www.kismetwireless.net/)
captures and produces a heatmap, either as image/JSON files or served on a
Google Maps web page.

This is a **work in progress port**. See
[specifications.md](specifications.md) for what's done, what's pending, and
the validation plan against the Haskell reference binary.

## Supported Kismet output

- `.kismet` — current SQLite-backed Kismet log database (KISMETDB schema
  versions 5 and up; legacy `db_version < 5` files have their integer lat/lon
  rescaled automatically).
- `.gpsxml` (paired with the corresponding `.netxml` in the same directory) —
  legacy XML format from older Kismet releases.

## Install

The fast path, from a checkout:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .

That installs a `kismapping` console script and pulls in numpy / scipy /
Pillow / Flask / lxml.

## Run

Same CLI surface as the Haskell binary. See `kismapping --help` for the full
list once installed.

    kismapping -e MyAP -i capture.kismet -o ./output

Web-server mode:

    kismapping -e MyAP -i capture.kismet -k <Google Maps API key>

See the upstream Haskell project's
[README](https://github.com/haxorthematrix/kismapping#run) for full operating
instructions; this port aims to match its behavior.

## Status

See [specifications.md](specifications.md) for the porting checklist and the
validation dataset.
