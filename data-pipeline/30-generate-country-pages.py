#!/usr/bin/env python3
"""Generate country directory/detail pages and publish prepared GeoJSON files."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template

from config.loader import SITE_DIR, DIST_DIR, population_metadata, OUTPUT_DIR as PROCESSED_DIR, REFERENCE_DATE, SCRIPT_DIR
from site_helpers import build_assets, asset_version, escape, format_number, positions, publish_pinned_release

PROJECT_DIR = SCRIPT_DIR.parent
COUNTRIES = {"ch": "Switzerland", "li": "Liechtenstein"}


def bounds(features):
    points = []
    for feature in features:
        if feature["geometry"]["type"] not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Expected country polygon geometry")
        points.extend(positions(feature["geometry"]["coordinates"]))
    return escape(json.dumps([[min(p[0] for p in points), min(p[1] for p in points)],
                              [max(p[0] for p in points), max(p[1] for p in points)]]))


def build(input_dir: Path, output_dir: Path, *, current_only=False) -> None:
    source, destination = input_dir.resolve(), output_dir.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Output and processed inputs must be separate")
    metadata = population_metadata()
    dates = {"population_date": date.fromisoformat(metadata["population_date"]).strftime("%d %B %Y").lstrip("0"),
             "boundary_date": date.fromisoformat(REFERENCE_DATE).strftime("%d %B %Y").lstrip("0")}
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ["base", "country", "countries"]}
    files = {}
    data = {}
    for code in [*COUNTRIES, "ch-li", "ch-li-dissolved"]:
        raw = (input_dir / f"{code}.geojson").read_bytes()
        collection = json.loads(raw)
        expected = {"CH", "LI"} if code == "ch-li" else {"CH+LI"} if code == "ch-li-dissolved" else {code.upper()}
        features = collection.get("features", [])
        if collection.get("type") != "FeatureCollection" or len(features) != len(expected) or {f["properties"]["icc"] for f in features} != expected:
            raise ValueError(f"Unexpected country features in {code}.geojson")
        data[code] = features
        files[Path("countries") / f"{code}.geojson"] = raw

    for filename in ("ch.png", "li.png", "countries.zip"):
        files[Path("countries") / filename] = (input_dir / filename).read_bytes()

    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, body):
        return templates["base"].substitute(title=escape(title), description=escape(f"{title}: administrative boundaries and GeoJSON downloads."),
                                            body=body, countries_class="active", cantons_class="", asset_version=version, municipalities_class="", districts_class="").encode("utf-8")

    rows = {}
    for code, name in COUNTRIES.items():
        props = {"einwohnerzahl": 0, "landesflaeche": 0}
        for feature in data[code]:
            for key in props:
                value = feature["properties"][key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid {key} for {code}")
                props[key] += value
        upper_code = code.upper()
        population = format_number(props["einwohnerzahl"])
        area = format_number(props["landesflaeche"] / 100, 2)
        context = dict(name=escape(name), code=code, upper_code=upper_code, population=population, area=area,
                       coat_image=f'<img src="./{code}.png" width="85" alt="" class="detail-coat-of-arms">',
                       coat_download=f'<a class="btn btn-outline-secondary" href="./{code}.png" download="{code}.png">↓ Coat of arms · PNG</a>',
                       entity_label="Country", code_label="Country code",
                       boundary_label="Country boundary",
                       mask_hint="Covers the area outside the country.",
                       facts=f'<div><dt>Country code</dt><dd>{upper_code}</dd></div><div><dt>Population</dt><dd>{population}<small>{dates["population_date"]}</small></dd></div><div><dt>Area</dt><dd>{area} km²</dd></div>',
                       bounds=bounds(data[code]), subdivision_link='<a class="back-link" href="../cantons/index.html">Browse 26 cantons ›</a>' if code == "ch" else "", **dates)
        files[Path("countries") / f"{code}.html"] = render(name, templates["country"].substitute(context))
        stats = f'<p class="canton-stats">{population} inhabitants · {format_number(props["landesflaeche"] / 100)} km²</p>'
        rows[code] = (f'<li class="canton-item"><img src="./{code}.png" width="40" alt="" class="canton-coat-of-arms">'
                    f'<div class="canton-details"><h2><a href="./{code}.html">{escape(name)}</a></h2>'
                    f'<p>{upper_code}</p>{stats}'
                    '</div>'
                    f'<a class="canton-next" href="./{code}.html" aria-label="View {escape(name)}"><span aria-hidden="true">›</span></a></li>')
    dissolved_context = dict(name="Switzerland + Liechtenstein", code="ch-li-dissolved",
                             upper_code="CH + LI", entity_label="Dissolved boundary",
                             boundary_label="Dissolved boundary", facts="", subdivision_link="",
                             coat_image="", coat_download="",
                             mask_hint="Covers the area outside Switzerland and Liechtenstein.",
                             bounds=bounds(data["ch-li-dissolved"]), **dates)
    files[Path("countries/ch-li-dissolved.html")] = render(
        "Switzerland + Liechtenstein", templates["country"].substitute(dissolved_context))
    files[Path("countries/index.html")] = render("Country", templates["countries"].substitute(rows="\n".join(rows[code] for code in COUNTRIES), bounds=bounds(data["ch-li"]), **dates))
    files.update(assets)
    if not current_only:
        publish_pinned_release(output_dir, files, "countries")
    for path, content in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (output_dir / "countries/ch-li.html").unlink(missing_ok=True)
    print(f"Generated country directory, 3 detail pages, and 4 GeoJSON assets in {output_dir / 'countries'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PROCESSED_DIR / "countries")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    parser.add_argument("--current-only", action="store_true", help="Build current pages and assets without publishing a pinned release")
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir, current_only=args.current_only)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Country generation failed: {error}\n")


if __name__ == "__main__":
    main()
