#!/usr/bin/env python3
"""Build the current five-layer boundary map as a static PMTiles archive."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from config.loader import DIST_DIR, INPUT_PATH, OUTPUT_DIR, RELEASE_SOURCE_DIR, SWISSBOUNDARIES_RELEASE


POLYGON_LAYERS = {
    "countries": OUTPUT_DIR / "countries/ch-li.geojson",
    "cantons": OUTPUT_DIR / "cantons/cantons.geojson",
    "districts": OUTPUT_DIR / "districts/districts.geojson",
    "municipalities": OUTPUT_DIR / "municipalities/municipalities.geojson",
}
BOUNDARY_SOURCE_LAYER = "tlm_hoheitsgrenze"


def named_layer(name: str, path: Path) -> str:
    return json.dumps({"file": str(path), "layer": name}, separators=(",", ":"))


def build(output_path: Path) -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    tippecanoe = shutil.which("tippecanoe")
    missing_tools = [name for name, path in (("ogr2ogr", ogr2ogr), ("tippecanoe", tippecanoe)) if not path]
    if missing_tools:
        raise ValueError(f"Missing required command: {', '.join(missing_tools)}")
    versioned_source = RELEASE_SOURCE_DIR / SWISSBOUNDARIES_RELEASE / "source.gpkg"
    source_path = versioned_source if versioned_source.is_file() else INPUT_PATH
    if not source_path.is_file():
        raise ValueError(f"Source GeoPackage not found: {versioned_source} or {INPUT_PATH}")
    missing = [str(path) for path in POLYGON_LAYERS.values() if not path.is_file()]
    if missing:
        raise ValueError(f"Missing prepared map layers: {', '.join(missing)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pmtiles-", dir=output_path.parent) as temporary:
        staging = Path(temporary)
        tile_layers = {}
        for name, source in POLYGON_LAYERS.items():
            normalized = staging / f"{name}.geojson"
            subprocess.run([
                ogr2ogr, "-f", "GeoJSON", "-s_srs", "EPSG:4979", "-t_srs", "EPSG:4326",
                "-dim", "XY", "-lco", "RFC7946=YES", "-lco", "COORDINATE_PRECISION=6",
                str(normalized), str(source),
            ], check=True)
            tile_layers[name] = normalized
        boundaries = staging / "boundaries.geojson"
        archive = staging / output_path.name
        subprocess.run([
            ogr2ogr, "-f", "GeoJSON", "-s_srs", "EPSG:2056", "-t_srs", "EPSG:4326",
            "-dim", "XY", "-nln", "boundaries", "-lco", "RFC7946=YES",
            "-lco", "COORDINATE_PRECISION=6",
            str(boundaries), str(source_path), "-dialect", "SQLite", "-sql",
            "SELECT geom, CASE objektart WHEN '1' THEN 2 WHEN '2' THEN 4 "
            "WHEN '3' THEN 6 WHEN '4' THEN 8 END AS admin_level, icc, typ "
            f"FROM {BOUNDARY_SOURCE_LAYER}",
        ], check=True)
        tile_layers["boundaries"] = boundaries
        subprocess.run([
            tippecanoe,
            "--output", str(archive),
            "--minimum-zoom", "0",
            "--maximum-zoom", "14",
            "--generate-ids",
            "--detect-shared-borders",
            "--no-feature-limit",
            "--no-tile-size-limit",
            "--name", "IndexMap administrative boundaries",
            "--attribution", "Geographic data: swisstopo",
            *(argument for name, path in tile_layers.items()
              for argument in ("--named-layer", named_layer(name, path))),
        ], check=True)
        if not archive.is_file() or archive.stat().st_size == 0:
            raise ValueError("Tippecanoe did not create a PMTiles archive")
        archive.replace(output_path)
    print(f"Generated five-layer PMTiles archive in {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DIST_DIR / "tiles/boundaries.pmtiles")
    args = parser.parse_args()
    try:
        build(args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"PMTiles generation failed: {error}\n")


if __name__ == "__main__":
    main()
