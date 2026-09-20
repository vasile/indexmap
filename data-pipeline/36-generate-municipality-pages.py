#!/usr/bin/env python3
"""Generate searchable municipality directory, detail pages and downloads."""

import argparse
from datetime import date
from html.parser import HTMLParser
import json
import math
from pathlib import Path
from string import Template
import unicodedata
from urllib.parse import urlsplit

from config.loader import SITE_DIR, DIST_DIR, population_metadata, CANTONS, CANTON_CODES, OUTPUT_DIR, REFERENCE_DATE, SCRIPT_DIR
from site_helpers import build_assets, asset_version, canonical_url, escape, external_references, format_number, positions


COAT_DIR = SCRIPT_DIR.parent / "data/source/coat-of-arms"


def credit_link(url, label):
    """Only publish web links, never raw Commons HTML."""
    if url and urlsplit(url).scheme in ("http", "https") and urlsplit(url).netloc:
        return f'<a href="{escape(url)}">{escape(label)}</a>'
    return escape(label)


class PermissionLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = dict(attrs).get("href", "")
            if url is None:
                return
            if url.startswith("//"):
                url = "https:" + url
            if urlsplit(url).scheme in ("http", "https") and urlsplit(url).netloc and url not in self.urls:
                self.urls.append(url)


def coat_credit(attribution):
    source = credit_link(attribution.get("page_url"), "Wikimedia Commons")
    license_name = attribution.get("license") or "License not recorded"
    if license_name == "Public domain":
        return f'<small class="coat-credit">Source: {source} · Public domain</small>'
    author = attribution.get("author")
    credit = f'{escape(author)} / {source}' if author else source
    license_link = credit_link(attribution.get("license_url"), license_name)
    title = escape(attribution.get("title") or "Coat of arms")
    lines = [f'{title} — {credit} · {license_link}', 'Converted to WebP and resized for display.']
    if attribution.get("credit"):
        lines.append(f'Source credit: {escape(attribution["credit"])}')
    permission = PermissionLinks()
    permission.feed((attribution.get("commons_metadata", {}).get("Permission") or {}).get("value", ""))
    lines.extend(credit_link(url, "Permission details") for url in permission.urls)
    return '<small class="coat-credit">' + '<br>'.join(lines) + '</small>'


def prepared_icon(coat_dir, filename):
    path = coat_dir / "municipalities-web" / filename
    if not path.is_file():
        raise ValueError(f"Missing prepared icon: {path}. Run fetch-coat-of-arms/prepare_web_icons.py locally and commit the prepared assets.")
    return path.read_bytes()


def municipality_coat(record, number, files, coat_dir):
    if record and record.get("status") == "available" and record.get("has_icon"):
        filename = f"{number}.webp"
        files[Path("municipality") / filename] = prepared_icon(coat_dir, filename)
        attribution = record["attribution"]
        original_url = attribution.get("original_url") or attribution.get("page_url")
        if not original_url or urlsplit(original_url).scheme not in ("http", "https") or not urlsplit(original_url).netloc:
            raise ValueError(f"Missing valid original image URL for {number}")
        download = (f'<a class="btn btn-outline-secondary" href="{escape(original_url)}">↓ Original coat of arms · Commons</a>'
                    + coat_credit(attribution))
        alt = ""
    else:
        filename = "placeholder.webp"
        placeholder_path = Path("municipality") / filename
        if placeholder_path not in files:
            files[placeholder_path] = prepared_icon(coat_dir, filename)
        alt = "Coat of arms unavailable"
        download = '<small class="coat-credit">Coat of arms unavailable. Placeholder shown.</small>'
    image = f'<img src="./{filename}" width="85" alt="{alt}" class="detail-coat-of-arms">'
    return image, download, filename


def build(input_dir, output_dir, *, coat_dir=COAT_DIR):
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
    district_collection = json.loads(
        (input_dir.parent / "districts/districts.geojson").read_text(encoding="utf-8")
    )
    if district_collection.get("type") != "FeatureCollection":
        raise ValueError("Expected district FeatureCollection")
    district_names = {
        feature["properties"]["bezirksnummer"]: feature["properties"]["name"]
        for feature in district_collection.get("features", [])
    }
    features = sorted(collection["features"], key=lambda f: unicodedata.normalize("NFD", f["properties"]["name"].casefold()))
    files, rows, seen = {}, [], set()
    manifest = json.loads((coat_dir / "municipalities-web/index.json").read_text())
    if manifest.get("schema_version") != 1 or "municipalities" not in manifest:
        raise ValueError("Prepared manifest is outdated. Run fetch-coat-of-arms/prepare_web_icons.py locally and commit the prepared assets.")
    coats = {record["id"]: record for record in manifest["municipalities"]}
    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)

    def render(title, body, path, *, description=None):
        description = description or f"{title}: municipality boundaries and downloads."
        return templates["base"].substitute(title=escape(title), description=escape(description),
                                            body=body, home_class="", countries_class="", cantons_class="", municipalities_class="active", districts_class="",
                                            root_path="../", canonical_url=escape(canonical_url(path)), asset_version=version).encode("utf-8")

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
        if country == "CH":
            canton_name = escape(CANTONS[canton.lower()]["display_name"])
            parent_fact = (
                f'<div><dt>Canton</dt><dd><a href="../canton/{canton.lower()}.html">'
                f'{canton_name} ({canton})</a></dd></div>'
            )
            district_number = props.get("bezirksnummer")
            district_name = district_names.get(district_number)
            if (isinstance(district_number, int) and district_number > 0
                    and isinstance(district_name, str) and district_name.strip()):
                district_name = escape(district_name)
                parent_fact += (
                    f'<div><dt>District</dt><dd><a href="../district/{district_number}.html">'
                    f'{district_name} (BFS {district_number})</a></dd></div>'
                )
        else:
            parent_fact = '<div><dt>Country</dt><dd><a href="../country/li.html">Liechtenstein (LI)</a></dd></div>'
        facts = (f'<div><dt>BFS number</dt><dd>{number}</dd></div>'
                 f'{parent_fact}'
                 f'<div><dt>Population</dt><dd>{population}<small>{dates["population_date"]}</small></dd></div>'
                 f'<div><dt>Area</dt><dd>{area} km²</dd></div>')
        coat_record = coats.get(number)
        coat_image, coat_download, coat_filename = municipality_coat(coat_record, number, files, coat_dir)
        references = external_references(
            f"https://geo.ld.admin.ch/boundaries/municipality/{number}",
            coat_record,
        )
        context = dict(name=escape(name), code=number, upper_code=f"{number} · {canton}", entity_label="Municipality",
                       boundary_label="Municipality boundary", facts=facts, subdivision_link="", related_sections="",
                       external_references=references,
                       coat_image=coat_image, coat_download=coat_download, directory_url="../municipalities/",
                       pmtiles_layer="municipalities", boundary_level=8, active_feature_ids=number,
                       mask_hint="Covers the area outside the municipality.", bounds=escape(json.dumps(bounds)), **dates)
        body = templates["country"].substitute(context).replace("‹ All countries", "‹ All municipalities")
        location = (f'{CANTONS[canton.lower()]["display_name"]}, Switzerland'
                    if country == "CH" else "Liechtenstein")
        files[Path("municipality") / f"{number}.html"] = render(
            f"{name} Municipality Boundary & GeoJSON", body, f"municipality/{number}.html",
            description=f"View and download the boundary of {name} municipality, {location}, as GeoJSON. BFS {number}.")
        files[Path("municipality") / f"{number}.geojson"] = raw
        rows.append(f'<li class="canton-item" data-feature-id="{number}" data-canton="{canton}" data-search="{escape(f"{name} {number} {canton} {country}")}">'
                    f'<img src="../municipality/{coat_filename}" alt="" class="canton-coat-of-arms" width="40" loading="lazy">'
                    f'<div class="canton-details"><h2><a href="../municipality/{number}.html">{escape(name)}</a></h2><p>{number} · {canton}</p>'
                    f'<p class="canton-stats">{population} inhabitants · {area} km²</p></div>'
                    f'<a class="canton-next" href="../municipality/{number}.html" aria-label="View {escape(name)}">›</a></li>')
    files[Path("municipalities/index.html")] = render("Municipalities", templates["municipalities"].substitute(rows="\n".join(rows), count=len(rows), **dates), "municipalities/index.html")
    for name in ("municipalities.geojson", "municipalities.zip"):
        files[Path("municipalities") / name] = (input_dir / name).read_bytes()
    files.update(assets)
    for path, raw in files.items():
        target = output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for folder in ("municipalities", "municipality"):
        for path in (output_dir / folder).iterdir():
            if (path.suffix in (".png", ".webp", ".html", ".geojson")
                    and (path.stem.isdigit() or path.stem == "placeholder")
                    and Path(folder) / path.name not in files):
                path.unlink()
    print(f"Generated {len(rows)} municipality detail pages, directory and downloads in {output_dir / 'municipalities'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_DIR / "municipalities")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Municipality generation failed: {error}\n")


if __name__ == "__main__":
    main()
