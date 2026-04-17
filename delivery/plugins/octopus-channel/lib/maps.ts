// ---------------------------------------------------------------------------
// Wave 2a extraction: pure map-URL parsing helpers.
// Deterministic URL/regex transforms used by the inbound message pipeline
// when a customer pastes a Google/Apple Maps link. No I/O, no state —
// the HTTP-backed `resolveMapUrlToLocation` that follows short-URL redirects
// remains in `index.ts` because it needs the geo-area loader and the
// octopus-channel module-scope fetch context.
// ---------------------------------------------------------------------------

import type { CachedGeoArea } from "./types";

export const MAP_URL_RE =
  /https?:\/\/(?:(?:www\.)?google\.[a-z.]+\/maps|maps\.google\.[a-z.]+|goo\.gl\/maps|maps\.app\.goo\.gl|maps\.apple\.com)[^\s)}\]"']*/gi;
export const SHORTENED_RE = /^https?:\/\/(?:goo\.gl\/maps|maps\.app\.goo\.gl)\//i;
export const COORDS_AT_RE = /@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/;
export const COORDS_Q_RE = /[?&](?:q|query|ll|center|sll)=(-?\d{1,3}\.\d+)[,+](-?\d{1,3}\.\d+)/;
export const COORDS_SEARCH_RE = /\/maps\/(?:search|dir)\/(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/;
export const PLACE_NAME_RE = /\/maps\/place\/([^/@]+)/;
export const Q_PARAM_RE = /[?&](?:q|query)=([^&]+)/;

export type MapUrlExtraction = {
  lat: number | null;
  lng: number | null;
  placeName: string | null;
};

export function normalizeMapPlaceName(text: string): string {
  return text
    .toLowerCase()
    .replace(/[,_|/\\()-]+/g, " ")
    .replace(/\bgovernorate\b/g, " ")
    .replace(/\bal\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function extractFromMapUrl(url: string): MapUrlExtraction {
  for (const re of [COORDS_AT_RE, COORDS_Q_RE, COORDS_SEARCH_RE]) {
    const m = re.exec(url);
    if (m) {
      const lat = parseFloat(m[1]);
      const lng = parseFloat(m[2]);
      if (!isNaN(lat) && !isNaN(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
        const placeMatch = PLACE_NAME_RE.exec(url);
        const placeName = placeMatch
          ? decodeURIComponent(placeMatch[1]).replace(/\+/g, " ")
          : null;
        return { lat, lng, placeName };
      }
    }
  }

  const placeMatch = PLACE_NAME_RE.exec(url);
  if (placeMatch) {
    return {
      lat: null,
      lng: null,
      placeName: decodeURIComponent(placeMatch[1]).replace(/\+/g, " "),
    };
  }

  const qMatch = Q_PARAM_RE.exec(url);
  if (qMatch) {
    const raw = decodeURIComponent(qMatch[1]).replace(/\+/g, " ").trim();
    if (raw && !/^-?\d{1,3}\.\d+[, ]-?\d{1,3}\.\d+$/.test(raw)) {
      return { lat: null, lng: null, placeName: raw };
    }
  }

  return { lat: null, lng: null, placeName: null };
}

export function matchPlaceNameToGeoArea(
  placeName: string,
  areas: CachedGeoArea[],
): CachedGeoArea | null {
  if (!placeName || areas.length === 0) return null;
  const normalizedPlace = normalizeMapPlaceName(placeName);

  for (const area of areas) {
    if (normalizeMapPlaceName(area.name) === normalizedPlace) return area;
  }

  const sorted = [...areas].sort((a, b) => b.name.length - a.name.length);
  for (const area of sorted) {
    const normalizedArea = normalizeMapPlaceName(area.name);
    if (normalizedArea.length >= 3 && normalizedPlace.includes(normalizedArea)) return area;
  }

  return null;
}
