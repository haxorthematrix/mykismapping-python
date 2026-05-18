"""Flask web server output mode.

Serves the bundled `map.html` (a Google Maps page) and four data endpoints
that the page polls on load: `/coords`, `/config`, plus either `/overlay.png`
(image mode) or `/overlay.json` (polygon mode). Matches the endpoint contract
of the Haskell Spock-based server in `Kismapping.Output.WebApp`.
"""

from __future__ import annotations

import io
import json
import sys
from importlib.resources import files
from pathlib import Path

from flask import Flask, Response
from PIL import Image

from .geometry import Region


def _coords_payload(region: Region) -> bytes:
    return json.dumps(
        {"west": region.west, "south": region.south, "east": region.east, "north": region.north}
    ).encode("utf-8")


def _load_map_html(apikey: str) -> str:
    template = files("kismapping.templates").joinpath("map.html").read_text(encoding="utf-8")
    return template.replace("${{KEY}}", apikey)


def _build_app(
    apikey: str,
    region: Region,
    config_payload: bytes,
    overlay_path: str,
    overlay_payload: bytes,
    overlay_mimetype: str,
) -> Flask:
    page_bytes = _load_map_html(apikey).encode("utf-8")
    coords_bytes = _coords_payload(region)
    app = Flask(__name__)

    @app.route("/")
    def root():
        return Response(page_bytes, mimetype="text/html; charset=utf-8")

    @app.route("/coords")
    def coords_handler():
        return Response(coords_bytes, mimetype="application/json")

    @app.route("/config")
    def config_handler():
        return Response(config_payload, mimetype="application/json")

    @app.route(overlay_path)
    def overlay_handler():
        return Response(overlay_payload, mimetype=overlay_mimetype)

    return app


def _announce(port: int) -> None:
    print(f"Running webserver on 0.0.0.0:{port}", file=sys.stderr)
    print(f"Navigate to http://127.0.0.1:{port}/ to access map.", file=sys.stderr)


def serve_image(apikey: str, port: int, region: Region, image: Image.Image) -> None:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    app = _build_app(
        apikey, region,
        json.dumps({"type": "overlayImage"}).encode("utf-8"),
        "/overlay.png", buf.getvalue(), "image/png",
    )
    _announce(port)
    app.run(host="0.0.0.0", port=port)


def serve_polygons(apikey: str, port: int, region: Region, polys: list[dict]) -> None:
    app = _build_app(
        apikey, region,
        json.dumps({"type": "overlayPolygon"}).encode("utf-8"),
        "/overlay.json", json.dumps(polys).encode("utf-8"), "application/json",
    )
    _announce(port)
    app.run(host="0.0.0.0", port=port)
