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

