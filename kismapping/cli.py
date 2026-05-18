"""Command-line entry point. Mirrors the Haskell binary's flag set."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cleanup import remove_invalid_data
from .heatpoints import essid_map_to_heatpoints
from .input.kismet_sqlite import read_kismet_sqlite
from .input.kismet_xml import munge_to_printable, read_kismet_xml
from .output_file import write_image, write_polygons
from .output_web import serve_image, serve_polygons
from .render_image import render_image
from .render_polygon import render_polygons


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kismapping",
        description=(
            "kismapping is a tool for generating and displaying visualizations of "
            "WiFi heatmap data overlayed on a map. Provide an ESSID, and a .kismet "
            "or .gpsxml file, and kismapping will generate a heatmap from all "
            "BSSIDs associated with the specified ESSID. By default, kismapping "
            "will generate a 2048x2048 overlay image, and serve it on port 8080."
        ),
    )
    p.add_argument(
        "-e", "--essid",
        action="append", required=True, metavar="ESSID",
        help="Specify ESSID to use for input data. Use multiple times to include multiple ESSIDs.",
    )
    p.add_argument(
        "-i", "--input",
        action="append", required=True, metavar="FILE", dest="input_files",
        help="Set input file. Use multiple times to include multiple inputs. .kismet or .gpsxml.",
    )

    out_kind = p.add_mutually_exclusive_group()
    out_kind.add_argument(
        "-r", "--resolution", type=int, default=2048, metavar="RES",
        help="Output an image of the set resolution. Default 2048.",
    )
    out_kind.add_argument(
        "--polygons", action="store_true",
        help="Output polygons, one per BSSID, instead of a raster image.",
    )

    sink = p.add_mutually_exclusive_group(required=True)
    sink.add_argument(
        "-o", "--output", metavar="DIRECTORY",
        help="Set output directory for file output.",
    )
    sink.add_argument(
        "-k", "--apikey", metavar="APIKEY",
        help="Launch a web server using the specified Google Maps API key.",
    )
    p.add_argument(
        "-p", "--port", type=int, default=8080, metavar="PORT",
        help="Specify the port of the web server. Default 8080.",
    )

    p.add_argument(
        "--min-points", type=int, default=4, metavar="N", dest="min_points",
        help=(
            "Discard any AP seen at fewer than this many distinct GPS positions. "
            "Lowering this below 4 surfaces sparsely-observed APs but disables "
            "meaningful outlier filtering for those APs. Default 4."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    sqlite_paths: list[Path] = []
    xml_paths: list[Path] = []
    for raw in args.input_files:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix == ".kismet":
            sqlite_paths.append(path)
        elif suffix == ".gpsxml":
            xml_paths.append(path)
        else:
            print(f"ERROR: unsupported input extension: {raw}", file=sys.stderr)
            return 2

    # SQLite stores the raw ESSID in the device JSON's `name` field; .netxml
    # stores the munged form (non-printable bytes escaped as `\nnn`). For an
    # ASCII ESSID these are the same string, so a single union of both forms
    # covers every lookup case.
    lookup_essids = list({*args.essid, *(munge_to_printable(e) for e in args.essid)})

    essid_map: dict = {}
    if sqlite_paths:
        sm = read_kismet_sqlite(sqlite_paths, args.essid)
        for essid, bssids in sm.items():
            essid_map.setdefault(essid, {}).update(bssids)
    if xml_paths:
        xm = read_kismet_xml(xml_paths, args.essid)
        for essid, bssids in xm.items():
            essid_map.setdefault(essid, {}).update(bssids)

    aps = essid_map_to_heatpoints(essid_map, lookup_essids)
    if not aps:
        print(
            f"ERROR: No BSSIDs found with given ESSIDs: {args.essid}",
            file=sys.stderr,
        )
        return 1

    print("Parsing GPS Points")
    aps = remove_invalid_data(args.min_points, aps)

    if args.apikey:
        if args.polygons:
            region, polys = render_polygons(aps)
            serve_polygons(args.apikey, args.port, region, polys)
        else:
            region, img = render_image(args.resolution, args.resolution, aps)
            serve_image(args.apikey, args.port, region, img)
        return 0

    out_dir = Path(args.output)
    if args.polygons:
        region, polys = render_polygons(aps)
        write_polygons(out_dir, region, polys)
    else:
        region, img = render_image(args.resolution, args.resolution, aps)
        write_image(out_dir, region, img)
    return 0


if __name__ == "__main__":
    sys.exit(main())
