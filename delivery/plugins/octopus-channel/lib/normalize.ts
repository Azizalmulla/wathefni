// ---------------------------------------------------------------------------
// Wave 2a extraction: pure string / phone / admin-sender normalization helpers.
// No module-scope state, no I/O, no dependence on runtime configuration —
// just deterministic string transforms. Extracted from
// `plugins/octopus-channel/index.ts` so inbound handlers and other lib modules
// can share them without pulling in the full plugin bootstrap surface.
// ---------------------------------------------------------------------------

export function asTrimmedString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function normalizePhone(value: unknown): string | null {
  const raw = asTrimmedString(value);
  if (!raw) return null;
  const digits = raw.replace(/[^\d+]/g, "");
  return digits || null;
}

export function looksLikePhone(value: string | null | undefined): boolean {
  return typeof value === "string" && /^\+?\d{7,20}$/.test(value.trim());
}

export function normalizeAllowEntry(value: unknown): string {
  const text = asTrimmedString(value) ?? "";
  const phone = normalizePhone(text);
  if (phone && looksLikePhone(phone)) {
    return phone.replace(/^\+/, "");
  }
  return text;
}

export function normalizeAdminSenderId(value: unknown): string {
  const text = asTrimmedString(value) ?? "";
  if (!text) return "";
  return text
    .replace(/^whatsapp:/i, "")
    .replace(/^octopus:/i, "")
    .replace(/^tel:/i, "")
    .replace(/[^\d+]/g, "")
    .replace(/^\+/, "")
    .trim();
}

export function buildAdminSenderIdCandidates(value: unknown): string[] {
  const normalized = normalizeAdminSenderId(value);
  if (!normalized) return [];

  const candidates = new Set([normalized]);
  if (/^965\d{8}$/.test(normalized)) {
    candidates.add(normalized.slice(-8));
  }
  if (/^00965\d{8}$/.test(normalized)) {
    candidates.add(normalized.slice(-8));
    candidates.add(normalized.slice(2));
  }
  if (/^\d{8}$/.test(normalized)) {
    candidates.add(`965${normalized}`);
    candidates.add(`00965${normalized}`);
  }

  return Array.from(candidates);
}

export function splitMimeType(value: unknown): string | null {
  const mimeType = asTrimmedString(value);
  if (!mimeType) return null;
  return mimeType.split(";")[0]?.trim().toLowerCase() || null;
}

export function describePath(pathValue: string | URL): string {
  return pathValue instanceof URL ? pathValue.pathname : pathValue;
}

export function computeStableTextHash(value: string): string {
  let hashA = 2166136261;
  let hashB = 5381;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    hashA ^= code;
    hashA = Math.imul(hashA, 16777619);
    hashB = Math.imul(hashB, 33) ^ code;
  }
  const partA = (hashA >>> 0).toString(16).padStart(8, "0");
  const partB = (hashB >>> 0).toString(16).padStart(8, "0");
  return `${partA}${partB}`.slice(0, 12);
}
