#!/usr/bin/env python3

import shutil

from config import CANTON_CODES, OUTPUT_DIR as PROCESSED_DIR, SCRIPT_DIR


SOURCE_DIR = SCRIPT_DIR / "data/source/coat-of-arms/cantons"
OUTPUT_DIR = PROCESSED_DIR / "cantons"


def main() -> None:
    missing = [code for code in CANTON_CODES.values() if not (SOURCE_DIR / f"{code}.png").is_file()]
    if missing:
        raise SystemExit(f"Missing canton coat-of-arms images: {', '.join(missing)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for code in CANTON_CODES.values():
        output_path = OUTPUT_DIR / f"{code}.png"
        shutil.copyfile(SOURCE_DIR / f"{code}.png", output_path)
        print(f"Created {output_path}")


if __name__ == "__main__":
    main()
