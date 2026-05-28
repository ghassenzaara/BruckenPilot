/** Great-circle distance in kilometres. */
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

type Ring = number[][]; // [[lng,lat], ...]

/** Ray-casting point-in-polygon for a single ring ([lng,lat] coords). */
function inRing(lng: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect =
      yi > lat !== yj > lat &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/** Point-in-polygon for a GeoJSON Polygon or MultiPolygon geometry. */
export function pointInGeometry(lng: number, lat: number, geometry: any): boolean {
  if (!geometry) return false;
  const polys =
    geometry.type === 'Polygon' ? [geometry.coordinates]
    : geometry.type === 'MultiPolygon' ? geometry.coordinates
    : [];
  for (const poly of polys) {
    // poly[0] = outer ring; ignore holes (good enough for state borders)
    if (poly[0] && inRing(lng, lat, poly[0])) return true;
  }
  return false;
}
