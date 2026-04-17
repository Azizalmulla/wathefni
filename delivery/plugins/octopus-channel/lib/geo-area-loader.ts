// ---------------------------------------------------------------------------
// Wave 3 extraction: geo-area loader factory.
// Owns the cached Riders Grid geo-area list and nearest-area Haversine lookup.
// Previously two module-scoped `let` bindings in `plugins/octopus-channel/
// index.ts`; now encapsulated in a factory whose two exported methods are the
// only way to touch the cache. Loader still returns `[]` on any failure so
// callers remain graceful.
// ---------------------------------------------------------------------------

import type { CachedGeoArea } from "./types";

export type GeoAreaLoaderOptions = {
  baseUrl: string;
  apiKey: string;
  maxMatchDistanceKm?: number;
  fetchImpl?: typeof fetch;
};

export type GeoAreaLoader = {
  loadAll(): Promise<CachedGeoArea[]>;
  resolveNearestArea(
    lat: number,
    lng: number,
  ): Promise<{ name: string; distance_km: number; governorate: string } | null>;
};

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function createGeoAreaLoader(options: GeoAreaLoaderOptions): GeoAreaLoader {
  const baseUrl = options.baseUrl.replace(/\/+$/, "");
  const apiKey = options.apiKey.trim();
  const maxMatchDistanceKm = options.maxMatchDistanceKm ?? 15;
  const fetchImpl = options.fetchImpl ?? fetch;

  let cache: CachedGeoArea[] | null = null;
  let loading: Promise<CachedGeoArea[]> | null = null;

  async function loadAll(): Promise<CachedGeoArea[]> {
    if (cache) return cache;
    if (loading) return loading;

    loading = (async () => {
      try {
        if (!apiKey) return [];
        const headers: Record<string, string> = {
          Accept: "application/json",
          "x-api-key": apiKey,
          Authorization: `Bearer ${apiKey}`,
        };
        const govRes = await fetchImpl(`${baseUrl}/geo/govs`, { headers });
        if (!govRes.ok) return [];
        const govData = (await govRes.json()) as { data?: any[] };
        const govs = Array.isArray(govData.data) ? govData.data : [];

        const allAreas: CachedGeoArea[] = [];
        const areaFetches = govs.map(async (gov: any) => {
          const govId = Number(gov.id);
          const govName = String(gov.name || "");
          try {
            const areaRes = await fetchImpl(
              `${baseUrl}/geo/areas?governorate_id=${encodeURIComponent(String(govId))}`,
              { headers },
            );
            if (!areaRes.ok) return;
            const areaData = (await areaRes.json()) as { data?: any[] };
            if (!Array.isArray(areaData.data)) return;
            for (const item of areaData.data) {
              const lat = parseFloat(item.lat);
              const lng = parseFloat(item.lng);
              if (!isNaN(lat) && !isNaN(lng)) {
                allAreas.push({
                  name: String(item.name || ""),
                  lat,
                  lng,
                  governorate_name: govName,
                });
              }
            }
          } catch {
            // Skip failed governorate
          }
        });
        await Promise.all(areaFetches);
        cache = allAreas;
        return allAreas;
      } catch {
        return [];
      } finally {
        loading = null;
      }
    })();

    return loading;
  }

  async function resolveNearestArea(
    lat: number,
    lng: number,
  ): Promise<{ name: string; distance_km: number; governorate: string } | null> {
    const areas = await loadAll();
    if (areas.length === 0) return null;

    let best: CachedGeoArea | null = null;
    let bestDist = Infinity;

    for (const area of areas) {
      const d = haversineKm(lat, lng, area.lat, area.lng);
      if (d < bestDist) {
        bestDist = d;
        best = area;
      }
    }

    if (!best || bestDist > maxMatchDistanceKm) return null;
    return {
      name: best.name,
      distance_km: Math.round(bestDist * 10) / 10,
      governorate: best.governorate_name,
    };
  }

  return {
    loadAll,
    resolveNearestArea,
  };
}
