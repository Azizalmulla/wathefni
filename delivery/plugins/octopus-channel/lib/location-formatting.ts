// ---------------------------------------------------------------------------
// Wave 4 extraction: location-formatting helpers.
// Pure formatters for inbound location messages and pickup/dropoff pin
// rendering. Extracted from `plugins/octopus-channel/index.ts`. No module
// state or I/O; all inputs are passed as arguments.
// ---------------------------------------------------------------------------

import type { PersistedBookingLocation } from "../../shared/conversation-policy";
import { asTrimmedString } from "./normalize";
import type { OctopusInboundLocationMessage, SavedAddress } from "./types";

export function formatLocationAsText(
  loc: OctopusInboundLocationMessage,
  nearestArea?: string | null,
): string {
  const hasRealCoords = loc.latitude !== 0 || loc.longitude !== 0;
  const coords = hasRealCoords ? `${loc.latitude.toFixed(6)}, ${loc.longitude.toFixed(6)}` : null;
  const parts: string[] = [];
  if (loc.name || loc.address) {
    parts.push([loc.name, loc.address].filter(Boolean).join(" — "));
  }
  if (nearestArea) {
    parts.push(`Nearest Riders area: ${nearestArea}`);
  }
  if (parts.length > 0 && coords) {
    return `📍 ${parts.join(" | ")} (${coords})`;
  }
  if (parts.length > 0) {
    return `📍 ${parts.join(" | ")}`;
  }
  return coords ? `📍 ${coords}` : "📍 Location shared";
}

export function formatLocationPinContext(
  loc: OctopusInboundLocationMessage,
  nearestArea: string | null,
): string {
  const hasRealCoords = loc.latitude !== 0 || loc.longitude !== 0;
  const lines = [
    "[SYSTEM CONTEXT - LOCATION PIN]",
    "The customer just shared a location pin or map location link.",
    "This shared location counts as their address for pickup or delivery.",
  ];
  if (nearestArea) {
    lines.push(`Resolved Riders service area: ${nearestArea}`);
  }
  if (hasRealCoords) {
    lines.push(`Coordinates: ${loc.latitude.toFixed(6)}, ${loc.longitude.toFixed(6)}`);
  }
  if (loc.name) lines.push(`Place name: ${loc.name}`);
  if (loc.address) lines.push(`Address: ${loc.address}`);
  lines.push(
    "STRICT: Do NOT ask the customer for block, street, or building number. The pin IS the address.",
    "If you are collecting address details for booking, accept this pin and only ask if they want to add an apartment or house number.",
    "If pickup/dropoff context is unclear, ask which one this location is for.",
    "[/SYSTEM CONTEXT - LOCATION PIN]",
  );
  return lines.join("\n");
}

export function createPersistedBookingLocation(params: {
  locationMessage: OctopusInboundLocationMessage | null;
  nearestAreaName: string | null;
  source: PersistedBookingLocation["source"];
}): PersistedBookingLocation | null {
  const locationMessage = params.locationMessage;
  if (!locationMessage) {
    return null;
  }
  if (!Number.isFinite(locationMessage.latitude) || !Number.isFinite(locationMessage.longitude)) {
    return null;
  }
  return {
    source: params.source,
    latitude: locationMessage.latitude,
    longitude: locationMessage.longitude,
    name: locationMessage.name || null,
    address: locationMessage.address || null,
    resolvedAreaName: params.nearestAreaName || null,
  };
}

export function buildSavedAddress(args: Record<string, any>, prefix: string): SavedAddress {
  return {
    area: asTrimmedString(args?.[`${prefix}_area`]) || null,
    house: asTrimmedString(args?.[`${prefix}_house`]) || null,
    avenue: asTrimmedString(args?.[`${prefix}_street`]) || asTrimmedString(args?.[`${prefix}_avenue`]) || null,
    notes: asTrimmedString(args?.[`${prefix}_notes`]) || null,
  };
}
