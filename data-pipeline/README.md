# Data pipeline

Run from the project root:

```sh
python3 data-pipeline/00-download-swissboundaries.py
python3 data-pipeline/01-convert-country-geojson.py
python3 data-pipeline/02-convert-cantons-geojson.py
python3 data-pipeline/03-convert-districts-geojson.py
python3 data-pipeline/04-copy-canton-coat-of-arms.py
python3 data-pipeline/20-generate-cantons-pages.py
```

Python's standard library handles downloading and generating the site.
Steps 01–03 also require GDAL's `ogr2ogr` (Ubuntu package: `gdal-bin`).

`REFERENCE_DATE` in `config.py` is the dataset's reference date, currently
`2026-01-01`. All processed outputs go into
`data/processed/2026-01-01/{countries,cantons,districts}`. Step 20 reads this
version automatically and publishes current paths under `dist/cantons` plus
a pinned snapshot under `dist/2026-01-01`, including its own shared assets.
The date also supplies the boundary date displayed on the site and the
year-month release used for downloading. Rebuilding a release updates its
folder; changing the date preserves previously processed releases.

Step 00 downloads the official swissBOUNDARIES3D GeoPackage ZIP for LV95
(EPSG:2056) and LN02 (EPSG:5728), pinned to `SWISSBOUNDARIES_RELEASE`, derived
from `REFERENCE_DATE` in `config.py`. It extracts the database to `INPUT_PATH`, checks that the required
layers exist, and removes temporary download files. The existing database is
replaced only after the new one passes validation.

An existing valid GeoPackage is reused, including a locally linked source
directory. Its release is not independently checked. Use `--force` to replace
it with the configured release, or `--output /path/to/source.gpkg` for a
different destination. Changing the download destination does not change
the converters' `INPUT_PATH`.

For GitHub Actions, step 00 creates the source directory in a fresh checkout.
Do not commit the machine-specific source symlink or the downloaded database.
Cache keys should include `SWISSBOUNDARIES_RELEASE`. When changing releases,
run step 00 with `--force` to replace the old source database, then rerun
preprocessing. Check the population date in `site-generator/config.json`
against the new release notes; it is separate from the boundary reference date.

Official download catalogue:
https://ogd.swisstopo.admin.ch/ch.swisstopo.swissboundaries3d?lang=en
