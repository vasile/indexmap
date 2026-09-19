(async () => {
  "use strict";
  const scriptUrl = document.currentScript?.src;
  const assetQuery = scriptUrl ? new URL(scriptUrl).search : "";
  const tilesUrl = scriptUrl ? new URL("../tiles/boundaries.pmtiles", scriptUrl).href : "../tiles/boundaries.pmtiles";
  const boundaryColor = "#1d4ed8";
  const search = document.querySelector("#canton-search");
  const items = [...document.querySelectorAll(".canton-item")];
  const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const searchableItems = items.map(item => ({ item, text: normalize(item.dataset.search || "") }));
  const filterDirectory = () => {
    const terms = normalize(search.value).split(/\s+/).filter(Boolean);
    let count = 0;
    searchableItems.forEach(({ item, text }) => {
      item.hidden = !terms.every(term => text.includes(term));
      if (!item.hidden) count++;
    });
    document.querySelector("#result-count").textContent = count + (" " + (count === 1 ? (search.dataset.singular || "canton") : (search.dataset.plural || "cantons")));
    document.querySelector("#no-results").hidden = count !== 0;
  };
  search?.addEventListener("input", filterDirectory);
  if (search) {
    const query = new URLSearchParams(location.search).get("q");
    if (query) {
      search.value = query;
      filterDirectory();
    }
  }
  const container = document.querySelector("#map");
  const download = document.querySelector("#boundary-download");
  const maskCheckbox = document.querySelector("#boundary-mask");
  const maskCheckboxes = [...document.querySelectorAll("#boundary-mask, #map-boundary-mask")];
  const maskStatus = document.querySelector("#mask-status");
  const boundaryPromises = new Map();
  let activeGeometry;
  const loadBoundary = (url = container.dataset.geojson) => {
    if (!boundaryPromises.has(url)) {
      boundaryPromises.set(url, fetch(url).then(response => {
        if (!response.ok) throw new Error("Boundary request failed");
        return response.json();
      }).catch(error => { boundaryPromises.delete(url); throw error; }));
    }
    return boundaryPromises.get(url);
  };
  function previewGeometry(data) {
    activeGeometry = data;
    container.dispatchEvent(new CustomEvent("boundarychange", { detail: data }));
  }
  let countryModeRequest = 0;
  document.querySelectorAll('input[name="country-mode"]').forEach(input => {
    input.addEventListener("change", async () => {
      if (!input.checked) return;
      const request = ++countryModeRequest;
      const status = document.querySelector("#map-status");
      status.textContent = "Loading boundary…";
      status.hidden = false;
      try {
        const data = await loadBoundary(input.dataset.geojson);
        if (request !== countryModeRequest) return;
        previewGeometry(data);
        status.hidden = true;
      } catch {
        if (request !== countryModeRequest) return;
        status.textContent = "The boundary could not load. Select a section to try again.";
      }
    });
  });
  if (download && maskCheckbox) {
    const originalHref = download.getAttribute("href");
    const originalName = download.download;
    let requestId = 0;
    let objectUrl;
    let mask;
    let pending = false;
    download.addEventListener("click", event => { if (pending) event.preventDefault(); });
    maskCheckboxes.forEach(checkbox => checkbox.addEventListener("change", async () => {
      const checked = checkbox.checked;
      maskCheckboxes.forEach(input => { input.checked = checked; });
      const id = ++requestId;
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = undefined; }
      download.href = originalHref;
      download.download = originalName;
      download.textContent = "Download GeoJSON";
      pending = maskCheckbox.checked;
      download.setAttribute("aria-disabled", String(pending));
      maskStatus.hidden = !pending;
      maskStatus.textContent = pending ? "Generating mask…" : "";
      try {
        const boundary = await loadBoundary();
        if (id !== requestId) return;
        if (!maskCheckbox.checked) { previewGeometry(boundary); return; }
        if (!mask) {
          const { createInverseMask } = await import(`./mask.js${assetQuery}`);
          mask = createInverseMask(boundary);
        }
        if (id !== requestId) return;
        objectUrl = URL.createObjectURL(new Blob([JSON.stringify(mask, null, 2) + "\n"], { type: "application/geo+json" }));
        download.href = objectUrl;
        download.download = originalName.replace(/\.geojson$/, "-mask.geojson");
        download.textContent = "Download GeoJSON";
        previewGeometry(mask);
        maskStatus.hidden = true;
      } catch {
        if (id !== requestId) return;
        maskCheckboxes.forEach(input => { input.checked = false; });
        maskStatus.hidden = false;
        maskStatus.textContent = "The mask could not be generated. Try again; the boundary download is still available.";
      } finally {
        if (id === requestId) { pending = false; download.setAttribute("aria-disabled", "false"); }
      }
    }));
    window.addEventListener("pagehide", event => {
      if (!event.persisted && objectUrl) URL.revokeObjectURL(objectUrl);
    });
  }
  if (!container) return;
  const status = document.querySelector("#map-status");
  function showError(error) {
    if (error) console.error("IndexMap: map loading error.", error.error || error);
    status.hidden = false;
    status.textContent = "The basemap could not load. Check your connection or Mapbox configuration.";
  }
  if (!window.mapboxgl || !window.INDEXMAP_CONFIG?.mapboxToken) {
    showError();
    return;
  }
  try {
    const styleResponse = await fetch(`https://api.mapbox.com/styles/v1/mapbox/light-v11?access_token=${encodeURIComponent(window.INDEXMAP_CONFIG.mapboxToken)}`);
    if (!styleResponse.ok) throw new Error(`Mapbox style request failed (${styleResponse.status})`);
    const mapStyle = await styleResponse.json();
    const countryLabels = mapStyle.layers?.find(layer => layer.id === "country-label");
    if (countryLabels) {
      const excludeLocalCountries = ["match", ["get", "iso_3166_1"], ["CH", "LI"], false, true];
      countryLabels.filter = countryLabels.filter
        ? ["all", countryLabels.filter, excludeLocalCountries]
        : excludeLocalCountries;
    }
    ["settlement-major-label", "settlement-minor-label"].forEach(id => {
      const layer = mapStyle.layers?.find(candidate => candidate.id === id);
      if (layer) layer.minzoom = Math.max(layer.minzoom ?? 0, 9);
    });
    let pmtilesReady = false;
    let pmtilesSourceType;
    if (container.dataset.pmtilesLayer && window.mapboxPmTiles?.PmTilesSource) {
      pmtilesSourceType = window.mapboxPmTiles.PmTilesSource.SOURCE_TYPE || window.mapboxPmTiles.SOURCE_TYPE;
      mapboxgl.Style.setSourceType(pmtilesSourceType, window.mapboxPmTiles.PmTilesSource);
      pmtilesReady = true;
    } else if (container.dataset.pmtilesLayer) {
      console.error("IndexMap: PMTiles could not be initialized.", {
        pmtilesLibraryLoaded: Boolean(window.mapboxPmTiles?.PmTilesSource),
        archiveUrl: tilesUrl,
        layer: container.dataset.pmtilesLayer,
      });
    }
    const map = new mapboxgl.Map({
      container,
      accessToken: window.INDEXMAP_CONFIG.mapboxToken,
      style: mapStyle,
      bounds: container.dataset.bounds ? JSON.parse(container.dataset.bounds) : [[5.95, 45.8], [10.5, 47.85]],
      fitBoundsOptions: { padding: 45 },
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new mapboxgl.ScaleControl({ maxWidth: 150, unit: "metric" }), "bottom-left");
    map.on("error", showError);
    map.on("load", async () => {
      if (pmtilesReady) {
        const source = "indexmap-boundaries";
        const level = Number(container.dataset.boundaryLevel);
        const levelControls = [...document.querySelectorAll('input[name="boundary-level"]')];
        map.addSource(source, { type: pmtilesSourceType, url: tilesUrl });
        const fillLayerIds = ["boundary-fill"];
        map.addLayer({
          id: "boundary-fill",
          type: "fill",
          source,
          "source-layer": container.dataset.pmtilesLayer,
          paint: { "fill-antialias": false, "fill-color": "#2563eb", "fill-opacity": 0.12 },
        });
        const boundaryLayerIds = [];
        const addBoundaryLayer = (id, adminLevel, paint) => {
          if (adminLevel > level) return;
          boundaryLayerIds.push(id);
          map.addLayer({
            id,
            type: "line",
            source,
            "source-layer": "boundaries",
            filter: ["==", ["get", "admin_level"], adminLevel],
            layout: { "line-cap": "round", "line-join": "miter" },
            paint,
          });
        };
        addBoundaryLayer("national-boundary", 2,
          { "line-color": boundaryColor, "line-opacity": 1, "line-width": 2 });
        addBoundaryLayer("cantonal-boundary", 4,
          { "line-color": boundaryColor, "line-opacity": 1, "line-width": 2 });
        addBoundaryLayer("district-boundary", 6,
          { "line-color": boundaryColor, "line-opacity": 1, "line-width": 1 });
        addBoundaryLayer("municipal-boundary", 8,
          { "line-color": boundaryColor, "line-opacity": 1, "line-width": 1,
            "line-dasharray": ["step", ["zoom"], ["literal", [1, 0]],
              9, ["literal", [4, 4]]] });        
        const selectBoundaryLevel = selected => {
          const selectedIndex = levelControls.indexOf(selected);
          levelControls.forEach((input, index) => {
            const visible = index <= selectedIndex ? "visible" : "none";
            if (map.getLayer(input.dataset.boundaryLayer)) {
              map.setLayoutProperty(input.dataset.boundaryLayer, "visibility", visible);
            }
          });
        };
        if (levelControls.length) {
          selectBoundaryLevel(levelControls.find(input => input.checked));
          levelControls.forEach(input => input.addEventListener("change", () => {
            if (input.checked) selectBoundaryLevel(input);
          }));
        }
        container.addEventListener("boundarychange", event => {
          if (!map.getSource("boundary-selection")) {
            map.addSource("boundary-selection", { type: "geojson", data: event.detail });
            map.addLayer({ id: "boundary-selection-fill", type: "fill", source: "boundary-selection",
              paint: { "fill-color": "#2563eb", "fill-opacity": 0.12 } });
            map.addLayer({ id: "boundary-selection-outline", type: "line", source: "boundary-selection",
              paint: { "line-color": boundaryColor, "line-width": 2 } });
          } else {
            map.getSource("boundary-selection").setData(event.detail);
          }
          fillLayerIds.forEach(id => map.setLayoutProperty(id, "visibility", "none"));
          boundaryLayerIds.forEach(id => map.setLayoutProperty(id, "visibility", "none"));
        });
      } else if (container.dataset.geojson && !container.dataset.pmtilesLayer) {
        try {
          const data = await loadBoundary();
          map.addSource("canton", { type: "geojson", data: activeGeometry || data });
          map.addLayer({ id: "canton-fill", type: "fill", source: "canton", paint: { "fill-color": "#2563eb", "fill-opacity": 0.12 } });
          map.addLayer({ id: "canton-outline", type: "line", source: "canton", paint: { "line-color": boundaryColor, "line-width": 2 } });
          container.addEventListener("boundarychange", event => map.getSource("canton")?.setData(event.detail));
        } catch {
          status.hidden = false;
          status.textContent = "The boundary could not load. You can still download the GeoJSON.";
          return;
        }
      } else if (container.dataset.pmtilesLayer) {
        status.hidden = true;
        return;
      }
      status.hidden = true;
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container);
    window.addEventListener("pagehide", (event) => {
      if (!event.persisted) { observer.disconnect(); map.remove(); }
    });
  } catch (error) { showError(error); }
})();
