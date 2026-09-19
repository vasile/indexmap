"""Shared rendering helpers for site generators."""

import html
import hashlib
import math
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit
from dotenv import dotenv_values
from config.loader import PIPELINE, SCRIPT_DIR


FINGERPRINTED_ASSETS = ("config.js", "favicon.svg", "site.css", "site.js", "swisstopo-light.json")
FINGERPRINT_RE = re.compile(r"\.[0-9a-f]{16}(?=\.[^.]+$)")


def site_url(path="") -> str:
    """Build production URLs independently of the local preview address."""
    origin = PIPELINE["site_url"]
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("site_url must be an HTTPS origin without a path, query, or credentials")
    relative = str(path)
    if relative.startswith("/") or ".." in relative.split("/"):
        raise ValueError(f"Expected a site-relative path: {path}")
    return origin.rstrip("/") + "/" + quote(relative, safe="/")


def canonical_url(path) -> str:
    """Use directory URLs and prefer the homepage over its Country alias."""
    relative = Path(path).as_posix()
    if relative == "countries/index.html":
        relative = "index.html"
    if relative == "index.html" or relative.endswith("/index.html"):
        relative = relative[:-len("index.html")]
    return site_url(relative)


def build_assets(asset_dir: Path) -> dict[Path, bytes]:
    settings = {
        **dotenv_values(SCRIPT_DIR.parent / ".env"),
        **os.environ,
        **dotenv_values(SCRIPT_DIR.parent / ".env.local"),
    }
    token = settings.get("MAPBOX_ACCESS_TOKEN")
    token = (token or "").strip()
    if not token:
        raise ValueError("Set MAPBOX_ACCESS_TOKEN in the environment or project-root .env.local before generating site pages")
    if not token.startswith("pk."):
        raise ValueError("MAPBOX_ACCESS_TOKEN must be a public Mapbox token (pk.), since it is published to the browser")
    assets = {Path("assets") / path.relative_to(asset_dir): path.read_bytes()
              for path in asset_dir.rglob("*") if path.is_file()}
    swisstopo_style = SCRIPT_DIR.parent / "data" / "source" / "styles" / "swisstopo-light.json"
    if not swisstopo_style.is_file():
        raise ValueError(f"Missing local swisstopo basemap style: {swisstopo_style}")
    assets[Path("assets/swisstopo-light.json")] = swisstopo_style.read_bytes()
    assets[Path("assets/config.js")] = (
        "// Generated at build time; this public token is visible to browsers.\n"
        "window.INDEXMAP_CONFIG = " + json.dumps({"mapboxToken": token}) + ";\n"
    ).encode("utf-8")
    version = asset_version(assets)
    for name in FINGERPRINTED_ASSETS:
        path = Path("assets") / name
        if path in assets:
            fingerprinted = path.with_name(f"{path.stem}.{version}{path.suffix}")
            assets[fingerprinted] = assets[path]
    return assets


def asset_version(assets: dict[Path, bytes]) -> str:
    digest = hashlib.sha256()
    for path, content in sorted(assets.items()):
        if FINGERPRINT_RE.search(path.name):
            continue
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()[:16]


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def format_number(value, digits=0) -> str:
    return f"{value:,.{digits}f}".replace(",", "’")


def positions(coordinates):
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("Empty or invalid geometry coordinates")
    if isinstance(coordinates[0], (int, float)):
        if len(coordinates) < 2 or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in coordinates):
            raise ValueError("Invalid geometry position")
        yield coordinates
    else:
        for child in coordinates:
            yield from positions(child)
