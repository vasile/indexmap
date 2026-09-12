// Inputs are prepared, non-overlapping Polygon/MultiPolygon boundaries inside
// the world extent. GDAL establishes their winding during preprocessing.
export function createInverseMask(input) {
  const features = input.type === "FeatureCollection" ? input.features : [input];
  if (!features.length || features.some(feature => !["Polygon", "MultiPolygon"].includes(feature.geometry?.type))) {
    throw new Error("A polygon boundary is required.");
  }
  const world = [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]];
  const outside = [world];
  const islands = [];
  // Roles flip in the inverse: shells become holes, and holes become shells.
  // Reverse copies for that role change; do not check winding or mutate input.
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
