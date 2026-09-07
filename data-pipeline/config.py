from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = Path(f"{SCRIPT_DIR}/data/source/swissBOUNDARIES3D/swissBOUNDARIES3D_1_5_LV95_LN02.gpkg")
OUTPUT_DIR = Path(f"{SCRIPT_DIR}/data/processed")
