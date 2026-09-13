#!/usr/bin/env python3
"""Generate canton pages and copy prepared downloads using shared YAML configuration."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template
import unicodedata

from site_helpers import build_assets, asset_version, escape, format_number, positions, publish_pinned_release

from config.loader import CANTONS, SITE_DIR, DIST_DIR, population_metadata, CANTON_CODES, OUTPUT_DIR as PROCESSED_DIR, REFERENCE_DATE, SCRIPT_DIR


PROJECT_DIR = SCRIPT_DIR.parent


def sort_key(name):
    return "".join(c for c in unicodedata.normalize("NFD", name.casefold()) if not unicodedata.combining(c))


def load_cantons(input_dir: Path, lookup: dict):
    if set(lookup) != set(CANTON_CODES.values()):
        raise ValueError("Canton lookup codes must match config.CANTON_CODES")
    cantons = []
    for number, code in CANTON_CODES.items():
        path = input_dir / f"{code}.geojson"
        raw = path.read_bytes()
        data = json.loads(raw)
        if data.get("type") != "FeatureCollection" or len(data.get("features", [])) != 1:
            raise ValueError(f"{path}: expected one canton feature")
        feature = data["features"][0]
        props = feature["properties"]
        if props["kantonsnummer"] != number:
            raise ValueError(f"{path}: canton number does not match {code}")
        for key in ["einwohnerzahl", "kantonsflaeche"]:
            value = props[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{path}: invalid {key}")
        if feature["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"{path}: expected polygon geometry")
        points = list(positions(feature["geometry"]["coordinates"]))
        bounds = [[min(p[0] for p in points), min(p[1] for p in points)],
                  [max(p[0] for p in points), max(p[1] for p in points)]]
        png = (input_dir / f"{code}.png").read_bytes()
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"Invalid PNG for {code}")
        name = lookup[code].get("display_name") or props["name"]
        seat = lookup[code]["seat"]
        if not isinstance(name, str) or not name.strip() or not isinstance(seat, str) or not seat.strip():
            raise ValueError(f"Missing name or seat for {code}")
        context = {
            "name": escape(name), "code": code, "upper_code": code.upper(),
            "seat": escape(seat), "bfs": number,
            "population": format_number(props["einwohnerzahl"]),
            "area": format_number(props["kantonsflaeche"] / 100, 2),
            "rounded_area": format_number(props["kantonsflaeche"] / 100),
            "bounds": escape(json.dumps(bounds)),
            "search": escape(f"{code.upper()} {name} {seat}"),
        }
        cantons.append({"name": name, "context": context, "geojson": raw, "png": png})
    return sorted(cantons, key=lambda canton: sort_key(canton["name"]))


def build(input_dir: Path, output_dir: Path, *, current_only=False) -> None:
    if output_dir.resolve() == input_dir.resolve() or output_dir.resolve() in input_dir.resolve().parents or input_dir.resolve() in output_dir.resolve().parents:
        raise ValueError("Output and processed canton inputs must be separate")
    lookup = CANTONS
    metadata = population_metadata()
    metadata["boundary_date"] = REFERENCE_DATE
    dates = {key: date.fromisoformat(metadata[key]).strftime("%d %B %Y").lstrip("0")
             for key in ["population_date", "boundary_date"]}
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ["base", "cantons", "canton", "canton-row"]}
    cantons = load_cantons(input_dir, lookup)
    bundles = {}
    for filename in ["cantons.geojson", "cantons.zip"]:
        path = input_dir / filename
        if not path.is_file():
            raise ValueError(f"Missing {path}; run 22-prepare-cantons.py first")
        bundles[filename] = path.read_bytes()

    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, description, body):
        return templates["base"].substitute(title=escape(title), description=escape(description), body=body, root_path="../", countries_class="", cantons_class="active", asset_version=version, municipalities_class="", districts_class="")

    # Validate and render every page before writing output.
    pages = {}
    rows = []
    for canton in cantons:
        context = canton["context"] | dates
        rows.append(templates["canton-row"].substitute(context))
        pages[f'{context["code"]}.html'] = render(
            canton["name"], f'{canton["name"]}: boundary map, population, area, and downloads.',
            templates["canton"].substitute(context),
        )
    pages["index.html"] = render("Cantons of Switzerland", "Explore Switzerland’s 26 cantons and download their administrative boundaries.",
                                 templates["cantons"].substitute(rows="\n".join(rows), count=len(cantons), **dates))
    files = {Path("cantons") / filename: page.encode("utf-8") for filename, page in pages.items()}
    files.update(assets)
    for canton in cantons:
        code = canton["context"]["code"]
        for extension in ["geojson", "png"]:
            files[Path("cantons") / f"{code}.{extension}"] = canton[extension]
    for filename, raw in bundles.items():
        files[Path("cantons") / filename] = raw
    if not current_only:
        publish_pinned_release(output_dir, files, "cantons")
    for path, content in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    print(f"Generated {len(pages)} current pages and downloads in {output_dir / 'cantons'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PROCESSED_DIR / "cantons")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    parser.add_argument("--current-only", action="store_true", help="Leave pinned releases unchanged")
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir, current_only=args.current_only)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Canton generation failed: {error}\n")


if __name__ == "__main__":
    main()
