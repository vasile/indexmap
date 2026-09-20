#!/usr/bin/env python3
"""Generate canton pages and copy prepared downloads using shared YAML configuration."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template
import unicodedata

from site_helpers import build_assets, asset_version, canonical_url, escape, external_references, format_number, positions

from config.loader import CANTONS, SITE_DIR, DIST_DIR, population_metadata, CANTON_CODES, OUTPUT_DIR as PROCESSED_DIR, REFERENCE_DATE, SCRIPT_DIR


PROJECT_DIR = SCRIPT_DIR.parent
COAT_DIR = PROJECT_DIR / "data/source/coat-of-arms/municipalities-web"
REFERENCE_MANIFEST = PROJECT_DIR / "data/source/references/administrative.json"


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


def load_subdivisions(processed_dir: Path):
    districts = json.loads((processed_dir / "districts/districts.geojson").read_text(encoding="utf-8"))
    municipalities = json.loads((processed_dir / "municipalities/municipalities.geojson").read_text(encoding="utf-8"))
    manifest = json.loads((COAT_DIR / "index.json").read_text(encoding="utf-8"))
    if districts.get("type") != "FeatureCollection" or municipalities.get("type") != "FeatureCollection":
        raise ValueError("Expected district and municipality FeatureCollections")
    if manifest.get("schema_version") != 1 or "municipalities" not in manifest:
        raise ValueError("Prepared municipality coat-of-arms manifest is outdated")
    available_coats = {
        record["id"] for record in manifest["municipalities"]
        if record.get("status") == "available" and record.get("has_icon")
    }
    by_canton = {number: {"districts": [], "municipalities": []} for number in CANTON_CODES}
    for feature in districts["features"]:
        properties = feature["properties"]
        by_canton[properties["kantonsnummer"]]["districts"].append(
            (properties["name"], properties["bezirksnummer"])
        )
    for feature in municipalities["features"]:
        properties = feature["properties"]
        if properties.get("icc") != "CH":
            continue
        number = properties["bfs_nummer"]
        by_canton[properties["kantonsnummer"]]["municipalities"].append(
            (properties["name"], number, f"{number}.webp" if number in available_coats else "placeholder.webp")
        )
    for subdivisions in by_canton.values():
        subdivisions["districts"].sort(key=lambda item: sort_key(item[0]))
        subdivisions["municipalities"].sort(key=lambda item: sort_key(item[0]))
    return by_canton


def subdivision_sections(subdivisions, canton_code):
    district_section = ""
    if subdivisions["districts"]:
        midpoint = (len(subdivisions["districts"]) + 1) // 2
        columns = []
        for districts in (subdivisions["districts"][:midpoint], subdivisions["districts"][midpoint:]):
            rows = "".join(
                f'<li><a href="../district/{number}.html">{escape(name)} <small>· BFS {number}</small></a></li>'
                for name, number in districts
            )
            columns.append(f'<ul class="subdivision-list district-column">{rows}</ul>')
        district_section = (
            '<section class="canton-subdivisions" aria-labelledby="canton-districts">'
            f'<h2 id="canton-districts"><a href="../districts/?canton={canton_code.upper()}">'
            f'Districts <span>({len(subdivisions["districts"])})</span></a></h2>'
            f'<div class="district-links">{"".join(columns)}</div></section>'
        )
    municipality_rows = "".join(
        '<li><a href="../municipality/{number}.html">'
        '<img src="../municipality/{icon}" width="30" loading="lazy" alt="">'
        '<span>{name} <small>· BFS {number}</small></span></a></li>'.format(
            number=number, icon=icon, name=escape(name))
        for name, number, icon in subdivisions["municipalities"]
    )
    municipality_section = (
        '<section class="canton-subdivisions" aria-labelledby="canton-municipalities">'
        f'<h2 id="canton-municipalities"><a href="../municipalities/?canton={canton_code.upper()}">'
        f'Municipalities <span>({len(subdivisions["municipalities"])})</span></a></h2>'
        f'<ul class="subdivision-list municipality-links">{municipality_rows}</ul></section>'
    )
    return district_section, municipality_section


def build(input_dir: Path, output_dir: Path) -> None:
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
    subdivisions = load_subdivisions(input_dir.parent)
    reference_manifest = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    if reference_manifest.get("schema_version") != 1:
        raise ValueError(f"Invalid administrative reference manifest: {REFERENCE_MANIFEST}")
    canton_references = {record["id"]: record for record in reference_manifest.get("cantons", [])}
    bundles = {}
    for filename in ["cantons.geojson", "cantons.zip"]:
        path = input_dir / filename
        if not path.is_file():
            raise ValueError(f"Missing {path}; run 22-prepare-cantons.py first")
        bundles[filename] = path.read_bytes()

    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, description, body, path):
        return templates["base"].substitute(title=escape(title), description=escape(description), body=body, root_path="../", canonical_url=escape(canonical_url(path)), home_class="", countries_class="", cantons_class="active", asset_version=version, municipalities_class="", districts_class="")

    # Validate and render every page before writing output.
    pages = {}
    rows = []
    for canton in cantons:
        context = canton["context"] | dates
        context["external_references"] = external_references(
            f'https://geo.ld.admin.ch/boundaries/canton/{context["bfs"]}',
            canton_references.get(context["code"]),
        )
        canton_subdivisions = subdivisions[context["bfs"]]
        district_section, municipality_section = subdivision_sections(canton_subdivisions, context["code"])
        subdivision_stats = []
        if canton_subdivisions["districts"]:
            subdivision_stats.append(
                f'<a href="../districts/?canton={context["upper_code"]}">'
                f'Districts ({len(canton_subdivisions["districts"])})</a>'
            )
        subdivision_stats.append(
            f'<a href="../municipalities/?canton={context["upper_code"]}">'
            f'Municipalities ({len(canton_subdivisions["municipalities"])})</a>'
        )
        context |= {
            "district_section": district_section,
            "municipality_section": municipality_section,
            "subdivision_stats": ' <span class="detail-separator">·</span> '.join(subdivision_stats),
        }
        rows.append(templates["canton-row"].substitute(context))
        pages[f'{context["code"]}.html'] = render(
            f'{canton["name"]} Canton Boundary & GeoJSON',
            f'View and download the boundary of {canton["name"]} canton, Switzerland, as GeoJSON. Canton code {context["upper_code"]}.',
            templates["canton"].substitute(context), f'canton/{context["code"]}.html',
        )
    pages["index.html"] = render("Cantons of Switzerland", "Explore Switzerland’s 26 cantons and download their administrative boundaries.",
                                 templates["cantons"].substitute(rows="\n".join(rows), count=len(cantons), **dates), "cantons/index.html")
    files = {Path("cantons" if filename == "index.html" else "canton") / filename: page.encode("utf-8") for filename, page in pages.items()}
    files.update(assets)
    for canton in cantons:
        code = canton["context"]["code"]
        for extension in ["geojson", "png"]:
            files[Path("canton") / f"{code}.{extension}"] = canton[extension]
    for filename, raw in bundles.items():
        files[Path("cantons") / filename] = raw
    for path, content in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for code in CANTON_CODES.values():
        for extension in ("html", "geojson", "png"):
            (output_dir / "cantons" / f"{code}.{extension}").unlink(missing_ok=True)
    print(f"Generated {len(pages)} current pages and downloads in {output_dir / 'cantons'} and {output_dir / 'canton'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PROCESSED_DIR / "cantons")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Canton generation failed: {error}\n")


if __name__ == "__main__":
    main()
