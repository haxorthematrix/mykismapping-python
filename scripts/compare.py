#!/usr/bin/env python3
"""Compare Python port output against the Haskell reference binary.

Usage:
    python scripts/compare.py <input.kismet> <ESSID> [ESSID ...] [--min-points N]
                              [--haskell-bin <path>] [--res N]

Runs both `python -m kismapping` (from the checkout) and the Haskell
`kismapping` binary against the same input, then diffs coords.json and either
overlay.json (polygons mode) or overlay.png (image mode). Exit status 0 means
within tolerance.

The Haskell binary is expected to be on PATH unless --haskell-bin is given.
The script does both the polygon run and an image run when --res is set.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _run(label: str, cmd: list[str]) -> None:
    print(f"  $ {label}: {' '.join(map(str, cmd))}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        raise SystemExit(f"{label} failed (exit {res.returncode})")


def _bounds(d: Path) -> dict[str, float]:
    return json.loads((d / "coords.json").read_text())


def _polys(d: Path) -> list[dict]:
    return json.loads((d / "overlay.json").read_text())


def _diff_bounds(a: dict, b: dict, tol: float) -> bool:
    ok = True
    for k in ("west", "south", "east", "north"):
        delta = abs(a[k] - b[k])
        marker = " " if delta <= tol else "!"
        print(f"    {marker} {k}: hask={a[k]:.15f}  py={b[k]:.15f}  Δ={delta:.2e}")
        if delta > tol:
            ok = False
    return ok


def _diff_polygons(hask: list[dict], py: list[dict], tol: float) -> bool:
    print(f"    polygons: hask={len(hask)} py={len(py)}")
    if len(hask) != len(py):
        return False
    def fingerprint(poly):
        pts = tuple(sorted((round(p['lng'], 8), round(p['lat'], 8)) for p in poly['paths']))
        return pts
    hs = {fingerprint(p): p for p in hask}
    ps = {fingerprint(p): p for p in py}
    print(f"    matched fingerprints: {len(hs.keys() & ps.keys())} of {len(hs)}")
    return hs.keys() == ps.keys()


def _diff_image(hask: Path, py: Path) -> tuple[float, int]:
    a = np.asarray(Image.open(hask).convert("RGBA"))
    b = np.asarray(Image.open(py).convert("RGBA"))
    if a.shape != b.shape:
        raise SystemExit(f"image shape mismatch: hask={a.shape} py={b.shape}")
    d = np.abs(a.astype(int) - b.astype(int))
    return float(d.mean()), int(d.max())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", type=Path)
    p.add_argument("essids", nargs="+")
    p.add_argument("--min-points", type=int, default=4)
    p.add_argument("--res", type=int, default=None, help="If given, also do an image diff at this resolution.")
    p.add_argument("--haskell-bin", default="kismapping")
    p.add_argument("--tol", type=float, default=1e-12)
    args = p.parse_args()

    if not shutil.which(args.haskell_bin) and not Path(args.haskell_bin).exists():
        print(f"haskell binary not found: {args.haskell_bin}", file=sys.stderr)
        return 2

    essid_flags = [a for e in args.essids for a in ("-e", e)]
    common = [*essid_flags, "-i", str(args.input), "--min-points", str(args.min_points)]
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        hask = Path(tmp) / "hask"
        py = Path(tmp) / "py"
        hask.mkdir()
        py.mkdir()

        print("# polygon mode")
        _run("haskell", [args.haskell_bin, *common, "--polygons", "-o", str(hask)])
        _run("python ", [sys.executable, "-m", "kismapping", *common, "--polygons", "-o", str(py)])
        ok &= _diff_bounds(_bounds(hask), _bounds(py), args.tol)
        ok &= _diff_polygons(_polys(hask), _polys(py), args.tol)

        if args.res:
            for sub in (hask, py):
                shutil.rmtree(sub); sub.mkdir()
            print(f"# image mode @ {args.res}")
            _run("haskell", [args.haskell_bin, *common, "-r", str(args.res), "-o", str(hask)])
            _run("python ", [sys.executable, "-m", "kismapping", *common, "-r", str(args.res), "-o", str(py)])
            ok &= _diff_bounds(_bounds(hask), _bounds(py), args.tol)
            mean, mx = _diff_image(hask / "overlay.png", py / "overlay.png")
            print(f"    pixel diff: mean={mean:.3f}/255  max={mx}/255")
            if mx > 16:
                ok = False

    print()
    print("OK ✓" if ok else "FAIL ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
