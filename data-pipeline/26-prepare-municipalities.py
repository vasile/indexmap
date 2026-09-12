#!/usr/bin/env python3
"""Export CH/LI municipalities, individual GeoJSONs and bulk downloads."""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from config.loader import INPUT_PATH, OUTPUT_DIR


def main():
    ogr2ogr = shutil.which("ogr2ogr")
    if not ogr2ogr or not INPUT_PATH.is_file():
        raise SystemExit("Requires ogr2ogr and the source GeoPackage; run step 10 first")
    destination = OUTPUT_DIR / "municipalities"
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".municipalities-", dir=OUTPUT_DIR) as temporary:
        staging = Path(temporary)
        exported = staging / "export.geojson"
        subprocess.run([
            ogr2ogr, "-f", "GeoJSON", "-s_srs", "EPSG:2056", "-t_srs", "EPSG:4326",
            "-where", "icc IN ('CH', 'LI') AND objektart = 'Gemeindegebiet'",
            "-nln", "municipality", "-lco", "RFC7946=YES",  # Normalize ring winding.
            "-lco", "COORDINATE_PRECISION=6", str(exported), str(INPUT_PATH), "tlm_hoheitsgebiet",
        ], check=True)
        features = json.loads(exported.read_text())["features"]
        if not features:
            raise ValueError("No municipalities found")
        features.sort(key=lambda feature: feature["properties"]["bfs_nummer"])
        seen = set()
        with ZipFile(staging / "municipalities.zip", "w", compression=ZIP_DEFLATED) as archive:
            for feature in features:
                number = feature["properties"]["bfs_nummer"]
                if not isinstance(number, int) or number <= 0 or number in seen:
                    raise ValueError(f"Invalid or duplicate municipality number: {number}")
                if feature["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
                    raise ValueError(f"Invalid municipality geometry: {number}")
                seen.add(number)
                name = f"{number}.geojson"
                raw = encode_collection([feature])
                (staging / name).write_bytes(raw)
                info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, raw)
        (staging / "municipalities.geojson").write_bytes(encode_collection(features))
        exported.unlink()
        for path in staging.iterdir():
            shutil.copyfile(path, destination / path.name)
        # Remove retired municipality files when rebuilding the same reference date.
        for path in destination.glob("*.geojson"):
            if path.stem.isdigit() and int(path.stem) not in seen:
                path.unlink()
    print(f"Created {len(features)} municipality GeoJSONs, combined GeoJSON and ZIP in {destination}")


def encode_collection(features):
    return (json.dumps({"type": "FeatureCollection", "features": features},
                       ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


if __name__ == "__main__":
    main()
