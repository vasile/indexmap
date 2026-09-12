"""Load and validate YAML configuration; derive runtime paths for pipeline scripts."""

from datetime import date
import os
from pathlib import Path
import re

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is required. Activate data-pipeline/.venv and install data-pipeline/requirements.txt")

CONFIG_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = CONFIG_DIR.parent


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate settings instead of silently taking the last value."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path):
    with Path(path).open(encoding="utf-8") as source:
        value = yaml.load(source, Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def iso_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a quoted YYYY-MM-DD date")
    date.fromisoformat(value)
    return value


def read_releases(path):
    releases = load_yaml(path).get("releases")
    if not isinstance(releases, dict) or not releases:
        raise ValueError("Release catalog must contain a nonempty releases mapping")
    for release, metadata in releases.items():
        if not isinstance(release, str) or not re.fullmatch(r"\d{4}-\d{2}", release) or not isinstance(metadata, dict):
            raise ValueError(f"Invalid release entry: {release}")
        reference = iso_date(metadata.get("reference_date"), f"{release}.reference_date")
        if reference[:7] != release:
            raise ValueError(f"Release and reference date disagree: {release}")
        if metadata.get("population_date") is not None:
            iso_date(metadata["population_date"], f"{release}.population_date")
        url = metadata.get("population_source_url")
        if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
            raise ValueError(f"Invalid population source URL for {release}")
    return releases


PIPELINE = load_yaml(CONFIG_DIR / "pipeline.yaml")
RELEASES = read_releases(Path(os.environ.get("INDEXMAP_RELEASE_CATALOG", CONFIG_DIR / "releases.yaml")))
CURRENT_RELEASE = PIPELINE["current_release"]
if CURRENT_RELEASE not in RELEASES:
    raise ValueError("current_release must exist in releases.yaml")
CURRENT_REFERENCE_DATE = RELEASES[CURRENT_RELEASE]["reference_date"]
REFERENCE_DATE = iso_date(os.environ.get("INDEXMAP_REFERENCE_DATE", CURRENT_REFERENCE_DATE), "reference date")
SWISSBOUNDARIES_RELEASE = REFERENCE_DATE[:7]
if SWISSBOUNDARIES_RELEASE not in RELEASES or RELEASES[SWISSBOUNDARIES_RELEASE]["reference_date"] != REFERENCE_DATE:
    raise ValueError("Selected reference date is not in the release catalog")


def configured_path(key):
    value = PIPELINE["paths"][key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid path setting: {key}")
    return (SCRIPT_DIR / value).resolve()


CURRENT_INPUT_PATH = configured_path("current_source")
RELEASE_SOURCE_DIR = configured_path("release_sources")
PROCESSED_ROOT = configured_path("processed")
SITE_DIR = configured_path("site")
DIST_DIR = configured_path("output")
INPUT_PATH = Path(os.environ.get("INDEXMAP_INPUT_PATH", CURRENT_INPUT_PATH if SWISSBOUNDARIES_RELEASE == CURRENT_RELEASE
                                else RELEASE_SOURCE_DIR / SWISSBOUNDARIES_RELEASE / "source.gpkg")).resolve()
OUTPUT_DIR = PROCESSED_ROOT / REFERENCE_DATE
url_template = PIPELINE["swissboundaries"]["download_url"]
if not isinstance(url_template, str) or not url_template.startswith("https://") or "{release}" not in url_template:
    raise ValueError("Download URL must be HTTPS and contain {release}")
SWISSBOUNDARIES_DOWNLOAD_URL = url_template.format(release=SWISSBOUNDARIES_RELEASE)

CANTONS = load_yaml(CONFIG_DIR / "cantons.yaml").get("cantons")
if not isinstance(CANTONS, dict) or len(CANTONS) != 26:
    raise ValueError("Expected 26 canton lookup entries")
CANTON_CODES = {}
for code, canton in CANTONS.items():
    if not isinstance(code, str) or not re.fullmatch(r"[a-z]{2}", code) or not isinstance(canton, dict):
        raise ValueError(f"Invalid canton: {code}")
    number = canton.get("bfs_number")
    if type(number) is not int or number not in range(1, 27) or number in CANTON_CODES:
        raise ValueError(f"Invalid or duplicate canton BFS number: {number}")
    if not isinstance(canton.get("seat"), str) or not canton["seat"].strip():
        raise ValueError(f"Missing seat for {code}")
    display_name = canton.get("display_name")
    if display_name is not None and (not isinstance(display_name, str) or not display_name.strip()):
        raise ValueError(f"Invalid display name for {code}")
    if type(canton.get("verified")) is not bool:
        raise ValueError(f"Invalid verification status for {code}")
    CANTON_CODES[number] = code
CANTON_CODES = dict(sorted(CANTON_CODES.items()))


def population_metadata():
    metadata = RELEASES[SWISSBOUNDARIES_RELEASE]
    if metadata.get("population_date") is None:
        raise ValueError(f"Population date for {SWISSBOUNDARIES_RELEASE} is unverified; fill config/releases.yaml before generating pages")
    return dict(metadata)
