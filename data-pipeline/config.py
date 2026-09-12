from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = Path(f"{SCRIPT_DIR}/data/source/swissBOUNDARIES3D/swissBOUNDARIES3D_1_5_LV95_LN02.gpkg")

# use from https://www.swisstopo.admin.ch/en/landscape-model-swissboundaries3d
REFERENCE_DATE = "2026-01-01"
date.fromisoformat(REFERENCE_DATE) # validate

OUTPUT_DIR = SCRIPT_DIR / "data/processed" / REFERENCE_DATE
SWISSBOUNDARIES_RELEASE = REFERENCE_DATE[:7]
SWISSBOUNDARIES_DOWNLOAD_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/"
    f"swissboundaries3d_{SWISSBOUNDARIES_RELEASE}/"
    f"swissboundaries3d_{SWISSBOUNDARIES_RELEASE}_2056_5728.gpkg.zip"
)


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
