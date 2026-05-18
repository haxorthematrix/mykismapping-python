"""File-mode output: writes coords.json plus overlay.png or overlay.json."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .geometry import Region


def _region_dict(r: Region) -> dict[str, float]:
    return {"west": r.west, "south": r.south, "east": r.east, "north": r.north}


def write_image(out_dir: Path, region: Region, image: Image.Image) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coords.json").write_text(json.dumps(_region_dict(region)))
    image.save(out_dir / "overlay.png")


def write_polygons(out_dir: Path, region: Region, polys: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coords.json").write_text(json.dumps(_region_dict(region)))
    (out_dir / "overlay.json").write_text(json.dumps(polys))
