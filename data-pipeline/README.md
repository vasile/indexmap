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
```

Python's standard library handles downloading and generating the site.
Steps 20–24 also require GDAL's `ogr2ogr` (Ubuntu package: `gdal-bin`).

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

`REFERENCE_DATE` in `config.py` is the dataset's reference date, currently
`2026-01-01`. All processed outputs go into
`data/processed/2026-01-01/{countries,cantons,districts}`. Step 32 reads this
version automatically and publishes current paths under `dist/cantons` plus
a pinned snapshot under `dist/2026-01-01`, including its own shared assets.
The date also supplies the boundary date displayed on the site and the
year-month release used for downloading. Rebuilding a release updates its
folder; changing the date preserves previously processed releases.

Step 10 downloads the official swissBOUNDARIES3D GeoPackage ZIP for LV95
(EPSG:2056) and LN02 (EPSG:5728), pinned to `SWISSBOUNDARIES_RELEASE`, derived
from `REFERENCE_DATE` in `config.py`. It extracts the database to `INPUT_PATH`, checks that the required
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
preprocessing. Check the population date in `site-generator/config.json`
against the new release notes; it is separate from the boundary reference date.

Official download catalogue:
https://ogd.swisstopo.admin.ch/ch.swisstopo.swissboundaries3d?lang=en

Step 20 also builds `countries/countries.zip` with the unchanged `ch.geojson`
and `li.geojson` files, using fixed ZIP timestamps like the canton archive.
