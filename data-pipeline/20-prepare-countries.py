#!/usr/bin/env python3

from pathlib import Path
import json
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from config.loader import INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR, SCRIPT_DIR


OUTPUT_DIR = Path(f"{PROCESSED_DIR}/countries")
SOURCE_LAYER = "tlm_landesgebiet"


def convert_country(ogr2ogr: str, country_filter: str, output_name: str, *, dissolve=False,
                    simplify=None) -> None:
    output_path = Path(f"{OUTPUT_DIR}/{output_name}.geojson")

    command = [
        ogr2ogr,
        "-f",
        "GeoJSON",
        "-s_srs",
        "EPSG:2056",
        "-t_srs",
        "EPSG:4326",
        "-nln",
        "country",
        "-lco",
        "RFC7946=YES",  # Normalize winding: counterclockwise shells, clockwise holes.
        "-lco",
        "COORDINATE_PRECISION=6",
        str(output_path),
        str(INPUT_PATH),
    ]
    if simplify is not None:
        command[1:1] = ["-simplify", str(simplify)]
    if dissolve:
        # Union in the source CRS before reprojection/rounding removes the shared border.
        command.extend(["-dialect", "SQLite", "-sql",
                        "SELECT ST_Union(geom) AS geom, 'CH+LI' AS icc, "
                        "'Switzerland + Liechtenstein' AS name "
                        f"FROM {SOURCE_LAYER} WHERE {country_filter}"])
    else:
        command.extend(["-where", country_filter, SOURCE_LAYER])

    output_path.unlink(missing_ok=True)
    subprocess.run(command, check=True)
    print(f"Created {output_path}")


def build_territory_mask(ogr2ogr: str) -> None:
    """Create the inverse map mask from the same dissolved CH+LI source."""
    temporary_name = ".ch-li-mask-boundary"
    temporary_path = OUTPUT_DIR / f"{temporary_name}.geojson"
    try:
        # Simplification runs in EPSG:2056, so the tolerance is 10 metres.
        convert_country(ogr2ogr, "icc IN ('CH', 'LI')", temporary_name,
                        dissolve=True, simplify=10)
        data = json.loads(temporary_path.read_text())
        features = data.get("features", [])
        if len(features) != 1 or features[0].get("geometry", {}).get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("Expected one simplified CH+LI polygon")
        geometry = features[0]["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        outside = [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]]
        islands = []
        inverse_ring = lambda ring: [position[:] for position in reversed(ring)]
        for shell, *holes in polygons:
            outside.append(inverse_ring(shell))
            islands.extend([[inverse_ring(hole)] for hole in holes])
        mask_geometry = ({"type": "MultiPolygon", "coordinates": [outside, *islands]}
                         if islands else {"type": "Polygon", "coordinates": outside})
        mask = {"type": "FeatureCollection", "name": "ch-li-mask", "features": [{
            "type": "Feature",
            "properties": {"name": "Outside Switzerland and Liechtenstein"},
            "geometry": mask_geometry,
        }]}
        output_path = OUTPUT_DIR / "ch-li-mask.geojson"
        output_path.write_text(json.dumps(mask, separators=(",", ":")) + "\n")
        print(f"Created {output_path}")
    finally:
        temporary_path.unlink(missing_ok=True)


def build_downloads() -> None:
    zip_path = OUTPUT_DIR / "countries.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for code in ("ch", "li"):
            name = f"{code}.geojson"
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, (OUTPUT_DIR / name).read_bytes())
    print(f"Created {zip_path}")


def main() -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise SystemExit("ogr2ogr was not found in PATH")

    if not INPUT_PATH.is_file():
        raise SystemExit(f"Input GeoPackage not found: {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    convert_country(ogr2ogr, "icc = 'CH'", "ch")
    convert_country(ogr2ogr, "icc = 'LI'", "li")
    convert_country(ogr2ogr, "icc IN ('CH', 'LI')", "ch-li")
    convert_country(ogr2ogr, "icc IN ('CH', 'LI')", "ch-li-dissolved", dissolve=True)
    build_territory_mask(ogr2ogr)

    build_downloads()

    image_source = SCRIPT_DIR / "data/source/coat-of-arms"
    for code in ("ch", "li"):
        shutil.copyfile(image_source / "countries" / f"{code}.png", OUTPUT_DIR / f"{code}.png")


if __name__ == "__main__":
    main()
