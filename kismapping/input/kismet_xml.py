"""Read legacy Kismet output: paired `.gpsxml` (per-packet GPS+signal) and
`.netxml` (BSSID -> ESSID mapping) files.

Mirrors `Kismapping.Input.KismetXML`. Each .gpsxml's `<network-file>` element
names the .netxml that sits next to it; we follow that pointer to resolve
BSSIDs to ESSIDs. Sentinel gps-point entries with the literal BSSID
`GP:SD:TR:AC:KL:OG` are skipped — they're GPS-only fixes with no packet.

The file format encodes non-printable bytes in ESSIDs as `\\nnn` octal
triples. We munge user-supplied ESSIDs the same way before matching so that
e.g. `Café` matches what Kismet wrote.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import DefaultDict

from lxml import etree


EssidMap = dict[str, dict[str, dict[tuple[float, float], list[float]]]]

# Sentinel BSSID for GPS-fix-only points in .gpsxml
GPS_SENTINEL = "GP:SD:TR:AC:KL:OG"


def munge_to_printable(text: str) -> str:
    """Match Haskell `Options.mungeToPrintable`: replace every non-printable
    UTF-8 byte with `\\nnn` octal. Run user-supplied ESSIDs through this
    before comparing against ESSIDs read from .netxml."""
    encoded = text.encode("utf-8")
    out = bytearray()
    for b in encoded:
        if 32 <= b <= 126:
            out.append(b)
        else:
            out.append(ord("\\"))
            out.append(((b >> 6) & 0x03) + ord("0"))
            out.append(((b >> 3) & 0x07) + ord("0"))
            out.append((b & 0x07) + ord("0"))
    return out.decode("utf-8")


def _parse_netxml(path: Path) -> dict[str, str]:
    """Return {bssid: essid} from a .netxml file. Falls back to "" when the
    network has no <essid> child."""
    out: dict[str, str] = {}
    bssid: str | None = None
    essid: str | None = None
    in_network = False
    in_ssid = False

    for event, elem in etree.iterparse(str(path), events=("start", "end"), recover=True):
        tag = etree.QName(elem.tag).localname
        if event == "start":
            if tag == "wireless-network":
                in_network = True
                bssid = None
                essid = None
            elif tag == "SSID" and in_network:
                in_ssid = True
        else:  # end
            if tag == "BSSID" and in_network:
                bssid = (elem.text or "").strip()
            elif tag == "essid" and in_ssid:
                if essid is None:
                    essid = (elem.text or "")
            elif tag == "SSID":
                in_ssid = False
            elif tag == "wireless-network":
                if bssid:
                    out[bssid] = essid or ""
                in_network = False
                # Free memory for very large netxml files.
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
    return out


def _parse_gpsxml_points(path: Path):
    """Yield (bssid, lon, lat, signal_dbm) tuples for each non-sentinel
    gps-point with a signal reading."""
    for event, elem in etree.iterparse(str(path), events=("end",), tag="{*}gps-point", recover=True):
        attrs = elem.attrib
        bssid = attrs.get("bssid")
        if not bssid or bssid == GPS_SENTINEL:
            elem.clear()
            continue
        sig = attrs.get("signal_dbm")
        if sig is None:
            elem.clear()
            continue
        try:
            lat = float(attrs["lat"])
            lon = float(attrs["lon"])
            db = float(sig)
        except (KeyError, ValueError):
            elem.clear()
            continue
        yield bssid, lon, lat, db
        elem.clear()


def _network_file(path: Path) -> str | None:
    """Read the `<network-file>` element from the head of a .gpsxml file."""
    for event, elem in etree.iterparse(str(path), events=("end",), tag="{*}network-file", recover=True):
        name = (elem.text or "").strip()
        elem.clear()
        return name
    return None


def read_kismet_xml(
    gpsxml_files: Iterable[Path | str],
    essids: Iterable[str],
) -> EssidMap:
    """Load one or more .gpsxml files (each paired with its sibling .netxml)
    into an EssidMap keyed on the munged form of each requested ESSID."""
    wanted_munged = {munge_to_printable(e) for e in essids}
    out: DefaultDict[str, DefaultDict[str, DefaultDict[tuple[float, float], list[float]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for raw in gpsxml_files:
        gpsxml = Path(raw)
        netxml_name = _network_file(gpsxml)
        if not netxml_name:
            raise ValueError(f"{gpsxml}: no <network-file> element")
        netxml = gpsxml.parent / netxml_name
        bssid_to_essid = _parse_netxml(netxml)
        for bssid, lon, lat, db in _parse_gpsxml_points(gpsxml):
            essid = bssid_to_essid.get(bssid, "")
            if essid not in wanted_munged:
                continue
            out[essid][bssid][(lon, lat)].append(db)
    return {
        essid: {bssid: dict(points) for bssid, points in bssids.items()}
        for essid, bssids in out.items()
    }
