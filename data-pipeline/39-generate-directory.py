#!/usr/bin/env python3
"""Generate a lightweight HTML directory of every current boundary page."""

import argparse
from datetime import date
import json
from pathlib import Path
from string import Template
import unicodedata

from config.loader import CANTON_CODES, DIST_DIR, OUTPUT_DIR, REFERENCE_DATE, SITE_DIR
from site_helpers import asset_version, build_assets, canonical_url, escape


def sort_key(record):
    return unicodedata.normalize("NFD", record[0].casefold())


def load_features(path):
    collection = json.loads(path.read_text())
    if collection.get("type") != "FeatureCollection" or not collection.get("features"):
        raise ValueError(f"Expected FeatureCollection: {path}")
    return collection["features"]


def item(name, meta, href, search, icon=None):
    image = f'<img src="{icon}" width="28" alt="" loading="lazy" decoding="async">' if icon else ""
    return (f'<li class="canton-item directory-link" data-search="{escape(search)}">'
            f'<a href="{href}">{image}<span><strong>{escape(name)}</strong>'
            f'<small>{escape(meta)}</small></span></a></li>')


def section(title, records, *, alphabet=False, preserve_order=False):
    groups = {}
    ordered_records = records if preserve_order else sorted(records, key=sort_key)
    for name, html in ordered_records:
        letter = unicodedata.normalize("NFD", name)[0].upper() if alphabet else ""
        groups.setdefault(letter, []).append(html)
    blocks = []
    for letter, rows in groups.items():
        heading = f'<h3 id="letter-{escape(letter)}">{escape(letter)}</h3>' if letter else ""
        blocks.append(f'{heading}<ul class="directory-links">{"".join(rows)}</ul>')
    return f'<section class="directory-group"><h2>{title}</h2>{"".join(blocks)}</section>'


def build(processed_dir: Path, output_dir: Path):
    countries = []
    for feature in load_features(processed_dir / "countries/ch-li.geojson"):
        props = feature["properties"]
        code = props["icc"].lower()
        name = {"ch": "Switzerland", "li": "Liechtenstein"}.get(code, props["name"])
        countries.append((name, item(name, props["icc"], f"../country/{code}.html",
                                     f'{name} {props["icc"]}', f"../country/{code}.png")))
    countries.sort(key=lambda record: (record[0] != "Switzerland", sort_key(record)))

    cantons = []
    for feature in load_features(processed_dir / "cantons/cantons.geojson"):
        props = feature["properties"]
        code = CANTON_CODES[props["kantonsnummer"]].upper()
        cantons.append((props["name"], item(props["name"], code, f"../canton/{code.lower()}.html",
                                            f'{props["name"]} {code}', f"../canton/{code.lower()}.png")))

    districts = []
    for feature in load_features(processed_dir / "districts/districts.geojson"):
        props = feature["properties"]
        number = props["bezirksnummer"]
        code = CANTON_CODES[props["kantonsnummer"]].upper()
        districts.append((props["name"], item(props["name"], f"{number} · {code}",
                                               f"../district/{number}.html", f'{props["name"]} {number} {code}')))

    municipalities = []
    for feature in load_features(processed_dir / "municipalities/municipalities.geojson"):
        props = feature["properties"]
        number = props["bfs_nummer"]
        code = CANTON_CODES[props["kantonsnummer"]].upper() if props["icc"] == "CH" else "LI"
        municipalities.append((props["name"], item(props["name"], f"{number} · {code}",
                                                    f"../municipality/{number}.html",
                                                    f'{props["name"]} {number} {code} {props["icc"]}',
                                                    f"../municipality/{number}.webp")))

    sections = "".join((section("Country", countries, preserve_order=True), section("Cantons", cantons),
                        section("Districts", districts), section("Municipalities", municipalities, alphabet=True)))
    count = sum(map(len, (countries, cantons, districts, municipalities)))
    templates = {name: Template((SITE_DIR / "templates" / f"{name}.html").read_text())
                 for name in ("base", "directory")}
    body = templates["directory"].substitute(
        sections=sections, count=count,
        boundary_date=date.fromisoformat(REFERENCE_DATE).strftime("%d %B %Y").lstrip("0"))
    assets = build_assets(SITE_DIR / "assets")
    version = asset_version(assets)
    html = templates["base"].substitute(
        title="Boundary Directory", description="Text directory of country, canton, district and municipality boundaries for Switzerland and Liechtenstein.",
        body=body, root_path="../", canonical_url=escape(canonical_url("directory/index.html")),
        home_class="", countries_class="", cantons_class="", districts_class="", municipalities_class="",
        asset_version=version)
    target = output_dir / "directory/index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    for path, content in assets.items():
        asset_target = output_dir / path
        asset_target.parent.mkdir(parents=True, exist_ok=True)
        asset_target.write_bytes(content)
    print(f"Generated text directory with {count} boundaries in {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    try:
        build(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Directory generation failed: {error}\n")


if __name__ == "__main__":
    main()
