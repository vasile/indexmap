(async () => {
  "use strict";
  const scriptUrl = document.currentScript?.src;
  const tilesUrl = scriptUrl ? new URL("../tiles/boundaries.pmtiles", scriptUrl).href : "../tiles/boundaries.pmtiles";
  const territoryMaskUrl = scriptUrl ? new URL("../countries/ch-li-mask.geojson", scriptUrl).href : "../countries/ch-li-mask.geojson";
  const siteRoot = scriptUrl ? new URL("../", scriptUrl) : new URL("./", location.href);
  const boundaryColor = "#1d4ed8";
  const container = document.querySelector("#map");
  const search = document.querySelector("#canton-search");
  const items = [...document.querySelectorAll(".canton-item")];
  const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const searchableItems = items.map(item => ({ item, text: normalize(item.dataset.search || "") }));
  const selectionDownloadPanel = document.querySelector("#selection-download-panel");
  const selectionDownload = document.querySelector("#selection-download");
  const selectionDownloadStatus = document.querySelector("#selection-download-status");
  let directorySelection = { active: false, ids: [] };
  let cantonFilter = "";
  const filterDirectory = () => {
    const terms = normalize(search.value).split(/\s+/).filter(Boolean);
    const exactCanton = cantonFilter && normalize(search.value) === cantonFilter;
    let count = 0;
    searchableItems.forEach(({ item, text }) => {
      item.hidden = exactCanton
        ? normalize(item.dataset.canton || "") !== cantonFilter
        : !terms.every(term => text.includes(term));
      if (!item.hidden) count++;
    });
    document.querySelector("#result-count").textContent = count + (" " + (count === 1 ? (search.dataset.singular || "canton") : (search.dataset.plural || "cantons")));
    document.querySelector("#no-results").hidden = count !== 0;
    directorySelection = {
      active: Boolean(exactCanton || terms.length),
      ids: searchableItems.filter(({ item }) => !item.hidden)
        .map(({ item }) => Number(item.dataset.featureId)).filter(Number.isFinite),
    };
    if (selectionDownloadPanel && selectionDownload) {
      selectionDownloadPanel.hidden = !directorySelection.active;
      selectionDownload.disabled = count === 0;
      selectionDownload.textContent = `↓ Download selection (${count}) · GeoJSON`;
      selectionDownloadStatus.textContent = "";
    }
    container?.dispatchEvent(new CustomEvent("directoryfilterchange", {
      detail: directorySelection,
    }));
  };
  search?.addEventListener("input", filterDirectory);
  if (search) {
    const parameters = new URLSearchParams(location.search);
    const query = parameters.get("q");
    const canton = parameters.get("canton");
    if (canton) {
      cantonFilter = normalize(canton);
      search.value = canton.toUpperCase();
      filterDirectory();
    } else if (query) {
      search.value = query;
      filterDirectory();
    }
  }
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
  selectionDownload?.addEventListener("click", async () => {
    if (!directorySelection.active || !directorySelection.ids.length) return;
    const idProperties = { districts: "bezirksnummer", municipalities: "bfs_nummer" };
    const layer = container?.dataset.pmtilesLayer;
    const idProperty = idProperties[layer];
    if (!idProperty) return;
    const originalText = selectionDownload.textContent;
    selectionDownload.disabled = true;
    selectionDownload.textContent = "Preparing selection…";
    selectionDownloadStatus.textContent = "";
    try {
      const collection = await loadBoundary();
      const selectedIds = new Set(directorySelection.ids.map(String));
      const selected = {
        ...collection,
        features: collection.features.filter(feature =>
          selectedIds.has(String(feature.properties?.[idProperty]))),
      };
      const query = normalize(search.value).replace(/\s+/g, "-") || "selection";
      const filename = `${layer}-${query}.geojson`;
      const objectUrl = URL.createObjectURL(new Blob(
        [JSON.stringify(selected) + "\n"], { type: "application/geo+json" }));
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (error) {
      console.error("IndexMap: selected boundaries could not be prepared.", error);
      selectionDownloadStatus.textContent = "The selection could not be downloaded. Try again.";
    } finally {
      selectionDownload.disabled = !directorySelection.ids.length;
      selectionDownload.textContent = originalText;
    }
  });
  function previewGeometry(data) {
    activeGeometry = data;
    container.dispatchEvent(new CustomEvent("boundarychange", { detail: data }));
  }
  // Inputs are prepared, non-overlapping Polygon/MultiPolygon boundaries.
  // In the inverse, shells become holes and holes become shells.
  function createInverseMask(input) {
    const features = input.type === "FeatureCollection" ? input.features : [input];
    if (!features.length || features.some(feature =>
      !["Polygon", "MultiPolygon"].includes(feature.geometry?.type))) {
      throw new Error("A polygon boundary is required.");
    }
    const world = [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]];
    const outside = [world];
    const islands = [];
    const inverseRing = ring => ring.slice().reverse().map(position => position.slice());
    for (const feature of features) {
      const geometry = feature.geometry;
      const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
      for (const [shell, ...holes] of polygons) {
        outside.push(inverseRing(shell));
        for (const hole of holes) islands.push([inverseRing(hole)]);
      }
    }
    return {
      type: "Feature",
      properties: {},
      geometry: islands.length
        ? { type: "MultiPolygon", coordinates: [outside, ...islands] }
        : { type: "Polygon", coordinates: outside },
    };
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
    const selectedCantonCode = (new URLSearchParams(location.search).get("canton") || "").toLowerCase();
    const isCantonDirectoryFilter = /^[a-z]{2}$/.test(selectedCantonCode)
      && ["districts", "municipalities"].includes(container.dataset.pmtilesLayer)
      && !container.dataset.activeFeatureIds;
    let initialBounds = container.dataset.bounds
      ? JSON.parse(container.dataset.bounds)
      : [[5.95, 45.8], [10.5, 47.85]];
    if (isCantonDirectoryFilter) {
      try {
        const response = await fetch(new URL(`canton/${selectedCantonCode}.geojson`, siteRoot));
        if (!response.ok) throw new Error(`Canton boundary request failed (${response.status})`);
        const boundary = await response.json();
        const extent = [Infinity, Infinity, -Infinity, -Infinity];
        const includePositions = coordinates => {
          if (typeof coordinates?.[0] === "number") {
            extent[0] = Math.min(extent[0], coordinates[0]);
            extent[1] = Math.min(extent[1], coordinates[1]);
            extent[2] = Math.max(extent[2], coordinates[0]);
            extent[3] = Math.max(extent[3], coordinates[1]);
          } else {
            coordinates?.forEach(includePositions);
          }
        };
        boundary.features?.forEach(feature => includePositions(feature.geometry?.coordinates));
        if (extent.every(Number.isFinite)) initialBounds = [[extent[0], extent[1]], [extent[2], extent[3]]];
      } catch (error) {
        console.error("IndexMap: filtered canton extent could not load.", error);
      }
    }
    const map = new mapboxgl.Map({
      container,
      accessToken: window.INDEXMAP_CONFIG.mapboxToken,
      style: mapStyle,
      bounds: initialBounds,
      fitBoundsOptions: { padding: 45 },
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new mapboxgl.ScaleControl({ maxWidth: 150, unit: "metric" }), "bottom-left");
    map.on("error", showError);
    map.on("load", async () => {
      try {
        const response = await fetch(territoryMaskUrl);
        if (!response.ok) throw new Error(`Territory mask request failed (${response.status})`);
        map.addSource("indexmap-territory-mask", { type: "geojson", data: await response.json() });
        map.addLayer({
          id: "indexmap-territory-mask",
          type: "fill",
          source: "indexmap-territory-mask",
          paint: { "fill-color": "#ffffff", "fill-opacity": 0.6 },
        });
      } catch (error) {
        console.error("IndexMap: territory mask could not load.", error);
      }
      if (pmtilesReady) {
        const source = "indexmap-boundaries";
        const level = Number(container.dataset.boundaryLevel);
        const activeFeatureIds = new Set((container.dataset.activeFeatureIds || "")
          .split(",").filter(Boolean));
        const isDetailMap = activeFeatureIds.size > 0;
        const cantonCodes = [null, "zh", "be", "lu", "ur", "sz", "ow", "nw", "gl", "zg", "fr", "so", "bs", "bl", "sh", "ar", "ai", "sg", "gr", "ag", "tg", "ti", "vd", "vs", "ne", "ge", "ju"];
        const selectedCantonNumber = cantonCodes.indexOf(selectedCantonCode);
        const cantonFiltered = isCantonDirectoryFilter && selectedCantonNumber > 0;
        const cantonFilter = ["==", ["get", "kantonsnummer"], selectedCantonNumber];
        const levelControls = [...document.querySelectorAll('input[name="boundary-level"]')];
        const isFilterableDirectoryMap = !isDetailMap && !levelControls.length
          && ["districts", "municipalities"].includes(container.dataset.pmtilesLayer);
        map.addSource(source, {
          type: pmtilesSourceType,
          url: tilesUrl,
          promoteId: {
            countries: "icc",
            cantons: "kantonsnummer",
            districts: "bezirksnummer",
            municipalities: "bfs_nummer",
          },
        });
        const fillLayerIds = [];
        let activeInteraction;
        let hoveredFeature;
        let hoverPopup;
        let popup;
        const interactionLayers = levelControls.map((input, index) => {
          const fillId = `boundary-fill-${index}`;
          fillLayerIds.push(fillId);
          map.addLayer({
            id: fillId, type: "fill", source, "source-layer": input.dataset.sourceLayer,
            layout: { visibility: input.checked ? "visible" : "none" },
            paint: { "fill-antialias": false, "fill-color": boundaryColor,
              "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.34, 0.12] },
          });
          return { input, fillId };
        });
        if (!levelControls.length) {
          fillLayerIds.push("boundary-fill");
          const idProperties = { countries: "icc", cantons: "kantonsnummer",
            districts: "bezirksnummer", municipalities: "bfs_nummer" };
          const idProperty = idProperties[container.dataset.pmtilesLayer];
          const fillLayer = {
            id: "boundary-fill", type: "fill", source, "source-layer": container.dataset.pmtilesLayer,
            paint: { "fill-antialias": false,
              "fill-color": isDetailMap ? "#60a5fa" : boundaryColor,
              "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false],
                isDetailMap ? 0.22 : 0.34,
                isDetailMap ? 0 : 0.12] },
          };
          if (cantonFiltered) fillLayer.filter = cantonFilter;
          map.addLayer(fillLayer);
          if (isFilterableDirectoryMap) {
            map.addLayer({
              id: "boundary-filter-outline", type: "line", source,
              "source-layer": container.dataset.pmtilesLayer,
              filter: cantonFiltered ? cantonFilter : ["==", ["get", idProperty], -1],
              layout: { "line-cap": "round", "line-join": "miter",
                visibility: cantonFiltered ? "visible" : "none" },
              paint: { "line-color": boundaryColor, "line-width": 1 },
            });
          }
          if (idProperty) {
            interactionLayers.push({
              input: { dataset: { sourceLayer: container.dataset.pmtilesLayer, idProperty } },
              fillId: "boundary-fill",
            });
          }
        }
        const clearHover = () => {
          if (hoveredFeature) {
            map.setFeatureState({ source, sourceLayer: hoveredFeature.sourceLayer, id: hoveredFeature.id },
              { hover: false });
          }
          hoveredFeature = undefined;
          hoverPopup?.remove();
          hoverPopup = undefined;
          map.getCanvas().style.cursor = "";
        };
        const featureDetails = feature => {
          const properties = feature.properties || {};
          const sourceLayer = activeInteraction.input.dataset.sourceLayer;
          if (sourceLayer === "countries") return { label: "Country", id: properties.icc,
            path: `country/${String(properties.icc).toLowerCase()}.html`,
            icon: `country/${String(properties.icc).toLowerCase()}.png`,
            name: { CH: "Switzerland", LI: "Liechtenstein" }[properties.icc] };
          if (sourceLayer === "cantons") return { label: "Canton", id: cantonCodes[Number(properties.kantonsnummer)]?.toUpperCase(),
            path: `canton/${cantonCodes[Number(properties.kantonsnummer)]}.html`,
            icon: `canton/${cantonCodes[Number(properties.kantonsnummer)]}.png` };
          if (sourceLayer === "districts") return { label: "District", id: properties.bezirksnummer,
            path: `district/${properties.bezirksnummer}.html`, canton: cantonCodes[Number(properties.kantonsnummer)],
            cantonName: properties.kantonsname };
          return { label: "Municipality", id: `BFS ${properties.bfs_nummer}`,
            path: `municipality/${properties.bfs_nummer}.html`,
            icon: `municipality/${properties.bfs_nummer}.webp`, canton: cantonCodes[Number(properties.kantonsnummer)],
            cantonName: properties.kantonsname, district: properties.bezirksnummer,
            districtName: properties.bezirksname };
        };
        const showHoverPopup = (feature, lngLat) => {
          if (popup) return;
          const details = featureDetails(feature);
          const content = document.createElement("div");
          content.className = "boundary-hover-content";
          const heading = document.createElement("div");
          heading.className = "boundary-popup-heading";
          if (details.icon) {
            const icon = document.createElement("img");
            icon.src = new URL(details.icon, siteRoot).href;
            icon.alt = "";
            icon.width = 34;
            heading.append(icon);
          }
          const title = document.createElement("strong");
          const name = details.name || feature.properties?.name || details.label;
          const hoverId = details.label === "Municipality"
            ? String(feature.properties?.bfs_nummer || "")
            : details.label === "District" || details.label === "Canton" ? String(details.id || "") : "";
          title.textContent = hoverId ? `${name} (${hoverId})` : name;
          heading.append(title);
          content.append(heading);
          if (details.canton) {
            const canton = document.createElement("span");
            canton.textContent = `Canton: ${details.cantonName || details.canton.toUpperCase()} (${details.canton.toUpperCase()})`;
            content.append(canton);
          }
          if (details.district) {
            const district = document.createElement("span");
            district.textContent = `District: ${details.districtName || "District"} (${details.district})`;
            content.append(district);
          }
          hoverPopup?.remove();
          hoverPopup = new mapboxgl.Popup({
            closeButton: false,
            closeOnClick: false,
            focusAfterOpen: false,
            className: "boundary-hover-popup",
            maxWidth: "200px",
            offset: 12,
          }).setLngLat(lngLat).setDOMContent(content).addTo(map);
        };
        const showPopup = (feature, lngLat) => {
          const details = featureDetails(feature);
          if (!details.path || !details.id) return;
          const content = document.createElement("div");
          content.className = "boundary-popup";
          const heading = document.createElement("a");
          heading.className = "boundary-popup-heading boundary-popup-detail-link";
          heading.href = new URL(details.path, siteRoot).href;
          if (details.icon) {
            const icon = document.createElement("img");
            icon.src = new URL(details.icon, siteRoot).href;
            icon.alt = "";
            icon.width = 34;
            heading.append(icon);
          }
          const title = document.createElement("strong");
          title.textContent = details.name || feature.properties?.name || details.label;
          heading.append(title);
          const meta = document.createElement("span");
          meta.textContent = `${details.label} · ${details.id}`;
          const link = document.createElement("a");
          link.href = new URL(details.path, siteRoot).href;
          link.textContent = "View details →";
          const geojsonLink = document.createElement("a");
          geojsonLink.href = new URL(details.path.replace(/\.html$/, ".geojson"), siteRoot).href;
          geojsonLink.download = details.path.split("/").pop().replace(/\.html$/, ".geojson");
          geojsonLink.textContent = "GeoJSON ↓";
          const parents = document.createElement("div");
          parents.className = "boundary-popup-parents";
          if (details.canton) {
            const cantonRow = document.createElement("div");
            cantonRow.className = "boundary-popup-parent";
            const cantonLabel = document.createElement("span");
            cantonLabel.textContent = "Canton:";
            const cantonLink = document.createElement("a");
            cantonLink.href = new URL(`canton/${details.canton}.html`, siteRoot).href;
            cantonLink.textContent = `${details.cantonName || details.canton.toUpperCase()} (${details.canton.toUpperCase()}) →`;
            cantonRow.append(cantonLabel, cantonLink);
            parents.append(cantonRow);
          }
          if (details.district) {
            const districtRow = document.createElement("div");
            districtRow.className = "boundary-popup-parent";
            const districtLabel = document.createElement("span");
            districtLabel.textContent = "District:";
            const districtLink = document.createElement("a");
            districtLink.href = new URL(`district/${details.district}.html`, siteRoot).href;
            districtLink.textContent = `${details.districtName || "District"} (${details.district}) →`;
            districtRow.append(districtLabel, districtLink);
            parents.append(districtRow);
          }
          const actions = document.createElement("div");
          actions.className = "boundary-popup-actions";
          actions.append(link, geojsonLink);
          content.append(heading, meta);
          if (parents.childElementCount) content.append(parents);
          content.append(actions);
          hoverPopup?.remove();
          hoverPopup = undefined;
          popup?.remove();
          const nextPopup = new mapboxgl.Popup({ closeButton: true, focusAfterOpen: false, maxWidth: "240px" })
            .setLngLat(lngLat).setDOMContent(content).addTo(map);
          popup = nextPopup;
          nextPopup.on("close", () => {
            if (popup === nextPopup) popup = undefined;
          });
        };
        map.on("mousemove", event => {
          if (!activeInteraction) return;
          const feature = map.queryRenderedFeatures(event.point, { layers: [activeInteraction.fillId] })[0];
          if (!feature) { clearHover(); return; }
          if (feature.id === undefined || feature.id === null) { clearHover(); return; }
          if (activeFeatureIds.has(String(feature.id))) { clearHover(); return; }
          if (hoveredFeature?.id === feature.id && hoveredFeature.sourceLayer === feature.sourceLayer) {
            hoverPopup?.setLngLat(event.lngLat);
            return;
          }
          clearHover();
          map.getCanvas().style.cursor = "pointer";
          hoveredFeature = { id: feature.id, sourceLayer: feature.sourceLayer };
          map.setFeatureState({ source, sourceLayer: feature.sourceLayer, id: feature.id }, { hover: true });
          showHoverPopup(feature, event.lngLat);
        });
        map.getCanvas().addEventListener("mouseleave", clearHover);
        map.on("click", event => {
          if (!activeInteraction) return;
          const feature = map.queryRenderedFeatures(event.point, { layers: [activeInteraction.fillId] })[0];
          if (!feature) return;
          if (activeFeatureIds.has(String(feature.id))) return;
          showPopup(feature, event.lngLat);
        });
        const boundaryLayerIds = [];
        const boundaryAdminLevels = new Map();
        const addBoundaryLayer = (id, adminLevel, paint) => {
          if (adminLevel > level) return;
          boundaryLayerIds.push(id);
          boundaryAdminLevels.set(id, adminLevel);
          map.addLayer({
            id,
            type: "line",
            source,
            "source-layer": "boundaries",
            filter: ["==", ["get", "admin_level"], adminLevel],
            layout: { "line-cap": "round", "line-join": "miter",
              visibility: cantonFiltered && adminLevel > 4 ? "none" : "visible" },
            paint,
          });
        };
        const contextLineColor = isDetailMap ? "#7c8ba1" : boundaryColor;
        const contextLineOpacity = isDetailMap ? 0.62 : 1;
        addBoundaryLayer("national-boundary", 2,
          { "line-color": contextLineColor, "line-opacity": contextLineOpacity, "line-width": 2 });
        addBoundaryLayer("cantonal-boundary", 4,
          { "line-color": contextLineColor, "line-opacity": contextLineOpacity, "line-width": 2 });
        addBoundaryLayer("district-boundary", 6,
          { "line-color": contextLineColor, "line-opacity": contextLineOpacity, "line-width": 1 });
        addBoundaryLayer("municipal-boundary", 8,
          { "line-color": contextLineColor, "line-opacity": contextLineOpacity, "line-width": 1,
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
          interactionLayers.forEach(interaction => {
            const visible = interaction.input === selected ? "visible" : "none";
            map.setLayoutProperty(interaction.fillId, "visibility", visible);
          });
          clearHover();
          popup?.remove();
          popup = undefined;
          activeInteraction = interactionLayers.find(interaction => interaction.input === selected);
        };
        if (levelControls.length) {
          selectBoundaryLevel(levelControls.find(input => input.checked));
          levelControls.forEach(input => input.addEventListener("change", () => {
            if (input.checked) selectBoundaryLevel(input);
          }));
        } else {
          activeInteraction = interactionLayers[0];
        }
        container.addEventListener("directoryfilterchange", event => {
          if (!isFilterableDirectoryMap) return;
          const idProperty = activeInteraction?.input.dataset.idProperty;
          if (!idProperty) return;
          const ids = event.detail?.ids || [];
          const active = Boolean(event.detail?.active);
          const featureFilter = active
            ? (ids.length
              ? ["in", ["get", idProperty], ["literal", ids]]
              : ["==", ["get", idProperty], -1])
            : null;
          map.setFilter("boundary-fill", featureFilter);
          map.setFilter("boundary-filter-outline", featureFilter || ["==", ["get", idProperty], -1]);
          map.setLayoutProperty("boundary-filter-outline", "visibility", active ? "visible" : "none");
          boundaryLayerIds.forEach(id => {
            if (boundaryAdminLevels.get(id) > 4) {
              map.setLayoutProperty(id, "visibility", active ? "none" : "visible");
            }
          });
          clearHover();
          popup?.remove();
          popup = undefined;
        });
        if (search?.value) search.dispatchEvent(new Event("input"));
        const showBoundarySelection = data => {
          if (!map.getSource("boundary-selection")) {
            map.addSource("boundary-selection", { type: "geojson", data });
            map.addLayer({ id: "boundary-selection-fill", type: "fill", source: "boundary-selection",
              paint: { "fill-color": "#2563eb", "fill-opacity": 0.12 } });
            map.addLayer({ id: "boundary-selection-outline", type: "line", source: "boundary-selection",
              paint: { "line-color": boundaryColor, "line-width": 2 } });
          } else {
            map.getSource("boundary-selection").setData(data);
          }
          if (!isDetailMap) {
            fillLayerIds.forEach(id => map.setLayoutProperty(id, "visibility", "none"));
            boundaryLayerIds.forEach(id => map.setLayoutProperty(id, "visibility", "none"));
          }
        };
        container.addEventListener("boundarychange", event => {
          showBoundarySelection(event.detail);
        });
        if (isDetailMap && container.dataset.geojson) showBoundarySelection(await loadBoundary());
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
