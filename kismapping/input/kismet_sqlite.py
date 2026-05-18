"""Read Kismet `.kismet` SQLite log databases.

Schema reference: https://www.kismetwireless.net/docs/dev/kismetdb/
The current KISMETDB layout (db_version >= 5) stores per-packet lat/lon as
REAL decimal degrees. Versions < 5 stored them as integers multiplied by
100000, so we rescale when needed.

The reader returns a nested mapping equivalent to the Haskell `EssidMap`:

    { essid: { bssid: { (lon, lat): [signal_dbm, ...] } } }

mirroring the per-location signal accumulation used by the rest of the
pipeline.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import DefaultDict

# Default schema version assumed when the KISMET metadata table or row is
# missing. 10 is the latest known release schema; assuming "modern" here is
# safer than assuming "legacy integer lat/lon".
DEFAULT_DB_VERSION = 10

# Per-essid -> per-bssid -> per-(lon, lat) -> list of dBm readings.
EssidMap = dict[str, dict[str, dict[tuple[float, float], list[float]]]]


def _db_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT db_version FROM KISMET").fetchone()
    except sqlite3.DatabaseError:
        return DEFAULT_DB_VERSION
    if row is None:
        return DEFAULT_DB_VERSION
    return int(row[0])


def _access_points(conn: sqlite3.Connection) -> dict[str, str]:
    """Return {bssid: essid} for Wi-Fi APs in the devices table.

    Mirrors the Haskell `AccessPointDetails` parser: prefer
    `kismet.device.base.name`, fall back to `kismet.device.base.commonname`
    (which Kismet seeds with the SSID and replaces with the MAC string when
    the SSID is unknown/cloaked).
    """
    bssid_to_essid: dict[str, str] = {}
    cursor = conn.execute(
        'SELECT device FROM devices WHERE type = "Wi-Fi AP"'
    )
    for (blob,) in cursor:
        if not blob:
            continue
        try:
            obj = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        mac = obj.get("kismet.device.base.macaddr")
        if not mac:
            continue
        name = obj.get("kismet.device.base.name") or ""
        if not name:
            name = obj.get("kismet.device.base.commonname") or ""
        bssid_to_essid[mac] = name
    return bssid_to_essid


def _packet_query(db_version: int) -> str:
    if db_version >= 2:
        return (
            "SELECT lat, lon, signal, sourcemac FROM packets "
            "WHERE phyname = 'IEEE802.11' AND lat != 0 AND lon != 0"
        )
    return (
        "SELECT lat, lon, signal, sourcemac FROM packets "
        "WHERE lat != 0 AND lon != 0"
    )


def read_kismet_sqlite(
    files: Iterable[Path | str],
    essids: Iterable[str],
) -> EssidMap:
    """Load one or more `.kismet` files into an EssidMap, keyed on the SSIDs
    listed in `essids`. Other SSIDs are ignored (they would just be filtered
    out downstream anyway, but skipping them keeps the map small)."""
    wanted = set(essids)
    out: DefaultDict[str, DefaultDict[str, DefaultDict[tuple[float, float], list[float]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for path in files:
        conn = sqlite3.connect(str(path))
        try:
            version = _db_version(conn)
            scale = (lambda x: x / 100000.0) if version < 5 else (lambda x: x)
            bssid_to_essid = _access_points(conn)
            cursor = conn.execute(_packet_query(version))
            for lat, lon, signal, mac in cursor:
                essid = bssid_to_essid.get(mac)
                if essid is None or essid not in wanted:
                    continue
                lon_s = scale(float(lon))
                lat_s = scale(float(lat))
                out[essid][mac][(lon_s, lat_s)].append(float(signal))
        finally:
            conn.close()
    # Freeze defaultdicts into plain dicts to keep downstream behavior obvious.
    return {
        essid: {bssid: dict(points) for bssid, points in bssids.items()}
        for essid, bssids in out.items()
    }


def db_stats(path: Path | str) -> dict[str, int | str]:
    """Return summary statistics about a .kismet file. Useful for sanity
    checks before running the full pipeline."""
    conn = sqlite3.connect(str(path))
    try:
        try:
            kismet_row = conn.execute(
                "SELECT kismet_version, db_version FROM KISMET"
            ).fetchone()
        except sqlite3.DatabaseError:
            kismet_row = (None, None)
        devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        wifi_aps = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE type = 'Wi-Fi AP'"
        ).fetchone()[0]
        version = _db_version(conn)
        usable = conn.execute(_packet_query(version)).fetchall()
    finally:
        conn.close()
    return {
        "kismet_version": kismet_row[0] if kismet_row else None,
        "db_version": int(kismet_row[1]) if kismet_row and kismet_row[1] else None,
        "devices": int(devices),
        "wifi_aps": int(wifi_aps),
        "usable_packets": len(usable),
    }
