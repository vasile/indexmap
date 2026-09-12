#!/usr/bin/env python3

from pathlib import Path
import shutil
import sqlite3
import subprocess

from config import INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR


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


if __name__ == "__main__":
    main()
