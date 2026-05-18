"""Bridge between the per-(lon,lat) signal-reading map produced by the input
readers and the HeatPoint lists the propagation/render code expects.
"""

from __future__ import annotations

from .geometry import lonlat_to_euclidean
from .propagation import HeatPoint


def essid_map_to_heatpoints(essid_map, essids):
    """For each requested ESSID, gather the union of all its BSSIDs' readings
    and emit a list of (BSSID -> list[HeatPoint]) groups.

    Each (lon, lat) cell becomes a single HeatPoint whose dBm is the mean of
    all readings at that cell — mirroring the Haskell `toHeatpoints` helper.
    """
    out = []
    for essid in essids:
        bssids = essid_map.get(essid, {})
        for bssid, points in bssids.items():
            hp_list = []
            for (lon, lat), readings in points.items():
                if not readings:
                    continue
                mean_db = sum(readings) / len(readings)
                loc = lonlat_to_euclidean(lon, lat)
                hp_list.append(HeatPoint(loc, mean_db))
            if hp_list:
                out.append(hp_list)
    return out
