#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess

from config import INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR


OUTPUT_DIR = Path(f"{PROCESSED_DIR}/cantons")
SOURCE_LAYER = "tlm_kantonsgebiet"

# swissBOUNDARIES3D uses the official canton numbering order.
CANTON_CODES = {
    1: "zh",
    2: "be",
    3: "lu",
    4: "ur",
    5: "sz",
    6: "ow",
    7: "nw",
    8: "gl",
    9: "zg",
    10: "fr",
    11: "so",
    12: "bs",
    13: "bl",
    14: "sh",
    15: "ar",
    16: "ai",
    17: "sg",
    18: "gr",
    19: "ag",
    20: "tg",
    21: "ti",
    22: "vd",
    23: "vs",
    24: "ne",
    25: "ge",
    26: "ju",
}


def convert_canton(ogr2ogr: str, canton_number: int, canton_code: str) -> None:
    output_path = Path(f"{OUTPUT_DIR}/{canton_code}.geojson")

    command = [
        ogr2ogr,
        "-f",
        "GeoJSON",
        "-s_srs",
        "EPSG:2056",
        "-t_srs",
        "EPSG:4326",
        "-where",
        f"kantonsnummer = {canton_number}",
        "-nln",
        "canton",
        "-lco",
        "RFC7946=YES",
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

    for canton_number, canton_code in CANTON_CODES.items():
        convert_canton(ogr2ogr, canton_number, canton_code)


if __name__ == "__main__":
    main()
