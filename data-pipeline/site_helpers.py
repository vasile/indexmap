"""Shared rendering and release publishing helpers for site generators."""

import html
import hashlib
import math
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlsplit
from dotenv import dotenv_values
from config.loader import PIPELINE, REFERENCE_DATE, SCRIPT_DIR


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
    assets[Path("assets/config.js")] = (
        "// Generated at build time; this public token is visible to browsers.\n"
        "window.INDEXMAP_CONFIG = " + json.dumps({"mapboxToken": token}) + ";\n"
    ).encode("utf-8")
    return assets


def asset_version(assets: dict[Path, bytes]) -> str:
    digest = hashlib.sha256()
    for path, content in sorted(assets.items()):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()[:16]


def publish_pinned_release(output_dir: Path, files: dict[Path, bytes], section: str) -> None:
    release_dir = output_dir / "versions" / REFERENCE_DATE
    section_dir = release_dir / section
    if section_dir.exists():
        for path, content in files.items():
            if path.parts[0] == section and path.suffix in {".geojson", ".png", ".zip"}:
                target = release_dir / path
                if not target.is_file() or target.read_bytes() != content:
                    raise ValueError(f"Pinned release differs at {target}; existing releases cannot be overwritten")
        print(f"Preserved pinned section {section_dir}")
        return
    release_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".section-", dir=release_dir) as temporary:
        staging = Path(temporary) / section
        for path, content in files.items():
            if path.parts[0] == section:
                target = Path(temporary) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".html":
                    # Dated pages describe their own release, not today's data.
                    old_link = f'<link rel="canonical" href="{escape(canonical_url(path))}">'
                    dated_path = Path("versions") / REFERENCE_DATE / path
                    new_link = f'<link rel="canonical" href="{escape(canonical_url(dated_path))}">'
                    content = content.replace(old_link.encode(), new_link.encode())
                    # The brand always links to the current site's homepage.
                    content = content.replace(b'<a href="../" class="brand ', b'<a href="../../../" class="brand ')
                    # Dated sections have a Country directory but no root homepage.
                    content = content.replace(b'href="../"', b'href="../countries/"')
                target.write_bytes(content)
            elif path.parts[0] == "assets":
                target = release_dir / path
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
        staging.rename(section_dir)
    print(f"Created pinned section {section_dir}")


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
