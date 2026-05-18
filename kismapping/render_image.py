"""PNG raster renderer.

Mirrors `Kismapping.Render.Image`. For each AP we have:
    center  c     -- Euclidean
    falloff fd    -- mean distance from c to perimeter at -75 dB

The pixel at Euclidean position x picks the gradient index
    idx = floor( |x - c|² / fd² * (gradient_size - 1) )
across all APs and uses the *minimum* index — i.e. the AP with the strongest
predicted signal at that pixel. The gradient is a hand-rolled HSL ramp from
-40 dB (strongest, clamped) to -75 dB (weakest) with a soft alpha falloff
below -75 dB.

The Haskell code uses a 128×128 block subdivision to avoid evaluating distant
APs for every pixel — that's a pure optimization, since the per-AP index
strictly exceeds the default for out-of-range pixels, so `min` ignores them
anyway. We do the simpler all-APs vectorized min here; for the AP counts
this project handles (tens, maybe low hundreds), numpy is fast enough.
"""

from __future__ import annotations

import colorsys
import math

import numpy as np
from PIL import Image

from .geometry import EARTH_RADIUS, Region, euclidean_bounds
from .propagation import HeatPoint, perimeter


GRADIENT_RESOLUTION = 8192
MIN_SIG_DB = -75.0
MAX_SIG_DB = -40.0
FALLOFF_DB = -75.0


def _wrap_hue(h: float) -> float:
    """Match the Haskell `wrap`: add 360 until non-negative. The original
    only handles negative inputs; we leave positive values alone."""
    while h < 0:
        h += 360.0
    return h


def _color(db: float) -> tuple[int, int, int, int]:
    constrained = max(MIN_SIG_DB, min(MAX_SIG_DB, db))
    norm_str = 1.0 + (MAX_SIG_DB - constrained) / (MIN_SIG_DB - MAX_SIG_DB)
    if norm_str > 0.05:
        hue = -14.0 + ((norm_str - 0.05) / 0.9) * (54.0 - (-14.0))
    else:
        hue = -120.0 + (norm_str / 0.05) * (-14.0 - (-120.0))
    hue = _wrap_hue(hue)
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.7, 1.0)
    if norm_str <= 0.05:
        a = 0.6 * math.sin(norm_str / 0.05 * math.pi / 2.0)
    else:
        a = 0.6
    return (
        int(math.floor(r * 255)),
        int(math.floor(g * 255)),
        int(math.floor(b * 255)),
        int(math.floor(a * 255)),
    )


def _build_gradient() -> np.ndarray:
    res = GRADIENT_RESOLUTION
    arr = np.zeros((res, 4), dtype=np.uint8)
    for i in range(res):
        if i == 0:
            db = float("inf")
        else:
            norm_d2 = i / (res - 1)
            db = -75.0 + 10.0 * math.log10(1.0 / norm_d2)
        arr[i] = _color(db)
    return arr


def _heatmap_params(ap: list[HeatPoint]) -> tuple[np.ndarray, float, Region]:
    """Return (center, falloff_distance, lon/lat region) for one AP."""
    ring, c = perimeter(FALLOFF_DB, ap)
    if not ring:
        return c.location, 0.0, Region.empty()
    distances = [float(np.linalg.norm(p.location - c.location)) for p in ring]
    falloff = sum(distances) / len(distances)
    region = euclidean_bounds(c.location, falloff)
    return c.location, falloff, region


def _lonlat_grid_to_euclidean(
    lons: np.ndarray, lats: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized lon/lat (degrees) -> Euclidean meters on a sphere."""
    lon_r = np.radians(lons)
    lat_r = np.radians(lats)
    r = np.cos(lat_r)
    x = r * np.cos(lon_r) * EARTH_RADIUS
    y = np.sin(lat_r) * EARTH_RADIUS
    z = r * np.sin(lon_r) * EARTH_RADIUS
    return x, y, z


def render_image(width: int, height: int, aps: list[list[HeatPoint]]) -> tuple[Region, Image.Image]:
    """Return (combined bounds, RGBA PIL Image)."""
    if not aps:
        return Region.empty(), Image.new("RGBA", (width, height), (0, 0, 0, 0))

    params = [_heatmap_params(ap) for ap in aps]
    region = Region.empty()
    for _, _, r in params:
        region = region.union(r)

    # y=0 is the top of the image, mapped to the north edge of the region;
    # y=height-1 maps to the south edge (matching the Haskell `flipArray`).
    xs = np.linspace(region.west, region.east, width)
    ys = np.linspace(region.north, region.south, height)
    lon_grid, lat_grid = np.meshgrid(xs, ys)
    px, py, pz = _lonlat_grid_to_euclidean(lon_grid, lat_grid)

    max_idx = GRADIENT_RESOLUTION - 1
    indices = np.full((height, width), max_idx, dtype=np.int32)
    for center, falloff, _ in params:
        if falloff <= 0:
            continue
        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
        d2 = (px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2
        # floor(qd/fd² * (res-1)), clamped to [0, max_idx]
        scaled = d2 / (falloff * falloff) * max_idx
        ap_idx = np.clip(np.floor(scaled), 0, max_idx).astype(np.int32)
        np.minimum(indices, ap_idx, out=indices)

    gradient = _build_gradient()
    rgba = gradient[indices]  # shape (h, w, 4)
    return region, Image.fromarray(rgba, "RGBA")
