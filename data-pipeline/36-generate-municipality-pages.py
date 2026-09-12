#!/usr/bin/env python3
"""Generate searchable municipality directory, detail pages and downloads."""

import argparse
from datetime import date
import json
import math
from pathlib import Path
from string import Template
import unicodedata

from config.loader import SITE_DIR, DIST_DIR, population_metadata, CANTON_CODES, OUTPUT_DIR, REFERENCE_DATE, SCRIPT_DIR
from site_helpers import build_assets, asset_version, escape, format_number, positions, publish_pinned_release



def build(input_dir, output_dir, *, current_only=False):
    source, destination = input_dir.resolve(), output_dir.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Output and processed inputs must be separate")
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ("base", "country", "municipalities")}
    metadata = population_metadata()
    dates = {"population_date": date.fromisoformat(metadata["population_date"]).strftime("%d %B %Y").lstrip("0"),
             "boundary_date": date.fromisoformat(REFERENCE_DATE).strftime("%d %B %Y").lstrip("0")}
    collection = json.loads((input_dir / "municipalities.geojson").read_text())
    if collection.get("type") != "FeatureCollection" or not collection.get("features"):
        raise ValueError("Expected municipality FeatureCollection")
    features = sorted(collection["features"], key=lambda f: unicodedata.normalize("NFD", f["properties"]["name"].casefold()))
    files, rows, seen = {}, [], set()
    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, body):
        return templates["base"].substitute(title=escape(title), description=escape(f"{title}: municipality boundaries and downloads."),
                                            body=body, countries_class="", cantons_class="", municipalities_class="active", districts_class="",
                                            asset_version=version).encode("utf-8")

    for feature in features:
        props = feature["properties"]
        number, name, country = props["bfs_nummer"], props["name"], props["icc"]
        if not isinstance(number, int) or number <= 0 or number in seen or country not in ("CH", "LI") or props["objektart"] != "Gemeindegebiet":
            raise ValueError(f"Unexpected municipality: {number}")
        seen.add(number)
        raw = (input_dir / f"{number}.geojson").read_bytes()
        if json.loads(raw).get("features") != [feature]:
            raise ValueError(f"Individual and combined data differ for {number}")
        if feature["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"Invalid geometry for {number}")
        for key in ("einwohnerzahl", "gem_flaeche"):
            value = props[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {key} for {number}")
        points = list(positions(feature["geometry"]["coordinates"]))
        bounds = [[min(p[i] for p in points) for i in (0, 1)], [max(p[i] for p in points) for i in (0, 1)]]
        canton = CANTON_CODES[props["kantonsnummer"]].upper() if country == "CH" else "LI"
        population = format_number(props["einwohnerzahl"])
        area = format_number(props["gem_flaeche"] / 100, 2)
        facts = (f'<div><dt>BFS number</dt><dd>{number}</dd></div>'
                 f'<div><dt>{"Canton" if country == "CH" else "Country"}</dt><dd>{canton}</dd></div>'
                 f'<div><dt>Population</dt><dd>{population}<small>{dates["population_date"]}</small></dd></div>'
                 f'<div><dt>Area</dt><dd>{area} km²</dd></div>')
        context = dict(name=escape(name), code=number, upper_code=f"{number} · {canton}", entity_label="Municipality",
                       boundary_label="Municipality boundary", facts=facts, subdivision_link="", coat_image="", coat_download="",
                       mask_hint="Covers the area outside the municipality.", bounds=escape(json.dumps(bounds)), **dates)
        body = templates["country"].substitute(context).replace("‹ All countries", "‹ All municipalities")
        files[Path("municipalities") / f"{number}.html"] = render(name, body)
        files[Path("municipalities") / f"{number}.geojson"] = raw
        rows.append(f'<li class="canton-item" data-search="{escape(f"{name} {number} {canton} {country}")}">'
                    f'<div class="canton-details"><h2><a href="./{number}.html">{escape(name)}</a></h2><p>{number} · {canton}</p>'
                    f'<p class="canton-stats">{population} inhabitants · {area} km²</p></div>'
                    f'<a class="canton-next" href="./{number}.html" aria-label="View {escape(name)}">›</a></li>')
    files[Path("municipalities/index.html")] = render("Municipalities", templates["municipalities"].substitute(rows="\n".join(rows), count=len(rows), **dates))
    for name in ("municipalities.geojson", "municipalities.zip"):
        files[Path("municipalities") / name] = (input_dir / name).read_bytes()
    files.update(assets)
    if not current_only:
        publish_pinned_release(output_dir, files, "municipalities")
    for path, raw in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for path in (output_dir / "municipalities").iterdir():
        if path.suffix in (".html", ".geojson") and path.stem.isdigit() and int(path.stem) not in seen:
            path.unlink()
    print(f"Generated {len(rows)} municipality detail pages, directory and downloads in {output_dir / 'municipalities'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_DIR / "municipalities")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    parser.add_argument("--current-only", action="store_true", help="Leave pinned releases unchanged")
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir, current_only=args.current_only)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Municipality generation failed: {error}\n")


if __name__ == "__main__":
    main()
