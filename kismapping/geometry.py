"""Polar↔Euclidean conversions on a spherical earth.

Mirrors `Kismapping.Types` in the Haskell project: lon/lat in degrees mapped
to a 3D unit vector scaled by (earth radius + altitude). Latitudes use the
same `[-180, 180]` range bound the Haskell version enforces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EARTH_RADIUS = 6371000.0  # meters; matches Haskell `earthRadius`


@dataclass(frozen=True)
class Region:
    west: float
    south: float
    east: float
    north: float

    def union(self, other: "Region") -> "Region":
        return Region(
            min(self.west, other.west),
            min(self.south, other.south),
            max(self.east, other.east),
            max(self.north, other.north),
        )

    @staticmethod
    def empty() -> "Region":
        # Same negative sentinel the Haskell binary uses to mean "no data";
        # union with anything real yields the real region.
        return Region(180.0, 90.0, -180.0, -90.0)


def from_polar(lon_deg: float, lat_deg: float, alt: float = 0.0) -> np.ndarray:
    """Polar (lon, lat in degrees, alt in meters) -> Euclidean 3D."""
    if lat_deg < -180 or lat_deg > 180:
        raise ValueError(
            f"Kismapping.Types.fromPolar: latitude must be within [-180, 180], was {lat_deg}"
        )
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    r = math.cos(lat)
    x = r * math.cos(lon)
    y = math.sin(lat)
    z = r * math.sin(lon)
    return np.array([x, y, z]) * (alt + EARTH_RADIUS)


def to_polar(p: np.ndarray) -> tuple[float, float, float]:
    """Euclidean 3D -> (lon, lat, alt)."""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    norm = math.sqrt(x * x + y * y + z * z)
    alt = norm - EARTH_RADIUS
    lat = math.degrees(math.asin(y / norm))
    lon = math.degrees(math.atan2(z, x))
    return lon, lat, alt


def lonlat_from_euclidean(p: np.ndarray) -> tuple[float, float]:
    lon, lat, _ = to_polar(p)
    return lon, lat


def lonlat_to_euclidean(lon: float, lat: float) -> np.ndarray:
    return from_polar(lon, lat, 0.0)


def euclidean_bounds(center: np.ndarray, falloff: float) -> Region:
    """Bounding box (in lon/lat) of an AABB of half-width `falloff` meters
    around `center` in Euclidean space. Matches the Haskell
    `euclideanBounds` helper used to frame an AP's heatmap region."""
    region = Region.empty()
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    for dx in (-falloff, falloff):
        for dy in (-falloff, falloff):
            for dz in (-falloff, falloff):
                lon, lat = lonlat_from_euclidean(
                    np.array([cx + dx, cy + dy, cz + dz])
                )
                region = region.union(Region(lon, lat, lon, lat))
    return region
