#!/usr/bin/env python3
"""Generate the country homepage, directory/detail pages and prepared GeoJSON files."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template

from config.loader import (SITE_DIR, DIST_DIR, population_metadata, OUTPUT_DIR as PROCESSED_DIR,
                           REFERENCE_DATE, SCRIPT_DIR, SWISSBOUNDARIES_DOWNLOAD_URL)
from site_helpers import build_assets, asset_version, canonical_url, escape, format_number, positions

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


def build(input_dir: Path, output_dir: Path) -> None:
    source, destination = input_dir.resolve(), output_dir.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Output and processed inputs must be separate")
    metadata = population_metadata()
    dates = {"population_date": date.fromisoformat(metadata["population_date"]).strftime("%d %B %Y").lstrip("0"),
             "boundary_date": date.fromisoformat(REFERENCE_DATE).strftime("%d %B %Y").lstrip("0")}
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ["base", "country", "countries", "home", "country-row"]}
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
        files[Path("countries" if code == "ch-li" else "country") / f"{code}.geojson"] = raw

    for filename in ("ch.png", "li.png", "countries.zip"):
        files[Path("countries" if filename == "countries.zip" else "country") / filename] = (input_dir / filename).read_bytes()

    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, body, path, *, root_path="../", description=None):
        description = description or f"{title}: administrative boundaries and GeoJSON downloads."
        is_home = Path(path) == Path("index.html")
        return templates["base"].substitute(title=escape(title), description=escape(description),
                                            body=body, root_path=root_path, canonical_url=escape(canonical_url(path)),
                                            home_class="active" if is_home else "",
                                            countries_class="" if is_home else "active", cantons_class="",
                                            asset_version=version, municipalities_class="", districts_class="").encode("utf-8")

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
                       entity_label="Country", code_label="Country code", directory_url="../countries/",
                       boundary_label="Country boundary",
                       pmtiles_layer="countries", boundary_level=2, active_feature_ids=upper_code,
                       mask_hint="Covers the area outside the country.",
                       facts=f'<div><dt>Country code</dt><dd>{upper_code}</dd></div><div><dt>Population</dt><dd>{population}<small>{dates["population_date"]}</small></dd></div><div><dt>Area</dt><dd>{area} km²</dd></div>',
                       bounds=bounds(data[code]), subdivision_link='<a class="back-link" href="../cantons/">Browse 26 cantons ›</a>' if code == "ch" else "", **dates)
        path = Path("country") / f"{code}.html"
        files[path] = render(
            f"{name} Country Boundary & GeoJSON", templates["country"].substitute(context), path,
            description=f"View and download the boundary of {name} as GeoJSON. Country code {upper_code}.")
        stats = f'<p class="canton-stats">{population} inhabitants · {format_number(props["landesflaeche"] / 100)} km²</p>'
        rows[code] = dict(name=escape(name), code=code, upper_code=upper_code, stats=stats)
    dissolved_context = dict(name="Switzerland + Liechtenstein", code="ch-li-dissolved",
                             upper_code="CH + LI", entity_label="Dissolved boundary",
                             boundary_label="Dissolved boundary", facts="", subdivision_link="",
                             pmtiles_layer="countries", boundary_level=2, active_feature_ids="CH,LI",
                             coat_image="", coat_download="", directory_url="../countries/",
                             mask_hint="Covers the area outside Switzerland and Liechtenstein.",
                             bounds=bounds(data["ch-li-dissolved"]), **dates)
    files[Path("country/ch-li-dissolved.html")] = render(
        "Switzerland & Liechtenstein Combined Boundary & GeoJSON",
        templates["country"].substitute(dissolved_context), "country/ch-li-dissolved.html",
        description="View and download the combined boundary of Switzerland and Liechtenstein as GeoJSON.")

    def directory(country_path, collection_path):
        return templates["countries"].substitute(
            rows="\n".join(templates["country-row"].substitute(rows[code], country_path=country_path) for code in COUNTRIES),
            country_path=country_path, collection_path=collection_path, bounds=bounds(data["ch-li"]), **dates)

    homepage_description = ("Download current GeoJSON boundaries for Switzerland and Liechtenstein, including "
                            "cantons, districts, and municipalities. Based on official swisstopo boundaries.")
    files[Path("countries/index.html")] = render(
        "Swiss administrative boundaries as GeoJSON", directory("../country/", "./"),
        "countries/index.html", description=homepage_description)
    home_context = dict(
        bounds=bounds(data["ch-li"]), population_date=dates["population_date"],
        boundary_date=dates["boundary_date"],
        swisstopo_gpkg_url=escape(SWISSBOUNDARIES_DOWNLOAD_URL))
    files[Path("index.html")] = render(
        "Swiss administrative boundaries as GeoJSON", templates["home"].substitute(home_context),
        "index.html", root_path="./", description=homepage_description)
    files.update(assets)
    for path, content in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (output_dir / "countries/ch-li.html").unlink(missing_ok=True)
    for code in (*COUNTRIES, "ch-li-dissolved"):
        for extension in ("html", "geojson", "png"):
            (output_dir / "countries" / f"{code}.{extension}").unlink(missing_ok=True)
    print(f"Generated homepage, country directory, 3 detail pages, and 4 GeoJSON assets in {output_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PROCESSED_DIR / "countries")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Country generation failed: {error}\n")


if __name__ == "__main__":
    main()
