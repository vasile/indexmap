#!/usr/bin/env python3

from pathlib import Path
import json
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from config import CANTON_CODES, INPUT_PATH, OUTPUT_DIR as PROCESSED_DIR, SCRIPT_DIR


OUTPUT_DIR = Path(f"{PROCESSED_DIR}/cantons")
SOURCE_LAYER = "tlm_kantonsgebiet"
COAT_OF_ARMS_DIR = SCRIPT_DIR / "data/source/coat-of-arms/cantons"


def copy_coat_of_arms() -> None:
    missing = [code for code in CANTON_CODES.values() if not (COAT_OF_ARMS_DIR / f"{code}.png").is_file()]
    if missing:
        raise SystemExit(f"Missing canton coat-of-arms images: {', '.join(missing)}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for code in CANTON_CODES.values():
        output_path = OUTPUT_DIR / f"{code}.png"
        shutil.copyfile(COAT_OF_ARMS_DIR / f"{code}.png", output_path)
        print(f"Created {output_path}")


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


def build_downloads() -> None:
    features = []
    files = {}
    for number, code in CANTON_CODES.items():
        path = OUTPUT_DIR / f"{code}.geojson"
        raw = path.read_bytes()
        data = json.loads(raw)
        if data.get("type") != "FeatureCollection" or len(data.get("features", [])) != 1:
            raise ValueError(f"{path}: expected one canton feature")
        feature = data["features"][0]
        if feature["properties"]["kantonsnummer"] != number:
            raise ValueError(f"{path}: canton number does not match {code}")
        features.append(feature)
        files[path.name] = raw

    collection = {"type": "FeatureCollection", "features": features}
    combined_path = OUTPUT_DIR / "cantons.geojson"
    combined_path.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    zip_path = OUTPUT_DIR / "cantons.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
    print(f"Created {combined_path}")
    print(f"Created {zip_path}")


def main() -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise SystemExit("ogr2ogr was not found in PATH")

    if not INPUT_PATH.is_file():
        raise SystemExit(f"Input GeoPackage not found: {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for canton_number, canton_code in CANTON_CODES.items():
        convert_canton(ogr2ogr, canton_number, canton_code)
    build_downloads()
    copy_coat_of_arms()


if __name__ == "__main__":
    main()
