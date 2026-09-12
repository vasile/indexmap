#!/usr/bin/env python3
"""Download the pinned swissBOUNDARIES3D LV95/LN02 GeoPackage from swisstopo."""

import argparse
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from config import INPUT_PATH, SWISSBOUNDARIES_DOWNLOAD_URL, SWISSBOUNDARIES_RELEASE


def validate_geopackage(path: Path) -> None:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as database:
        layers = {row[0] for row in database.execute("SELECT table_name FROM gpkg_contents")}
    required = {"tlm_landesgebiet", "tlm_kantonsgebiet", "tlm_bezirksgebiet", "tlm_hoheitsgebiet"}
    if not required <= layers:
        raise ValueError(f"GeoPackage missing pipeline layers: {', '.join(sorted(required - layers))}")


def download(output: Path, force: bool = False) -> None:
    if output.is_file() and not force:
        validate_geopackage(output)
        print(f"Using existing {output} (release not rechecked; use --force to replace)")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the existing file intact until download, extraction, and validation succeed.
    with TemporaryDirectory(prefix="swissboundaries-", dir=output.parent) as temporary:
        directory = Path(temporary)
        archive_path = directory / "source.zip"
        request = Request(SWISSBOUNDARIES_DOWNLOAD_URL, headers={"User-Agent": "IndexMap-data-pipeline"})
        print(f"Downloading swissBOUNDARIES3D {SWISSBOUNDARIES_RELEASE}", flush=True)
        with urlopen(request, timeout=120) as response, archive_path.open("wb") as destination:
            shutil.copyfileobj(response, destination, length=1024 * 1024)
        extracted = directory / "source.gpkg"
        with ZipFile(archive_path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".gpkg")]
            if len(members) != 1:
                raise ValueError("Expected exactly one GeoPackage in the swisstopo archive")
            # Stream just the database to a fixed path; ignore other archive paths.
            with archive.open(members[0]) as source, extracted.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        validate_geopackage(extracted)
        extracted.replace(output)
    print(f"Created {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=INPUT_PATH)
    parser.add_argument("--force", action="store_true", help="Replace an existing GeoPackage with the configured release")
    args = parser.parse_args()
    try:
        download(args.output, args.force)
    except (OSError, ValueError, sqlite3.Error, BadZipFile) as error:
        parser.exit(1, f"swissBOUNDARIES3D download failed: {error}\n")


if __name__ == "__main__":
    main()
