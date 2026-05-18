"""Signal propagation model.

Mirrors `Kismapping.Propagation` in the Haskell project. Treats signal as
free-space power loss: power = 1/distance², dB = 10 log10(power).

A `HeatPoint` is a (Euclidean position, dBm reading) pair. The module is
agnostic to coordinate system as long as positions live in the same metric
3-space (we use Euclidean lon/lat-on-sphere coordinates in meters).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class HeatPoint:
    location: np.ndarray  # 3D Euclidean position (meters)
    strength: float       # dBm


# --- dB <-> power <-> distance lenses (matching Haskell isos) ---

def db_to_power(db: float) -> float:
    return 10.0 ** (db / 10.0)


def power_to_db(p: float) -> float:
    return 10.0 * math.log10(p)


def power_to_distance(p: float) -> float:
    """Unitless 'power distance': distance such that power = 1/d²."""
    return math.sqrt(1.0 / p)


def distance_to_power(d: float) -> float:
    return 1.0 / (d * d)


def db_to_distance(db: float) -> float:
    return power_to_distance(db_to_power(db))


def distance_to_db(d: float) -> float:
    return power_to_db(distance_to_power(d))


# --- core propagation functions ---

def strength(center: np.ndarray, falloff_distance: float, point: np.ndarray) -> float:
    """Predicted dB at `point` assuming the AP is at `center` and the signal
    is -75 dB at `falloff_distance` meters."""
    d2 = float(np.sum((center - point) ** 2))
    if d2 == 0.0:
        # At the AP location; logarithmically infinite power. Return a large
        # finite value to keep callers happy.
        return float("inf")
    fd2 = falloff_distance * falloff_distance
    # -75 dB anchor, then scale power by (fd²/d²) and back to dB
    return -75.0 + 10.0 * math.log10(fd2 / d2)


def falloff_distance(
    falloff_db: float,
    a_loc: np.ndarray, a_db: float,
    b_loc: np.ndarray, b_db: float,
) -> float:
    """Project from two readings to the meters distance at which signal would
    drop to `falloff_db`. Mirrors Haskell `falloffDistance`."""
    dpa = db_to_distance(a_db)
    dpb = db_to_distance(b_db)
    dpc = db_to_distance(falloff_db)
    real_d = float(np.linalg.norm(b_loc - a_loc))
    if dpa == dpb:
        return 0.0
    dr = real_d / abs(dpb - dpa)
    return dpc * dr


def falloff_point(
    falloff_db: float, a: HeatPoint, b: HeatPoint
) -> HeatPoint:
    """Project `b` outward from `a` to the position at which the signal would
    be `falloff_db`. Used to build the rendered perimeter."""
    fd = falloff_distance(falloff_db, a.location, a.strength, b.location, b.strength)
    diff = b.location - a.location
    n = float(np.linalg.norm(diff))
    direction = diff / n if n > 0 else np.zeros(3)
    return HeatPoint(a.location + direction * fd, falloff_db)


def center_of(points: Sequence[HeatPoint]) -> HeatPoint:
    """Trilaterate an AP location as the dB-weighted centroid of its
    observations. Each observation contributes its position scaled by the
    power-distance derived from its dB reading; the sum is normalized by the
    total weight."""
    sum_p = np.zeros(3)
    sum_r = 0.0
    for hp in points:
        r = db_to_distance(hp.strength)
        sum_p = sum_p + hp.location * r
        sum_r += r
    if sum_r == 0.0:
        return HeatPoint(np.zeros(3), 0.0)
    return HeatPoint(sum_p / sum_r, 0.0)


def _rotation_angle(center: HeatPoint, p: HeatPoint) -> float:
    """Angle of `p` around `center` in lon/lat space. Used only as the sort
    key for the perimeter ring, so its exact value doesn't matter — what
    matters is that points order consistently around the center."""
    # Match Haskell exactly: atan2(d_lat, d_lon) on polar (lon, lat) coords.
    from .geometry import to_polar
    c_lon, c_lat, _ = to_polar(center.location)
    p_lon, p_lat, _ = to_polar(p.location)
    return math.atan2(p_lat - c_lat, p_lon - c_lon)


def perimeter(
    falloff_db: float, points: Sequence[HeatPoint]
) -> tuple[list[HeatPoint], HeatPoint]:
    """Return (ring, center) where `ring` is the falloff perimeter sorted by
    angle around `center`."""
    c = center_of(points)
    projected = [falloff_point(falloff_db, c, p) for p in points]
    projected.sort(key=lambda p: _rotation_angle(c, p))
    return projected, c
