"""Outlier removal and min-points filtering.

Mirrors `Kismapping.DataCleanup`:

1. `removeOutlierPoints` — for each AP, drop readings whose extrapolated
   falloff distance is outside 95% CI (z=1.96) around the mean.
2. `>= min_points` — drop APs with fewer than `min_points` distinct GPS
   observations. The Haskell default is 4 (CLI `--min-points`).
3. `removeOutlierAPs` — drop entire APs whose perimeter radius is outside the
   95% CI of all APs' radii.

The 95% CI in the Haskell code is computed against the *standard error of
the mean*, i.e. `stddev / sqrt(n)`, so it tightens as you get more samples.
This is unusual — it's not a Z-test against the distribution; it's a Z-test
against the sampling distribution of the mean — but we reproduce it exactly
to match outputs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .propagation import HeatPoint, falloff_distance, perimeter, center_of


Z95 = 1.96


def _mean_and_stderr(values: Sequence[float]) -> tuple[float, float]:
    """Sample mean and standard error of the mean. Returns (mean, 0) for n<=1
    to avoid divide-by-zero; the caller's filter then degenerates to "keep
    everything matching the mean exactly," which preserves these samples."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    if n <= 1:
        return mean, 0.0
    # Unbiased sample variance (matches Haskell `meanVarianceUnb`).
    variance = float(((arr - mean) ** 2).sum() / (n - 1))
    stddev = math.sqrt(variance)
    stderr = stddev / math.sqrt(n)
    return mean, stderr


def _remove_outliers_by(
    z: float,
    key,
    items: list,
) -> list:
    """Keep items where |key(x) - mean| <= z * stderr. Matches the Haskell
    `removeOutliersBy`."""
    values = [key(x) for x in items]
    mean, stderr = _mean_and_stderr(values)
    keep = []
    for x, v in zip(items, values):
        if abs(v - mean) <= stderr * z:
            keep.append(x)
    return keep


def remove_outlier_points(points: list[HeatPoint]) -> list[HeatPoint]:
    """Drop signal readings whose extrapolated falloff distance from the
    AP's centroid is outside the 95% CI around the mean."""
    if not points:
        return []
    c = center_of(points)
    # falloff distance from c to each measurement, projected to -75 dB
    def fd_for(p: HeatPoint) -> float:
        return falloff_distance(-75.0, c.location, 0.0, p.location, p.strength)
    return _remove_outliers_by(Z95, fd_for, list(points))


def _ap_radius(points: Sequence[HeatPoint]) -> float:
    """Maximum distance from AP center to any point on its perimeter."""
    ring, c = perimeter(-75.0, points)
    if not ring:
        return 0.0
    return max(float(np.linalg.norm(p.location - c.location)) for p in ring)


def remove_outlier_aps(
    aps: list[list[HeatPoint]],
) -> list[list[HeatPoint]]:
    """Drop entire APs whose perimeter radius is outside the 95% CI."""
    if not aps:
        return []
    return _remove_outliers_by(Z95, _ap_radius, list(aps))


def remove_invalid_data(
    min_points: int,
    aps: list[list[HeatPoint]],
) -> list[list[HeatPoint]]:
    """Full cleanup pipeline equivalent to Haskell `removeInvalidData`."""
    cleaned = [remove_outlier_points(ap) for ap in aps]
    enough = [ap for ap in cleaned if len(ap) >= min_points]
    return remove_outlier_aps(enough)
