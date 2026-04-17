// ---------------------------------------------------------------------------
// Wave 1b extraction: pure helpers tied to the riders-tools plugin config and
// admin-sender normalization. No module-scope state is touched here — each
// function is a pure transformation. The stateful `applyPluginConfig` mutator
// still lives in `plugins/riders-tools/index.ts` because it writes a dozen
// module-scope `let` bindings; the store-based refactor for that happens in a
// follow-up wave 1b commit.
// ---------------------------------------------------------------------------

import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import type { PricingData, PricingSourceMode } from "./types";

export function parsePricingSourceMode(value: unknown): PricingSourceMode {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (normalized === "static_only") {
    return "static_only";
  }
  if (normalized === "google_sheet_live") {
    return "google_sheet_live";
  }
  return "published_preferred";
}

export function describePath(pathValue: string | URL) {
  return pathValue instanceof URL ? pathValue.pathname : pathValue;
}

export async function pathExists(pathValue: string | URL) {
  try {
    await fs.stat(pathValue);
    return true;
  } catch {
    return false;
  }
}

export function hashPricingData(data: PricingData) {
  return createHash("sha256").update(JSON.stringify(data)).digest("hex");
}

export function extractCommandErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object") {
    const commandError = error as {
      stdout?: string | Buffer;
      stderr?: string | Buffer;
      message?: string;
    };
    const stderr =
      typeof commandError.stderr === "string"
        ? commandError.stderr.trim()
        : Buffer.isBuffer(commandError.stderr)
          ? commandError.stderr.toString("utf-8").trim()
          : "";
    const stdout =
      typeof commandError.stdout === "string"
        ? commandError.stdout.trim()
        : Buffer.isBuffer(commandError.stdout)
          ? commandError.stdout.toString("utf-8").trim()
          : "";
    return stderr || stdout || commandError.message || fallback;
  }
  return fallback;
}

export function normalizeAdminSenderId(
  value: string | null | undefined,
): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/^octopus:/i, "")
    .replace(/[^\d+]/g, "")
    .replace(/^\+/, "")
    .trim();
}

export function buildAdminSenderIdCandidates(
  value: string | null | undefined,
): string[] {
  const normalized = normalizeAdminSenderId(value);
  if (!normalized) {
    return [];
  }

  const candidates = new Set<string>([normalized]);
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
