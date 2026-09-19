# Basemap styles

`swisstopo-light.json` is a local copy of swisstopo's Light Base Map style:

- Source: https://vectortiles.geo.admin.ch/styles/ch.swisstopo.lightbasemap.vt/style.json
- Service overview and available styles: https://www.geo.admin.ch/en/vector-tiles-service-available-services-and-data
- Provider: [Federal Office of Topography swisstopo](https://www.swisstopo.admin.ch/)

The site build copies the style into `dist/assets/` and creates a fingerprinted
version for cache-safe deployment. The vector tiles, glyphs, and sprites remain
hosted by `vectortiles.geo.admin.ch` and are referenced by the style.
