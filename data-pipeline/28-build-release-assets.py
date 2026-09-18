#!/usr/bin/env python3
"""Prepare catalogued releases and publish dated boundary downloads, without HTML."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from config.loader import (SCRIPT_DIR, CONFIG_DIR, CURRENT_INPUT_PATH, CURRENT_REFERENCE_DATE,
                    RELEASE_SOURCE_DIR, PROCESSED_ROOT, DIST_DIR, read_releases)


def download_path(path, processed):
    relative = path.relative_to(processed)
    section = relative.parts[0]
    singular = {"countries": "country", "cantons": "canton",
                "districts": "district", "municipalities": "municipality"}[section]
    combined = "ch-li.geojson" if section == "countries" else f"{section}.geojson"
    folder = section if path.suffix == ".zip" or path.name == combined else singular
    return Path(folder) / path.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CONFIG_DIR / "releases.yaml")
    parser.add_argument("--release", action="append", help="Build only this catalog release (repeatable)")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR)
    args = parser.parse_args()
    releases = read_releases(args.catalog)
    if args.release:
        if set(args.release) - set(releases):
            parser.error("Requested release is not in the catalog")
        releases = {release: metadata for release, metadata in releases.items() if release in args.release}
    for release, metadata in releases.items():
        reference = metadata["reference_date"]
        source = RELEASE_SOURCE_DIR / release / "source.gpkg"
        # The current release must use the configured current source path so later
        # current-site steps (including PMTiles generation) read the same database.
        # Historical downloads remain isolated by release.
        if reference == CURRENT_REFERENCE_DATE:
            source = CURRENT_INPUT_PATH
        env = os.environ | {"INDEXMAP_REFERENCE_DATE": reference, "INDEXMAP_INPUT_PATH": str(source.resolve()),
                            "INDEXMAP_RELEASE_CATALOG": str(args.catalog.resolve())}
        print(f"Preparing release {release}", flush=True)
        for script in ("10-download-swissboundaries.py", "20-prepare-countries.py", "22-prepare-cantons.py",
                       "24-prepare-districts.py", "26-prepare-municipalities.py"):
            subprocess.run([sys.executable, str(SCRIPT_DIR / script)], env=env, check=True)
        processed = PROCESSED_ROOT / reference
        files = [path for section in ("countries", "cantons", "districts", "municipalities")
                 for path in (processed / section).iterdir() if path.suffix in (".geojson", ".zip")]
        # Validate every existing pinned file before publishing any new files.
        for path in files:
            target = args.output_dir / "versions" / reference / download_path(path, processed)
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise ValueError(f"Pinned download differs: {target}")
        for path in files:
            target = args.output_dir / "versions" / reference / download_path(path, processed)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(path, target)
        total = sum(path.stat().st_size for path in files)
        print(f"Published {release}: {len(files)} boundary assets, {total / 1_000_000:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
