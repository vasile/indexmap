# Site generators

Run from the project root after activating `data-pipeline/.venv` and installing
`data-pipeline/requirements.txt` (PyYAML):

```sh
python3 data-pipeline/30-generate-country-pages.py
python3 data-pipeline/32-generate-canton-pages.py
python3 data-pipeline/34-generate-district-pages.py
python3 data-pipeline/36-generate-municipality-pages.py
```

Step 30 reads `data/processed/<reference-date>/countries/{ch,li,ch-li,ch-li-dissolved}.geojson`
from step 20. It generates the root `index.html` homepage. It also generates
`countries/index.html`, `countries/ch.html`, `countries/li.html`, and
`countries/ch-li-dissolved.html`, plus unchanged GeoJSON assets, at both current and
pinned paths. Country detail pages show population and area from the data,
and share the boundary map and optional browser mask with canton pages.
The GUI section label is “Country”; its directory contains Switzerland and
Liechtenstein. The plain directory lists Switzerland, then Liechtenstein.
The directory has Individual and Combined radio sections. Individual shows both
country features on the map; Combined shows the dissolved boundary. The combined
row opens its detail page with GeoJSON download and the browser mask control.
Both sections remain visible, separated by a rule, with Individual selected initially.
Use `--current-only` with step 30 to update current output while leaving pinned
releases alone (including when introducing new assets during development).
The country templates use English display names. The homepage renders the Country
directory directly, using the same templates with links relative to the site root.
It includes the map, country details and downloads without a redirect.
`countries/index.html` remains available at both current and pinned paths; the
homepage is generated only at the current root.

The command also works from other directories when invoked by its absolute
path. It does not read the GeoPackage directly or depend on the archived mock.

Inputs:

- `data/processed/<reference-date>/cantons/*.geojson`, produced by pipeline step 22.
- `data/processed/<reference-date>/cantons/cantons.geojson` and `cantons.zip`, also built by
  step 22 after exporting all individual cantons. Step 32 copies these unchanged.
- `data/processed/<reference-date>/cantons/*.png`, produced by step 22.
- `data-pipeline/config/cantons.yaml`: canton codes, BFS numbers, seats and optional display names.
- `data-pipeline/config/pipeline.yaml`: current release and paths.
- `data-pipeline/config/releases.yaml`: boundary reference date and population date/source for each release.
- `site-generator/templates/` and `site-generator/assets/`: page layout and shared assets.

Outputs:

- `dist/cantons/index.html`: alphabetical, searchable directory.
- `dist/cantons/{code}.html`: detail pages that load `{code}.geojson` for the map.
- `dist/cantons/{code}.geojson` and `{code}.png`: original downloads.
- `dist/cantons/cantons.geojson`: combined FeatureCollection.
- `dist/cantons/cantons.zip`: all 26 individual GeoJSON files.
- `dist/assets/`: CSS, browser configuration, and JavaScript.

The same structure is also published under `dist/versions/<reference-date>/`, including
its own assets. For example, both `/cantons/zh.geojson` (current) and
`/versions/2026-01-01/cantons/zh.geojson` (pinned) are available. Pages and their relative
links work at either location.

A dated section snapshot is created once. Steps 30 and 32 can each add their
section to the same release, in either order. Later builds retain its pages and assets,
and reject changed download bytes for that release before updating current
output. Older dated folders are never removed. Preserve these folders across
deployments: a fresh CI checkout must restore earlier snapshots before building
if the deployment replaces the whole site. The generator cannot restore past
releases from only the current inputs.

All pages share `base.html`. Edit templates and rebuild; do not edit generated
files. The build validates every canton's inputs and renders all templates
before writing outputs. It replaces current files without clearing other site
sections. `--input-dir` overrides the processed canton directory and
`--output-dir` overrides `dist`.

Preview over HTTP so the browser can fetch the GeoJSON:

```sh
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/` for the Country homepage or `/cantons/` for cantons.
The map uses a public Mapbox token injected into generated `assets/config.js`; Mapbox and the
Bootstrap CDN require network access. HTML facts and download links remain
available if the map fails.

When updating datasets, check the population date against the release
notes. Existing seats and multilingual display names were retained from the
original layout; the lookup records the seat verification status.

Step 20 also copies country coat-of-arms PNGs to
processed countries. Step 30 publishes these alongside the GeoJSONs, displays
the images in individual country rows and detail titles, and provides PNG
downloads. Source credits and reuse terms remain in `data/source/coat-of-arms/README.md`;
they are not copied to processed data or published pages.

The country directory uses the same bulk-download panel as cantons: `ch-li.geojson`
contains both individual country features, and `countries.zip` contains their
separate GeoJSON files. These downloads are independent of the map radio selection.

District and municipality pages are generated with steps 34 and 36 after
preparation steps 24 and 26. Their directories support search by name, BFS number
or canton. Details reuse the boundary/download layout and browser masking;
no coats of arms are provided for these levels yet. The directory maps initially
show the basemap; detail pages fetch only the selected boundary. Bulk downloads
include a combined FeatureCollection and a ZIP of individual GeoJSON files.

## Mapbox token

The four page generators load `.env` defaults, then environment variables,
then `.env.local` overrides (highest priority).
They generate `dist/assets/config.js`; there is no token in the source assets.
For local builds, copy `.env` to `.env.local` and fill in the public token.
The `.env.local` file is ignored by Git and is found regardless of the working directory.
Any key present in `.env.local` overrides the environment, including an empty value.
On GitHub Actions, `.env.local` is absent, so repository secrets override `.env`.
The token is included in the asset hash, so changing it updates cache versions.

For GitHub Actions, create a repository secret named `MAPBOX_ACCESS_TOKEN`
and pass it to the page-generation step:

```yaml
env:
  MAPBOX_ACCESS_TOKEN: ${{ secrets.MAPBOX_ACCESS_TOKEN }}
```

Use a public (`pk.`) Mapbox token. It is hidden from the source repository but
visible in the published JavaScript. Secret (`sk.`) tokens are rejected.
Existing pinned page snapshots retain their original assets.
