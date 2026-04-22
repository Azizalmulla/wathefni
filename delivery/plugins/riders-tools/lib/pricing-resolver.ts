// ---------------------------------------------------------------------------
// Wave 1b extraction: pure pricing-data & resolver-config helpers.
// Extracted from `plugins/riders-tools/index.ts`. These functions perform
// deterministic shape normalization, validation, and merging on resolver
// config + published pricing documents. They do not touch any module-scope
// state and are safe to call from anywhere (tool modules, scripts, tests).
// Stateful wrappers such as `applyPricingResolverOverlayIfConfigured`,
// `inspectPricingResolverOverlay`, `loadPricing`, `refreshPricing`, and the
// in-memory pricing cache remain in `index.ts`; they rely on module-scope
// path overrides and caches that are gated for a later `pricing-cache.ts`
// extraction once a small `createPricingStore()` factory is introduced.
// ---------------------------------------------------------------------------

import type {
  PricingArea,
  PricingData,
  PricingGeoAreaHint,
  PricingResolverAliasEntry,
  PricingResolverAmbiguityGroup,
  PricingResolverConfig,
  PricingResolverPricingGroup,
  PricingResolverSummary,
  QuoteableDeliveryType,
  BookableDeliveryType,
} from "./types";
import {
  normalizeForFuzzyMatch,
  stripArDefiniteArticle,
  canonicalizeAreaName,
  normalizeEn,
  normalizeLatinAreaKey,
} from "./area-matching";
import { isRecord } from "./google-sheets";

export const pricingColumnKeys: QuoteableDeliveryType[] = [
  "sedan_normal",
  "sedan_fast",
  "cooled_van_normal",
  "cooled_van_fast",
  "van_normal",
  "van_fast",
  "helper_standard",
];

export const defaultPricingColumns: Record<QuoteableDeliveryType, string> = {
  sedan_normal: "سيارة عادية توصيل عادي",
  sedan_fast: "سيارة عادية توصيل مستعجل",
  cooled_van_normal: "سيارة مبردة توصيل عادي",
  cooled_van_fast: "سيارة مبردة توصيل مستعجل",
  van_normal: "بوكس مقفل توصيل عادي",
  van_fast: "بوكس مقفل توصيل مستعجل",
  helper_standard: "مع مساعد (عادي)",
};

export const PRICING_AREA_PRICE_KEYS: Array<
  | "sedan_normal"
  | "sedan_fast"
  | "cooled_van_normal"
  | "cooled_van_fast"
  | "van_normal"
  | "van_fast"
  | "helper_standard"
> = [
  "sedan_normal",
  "sedan_fast",
  "cooled_van_normal",
  "cooled_van_fast",
  "van_normal",
  "van_fast",
  "helper_standard",
];

export function parseNumericPrice(value: string | number | null | undefined) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function normalizePricingNumber(value: number) {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error("Price must be a non-negative number.");
  }
  return Math.round(value * 1000) / 1000;
}

export function normalizePricingText(value: unknown, field: string) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${field} must be a non-empty string.`);
  }
  return value.trim();
}

export function normalizePublishedPricingValue(value: unknown, field: string) {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) {
      throw new Error(`${field} must be a number or null.`);
    }
    return normalizePricingNumber(parsed);
  }

  if (typeof value === "number") {
    return normalizePricingNumber(value);
  }

  throw new Error(`${field} must be a number or null.`);
}

export function normalizePublishedPricingColumns(
  input: unknown,
  fallback: Record<string, string>,
) {
  const columns: Record<string, string> = {};
  for (const key of pricingColumnKeys) {
    columns[key] = fallback[key] || defaultPricingColumns[key];
  }

  if (input === null || input === undefined) {
    return columns;
  }

  if (!isRecord(input)) {
    throw new Error("columns must be an object.");
  }

  for (const key of pricingColumnKeys) {
    if (!(key in input)) {
      continue;
    }
    const value = input[key];
    if (typeof value !== "string" || !value.trim()) {
      throw new Error(`columns.${key} must be a non-empty string.`);
    }
    columns[key] = value.trim();
  }

  return columns;
}

export function normalizePricingGeoAreaHint(
  input: unknown,
  field: string,
): PricingGeoAreaHint | undefined {
  if (input === undefined || input === null) {
    return undefined;
  }
  if (!isRecord(input)) {
    throw new Error(`${field} must be an object when provided.`);
  }

  const governorate =
    typeof input.governorate === "string" && input.governorate.trim()
      ? input.governorate.trim()
      : undefined;
  const areaNameAr =
    typeof input.area_name_ar === "string" && input.area_name_ar.trim()
      ? input.area_name_ar.trim()
      : undefined;
  const areaNameEn =
    typeof input.area_name_en === "string" && input.area_name_en.trim()
      ? input.area_name_en.trim()
      : undefined;
  const objectid =
    typeof input.objectid === "string" && input.objectid.trim()
      ? input.objectid.trim()
      : undefined;

  if (!governorate && !areaNameAr && !areaNameEn && !objectid) {
    return undefined;
  }

  return {
    ...(governorate ? { governorate } : {}),
    ...(areaNameAr ? { area_name_ar: areaNameAr } : {}),
    ...(areaNameEn ? { area_name_en: areaNameEn } : {}),
    ...(objectid ? { objectid } : {}),
  };
}

export function normalizePublishedPricingArea(
  input: unknown,
  index: number,
): PricingArea {
  if (!isRecord(input)) {
    throw new Error(`areas[${index}] must be an object.`);
  }

  const parsedId = typeof input.id === "string" ? Number(input.id) : input.id;
  if (
    typeof parsedId !== "number" ||
    !Number.isInteger(parsedId) ||
    parsedId <= 0
  ) {
    throw new Error(`areas[${index}].id must be a positive integer.`);
  }

  return {
    id: parsedId,
    governorate: normalizePricingText(
      input.governorate,
      `areas[${index}].governorate`,
    ),
    name_en: normalizePricingText(input.name_en, `areas[${index}].name_en`),
    name_ar: normalizePricingText(input.name_ar, `areas[${index}].name_ar`),
    sedan_normal: normalizePublishedPricingValue(
      input.sedan_normal,
      `areas[${index}].sedan_normal`,
    ),
    sedan_fast: normalizePublishedPricingValue(
      input.sedan_fast,
      `areas[${index}].sedan_fast`,
    ),
    cooled_van_normal: normalizePublishedPricingValue(
      input.cooled_van_normal,
      `areas[${index}].cooled_van_normal`,
    ),
    cooled_van_fast: normalizePublishedPricingValue(
      input.cooled_van_fast,
      `areas[${index}].cooled_van_fast`,
    ),
    van_normal: normalizePublishedPricingValue(
      input.van_normal,
      `areas[${index}].van_normal`,
    ),
    van_fast: normalizePublishedPricingValue(
      input.van_fast,
      `areas[${index}].van_fast`,
    ),
    helper_standard: normalizePublishedPricingValue(
      input.helper_standard,
      `areas[${index}].helper_standard`,
    ),
    ...(normalizePricingGeoAreaHint(input.geo, `areas[${index}].geo`)
      ? { geo: normalizePricingGeoAreaHint(input.geo, `areas[${index}].geo`) }
      : {}),
  };
}

export function normalizePricingResolverAliasEntry(
  input: unknown,
  index: number,
): PricingResolverAliasEntry {
  if (!isRecord(input)) {
    throw new Error(`resolver.aliases[${index}] must be an object.`);
  }

  const alias = normalizePricingText(
    input.alias,
    `resolver.aliases[${index}].alias`,
  );
  const areaId = input.area_id === undefined ? undefined : Number(input.area_id);
  const pricingGroupId =
    typeof input.pricing_group_id === "string" && input.pricing_group_id.trim()
      ? input.pricing_group_id.trim()
      : undefined;
  const ambiguityGroupId =
    typeof input.ambiguity_group_id === "string" &&
    input.ambiguity_group_id.trim()
      ? input.ambiguity_group_id.trim()
      : undefined;

  if (areaId !== undefined && (!Number.isInteger(areaId) || areaId <= 0)) {
    throw new Error(
      `resolver.aliases[${index}].area_id must be a positive integer when provided.`,
    );
  }

  const targetCount =
    Number(areaId !== undefined) +
    Number(Boolean(pricingGroupId)) +
    Number(Boolean(ambiguityGroupId));
  if (targetCount !== 1) {
    throw new Error(
      `resolver.aliases[${index}] must define exactly one of area_id, pricing_group_id, or ambiguity_group_id.`,
    );
  }

  return {
    alias,
    ...(areaId !== undefined ? { area_id: areaId } : {}),
    ...(pricingGroupId ? { pricing_group_id: pricingGroupId } : {}),
    ...(ambiguityGroupId ? { ambiguity_group_id: ambiguityGroupId } : {}),
  };
}

export function normalizePricingResolverStringArray(
  value: unknown,
  field: string,
): string[] | undefined {
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value)) {
    throw new Error(`${field} must be an array when provided.`);
  }
  const items = value
    .map((entry, index) => normalizePricingText(entry, `${field}[${index}]`))
    .filter(Boolean);
  return items.length > 0 ? items : undefined;
}

export function normalizePricingResolverPricingGroup(
  input: unknown,
  index: number,
): PricingResolverPricingGroup {
  if (!isRecord(input)) {
    throw new Error(`resolver.pricing_groups[${index}] must be an object.`);
  }
  const id =
    typeof input.id === "string" && input.id.trim()
      ? input.id.trim()
      : (() => {
          throw new Error(
            `resolver.pricing_groups[${index}].id must be a non-empty string.`,
          );
        })();
  if (!Array.isArray(input.area_ids) || input.area_ids.length === 0) {
    throw new Error(
      `resolver.pricing_groups[${index}].area_ids must be a non-empty array.`,
    );
  }
  const areaIds = input.area_ids.map((value, areaIndex) => {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      throw new Error(
        `resolver.pricing_groups[${index}].area_ids[${areaIndex}] must be a positive integer.`,
      );
    }
    return parsed;
  });

  return {
    id,
    ...(typeof input.name_ar === "string" && input.name_ar.trim()
      ? { name_ar: input.name_ar.trim() }
      : {}),
    ...(typeof input.name_en === "string" && input.name_en.trim()
      ? { name_en: input.name_en.trim() }
      : {}),
    area_ids: areaIds,
    ...(normalizePricingResolverStringArray(
      input.aliases,
      `resolver.pricing_groups[${index}].aliases`,
    )
      ? {
          aliases: normalizePricingResolverStringArray(
            input.aliases,
            `resolver.pricing_groups[${index}].aliases`,
          ),
        }
      : {}),
    ...(normalizePricingGeoAreaHint(
      input.geo,
      `resolver.pricing_groups[${index}].geo`,
    )
      ? {
          geo: normalizePricingGeoAreaHint(
            input.geo,
            `resolver.pricing_groups[${index}].geo`,
          ),
        }
      : {}),
  };
}

export function normalizePricingResolverAmbiguityGroup(
  input: unknown,
  index: number,
): PricingResolverAmbiguityGroup {
  if (!isRecord(input)) {
    throw new Error(`resolver.ambiguity_groups[${index}] must be an object.`);
  }
  const id =
    typeof input.id === "string" && input.id.trim()
      ? input.id.trim()
      : (() => {
          throw new Error(
            `resolver.ambiguity_groups[${index}].id must be a non-empty string.`,
          );
        })();

  // Class-12 invariant (2026-04-21): every ambiguity group MUST enumerate
  // its member areas. A group that resolves at runtime with `options=[]`
  // collapses the entire clarification flow (no choices surfaced in the
  // reply, no options for the DST-swap misroute guard on the next turn),
  // which is exactly the loop we saw on `kuwait_city_downtown`. We enforce
  // this at load time so the failure mode is a loud startup error on any
  // future group that ships incomplete, not a silent runtime degradation.
  const rawOptions = input.options;
  if (!Array.isArray(rawOptions) || rawOptions.length === 0) {
    throw new Error(
      `resolver.ambiguity_groups["${id}"].options must be a non-empty array of member areas. Every ambiguity group must enumerate the candidate areas it can disambiguate into.`,
    );
  }
  const options = rawOptions.map((entry, optionIndex) => {
    if (!isRecord(entry)) {
      throw new Error(
        `resolver.ambiguity_groups["${id}"].options[${optionIndex}] must be an object.`,
      );
    }
    if (typeof entry.area_id !== "number" || !Number.isFinite(entry.area_id)) {
      throw new Error(
        `resolver.ambiguity_groups["${id}"].options[${optionIndex}].area_id must be a finite number.`,
      );
    }
    const nameEn = normalizePricingText(
      entry.name_en,
      `resolver.ambiguity_groups["${id}"].options[${optionIndex}].name_en`,
    );
    const nameAr = normalizePricingText(
      entry.name_ar,
      `resolver.ambiguity_groups["${id}"].options[${optionIndex}].name_ar`,
    );
    return { area_id: entry.area_id, name_en: nameEn, name_ar: nameAr };
  });
  const seenOptionIds = new Set<number>();
  for (const opt of options) {
    if (seenOptionIds.has(opt.area_id)) {
      throw new Error(
        `resolver.ambiguity_groups["${id}"].options contains a duplicate area_id: ${opt.area_id}.`,
      );
    }
    seenOptionIds.add(opt.area_id);
  }

  return {
    id,
    prompt_ar: normalizePricingText(
      input.prompt_ar,
      `resolver.ambiguity_groups[${index}].prompt_ar`,
    ),
    prompt_en: normalizePricingText(
      input.prompt_en,
      `resolver.ambiguity_groups[${index}].prompt_en`,
    ),
    options,
    ...(normalizePricingResolverStringArray(
      input.aliases,
      `resolver.ambiguity_groups[${index}].aliases`,
    )
      ? {
          aliases: normalizePricingResolverStringArray(
            input.aliases,
            `resolver.ambiguity_groups[${index}].aliases`,
          ),
        }
      : {}),
  };
}

export function normalizePricingResolverConfig(
  input: unknown,
  fallback?: PricingResolverConfig,
): PricingResolverConfig | undefined {
  if (input === undefined || input === null) {
    return fallback;
  }
  if (!isRecord(input)) {
    throw new Error("resolver must be an object when provided.");
  }

  const aliases = Array.isArray(input.aliases)
    ? input.aliases.map((entry, index) =>
        normalizePricingResolverAliasEntry(entry, index),
      )
    : fallback?.aliases;
  const pricingGroups = Array.isArray(input.pricing_groups)
    ? input.pricing_groups.map((entry, index) =>
        normalizePricingResolverPricingGroup(entry, index),
      )
    : fallback?.pricing_groups;
  const ambiguityGroups = Array.isArray(input.ambiguity_groups)
    ? input.ambiguity_groups.map((entry, index) =>
        normalizePricingResolverAmbiguityGroup(entry, index),
      )
    : fallback?.ambiguity_groups;

  if (!aliases && !pricingGroups && !ambiguityGroups) {
    return undefined;
  }

  return {
    ...(aliases ? { aliases } : {}),
    ...(pricingGroups ? { pricing_groups: pricingGroups } : {}),
    ...(ambiguityGroups ? { ambiguity_groups: ambiguityGroups } : {}),
  };
}

export function validatePricingResolverConfig(
  resolver: PricingResolverConfig | undefined,
  areas: PricingArea[],
) {
  if (!resolver) return;

  const areaIds = new Set(areas.map((area) => area.id));
  const pricingGroupIds = new Set<string>();
  for (const group of resolver.pricing_groups || []) {
    if (pricingGroupIds.has(group.id)) {
      throw new Error(
        `resolver.pricing_groups contains a duplicate id: ${group.id}`,
      );
    }
    pricingGroupIds.add(group.id);
    for (const areaId of group.area_ids) {
      if (!areaIds.has(areaId)) {
        throw new Error(
          `resolver.pricing_groups["${group.id}"] references unknown area id ${areaId}.`,
        );
      }
    }
  }

  const ambiguityGroupIds = new Set<string>();
  for (const group of resolver.ambiguity_groups || []) {
    if (ambiguityGroupIds.has(group.id)) {
      throw new Error(
        `resolver.ambiguity_groups contains a duplicate id: ${group.id}`,
      );
    }
    ambiguityGroupIds.add(group.id);
    // Class-12 invariant: options[*].area_id must point to a real area.
    for (const opt of group.options) {
      if (!areaIds.has(opt.area_id)) {
        throw new Error(
          `resolver.ambiguity_groups["${group.id}"].options references unknown area id ${opt.area_id}.`,
        );
      }
    }
  }

  for (const aliasEntry of resolver.aliases || []) {
    if (aliasEntry.area_id !== undefined && !areaIds.has(aliasEntry.area_id)) {
      throw new Error(
        `resolver.aliases["${aliasEntry.alias}"] references unknown area id ${aliasEntry.area_id}.`,
      );
    }
    if (
      aliasEntry.pricing_group_id &&
      !pricingGroupIds.has(aliasEntry.pricing_group_id)
    ) {
      throw new Error(
        `resolver.aliases["${aliasEntry.alias}"] references unknown pricing group id ${aliasEntry.pricing_group_id}.`,
      );
    }
    if (
      aliasEntry.ambiguity_group_id &&
      !ambiguityGroupIds.has(aliasEntry.ambiguity_group_id)
    ) {
      throw new Error(
        `resolver.aliases["${aliasEntry.alias}"] references unknown ambiguity group id ${aliasEntry.ambiguity_group_id}.`,
      );
    }
  }
}

export function mergePricingResolverConfigs(
  base: PricingResolverConfig | undefined,
  overlay: PricingResolverConfig | undefined,
): PricingResolverConfig | undefined {
  if (!overlay) return base;
  if (!base) return overlay;

  const aliasByKey = new Map<string, PricingResolverAliasEntry>();
  for (const entry of base.aliases || []) {
    aliasByKey.set(normalizeForFuzzyMatch(entry.alias), entry);
  }
  for (const entry of overlay.aliases || []) {
    aliasByKey.set(normalizeForFuzzyMatch(entry.alias), entry);
  }

  const pricingGroupById = new Map<string, PricingResolverPricingGroup>();
  for (const group of base.pricing_groups || []) {
    pricingGroupById.set(group.id, group);
  }
  for (const group of overlay.pricing_groups || []) {
    pricingGroupById.set(group.id, group);
  }

  const ambiguityById = new Map<string, PricingResolverAmbiguityGroup>();
  for (const group of base.ambiguity_groups || []) {
    ambiguityById.set(group.id, group);
  }
  for (const group of overlay.ambiguity_groups || []) {
    ambiguityById.set(group.id, group);
  }

  const aliases =
    aliasByKey.size > 0 ? Array.from(aliasByKey.values()) : undefined;
  const pricing_groups =
    pricingGroupById.size > 0
      ? Array.from(pricingGroupById.values())
      : undefined;
  const ambiguity_groups =
    ambiguityById.size > 0 ? Array.from(ambiguityById.values()) : undefined;

  if (!aliases && !pricing_groups && !ambiguity_groups) {
    return undefined;
  }

  return {
    ...(aliases ? { aliases } : {}),
    ...(pricing_groups ? { pricing_groups } : {}),
    ...(ambiguity_groups ? { ambiguity_groups } : {}),
  };
}

export function buildPublishedPricingData(
  input: {
    currency?: unknown;
    last_updated?: unknown;
    columns?: unknown;
    resolver?: unknown;
    areas: unknown;
  },
  fallback: PricingData,
): PricingData {
  if (!Array.isArray(input.areas) || input.areas.length === 0) {
    throw new Error("areas must be a non-empty array.");
  }

  const areas = input.areas.map((item, index) =>
    normalizePublishedPricingArea(item, index),
  );
  const seenIds = new Set<number>();
  for (const area of areas) {
    if (seenIds.has(area.id)) {
      throw new Error(`Duplicate area id found: ${area.id}`);
    }
    seenIds.add(area.id);
  }

  const resolver = normalizePricingResolverConfig(
    input.resolver,
    fallback.resolver,
  );
  validatePricingResolverConfig(resolver, areas);

  return {
    currency:
      typeof input.currency === "string" && input.currency.trim()
        ? input.currency.trim()
        : fallback.currency || "KWD",
    last_updated:
      typeof input.last_updated === "string" && input.last_updated.trim()
        ? input.last_updated.trim()
        : new Date().toISOString(),
    columns: normalizePublishedPricingColumns(input.columns, fallback.columns),
    areas,
    ...(resolver ? { resolver } : {}),
  };
}

export function summarizePricingResolver(
  resolver: PricingResolverConfig | undefined,
): PricingResolverSummary {
  return {
    aliases_count: resolver?.aliases?.length ?? 0,
    pricing_group_count: resolver?.pricing_groups?.length ?? 0,
    ambiguity_group_count: resolver?.ambiguity_groups?.length ?? 0,
    alias_preview: (resolver?.aliases || [])
      .map((entry) => entry.alias)
      .slice(0, 10),
    pricing_group_ids: (resolver?.pricing_groups || [])
      .map((entry) => entry.id)
      .slice(0, 10),
    ambiguity_group_ids: (resolver?.ambiguity_groups || [])
      .map((entry) => entry.id)
      .slice(0, 10),
  };
}

export function resolvePricingResolverOverlayInput(
  parsed: unknown,
  overlayPath: string,
): {
  resolverInput: unknown;
  sourceShape: "resolver_wrapper" | "resolver_fields";
} {
  if (!isRecord(parsed)) {
    throw new Error(
      `Resolver overlay must decode to an object: ${overlayPath}`,
    );
  }

  if (parsed.resolver !== undefined && parsed.resolver !== null) {
    return {
      resolverInput: parsed.resolver,
      sourceShape: "resolver_wrapper",
    };
  }

  if (
    Array.isArray(parsed.aliases) ||
    Array.isArray(parsed.pricing_groups) ||
    Array.isArray(parsed.ambiguity_groups)
  ) {
    return {
      resolverInput: parsed,
      sourceShape: "resolver_fields",
    };
  }

  throw new Error(
    `Resolver overlay must contain either {"resolver": {...}} or top-level aliases/pricing_groups/ambiguity_groups: ${overlayPath}`,
  );
}

export function buildResolverLookupKeys(text: string): Set<string> {
  const keys = new Set<string>();
  const raw = typeof text === "string" ? text.trim() : "";
  if (!raw) return keys;

  const fuzzy = normalizeForFuzzyMatch(raw);
  if (fuzzy) {
    keys.add(`fuzzy:${fuzzy}`);
    const fuzzyStripped = stripArDefiniteArticle(fuzzy);
    if (fuzzyStripped && fuzzyStripped !== fuzzy) {
      keys.add(`fuzzy:${fuzzyStripped}`);
    }
  }

  const canonical = canonicalizeAreaName(raw);
  if (canonical) {
    keys.add(`canon:${canonical}`);
    const canonicalStripped = stripArDefiniteArticle(canonical);
    if (canonicalStripped && canonicalStripped !== canonical) {
      keys.add(`canon:${canonicalStripped}`);
    }
  }

  const english = normalizeEn(raw);
  if (english) keys.add(`en:${english}`);

  const latin = normalizeLatinAreaKey(raw);
  if (latin) keys.add(`latin:${latin}`);

  return keys;
}

export function matchesResolverAlias(
  queryKeys: Set<string>,
  alias: string,
): boolean {
  const aliasKeys = buildResolverLookupKeys(alias);
  for (const key of aliasKeys) {
    if (queryKeys.has(key)) return true;
  }
  return false;
}

export function buildPricingAreaFromResolverGroup(
  group: PricingResolverPricingGroup,
  areas: PricingArea[],
): PricingArea | null {
  const groupedAreas = group.area_ids
    .map((areaId) => areas.find((area) => area.id === areaId) || null)
    .filter((area): area is PricingArea => Boolean(area));
  if (
    groupedAreas.length !== group.area_ids.length ||
    groupedAreas.length === 0
  ) {
    return null;
  }

  const representative = groupedAreas[0];
  const sameGovernorate = groupedAreas.every(
    (area) =>
      normalizeForFuzzyMatch(area.governorate) ===
      normalizeForFuzzyMatch(representative.governorate),
  );
  const samePricingProfile = groupedAreas.every((area) =>
    PRICING_AREA_PRICE_KEYS.every((key) => area[key] === representative[key]),
  );
  if (!sameGovernorate || !samePricingProfile) {
    console.warn(
      `[resolver] pricing group ${group.id} could not be materialized because its member rows do not share one governorate and price profile.`,
    );
    return null;
  }

  return {
    ...representative,
    name_ar: group.name_ar || representative.name_ar,
    name_en: group.name_en || representative.name_en,
    ...(group.geo || representative.geo
      ? { geo: group.geo || representative.geo }
      : {}),
  };
}

export function pricesMatch(
  left: number | null | undefined,
  right: number | null | undefined,
) {
  if (
    left === null ||
    left === undefined ||
    right === null ||
    right === undefined
  ) {
    return false;
  }

  return Math.abs(left - right) < 0.0005;
}

export function maxPrice(a: number | null, b: number | null): number | null {
  if (a === null && b === null) return null;
  if (a === null) return b;
  if (b === null) return a;
  return Math.max(a, b);
}

export function getRouteSheetPrice(
  pickup: PricingArea,
  dropoff: PricingArea,
  deliveryType: BookableDeliveryType,
) {
  return maxPrice(pickup[deliveryType], dropoff[deliveryType]);
}

export function getBidirectionalRoutePrices(
  pickup: PricingArea,
  dropoff: PricingArea,
) {
  return {
    sedan_normal: maxPrice(pickup.sedan_normal, dropoff.sedan_normal),
    sedan_fast: maxPrice(pickup.sedan_fast, dropoff.sedan_fast),
    van_normal: maxPrice(pickup.van_normal, dropoff.van_normal),
    van_fast: maxPrice(pickup.van_fast, dropoff.van_fast),
    cooled_van_normal: maxPrice(
      pickup.cooled_van_normal,
      dropoff.cooled_van_normal,
    ),
    cooled_van_fast: maxPrice(pickup.cooled_van_fast, dropoff.cooled_van_fast),
    helper_standard: maxPrice(pickup.helper_standard, dropoff.helper_standard),
  };
}

export function getDeliveryTypeLabels(deliveryType: QuoteableDeliveryType) {
  return {
    sedan_normal: {
      ar: "سيارة عاديه + توصيل عادي",
      en: "Standard sedan",
    },
    sedan_fast: {
      ar: "سيارة عاديه + توصيل سريع",
      en: "Express sedan",
    },
    van_normal: {
      ar: "بوكس مقفل + توصيل عادي",
      en: "Standard box van",
    },
    van_fast: {
      ar: "بوكس مقفل + توصيل مستعجل",
      en: "Express box van",
    },
    cooled_van_normal: {
      ar: "سيارة مبردة + توصيل عادي",
      en: "Standard refrigerated van",
    },
    cooled_van_fast: {
      ar: "سيارة مبردة + توصيل سريع",
      en: "Express refrigerated van",
    },
    helper_standard: {
      ar: "مع مساعد (عادي)",
      en: "Helper service",
    },
  }[deliveryType];
}
