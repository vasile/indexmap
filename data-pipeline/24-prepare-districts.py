#!/usr/bin/env python3

from pathlib import Path
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import shutil
import sqlite3
import subprocess

from config.loader import INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR


OUTPUT_DIR = Path(f"{PROCESSED_DIR}/districts")
SOURCE_LAYER = "tlm_bezirksgebiet"


def convert_district(ogr2ogr: str, district_number: int) -> None:
    output_path = Path(f"{OUTPUT_DIR}/{district_number}.geojson")

    command = [
        ogr2ogr,
        "-f",
        "GeoJSON",
        "-s_srs",
        "EPSG:2056",
        "-t_srs",
        "EPSG:4326",
        "-where",
        f"bezirksnummer = {district_number}",
        "-nln",
        "district",
        "-lco",
        "RFC7946=YES",  # Normalize winding: counterclockwise shells, clockwise holes.
        "-lco",
        "COORDINATE_PRECISION=6",
        str(output_path),
        str(INPUT_PATH),
        SOURCE_LAYER,
    ]

    output_path.unlink(missing_ok=True)
    subprocess.run(command, check=True)
    print(f"Created {output_path}")


def build_downloads(numbers):
    features = []
    with ZipFile(OUTPUT_DIR / "districts.zip", "w", compression=ZIP_DEFLATED) as archive:
        for number in numbers:
            name = f"{number}.geojson"
            raw = (OUTPUT_DIR / name).read_bytes()
            collection = json.loads(raw)
            if collection.get("type") != "FeatureCollection" or len(collection.get("features", [])) != 1:
                raise ValueError(f"Expected one district in {name}")
            feature = collection["features"][0]
            if feature["properties"]["bezirksnummer"] != number:
                raise ValueError(f"District number mismatch in {name}")
            features.append(feature)
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
    (OUTPUT_DIR / "districts.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Created combined GeoJSON and ZIP for {len(features)} districts")


def main() -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise SystemExit("ogr2ogr was not found in PATH")

    if not INPUT_PATH.is_file():
        raise SystemExit(f"Input GeoPackage not found: {INPUT_PATH}")

    connection = sqlite3.connect(f"{INPUT_PATH.as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            f"SELECT DISTINCT bezirksnummer FROM {SOURCE_LAYER} "
            "WHERE bezirksnummer IS NOT NULL ORDER BY bezirksnummer"
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        raise SystemExit(f"No districts found in {SOURCE_LAYER}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for (district_number,) in rows:
        convert_district(ogr2ogr, int(district_number))
    build_downloads([int(row[0]) for row in rows])


if __name__ == "__main__":
    main()
