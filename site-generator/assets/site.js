(() => {
  "use strict";
  const assetQuery = document.currentScript ? new URL(document.currentScript.src).search : "";
  const search = document.querySelector("#canton-search");
  const items = [...document.querySelectorAll(".canton-item")];
  const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const searchableItems = items.map(item => ({ item, text: normalize(item.dataset.search || "") }));
  search?.addEventListener("input", () => {
    const terms = normalize(search.value).split(/\s+/).filter(Boolean);
    let count = 0;
    searchableItems.forEach(({ item, text }) => {
      item.hidden = !terms.every(term => text.includes(term));
      if (!item.hidden) count++;
    });
    document.querySelector("#result-count").textContent = count + (" " + (count === 1 ? (search.dataset.singular || "canton") : (search.dataset.plural || "cantons")));
    document.querySelector("#no-results").hidden = count !== 0;
  });
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
  function showError() {
    status.hidden = false;
    status.textContent = "The basemap could not load. Check your connection or Mapbox configuration.";
  }
  if (!window.mapboxgl || !window.INDEXMAP_CONFIG?.mapboxToken) {
    showError();
    return;
  }
  try {
    const map = new mapboxgl.Map({
      container,
      accessToken: window.INDEXMAP_CONFIG.mapboxToken,
      style: "mapbox://styles/mapbox/light-v11",
      bounds: container.dataset.bounds ? JSON.parse(container.dataset.bounds) : [[5.95, 45.8], [10.5, 47.85]],
      fitBoundsOptions: { padding: 45 },
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new mapboxgl.ScaleControl({ maxWidth: 150, unit: "metric" }), "bottom-left");
    map.on("error", showError);
    map.on("load", async () => {
      if (container.dataset.geojson) {
        try {
          const data = await loadBoundary();
          map.addSource("canton", { type: "geojson", data: activeGeometry || data });
          map.addLayer({ id: "canton-fill", type: "fill", source: "canton", paint: { "fill-color": "#2563eb", "fill-opacity": 0.12 } });
          map.addLayer({ id: "canton-outline", type: "line", source: "canton", paint: { "line-color": "#1d4ed8", "line-width": 2 } });
          container.addEventListener("boundarychange", event => map.getSource("canton")?.setData(event.detail));
        } catch {
          status.hidden = false;
          status.textContent = "The boundary could not load. You can still download the GeoJSON.";
          return;
        }
      }
      status.hidden = true;
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container);
    window.addEventListener("pagehide", (event) => {
      if (!event.persisted) { observer.disconnect(); map.remove(); }
    });
  } catch { showError(); }
})();
