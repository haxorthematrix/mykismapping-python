"""Polygon renderer.

Output shape matches the Haskell `overlay.json`: a JSON list of polygon
records, one per BSSID, each with `paths` (a ring of {"lng","lat"} pairs) and
hard-coded stroke/fill styling.
"""

from __future__ import annotations

import numpy as np

from .geometry import Region, lonlat_from_euclidean
from .propagation import HeatPoint, perimeter


FALLOFF_DB = -75.0


def _poly_for_ap(points: list[HeatPoint]) -> tuple[list[dict], Region]:
    ring, _ = perimeter(FALLOFF_DB, points)
    paths = []
    region = Region.empty()
    for hp in ring:
        lon, lat = lonlat_from_euclidean(hp.location)
        paths.append({"lng": lon, "lat": lat})
        region = region.union(Region(lon, lat, lon, lat))
    return paths, region


def render_polygons(aps: list[list[HeatPoint]]) -> tuple[Region, list[dict]]:
    """Return (combined bounds, list[polygon dicts])."""
    polys = []
    region = Region.empty()
    for ap in aps:
        paths, ap_region = _poly_for_ap(ap)
        if not paths:
            continue
        region = region.union(ap_region)
        polys.append({
            "paths": paths,
            "strokeColor": "#FF0000",
            "strokeOpacity": 0.0,
            "strokeWeight": 0.0,
            "fillColor": "#FF0000",
            "fillOpacity": 0.5,
        })
    return region, polys
