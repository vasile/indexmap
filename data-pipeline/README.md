# Data pipeline

Numbering: 10–19 downloads, 20–29 data preparation, 30–39 site generation.
Entity slots are paired: countries 20/30, cantons 22/32, districts 24/34,
municipalities 26/36. All four preparation and site-generation pairs are implemented.
Canton preparation (22) exports GeoJSONs, builds both bulk downloads, and
copies coat-of-arms PNGs.

Set up the Python environment once, then activate it for pipeline commands:

```sh
python3 -m venv data-pipeline/.venv
source data-pipeline/.venv/bin/activate
python -m pip install -r data-pipeline/requirements.txt
```

Run from the project root:

```sh
python3 data-pipeline/10-download-swissboundaries.py
python3 data-pipeline/20-prepare-countries.py
python3 data-pipeline/22-prepare-cantons.py
python3 data-pipeline/24-prepare-districts.py
python3 data-pipeline/26-prepare-municipalities.py
python3 data-pipeline/30-generate-country-pages.py
python3 data-pipeline/32-generate-canton-pages.py
python3 data-pipeline/34-generate-district-pages.py
python3 data-pipeline/36-generate-municipality-pages.py
```

PyYAML loads configuration; the Python standard library handles downloading and generating the site.
Steps 20–26 also require GDAL's `ogr2ogr` (Ubuntu package: `gdal-bin`).

Step 20 exports individual CH and LI files, `ch-li.geojson` containing both
country features, and `ch-li-dissolved.geojson` containing their union. GDAL
SQLite `ST_Union` dissolves the shared border in the source CRS before
reprojection and coordinate rounding. The dissolved feature carries a combined
name and code, without country statistics. Masks are generated only in the browser.

These exports normalize polygon winding with GDAL's `RFC7946=YES`: exterior
rings counterclockwise, holes clockwise. No separate rewind pass is needed.
Browser masks wrap the prepared polygon rings with a world ring. They use no
Turf dependency or winding checks; ring copies are reversed when their role
changes between outer boundary and hole.
GDAL reference: https://gdal.org/en/stable/drivers/vector/geojson.html#rfc-7946-write-support

`current_release` in `config/pipeline.yaml` selects the dataset; its reference date
comes from `config/releases.yaml`, currently
`2026-01-01`. All processed outputs go into
`data/processed/2026-01-01/{countries,cantons,districts}`. Step 32 reads this
version automatically and publishes current paths under `dist/cantons` plus
a pinned snapshot under `dist/versions/2026-01-01`, including its own shared assets.
The date also supplies the boundary date displayed on the site and the
year-month release used for downloading. Rebuilding a release updates its
folder; changing the date preserves previously processed releases.

Step 10 downloads the official swissBOUNDARIES3D GeoPackage ZIP for LV95
(EPSG:2056) and LN02 (EPSG:5728), pinned to `SWISSBOUNDARIES_RELEASE`, derived
from the selected YAML release metadata. It extracts the database to `INPUT_PATH`, checks that the required
layers exist, and removes temporary download files. The existing database is
replaced only after the new one passes validation.

An existing valid GeoPackage is reused, including a locally linked source
directory. Its release is not independently checked. Use `--force` to replace
it with the configured release, or `--output /path/to/source.gpkg` for a
different destination. Changing the download destination does not change
the converters' `INPUT_PATH`.

For GitHub Actions, step 10 creates the source directory in a fresh checkout.
Do not commit the machine-specific source symlink or the downloaded database.
Cache keys should include `SWISSBOUNDARIES_RELEASE`. When changing releases,
run step 10 with `--force` to replace the old source database, then rerun
preprocessing. Check the population date in `config/releases.yaml`
against the new release notes; it is separate from the boundary reference date.

Official download catalogue:
https://ogd.swisstopo.admin.ch/ch.swisstopo.swissboundaries3d?lang=en

Step 20 also builds `countries/countries.zip` with the unchanged `ch.geojson`
and `li.geojson` files, using fixed ZIP timestamps like the canton archive.

Step 26 exports CH and LI `Gemeindegebiet` features from `tlm_hoheitsgebiet` in
one GDAL invocation, then writes individual `{bfs_nummer}.geojson` files,
`municipalities.geojson`, and `municipalities.zip`. It excludes cantonal/lake
territories, communal territories and municipalities outside CH/LI. Source
properties and six-decimal WGS 84 coordinates are retained; JSON is compact.
Step 24 also builds `districts.geojson` and `districts.zip` from individual districts.
Both ZIPs use the same fixed timestamps as country/canton bundles.

Steps 34 and 36 generate searchable directories and detail pages with boundary
previews, population, area, canton/country, GeoJSON downloads and browser masks.
They copy prepared downloads unchanged. Use `--current-only` for steps 30, 34
and 36 during development when keeping existing pinned releases unchanged.

## Historical release assets

`config/releases.yaml` lists the available dataset versions, newest first. Run:

```sh
python3 data-pipeline/28-build-release-assets.py
```

Use `--release 2025-04` to build one catalog entry. The catalog contains a `releases` mapping keyed by quoted `YYYY-MM` values,
each with a reference date and optional population date/source URL. Historical GeoPackages are cached in `data/source/boundary-releases/<release>`;
processed files go into `data/processed/<reference-date>`.

Step 28 runs downloading and all four preparation steps, then publishes GeoJSONs
and ZIPs under `dist/versions/<reference-date>/<entity>/`. It checks existing files before
adding missing assets and refuses to overwrite different pinned download bytes.
It does not regenerate historical HTML or change the current website. Source
image copies are not published as historical assets. Keep `dist` between builds
to preserve previously published releases.

`INDEXMAP_REFERENCE_DATE` and `INDEXMAP_INPUT_PATH` allow the batch runner to
select a dataset for each child process without editing the default config.

## Configuration

All maintained pipeline and site-generation settings live in `data-pipeline/config/`:

- `pipeline.yaml`: current release, project paths and download URL template.
- `releases.yaml`: ordered release catalog with boundary and population metadata.
- `cantons.yaml`: lowercase codes, BFS numbers, seats, display names and verification metadata.

`config/__init__.py` is empty. `config/loader.py` loads/validates YAML and derives runtime values. Paths
in `pipeline.yaml` resolve relative to `data-pipeline/`, regardless of the working
directory. The loader rejects duplicate keys, invalid dates and duplicate canton
numbers. Historical population dates are null until checked; asset preparation
works without them, but historical page generation requires a verified date.
