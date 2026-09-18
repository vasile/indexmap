# Site generators

Generate the website from prepared boundary data. Edit `templates/` and `assets/`,
then rebuild; do not edit generated files in `dist/` directly.

## Build

From the repository root, with `data-pipeline/requirements.txt` installed in
`data-pipeline/.venv`:

```sh
data-pipeline/.venv/bin/python data-pipeline/30-generate-country-pages.py
data-pipeline/.venv/bin/python data-pipeline/32-generate-canton-pages.py
data-pipeline/.venv/bin/python data-pipeline/34-generate-district-pages.py
data-pipeline/.venv/bin/python data-pipeline/36-generate-municipality-pages.py
data-pipeline/.venv/bin/python data-pipeline/38-generate-seo.py
```

Run only the relevant page generator when changing one section. Run step 38
after page generation to update `sitemap.xml`, `robots.txt`, and `llms.txt`.

Inputs are prepared by pipeline steps 20–26 in
`data/processed/<reference-date>/`. Release dates and paths are configured in
`data-pipeline/config/`. See the [pipeline README](../data-pipeline/README.md)
for data preparation.

Output goes to `dist/`: the homepage, country/canton/district/municipality pages,
GeoJSON and ZIP downloads, images, and shared assets. Directory maps load combined
boundaries; detail pages load the selected boundary. The page generators accept
`--input-dir` and `--output-dir` overrides.

Collections and bulk downloads use plural folders; individual pages, boundaries
and icons use singular folders:

| Collection | Individual example |
| --- | --- |
| `/countries/` | `/country/ch.html` |
| `/cantons/` | `/canton/zh.html` |
| `/districts/` | `/district/101.html` |
| `/municipalities/` | `/municipality/4551.html` |

## Historical releases

**Page generators only build the current website.** Historical GeoJSON and ZIP
downloads are built separately by `data-pipeline/28-build-release-assets.py`
under `dist/versions/<reference-date>/`, without duplicated HTML pages or icons.
See the [pipeline README](../data-pipeline/README.md#historical-release-assets).

Page builds do not modify or remove existing historical folders. Preserve the
data releases you want to keep across deployments. New historical downloads use
the same plural/singular convention. Existing archives are not migrated or deleted.

## Municipality icons

Website builds, including GitHub Actions, read the committed folder:

```text
data/source/coat-of-arms/municipalities-web/
```

It contains small WebP icons, `placeholder.webp`, and a compact `index.json`
with credits and original download links. Step 36 copies the icons and embeds
credits below the Commons download buttons. Missing icons use the placeholder.

After fetching new originals, prepare web assets **locally**:

```sh
fetch-coat-of-arms/.venv/bin/python fetch-coat-of-arms/prepare_web_icons.py
```

Commit the prepared WebPs and compact manifest. Original PNGs, the large source
manifest, and the conversion cache are not needed by GitHub Actions. See the
[fetcher README](../fetch-coat-of-arms/README.md) for preparation details.

## SEO and checks

Canonical URLs use `site_url` from `data-pipeline/config/pipeline.yaml`
(`https://indexmap.ch`). The sitemap includes current pages and excludes downloads
and historical archives. The curated `site-generator/llms.txt` overview is copied
to the site root by step 38. Deploy `dist/` at the domain root.

Run the regression checks with:

```sh
data-pipeline/.venv/bin/python -m unittest discover -s data-pipeline/tests -v
```
