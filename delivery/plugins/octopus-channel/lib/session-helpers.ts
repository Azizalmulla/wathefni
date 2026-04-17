// ---------------------------------------------------------------------------
// Wave 2b extraction: pure session/JSON/behavior-filter helpers.
// These are dependency-free utilities for reading agent session records and
// applying tracking-only behavior filters. Extracted from
// `plugins/octopus-channel/index.ts` to reduce its size; nothing here touches
// module-scope state or external I/O.
// ---------------------------------------------------------------------------

import { asTrimmedString } from "./normalize";

export function safeJsonParse(value: string | null | undefined): any {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function parseObjectValue(value: unknown): Record<string, any> | null {
  if (!value) {
    return null;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, any>;
  }
  if (typeof value !== "string") {
    return null;
  }
  const parsed = safeJsonParse(value);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as Record<string, any>)
    : null;
}

export function extractTextFromContent(content: unknown): string | null {
  if (!Array.isArray(content)) {
    return null;
  }
  for (const item of content) {
    const text = item && typeof item === "object" ? asTrimmedString((item as { text?: unknown }).text) : null;
    if (text) return text;
  }
  return null;
}

export function getSessionRecordTimestamp(record: any): number {
  const candidate = record?.timestamp ?? record?.message?.timestamp;
  if (typeof candidate === "number" && Number.isFinite(candidate)) {
    return candidate;
  }
  if (typeof candidate === "string") {
    const parsed = Date.parse(candidate);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return 0;
}

export function isTrackingOnlyBehaviorText(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    normalized.includes("track_order") ||
    normalized.includes("order-") ||
    normalized.includes("tracking") ||
    normalized.includes("order status") ||
    normalized.includes("status update") ||
    normalized.includes("tracking_url") ||
    normalized.includes("agent_phone_number") ||
    normalized.includes("تتبع") ||
    normalized.includes("متابعة الطلب") ||
    normalized.includes("حالة الطلب") ||
    normalized.includes("رقم الطلب")
  );
}

export function filterTrackingOnlyBehaviorRules<T extends Record<string, unknown>>(
  rules: T[],
  includeTrackingOnly: boolean,
): T[] {
  if (includeTrackingOnly) {
    return rules;
  }
  return rules.filter((rule) => !isTrackingOnlyBehaviorText(JSON.stringify(rule)));
}
