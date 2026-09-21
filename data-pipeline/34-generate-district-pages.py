#!/usr/bin/env python3
"""Generate searchable district directory, detail pages and downloads."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template
import unicodedata

from config.loader import SITE_DIR, DIST_DIR, population_metadata, CANTONS, CANTON_CODES, OUTPUT_DIR, REFERENCE_DATE, SCRIPT_DIR
from site_helpers import build_assets, asset_version, canonical_url, directory_redirect, escape, external_references, format_number, positions


COAT_DIR = SCRIPT_DIR.parent / "data/source/coat-of-arms/municipalities-web"
REFERENCE_MANIFEST = SCRIPT_DIR.parent / "data/source/references/administrative.json"


def municipality_sections(processed_dir):
    collection = json.loads((processed_dir / "municipalities/municipalities.geojson").read_text(encoding="utf-8"))
    manifest = json.loads((COAT_DIR / "index.json").read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection" or manifest.get("schema_version") != 1:
        raise ValueError("Expected municipality data and current coat-of-arms manifest")
    available_coats = {
        record["id"] for record in manifest.get("municipalities", [])
        if record.get("status") == "available" and record.get("has_icon")
    }
    by_district = {}
    for feature in collection["features"]:
        properties = feature["properties"]
        district = properties.get("bezirksnummer")
        if district is None:
            continue
        number = properties["bfs_nummer"]
        icon = f"{number}.webp" if number in available_coats else "placeholder.webp"
        by_district.setdefault(district, []).append((properties["name"], number, icon))
    for municipalities in by_district.values():
        municipalities.sort(key=lambda item: unicodedata.normalize("NFD", item[0].casefold()))
    return by_district


def municipality_section(municipalities):
    rows = "".join(
        '<li><a href="../municipality/{number}.html">'
        '<img src="../municipality/{icon}" width="30" loading="lazy" alt="">'
        '<span>{name} <small>· BFS {number}</small></span></a></li>'.format(
            number=number, icon=icon, name=escape(name))
        for name, number, icon in municipalities
    )
    return (
        '<section class="canton-subdivisions" aria-labelledby="district-municipalities">'
        f'<h2 id="district-municipalities">Municipalities <span>({len(municipalities)})</span></h2>'
        f'<ul class="subdivision-list municipality-links">{rows}</ul></section>'
    )



def build(input_dir, output_dir):
    source, destination = input_dir.resolve(), output_dir.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Output and processed inputs must be separate")
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ("base", "country", "districts")}
    metadata = population_metadata()
    dates = {"population_date": date.fromisoformat(metadata["population_date"]).strftime("%d %B %Y").lstrip("0"),
             "boundary_date": date.fromisoformat(REFERENCE_DATE).strftime("%d %B %Y").lstrip("0")}
    collection = json.loads((input_dir / "districts.geojson").read_text())
    if collection.get("type") != "FeatureCollection" or not collection.get("features"):
        raise ValueError("Expected district FeatureCollection")
    features = sorted(collection["features"], key=lambda f: unicodedata.normalize("NFD", f["properties"]["name"].casefold()))
    municipalities_by_district = municipality_sections(input_dir.parent)
    reference_manifest = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    if reference_manifest.get("schema_version") != 1:
        raise ValueError(f"Invalid administrative reference manifest: {REFERENCE_MANIFEST}")
    district_references = {record["id"]: record for record in reference_manifest.get("districts", [])}
    files, rows, seen = {}, [], set()
    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, body, path, *, description=None):
        description = description or f"{title}: district boundaries and downloads."
        return templates["base"].substitute(title=escape(title), description=escape(description),
                                            body=body, home_class="", countries_class="", cantons_class="", districts_class="active", municipalities_class="",
                                            root_path="../", canonical_url=escape(canonical_url(path)), asset_version=version).encode("utf-8")

    for feature in features:
        props = feature["properties"]
        number, name, country = props["bezirksnummer"], props["name"], props["icc"]
        if not isinstance(number, int) or number <= 0 or number in seen or country != "CH" or props["objektart"] != "Bezirk":
            raise ValueError(f"Unexpected district: {number}")
        seen.add(number)
        raw = (input_dir / f"{number}.geojson").read_bytes()
        if json.loads(raw).get("features") != [feature]:
            raise ValueError(f"Individual and combined data differ for {number}")
        if feature["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"Invalid geometry for {number}")
        for key in ("einwohnerzahl", "bezirksflaeche"):
            value = props[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {key} for {number}")
        points = list(positions(feature["geometry"]["coordinates"]))
        bounds = [[min(p[i] for p in points) for i in (0, 1)], [max(p[i] for p in points) for i in (0, 1)]]
        canton = CANTON_CODES[props["kantonsnummer"]].upper() if country == "CH" else "LI"
        canton_name = CANTONS[canton.lower()]["display_name"]
        population = format_number(props["einwohnerzahl"])
        area = format_number(props["bezirksflaeche"] / 100, 2)
        facts = (f'<div><dt>BFS number</dt><dd>{number}</dd></div>'
                 f'<div><dt>Canton</dt><dd><a href="../canton/{canton.lower()}.html">'
                 f'{escape(canton_name)} ({canton})</a></dd></div>'
                 f'<div><dt>Population</dt><dd>{population}<small>{dates["population_date"]}</small></dd></div>'
                 f'<div><dt>Area</dt><dd>{area} km²</dd></div>')
        related_sections = municipality_section(municipalities_by_district.get(number, []))
        references = external_references(
            f"https://geo.ld.admin.ch/boundaries/district/{number}",
            district_references.get(number),
        )
        context = dict(name=escape(name), code=number, upper_code=f"{number} · {canton}", entity_label="District",
                       boundary_label="District boundary", facts=facts, subdivision_link="", related_sections=related_sections,
                       external_references=references,
                       coat_image="", coat_download="", directory_url="../districts/",
                       pmtiles_layer="districts", boundary_level=6, active_feature_ids=number,
                       mask_hint="Covers the area outside the district.", bounds=escape(json.dumps(bounds)), **dates)
        body = templates["country"].substitute(context).replace("‹ All countries", "‹ All districts")
        files[Path("district") / f"{number}.html"] = render(
            f"{name} District Boundary & GeoJSON", body, f"district/{number}.html",
            description=f"View and download the boundary of {name} district, {canton_name}, Switzerland, as GeoJSON. BFS {number}.")
        files[Path("district") / f"{number}.geojson"] = raw
        rows.append(f'<li class="canton-item" data-feature-id="{number}" data-canton="{canton}" data-search="{escape(f"{name} {number} {canton} {country}")}">'
                    f'<div class="canton-details"><h2><a href="../district/{number}.html">{escape(name)}</a></h2><p>{number} · {canton}</p>'
                    f'<p class="canton-stats">{population} inhabitants · {area} km²</p></div>'
                    f'<a class="canton-next" href="../district/{number}.html" aria-label="View {escape(name)}">›</a></li>')
    files[Path("districts/index.html")] = render("Districts", templates["districts"].substitute(rows="\n".join(rows), count=len(rows), **dates), "districts/index.html")
    files[Path("district/index.html")] = directory_redirect(
        "../districts/", "all districts", "districts/index.html")
    for name in ("districts.geojson", "districts.zip"):
        files[Path("districts") / name] = (input_dir / name).read_bytes()
    files.update(assets)
    for path, raw in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for folder in ("districts", "district"):
        for path in (output_dir / folder).iterdir():
            if path.suffix in (".html", ".geojson") and path.stem.isdigit() and Path(folder) / path.name not in files:
                path.unlink()
    print(f"Generated {len(rows)} district detail pages, directory and downloads in {output_dir / 'districts'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_DIR / "districts")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"District generation failed: {error}\n")


if __name__ == "__main__":
    main()
