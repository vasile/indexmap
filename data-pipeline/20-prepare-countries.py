#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess

from config import INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR


OUTPUT_DIR = Path(f"{PROCESSED_DIR}/countries")
SOURCE_LAYER = "tlm_landesgebiet"


def convert_country(ogr2ogr: str, country_filter: str, output_name: str) -> None:
    output_path = Path(f"{OUTPUT_DIR}/{output_name}.geojson")

    command = [
        ogr2ogr,
        "-f",
        "GeoJSON",
        "-s_srs",
        "EPSG:2056",
        "-t_srs",
        "EPSG:4326",
        "-where",
        country_filter,
        "-nln",
        "country",
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    convert_country(ogr2ogr, "icc = 'CH'", "ch")
    convert_country(ogr2ogr, "icc = 'LI'", "li")
    convert_country(ogr2ogr, "icc IN ('CH', 'LI')", "ch-li")


if __name__ == "__main__":
    main()
