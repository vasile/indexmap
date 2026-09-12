"""Shared rendering and release publishing helpers for site generators."""

import html
import hashlib
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from config.loader import REFERENCE_DATE


def asset_version(asset_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(asset_dir.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(asset_dir)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
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
