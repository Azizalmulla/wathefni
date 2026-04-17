// ---------------------------------------------------------------------------
// Wave 1b extraction: pure pricing-cache helpers.
// Extracted from `plugins/riders-tools/index.ts`. This module intentionally
// holds ONLY the pure fallback loader and a small state container that the
// stateful `loadPricing` / `refreshPricing` / `clearPricingCache` helpers in
// `index.ts` compose against. The full Google-Sheet backed refresh / overlay
// pipeline still lives in `index.ts` because it touches a dozen `let`-scoped
// env-derived bindings (source mode, path overrides, admin allowlists, sync
// bookkeeping); that moves into a `createPricingStore()` factory in a
// follow-up wave once callers route through injected dependencies only.
// ---------------------------------------------------------------------------

import fs from "node:fs/promises";
import type { PricingData } from "./types";
import { pathExists } from "./config";

export type PricingCacheState = {
  data: PricingData | null;
  pathKey: string | null;
  googleLiveLoadInFlight: Promise<PricingData> | null;
};

export function createPricingCacheState(): PricingCacheState {
  return {
    data: null,
    pathKey: null,
    googleLiveLoadInFlight: null,
  };
}

export function clearPricingCacheState(state: PricingCacheState) {
  state.data = null;
  state.pathKey = null;
  state.googleLiveLoadInFlight = null;
}

export async function loadPricingFallbackData(
  publishedPath: string | URL,
  defaultPath: string | URL,
): Promise<PricingData> {
  const targetPath = (await pathExists(publishedPath)) ? publishedPath : defaultPath;
  const raw = await fs.readFile(targetPath, "utf-8");
  return JSON.parse(raw) as PricingData;
}
