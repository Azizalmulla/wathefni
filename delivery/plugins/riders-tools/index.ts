import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import {
  buildConversationControllerKey,
  CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS,
  extractTrackingOrderId,
  hasRouteEvidence,
  isExplicitOrderConfirmation,
  isBookingStartIntent,
  isGeneralServiceInquiry,
  isPassengerTransportRequest,
  isSimpleGreeting,
  normalizeIntentText,
  resolveSessionIdentityKey,
} from "../shared/conversation-policy";
import {
  persistGuardSessionAliases,
  PersistedGuardSessionState,
} from "../shared/guard-state";
import {
  pushResponderStateOp,
  ResponderStateOp,
  ResponderBookingFieldOp,
  validateApplyBookingFieldOp,
  sanityCheckBookingDraft,
} from "../shared/responder-state-ops";
import {
  guardCreateSimpleOrder,
  describeRejection,
} from "../shared/order-guard";
import { looksLikeInteriorDetail } from "../shared/booking-draft";
import type { ToolDeps } from "./tools/deps";
import {
  parsePricingSourceMode,
  describePath,
  pathExists,
  hashPricingData,
  extractCommandErrorMessage,
  normalizeAdminSenderId,
  buildAdminSenderIdCandidates,
} from "./lib/config";
import {
  normalizeArabic,
  normalizeForFuzzyMatch,
  stripArDefiniteArticle,
  AREA_PREFIX_RE,
  AREA_DIRECTION_PREFIX_RE,
  canonicalizeAreaName,
  areaTokens,
  NON_DISTINGUISHING_AREA_TOKENS,
  NON_DISTINGUISHING_EN_TOKENS,
  normalizeEnSubstring,
  isNumericAreaSuffixToken,
  diffMeaningfulAreaTokens,
  diffMeaningfulEnTokens,
  stripTrailingNumericAreaSuffix,
  extractTrailingNumericAreaSuffix,
  stripFlexibleTrailingNumericAreaSuffix,
  hasTokenConflict,
  normalizeEn,
  normalizeLatinAreaToken,
  normalizeLatinAreaKey,
  normalizeLatinAreaKeyForMatching,
  canonicalizeAreaNameForMatching,
  scoreAreaMatchSimilarity,
  containsArabicScript,
  compactLookupKey,
  damerauLevenshteinDistance,
  normalizeGovernorateName,
  buildSheetHeaderFingerprints,
} from "./lib/area-matching";
import {
  asOptionalTrimmedString,
  parseJsonInput,
  createEmptyBehaviorPolicy,
  normalizeBehaviorPriority,
  getNextBehaviorPriority,
  normalizeBehaviorLanguageScope,
  createBehaviorRuleId,
  normalizeBehaviorEnabled,
  normalizeBehaviorStringArray,
  normalizeBehaviorReplyCorrection,
  normalizeBehaviorFlowRule,
  normalizeBehaviorPhraseGuard,
  sortBehaviorRules,
  normalizeBehaviorPolicyDocument,
  buildNextBehaviorPolicy as libBuildNextBehaviorPolicy,
  resolveBehaviorPolicyInput,
  resolveBehaviorRequiredStepsInput,
  resolveBehaviorLiveInstructionsInput,
  findBehaviorRuleLocation,
} from "./lib/behavior-policy";
import { registerAdminWorkspaceTools } from "./tools/admin-workspace";
import { registerAdminSheetsTools } from "./tools/admin-sheets";
import { registerAdminBehaviorTools } from "./tools/admin-behavior";
import { registerAdminPricingTools } from "./tools/admin-pricing";
import { registerCustomerSupportTools } from "./tools/support";
import { registerPricingTools } from "./tools/pricing";
import { registerBookingTools } from "./tools/booking";
import { createGuardModule } from "./tools/guards";

const RIDERS_ONE_BRAIN_ENABLED = (() => {
  const raw = String(process.env.RIDERS_ONE_BRAIN || "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
})();

function resolveToolConversationId(ctx: any): string {
  const direct = String(ctx?.ConversationId || ctx?.conversationId || ctx?.ConversationID || "").trim();
  if (direct) return direct;
  const to = String(ctx?.To || ctx?.to || "").trim();
  if (to.startsWith("octopus:")) {
    const extracted = to.slice("octopus:".length).trim();
    if (extracted) return extracted;
  }
  const sessionKey = String(ctx?.SessionKey || ctx?.sessionKey || "").trim();
  const match = sessionKey.match(/:octopus:direct:(.+?)(?:::prompt=|$)/);
  if (match?.[1]) {
    return match[1].trim();
  }
  return "";
}

function resolveToolTurnId(ctx: any): string {
  const value =
    ctx?.TurnId ||
    ctx?.turnId ||
    ctx?.MessageId ||
    ctx?.messageId ||
    ctx?.InboundMessageId ||
    ctx?.inboundMessageId;
  const trimmed = String(value || "").trim();
  return trimmed || String(Date.now());
}

// ---------------------------------------------------------------------------
// Types (moved to ./lib/types.ts in wave 1b; imported below)
// ---------------------------------------------------------------------------
import type {
  PricingArea,
  PricingGeoAreaHint,
  PricingResolverAliasEntry,
  PricingResolverPricingGroup,
  PricingResolverAmbiguityGroup,
  PricingResolverConfig,
  PricingData,
  PricingResolverSummary,
  PricingResolverOverlayStatus,
  GeoGovernorate,
  GeoShippingMethod,
  GeoArea,
  RidersApiPayload,
  BookableDeliveryType,
  PricingSourceMode,
  TrackingProvider,
  QuoteableDeliveryType,
  SpecialQuoteableDeliveryType,
  LiveDeliveryOptionSummary,
  SpecialDeliveryCapabilitySummary,
  RidersGridLiveSettingsSummary,
  ServiceCatalogEntry,
  RidersToolsPluginConfig,
  PricingAreaFieldKey,
  BehaviorLanguageScope,
  BehaviorPhraseGuardKind,
  BehaviorReplyCorrection,
  BehaviorFlowRule,
  BehaviorPhraseGuard,
  BehaviorPolicy,
} from "./lib/types";

import {
  pricingColumnKeys,
  defaultPricingColumns,
  PRICING_AREA_PRICE_KEYS,
  parseNumericPrice,
  normalizePricingNumber,
  normalizePricingText,
  normalizePublishedPricingValue,
  normalizePublishedPricingColumns,
  normalizePricingGeoAreaHint,
  normalizePublishedPricingArea,
  normalizePricingResolverAliasEntry,
  normalizePricingResolverStringArray,
  normalizePricingResolverPricingGroup,
  normalizePricingResolverAmbiguityGroup,
  normalizePricingResolverConfig,
  validatePricingResolverConfig,
  mergePricingResolverConfigs,
  buildPublishedPricingData,
  summarizePricingResolver,
  resolvePricingResolverOverlayInput,
  buildResolverLookupKeys,
  matchesResolverAlias,
  buildPricingAreaFromResolverGroup,
  pricesMatch,
  maxPrice,
  getRouteSheetPrice,
  getBidirectionalRoutePrices,
  getDeliveryTypeLabels,
} from "./lib/pricing-resolver";

import { loadPricingFallbackData as libLoadPricingFallbackData } from "./lib/pricing-cache";

const pricingSheetFieldAliases: Record<PricingAreaFieldKey, string[]> = {
  id: ["id", "area_id", "area id", "areaid", "geo_area_id", "geo area id", "geoid"],
  governorate: [
    "governorate",
    "governorate_name",
    "governorate name",
    "gov",
    "gov_name",
    "المحافظة - governorate",
    "المحافظة",
    "محافظة",
  ],
  name_en: [
    "name_en",
    "name en",
    "area_en",
    "area en",
    "area_name_en",
    "area name en",
    "english_name",
    "english name",
    "english_area",
    "english area",
    "name (english)",
    "name",
    "area",
  ],
  name_ar: [
    "name_ar",
    "name ar",
    "area_ar",
    "area ar",
    "area_name_ar",
    "area name ar",
    "arabic_name",
    "arabic name",
    "arabic_area",
    "arabic area",
    "name (arabic)",
    "اسم المنطقة",
    "الاسم العربي",
    "الإسم (عربي)",
    "الاسم (عربي)",
    "المنطقة",
  ],
  sedan_normal: [
    "sedan_normal",
    "sedan normal",
    "standard sedan",
    "car standard",
    "sedan normal delivery",
    "car (standard) price",
    "car standard price",
    defaultPricingColumns.sedan_normal,
  ],
  sedan_fast: [
    "sedan_fast",
    "sedan fast",
    "express sedan",
    "car express",
    "sedan fast delivery",
    "car (super rider) price",
    "car super rider price",
    defaultPricingColumns.sedan_fast,
  ],
  cooled_van_normal: [
    "cooled_van_normal",
    "cooled van normal",
    "refrigerated van standard",
    "standard refrigerated van",
    "cooled van normal delivery",
    "cooler (standard) price",
    "cooler standard price",
    defaultPricingColumns.cooled_van_normal,
  ],
  cooled_van_fast: [
    "cooled_van_fast",
    "cooled van fast",
    "refrigerated van express",
    "express refrigerated van",
    "cooled van fast delivery",
    "cooler (super rider) price",
    "cooler super rider price",
    defaultPricingColumns.cooled_van_fast,
  ],
  van_normal: [
    "van_normal",
    "van normal",
    "box van standard",
    "standard box van",
    "van normal delivery",
    "van (standard) price",
    "van standard price",
    defaultPricingColumns.van_normal,
  ],
  van_fast: [
    "van_fast",
    "van fast",
    "box van express",
    "express box van",
    "van fast delivery",
    "van (super rider) price",
    "van super rider price",
    defaultPricingColumns.van_fast,
  ],
  helper_standard: [
    "helper_standard",
    "helper standard",
    "helper",
    "helper service",
    "helper (standard) price",
    "helper standard price",
    defaultPricingColumns.helper_standard,
  ],
};

const pricingAreaFieldKeys: PricingAreaFieldKey[] = [
  "id",
  "governorate",
  "name_en",
  "name_ar",
  "sedan_normal",
  "sedan_fast",
  "cooled_van_normal",
  "cooled_van_fast",
  "van_normal",
  "van_fast",
  "helper_standard",
];

// ---------------------------------------------------------------------------
// Pricing data cache (loaded once, reused)
// ---------------------------------------------------------------------------

let pricingCache: PricingData | null = null;
let pricingCachePath: string | null = null;
let behaviorPolicyCache: BehaviorPolicy | null = null;
let behaviorPolicyCachePath: string | null = null;
let pricingGoogleLiveLoadInFlight: Promise<PricingData> | null = null;
let governoratesCache: GeoGovernorate[] | null = null;
const geoAreasCache = new Map<number, GeoArea[]>();
let ridersGridLiveSettingsCache: {
  value: RidersGridLiveSettingsSummary;
  loadedAtMs: number;
} | null = null;

const env = (
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env ?? {}
) as Record<string, string | undefined>;

const defaultPricingPath = new URL("../../workspaces/riders/data/pricing.json", import.meta.url);
const defaultPublishedPricingPath = new URL(
  "../../workspaces/riders/data/pricing.published.json",
  import.meta.url,
);
const defaultBehaviorPolicyPath = new URL(
  "../../workspaces/riders/data/behavior-policy.published.json",
  import.meta.url,
);

// parsePricingSourceMode moved to ./lib/config.ts (wave 1b).

let pricingSourceMode: PricingSourceMode = parsePricingSourceMode(env.RIDERS_PRICING_SOURCE_MODE);
let pricingPublishedPathOverride = env.RIDERS_PRICING_PUBLISHED_PATH?.trim() || "";
let pricingResolverOverlayPathOverride = env.RIDERS_PRICING_RESOLVER_OVERLAY_PATH?.trim() || "";
let pricingAdminAllowlist = (env.RIDERS_PRICING_ADMIN_ALLOWLIST || "")
  .split(",")
  .map((value) => normalizeAdminSenderId(value))
  .filter(Boolean);
let pricingGoogleSheetSpreadsheetId = env.RIDERS_PRICING_SHEET_ID?.trim() || "";
let pricingGoogleSheetName = env.RIDERS_PRICING_SHEET_NAME?.trim() || "";
let pricingGoogleSheetHeaderRow = Math.max(
  1,
  parseInt(env.RIDERS_PRICING_SHEET_HEADER_ROW || "1", 10) || 1,
);
let pricingGoogleAutoSyncEnabled = !/^(0|false|no|off)$/i.test(
  env.RIDERS_PRICING_GOOGLE_AUTO_SYNC || "true",
);
let pricingGoogleAutoSyncMinIntervalMs = Math.max(
  0,
  parseInt(env.RIDERS_PRICING_GOOGLE_AUTO_SYNC_MIN_INTERVAL_MS || "1000", 10) || 1000,
);
let pricingGoogleLastSyncAt: number | null = null;
let pricingGoogleLastSyncAttemptAt: number | null = null;
let pricingGoogleLastSyncError: string | null = null;
let pricingGoogleLastFingerprint = "";
let pricingGoogleSyncInFlight: Promise<void> | null = null;
let behaviorPublishedPathOverride = env.RIDERS_BEHAVIOR_POLICY_PUBLISHED_PATH?.trim() || "";
let behaviorAdminAllowlist = (env.RIDERS_BEHAVIOR_ADMIN_ALLOWLIST || "")
  .split(",")
  .map((value) => normalizeAdminSenderId(value))
  .filter(Boolean);
// ---------------------------------------------------------------------------
// Voyage embedding config
// ---------------------------------------------------------------------------
let voyageApiKey = env.VOYAGE_API_KEY?.trim() || "";
let voyageModel = "voyage-4";
let voyageModelLarge = "voyage-4-large";
let embeddingSimilarityThreshold = 0.75;
let embeddingAmbiguityMargin = 0.04;

const execFileAsync = promisify(execFile);
const trackingProvider: TrackingProvider =
  env.RIDERS_TRACKING_PROVIDER?.trim().toLowerCase() === "fleetrunnr"
    ? "fleetrunnr"
    : "riders";

const ridersApiBaseUrl =
  env.RIDERS_API_BASE_URL?.replace(/\/+$/, "") ||
  "https://order-riders.trywebsight.com/api";
const ridersGridApiBaseUrl =
  env.RIDERS_GRID_API_BASE_URL?.replace(/\/+$/, "") ||
  "https://app-order.tryriders.com/api";
const ridersApiKey = env.RIDERS_API_KEY?.trim() || "";
const ridersGridApiKey = env.RIDERS_GRID_API_KEY?.trim() || ridersApiKey;
const ridersBearerToken = env.RIDERS_BEARER_TOKEN?.trim() || ridersApiKey;
const fleetrunnrApiBaseUrl =
  env.FLEETRUNNR_API_BASE_URL?.replace(/\/+$/, "") ||
  "https://api.fleetrunnr.net/rest/v1";
const fleetrunnrBearerToken = env.FLEETRUNNR_BEARER_TOKEN?.trim() || "";
const writeActionsEnabled = /^(1|true|yes|on)$/i.test(
  env.WRITE_ACTIONS_ENABLED || "",
);
const ridersSourceId = parseInt(env.RIDERS_SOURCE_ID || "1", 10) || 1;
const activeOffers = [
  {
    code: "AM",
    title: "عرض الصباح",
    description:
      "خصم 10% على طلبات الصباح يوميًا حتى الساعة 11:59 صباحًا خلال شهر يناير.",
  },
  {
    code: "1880999",
    title: "عرض المناطق الجديدة",
    description:
      "خصم 10% على الطلب الأول لمناطق المطلاع، صباح الأحمد، الخيران، والوفرة من 10 صباحًا حتى 7 مساءً.",
  },
];

const RIDERS_GRID_SETTINGS_CACHE_TTL_MS = 60_000;

const DIRECT_CHAT_BOOKING_IMPLEMENTED_TYPES = new Set<QuoteableDeliveryType>([
  "sedan_normal",
  "sedan_fast",
  "van_normal",
  "van_fast",
]);

class RidersApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "RidersApiError";
    this.status = status;
    this.details = details;
  }
}

function applyPluginConfig(pluginConfig: unknown) {
  if (!pluginConfig || typeof pluginConfig !== "object") {
    return;
  }

  const config = pluginConfig as RidersToolsPluginConfig;
  const pricingConfig = config.pricing;
  if (pricingConfig && typeof pricingConfig === "object") {
    if (typeof pricingConfig.sourceMode === "string") {
      pricingSourceMode = parsePricingSourceMode(pricingConfig.sourceMode);
    }

    if (typeof pricingConfig.publishedPath === "string") {
      pricingPublishedPathOverride = pricingConfig.publishedPath.trim();
    }

    if (typeof pricingConfig.resolverOverlayPath === "string") {
      pricingResolverOverlayPathOverride = pricingConfig.resolverOverlayPath.trim();
    }

    if (Array.isArray(pricingConfig.adminAllowlist)) {
      pricingAdminAllowlist = Array.from(
        new Set([
          ...pricingAdminAllowlist,
          ...pricingConfig.adminAllowlist.map((value) => normalizeAdminSenderId(value)).filter(Boolean),
        ]),
      );
    }

    if (pricingConfig.googleSheet && typeof pricingConfig.googleSheet === "object") {
      if (
        typeof pricingConfig.googleSheet.spreadsheetId === "string" &&
        pricingConfig.googleSheet.spreadsheetId.trim()
      ) {
        pricingGoogleSheetSpreadsheetId = pricingConfig.googleSheet.spreadsheetId.trim();
      }
      if (typeof pricingConfig.googleSheet.sheetName === "string" && pricingConfig.googleSheet.sheetName.trim()) {
        pricingGoogleSheetName = pricingConfig.googleSheet.sheetName.trim();
      }
      if (typeof pricingConfig.googleSheet.headerRow === "number") {
        pricingGoogleSheetHeaderRow = Math.max(1, Math.trunc(pricingConfig.googleSheet.headerRow));
      }
      if (pricingConfig.googleSheet.autoSync && typeof pricingConfig.googleSheet.autoSync === "object") {
        if (typeof pricingConfig.googleSheet.autoSync.enabled === "boolean") {
          pricingGoogleAutoSyncEnabled = pricingConfig.googleSheet.autoSync.enabled;
        }
        if (typeof pricingConfig.googleSheet.autoSync.minIntervalMs === "number") {
          pricingGoogleAutoSyncMinIntervalMs = Math.max(
            0,
            Math.trunc(pricingConfig.googleSheet.autoSync.minIntervalMs),
          );
        }
      }
    }
  }

  const behaviorConfig = config.behavior;
  if (behaviorConfig && typeof behaviorConfig === "object") {
    if (typeof behaviorConfig.publishedPath === "string") {
      behaviorPublishedPathOverride = behaviorConfig.publishedPath.trim();
    }
    if (Array.isArray(behaviorConfig.adminAllowlist)) {
      behaviorAdminAllowlist = Array.from(
        new Set([
          ...behaviorAdminAllowlist,
          ...behaviorConfig.adminAllowlist.map((value) => normalizeAdminSenderId(value)).filter(Boolean),
        ]),
      );
    }
  }

  const embeddingConfig = config.embedding;
  if (embeddingConfig && typeof embeddingConfig === "object") {
    if (typeof embeddingConfig.voyageApiKey === "string" && embeddingConfig.voyageApiKey.trim()) {
      voyageApiKey = embeddingConfig.voyageApiKey.trim();
    }
    if (typeof embeddingConfig.model === "string" && embeddingConfig.model.trim()) {
      voyageModel = embeddingConfig.model.trim();
    }
    if (typeof embeddingConfig.similarityThreshold === "number") {
      embeddingSimilarityThreshold = Math.max(0, Math.min(1, embeddingConfig.similarityThreshold));
    }
  }

  clearPricingCache();
  clearBehaviorPolicyCache();
  areaEmbeddingCache = null; // invalidate embedding cache on config change
}

async function loadPricing(options?: { skipAutoSync?: boolean }): Promise<PricingData> {
  if (pricingSourceMode === "google_sheet_live") {
    if (pricingGoogleLiveLoadInFlight) {
      return await pricingGoogleLiveLoadInFlight;
    }

    pricingGoogleLiveLoadInFlight = (async () => {
      pricingGoogleLastSyncAttemptAt = Date.now();
      try {
        const fallback = await loadPricingFallbackData();
        const rawRows = await fetchPricingRowsFromGoogleSheet();
        const normalizedRows = normalizeSheetRowsToPublishedAreas(rawRows, {});
        let nextData = buildPublishedPricingData(
          {
            areas: normalizedRows.areas,
          },
          fallback,
        );
        nextData = await applyPricingResolverOverlayIfConfigured(nextData);
        pricingGoogleLastFingerprint = hashPricingData(nextData);
        pricingGoogleLastSyncAt = Date.now();
        pricingGoogleLastSyncError = null;
        return nextData;
      } catch (error) {
        pricingGoogleLastSyncError = error instanceof Error ? error.message : String(error);
        throw error;
      } finally {
        pricingGoogleLiveLoadInFlight = null;
      }
    })();

    return await pricingGoogleLiveLoadInFlight;
  }

  if (!options?.skipAutoSync) {
    await maybeAutoSyncPricingFromGoogleSheet();
  }
  const target = await resolvePricingLoadTarget();
  const overlayKey = pricingResolverOverlayPathOverride
    ? describePath(pricingResolverOverlayPathOverride)
    : "none";
  const targetKey = `${target.source}:${describePath(target.path)}:resolver_overlay=${overlayKey}`;
  if (pricingCache && pricingCachePath === targetKey) return pricingCache;
  const raw = await fs.readFile(target.path, "utf-8");
  let next = JSON.parse(raw) as PricingData;
  next = await applyPricingResolverOverlayIfConfigured(next);
  pricingCache = next;
  pricingCachePath = targetKey;
  return pricingCache;
}

async function loadPricingFallbackData(): Promise<PricingData> {
  return await libLoadPricingFallbackData(resolvePublishedPricingPath(), defaultPricingPath);
}

function clearPricingCache() {
  pricingCache = null;
  pricingCachePath = null;
  pricingGoogleLiveLoadInFlight = null;
}

function clearBehaviorPolicyCache() {
  behaviorPolicyCache = null;
  behaviorPolicyCachePath = null;
}

function resolveGogBinary() {
  return env.GOG_BIN?.trim() || "gog";
}

function buildGogCommandEnv() {
  const processEnv =
    (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
  const nextEnv = { ...processEnv };
  if (env.GOG_ACCOUNT?.trim()) {
    nextEnv.GOG_ACCOUNT = env.GOG_ACCOUNT.trim();
  }
  if (env.GOG_KEYRING_PASSWORD?.trim()) {
    nextEnv.GOG_KEYRING_PASSWORD = env.GOG_KEYRING_PASSWORD.trim();
  }
  if (env.GOG_CLIENT?.trim()) {
    nextEnv.GOG_CLIENT = env.GOG_CLIENT.trim();
  }
  return nextEnv;
}

// extractCommandErrorMessage moved to ./lib/config.ts (wave 1b).

async function runGogJsonCommand(args: string[], commandLabel: string) {
  try {
    const { stdout } = await execFileAsync(resolveGogBinary(), args, {
      env: buildGogCommandEnv(),
      maxBuffer: 20 * 1024 * 1024,
    });
    const text = stdout.trim();
    if (!text) {
      return null;
    }
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new Error(extractCommandErrorMessage(error, `${commandLabel} failed.`));
  }
}

function resolvePricingGoogleSheetReadConfig() {
  const spreadsheetId = pricingGoogleSheetSpreadsheetId.trim();
  if (!spreadsheetId) {
    throw new Error("Google spreadsheet_id is required.");
  }

  const sheetName = pricingGoogleSheetName.trim();
  if (!sheetName) {
    throw new Error("Google sheet_name is required.");
  }

  const headerRow = Math.max(1, Math.trunc(pricingGoogleSheetHeaderRow || 1));
  return {
    spreadsheetId,
    sheetName,
    headerRow,
    range: sheetName,
  };
}

function isPricingGoogleSheetConfigured() {
  return Boolean(pricingGoogleSheetSpreadsheetId.trim() && pricingGoogleSheetName.trim());
}

// Pure Google Sheets helpers moved to ./lib/google-sheets.ts (wave 1b).
import {
  isRecord,
  normalizeGoogleSheetCellValue,
  isGoogleSheetCellEmpty,
  buildGoogleSheetValueTable,
  convertGoogleSheetValuesToRows,
  formatGoogleSheetA1SheetName,
  sheetColumnNumberToLetters,
  parseSheetAreaId,
} from "./lib/google-sheets";

function resolveSheetHeaderNameFromHeaders(
  headers: string[],
  field: PricingAreaFieldKey,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const aliases = headerMap[field] ? [headerMap[field] as string] : pricingSheetFieldAliases[field];
  const aliasFingerprints = new Set(aliases.flatMap((alias) => buildSheetHeaderFingerprints(alias)));
  for (const header of headers) {
    const headerFingerprints = buildSheetHeaderFingerprints(header);
    if (headerFingerprints.some((fingerprint) => aliasFingerprints.has(fingerprint))) {
      return header;
    }
  }
  return null;
}

async function fetchPricingGoogleSheetTable(requestedProfileId?: string | null) {
  if (
    requestedProfileId &&
    env.GOG_ACCOUNT?.trim() &&
    requestedProfileId.trim() &&
    requestedProfileId.trim() !== env.GOG_ACCOUNT.trim()
  ) {
    throw new Error(
      `This Riders runtime now uses gog for Google Sheets access and is configured for ${env.GOG_ACCOUNT.trim()}.`,
    );
  }

  const sheetConfig = resolvePricingGoogleSheetReadConfig();
  const payload = await runGogJsonCommand(
    ["sheets", "get", sheetConfig.spreadsheetId, sheetConfig.range, "--json"],
    "gog sheets get",
  );
  if (!isRecord(payload)) {
    throw new Error("gog sheets get did not return a JSON object.");
  }

  return {
    sheetConfig,
    accessToken: "",
    profile_id: env.GOG_ACCOUNT?.trim() || requestedProfileId?.trim() || "default",
    profile_email: env.GOG_ACCOUNT?.trim() || null,
    table: buildGoogleSheetValueTable(Array.isArray(payload.values) ? payload.values : undefined, sheetConfig.headerRow),
  };
}

async function fetchPricingRowsFromGoogleSheet(requestedProfileId?: string | null) {
  const session = await fetchPricingGoogleSheetTable(requestedProfileId);
  return session.table.rows.map((item) => item.record);
}

async function updateGoogleSheetValue(params: {
  spreadsheetId: string;
  range: string;
  accessToken: string;
  value: string | number | null;
}) {
  void params.accessToken;
  const payload = await runGogJsonCommand(
    [
      "sheets",
      "update",
      params.spreadsheetId,
      params.range,
      "--values-json",
      JSON.stringify([[params.value === null ? "" : params.value]]),
      "--input",
      "USER_ENTERED",
      "--json",
    ],
    "gog sheets update",
  );

  const root = isRecord(payload) ? payload : {};
  const updates = isRecord(root.updates) ? root.updates : root;
  return {
    updatedRange:
      typeof updates.updatedRange === "string"
        ? updates.updatedRange
        : typeof root.updatedRange === "string"
          ? root.updatedRange
          : undefined,
    updatedRows:
      typeof updates.updatedRows === "number"
        ? updates.updatedRows
        : typeof root.updatedRows === "number"
          ? root.updatedRows
          : undefined,
    updatedColumns:
      typeof updates.updatedColumns === "number"
        ? updates.updatedColumns
        : typeof root.updatedColumns === "number"
          ? root.updatedColumns
          : undefined,
    updatedCells:
      typeof updates.updatedCells === "number"
        ? updates.updatedCells
        : typeof root.updatedCells === "number"
          ? root.updatedCells
          : undefined,
  };
}

async function clearGoogleSheetRange(params: {
  spreadsheetId: string;
  range: string;
  accessToken: string;
}) {
  void params.accessToken;
  const payload = await runGogJsonCommand(
    ["sheets", "clear", params.spreadsheetId, params.range, "--json"],
    "gog sheets clear",
  );

  const root = isRecord(payload) ? payload : {};
  return {
    clearedRange:
      typeof root.clearedRange === "string"
        ? root.clearedRange
        : typeof root.range === "string"
          ? root.range
          : undefined,
  };
}

async function appendGoogleSheetValues(params: {
  spreadsheetId: string;
  range: string;
  accessToken: string;
  values: Array<Array<string | number>>;
}) {
  void params.accessToken;
  const payload = await runGogJsonCommand(
    [
      "sheets",
      "append",
      params.spreadsheetId,
      params.range,
      "--values-json",
      JSON.stringify(params.values),
      "--input",
      "USER_ENTERED",
      "--json",
    ],
    "gog sheets append",
  );

  const root = isRecord(payload) ? payload : {};
  const updates = isRecord(root.updates) ? root.updates : root;
  return {
    tableRange:
      typeof root.tableRange === "string"
        ? root.tableRange
        : typeof updates.tableRange === "string"
          ? updates.tableRange
          : undefined,
    updatedRange:
      typeof updates.updatedRange === "string"
        ? updates.updatedRange
        : typeof root.updatedRange === "string"
          ? root.updatedRange
          : undefined,
    updatedRows:
      typeof updates.updatedRows === "number"
        ? updates.updatedRows
        : typeof root.updatedRows === "number"
          ? root.updatedRows
          : undefined,
    updatedColumns:
      typeof updates.updatedColumns === "number"
        ? updates.updatedColumns
        : typeof root.updatedColumns === "number"
          ? root.updatedColumns
          : undefined,
    updatedCells:
      typeof updates.updatedCells === "number"
        ? updates.updatedCells
        : typeof root.updatedCells === "number"
          ? root.updatedCells
          : undefined,
  };
}

function resolveNextPricingAreaIdFromSheetRows(
  rows: Array<{ record: Record<string, unknown> }>,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  let maxId = 0;
  for (const item of rows) {
    const candidate = parseSheetAreaId(resolveSheetFieldValue(item.record, "id", headerMap));
    if (candidate !== null && candidate > maxId) {
      maxId = candidate;
    }
  }
  return maxId + 1;
}

function buildPricingAreaSheetAppendRecord(area: PricingArea) {
  return {
    id: area.id,
    governorate: area.governorate,
    name_en: area.name_en,
    name_ar: area.name_ar,
    sedan_normal: area.sedan_normal,
    sedan_fast: area.sedan_fast,
    cooled_van_normal: area.cooled_van_normal,
    cooled_van_fast: area.cooled_van_fast,
    van_normal: area.van_normal,
    van_fast: area.van_fast,
    helper_standard: area.helper_standard,
  };
}

function buildPricingAreaSheetAppendValues(params: {
  headers: string[];
  area: PricingArea;
  headerMap: Partial<Record<PricingAreaFieldKey, string>>;
}) {
  const valuesByHeader = new Map<string, string | number>();
  const requiredFields: PricingAreaFieldKey[] = [
    "id",
    "governorate",
    "name_en",
    "name_ar",
    ...pricingColumnKeys,
  ];

  for (const field of requiredFields) {
    const headerName = resolveSheetHeaderNameFromHeaders(params.headers, field, params.headerMap);
    if (!headerName) {
      throw new Error(`Google Sheet column not found for ${field}.`);
    }
    const value = params.area[field];
    valuesByHeader.set(headerName, value === null ? "" : value);
  }

  return params.headers.map((header) => valuesByHeader.get(header) ?? "");
}

function isSamePricingAreaIdentity(
  left: Pick<PricingArea, "governorate" | "name_en" | "name_ar">,
  right: Pick<PricingArea, "governorate" | "name_en" | "name_ar">,
) {
  return (
    normalizeGovernorateName(left.governorate) === normalizeGovernorateName(right.governorate) &&
    normalizeEn(left.name_en) === normalizeEn(right.name_en) &&
    normalizeArabic(left.name_ar) === normalizeArabic(right.name_ar)
  );
}

function rowHasPricingAreaCandidate(
  row: Record<string, unknown>,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  return ["governorate", "name_en", "name_ar", ...pricingColumnKeys].some((field) => {
    const value = resolveSheetFieldValue(row, field as PricingAreaFieldKey, headerMap);
    return !isSheetCellEmpty(value);
  });
}

async function repairInvalidPricingSheetIds(params: {
  session: Awaited<ReturnType<typeof fetchPricingGoogleSheetTable>>;
  headerMap: Partial<Record<PricingAreaFieldKey, string>>;
}) {
  const idHeaderName = resolveSheetHeaderNameFromHeaders(params.session.table.headers, "id", params.headerMap);
  if (!idHeaderName) {
    throw new Error("Google Sheet column not found for id.");
  }

  const idColumnIndex = params.session.table.headers.indexOf(idHeaderName);
  if (idColumnIndex < 0) {
    throw new Error(`Google Sheet column index not found for ${idHeaderName}.`);
  }

  const usedIds = new Set<number>();
  for (const item of params.session.table.rows) {
    const parsedId = parseSheetAreaId(resolveSheetFieldValue(item.record, "id", params.headerMap));
    if (parsedId !== null) {
      usedIds.add(parsedId);
    }
  }

  let nextId = usedIds.size ? Math.max(...Array.from(usedIds)) + 1 : 1;
  const repairs: Array<{
    row_number: number;
    previous_value: unknown;
    assigned_id: number;
    cell_range: string;
    update_result: {
      updatedRange?: string;
      updatedRows?: number;
      updatedColumns?: number;
      updatedCells?: number;
    };
  }> = [];

  for (const item of params.session.table.rows) {
    const currentValue = resolveSheetFieldValue(item.record, "id", params.headerMap);
    const parsedId = parseSheetAreaId(currentValue);
    if (parsedId !== null || !rowHasPricingAreaCandidate(item.record, params.headerMap)) {
      continue;
    }

    while (usedIds.has(nextId)) {
      nextId += 1;
    }

    const cellRange = `${formatGoogleSheetA1SheetName(params.session.sheetConfig.sheetName)}!${sheetColumnNumberToLetters(idColumnIndex + 1)}${item.row_number}`;
    const updateResult = await updateGoogleSheetValue({
      spreadsheetId: params.session.sheetConfig.spreadsheetId,
      range: cellRange,
      accessToken: params.session.accessToken,
      value: nextId,
    });

    repairs.push({
      row_number: item.row_number,
      previous_value: currentValue ?? null,
      assigned_id: nextId,
      cell_range: cellRange,
      update_result: updateResult,
    });
    usedIds.add(nextId);
    nextId += 1;
  }

  return repairs;
}

function buildPricingAreaCandidateFromSheetRow(
  row: Record<string, unknown>,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
): Record<PricingAreaFieldKey, unknown> {
  const candidate = {} as Record<PricingAreaFieldKey, unknown>;
  for (const field of pricingAreaFieldKeys) {
    candidate[field] = resolveSheetFieldValue(row, field, headerMap);
  }
  return candidate;
}

function isMatchingMalformedPricingSheetRow(
  row: Record<string, unknown>,
  area: Pick<PricingArea, "governorate" | "name_en" | "name_ar">,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const candidate = buildPricingAreaCandidateFromSheetRow(row, headerMap);
  if (!isSkippableMalformedPricingSheetRow(candidate)) {
    return false;
  }

  const malformedCell =
    typeof candidate.id === "string"
      ? candidate.id.trim()
      : candidate.id === null || candidate.id === undefined
        ? ""
        : String(candidate.id).trim();
  if (!malformedCell) {
    return false;
  }

  const normalizedTextEn = normalizeEn(malformedCell);
  const normalizedTextAr = normalizeArabic(malformedCell);
  return (
    normalizedTextEn.includes(normalizeGovernorateName(area.governorate)) &&
    normalizedTextEn.includes(normalizeEn(area.name_en)) &&
    normalizedTextAr.includes(normalizeArabic(area.name_ar))
  );
}

async function clearMatchingMalformedPricingSheetRows(params: {
  session: Awaited<ReturnType<typeof fetchPricingGoogleSheetTable>>;
  area: Pick<PricingArea, "governorate" | "name_en" | "name_ar">;
  headerMap: Partial<Record<PricingAreaFieldKey, string>>;
}) {
  const lastColumnLetter = sheetColumnNumberToLetters(Math.max(1, params.session.table.headers.length));
  const clears: Array<{
    row_number: number;
    cell_range: string;
    previous_value: unknown;
    clear_result: {
      clearedRange?: string;
    };
  }> = [];

  for (const item of params.session.table.rows) {
    if (!isMatchingMalformedPricingSheetRow(item.record, params.area, params.headerMap)) {
      continue;
    }

    const cellRange = `${formatGoogleSheetA1SheetName(params.session.sheetConfig.sheetName)}!A${item.row_number}:${lastColumnLetter}${item.row_number}`;
    const clearResult = await clearGoogleSheetRange({
      spreadsheetId: params.session.sheetConfig.spreadsheetId,
      range: cellRange,
      accessToken: params.session.accessToken,
    });

    clears.push({
      row_number: item.row_number,
      cell_range: cellRange,
      previous_value: resolveSheetFieldValue(item.record, "id", params.headerMap) ?? null,
      clear_result: clearResult,
    });
  }

  return clears;
}

async function ensurePricingSheetIdsValidForPublish(params: {
  profileId?: string | null;
  headerMap: Partial<Record<PricingAreaFieldKey, string>>;
}) {
  const initialSession = await fetchPricingGoogleSheetTable(params.profileId);
  const repairs = await repairInvalidPricingSheetIds({
    session: initialSession,
    headerMap: params.headerMap,
  });

  return {
    session: repairs.length ? await fetchPricingGoogleSheetTable(params.profileId) : initialSession,
    repairs,
  };
}

function resolveGoogleSheetRowForArea(
  area: PricingArea,
  table: ReturnType<typeof buildGoogleSheetValueTable>,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const matchedRow = findGoogleSheetRowForArea(area, table, headerMap);
  if (matchedRow) {
    return matchedRow;
  }

  throw new Error(`The configured Google Sheet row could not be found for ${area.name_en}.`);
}

function findGoogleSheetRowForArea(
  area: PricingArea,
  table: ReturnType<typeof buildGoogleSheetValueTable>,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const byId = table.rows.find((item) => parseSheetAreaId(resolveSheetFieldValue(item.record, "id", headerMap)) === area.id);
  if (byId) {
    return byId;
  }

  const targetGov = normalizeGovernorateName(area.governorate);
  const targetNameEn = normalizeEn(area.name_en);
  const targetNameAr = normalizeArabic(area.name_ar);
  const byName = table.rows.find((item) => {
    const rowGovRaw = resolveSheetFieldValue(item.record, "governorate", headerMap);
    const rowNameEnRaw = resolveSheetFieldValue(item.record, "name_en", headerMap);
    const rowNameArRaw = resolveSheetFieldValue(item.record, "name_ar", headerMap);
    const rowGov = typeof rowGovRaw === "string" ? normalizeGovernorateName(rowGovRaw) : "";
    const rowNameEn = typeof rowNameEnRaw === "string" ? normalizeEn(rowNameEnRaw) : "";
    const rowNameAr = typeof rowNameArRaw === "string" ? normalizeArabic(rowNameArRaw) : "";
    const sameGovernorate = !targetGov || !rowGov || rowGov === targetGov || rowGov.includes(targetGov) || targetGov.includes(rowGov);
    return sameGovernorate && (rowNameEn === targetNameEn || rowNameAr === targetNameAr);
  });
  if (byName) {
    return byName;
  }

  return null;
}

async function updatePricingAreaGoogleSheetValue(params: {
  area: PricingArea;
  deliveryType: QuoteableDeliveryType;
  price: number | null;
  profileId?: string | null;
  headerMap: Partial<Record<PricingAreaFieldKey, string>>;
}) {
  const session = await fetchPricingGoogleSheetTable(params.profileId);
  const matchedRow = resolveGoogleSheetRowForArea(params.area, session.table, params.headerMap);
  const headerName = resolveSheetHeaderNameFromHeaders(
    session.table.headers,
    params.deliveryType,
    params.headerMap,
  );
  if (!headerName) {
    throw new Error(`Google Sheet column not found for ${params.deliveryType}.`);
  }

  const columnIndex = session.table.headers.indexOf(headerName);
  if (columnIndex < 0) {
    throw new Error(`Google Sheet column index not found for ${headerName}.`);
  }

  const cellRange = `${formatGoogleSheetA1SheetName(session.sheetConfig.sheetName)}!${sheetColumnNumberToLetters(columnIndex + 1)}${matchedRow.row_number}`;
  const previousValue = resolveSheetFieldValue(matchedRow.record, params.deliveryType, params.headerMap);
  const updateResult = await updateGoogleSheetValue({
    spreadsheetId: session.sheetConfig.spreadsheetId,
    range: cellRange,
    accessToken: session.accessToken,
    value: params.price,
  });

  return {
    spreadsheet_id: session.sheetConfig.spreadsheetId,
    sheet_name: session.sheetConfig.sheetName,
    profile_id: session.profile_id,
    profile_email: session.profile_email,
    row_number: matchedRow.row_number,
    column_header: headerName,
    cell_range: cellRange,
    previous_value: previousValue ?? null,
    update_result: updateResult,
  };
}

async function executeAdminGoogleSheetPriceUpdate(
  ctx: any,
  params: {
    area_id?: number | null;
    area_name?: string | null;
    governorate?: string | null;
    delivery_type: QuoteableDeliveryType;
    price: number | null;
    profile_id?: string | null;
    header_map?: Record<string, string> | null;
    header_map_json?: string | null;
  },
) {
  let googleSheetUpdate:
    | {
        spreadsheet_id: string;
        sheet_name: string;
        profile_id: string;
        profile_email: string | null;
        row_number: number;
        column_header: string;
        cell_range: string;
        previous_value: unknown;
        update_result: {
          updatedRange?: string;
          updatedRows?: number;
          updatedColumns?: number;
          updatedCells?: number;
        };
      }
    | null = null;
  let repairedInvalidIds: Array<{
    row_number: number;
    previous_value: unknown;
    assigned_id: number;
    cell_range: string;
    update_result: {
      updatedRange?: string;
      updatedRows?: number;
      updatedColumns?: number;
      updatedCells?: number;
    };
  }> = [];

  try {
    assertPricingAdminAuthorized(ctx);
    const currentData = await loadPricing({ skipAutoSync: true });
    const rawFallback = await loadPricingFallbackData();
    const area = resolveAdminPricingArea(params, currentData.areas);
    const nextPrice = params.price === null ? null : normalizePricingNumber(params.price);
    const headerMap = resolveSheetHeaderMapInput(params);

    const sheetPreparation = await ensurePricingSheetIdsValidForPublish({
      profileId: params.profile_id,
      headerMap,
    });
    repairedInvalidIds = sheetPreparation.repairs;

    googleSheetUpdate = await updatePricingAreaGoogleSheetValue({
      area,
      deliveryType: params.delivery_type,
      price: nextPrice,
      profileId: params.profile_id,
      headerMap,
    });

    const rawRows = await fetchPricingRowsFromGoogleSheet(params.profile_id);
    const normalizedRows = normalizeSheetRowsToPublishedAreas(rawRows, headerMap);
    const nextData = buildPublishedPricingData(
      {
        areas: normalizedRows.areas,
      },
      rawFallback,
    );
    await writePublishedPricing(nextData);

    const liveArea = resolveAdminPricingArea({ area_id: area.id }, nextData.areas);
    const status = await getPricingSourceStatus();
    return createTextResult(
      {
        status: "ok",
        message: "Google Sheet price updated and published successfully.",
        updated_by_sender: normalizeAdminSenderId(ctx.requesterSenderId) || null,
        area_id: liveArea.id,
        area_name_en: liveArea.name_en,
        area_name_ar: liveArea.name_ar,
        governorate: liveArea.governorate,
        delivery_type: params.delivery_type,
        previous_price: area[params.delivery_type],
        requested_price: nextPrice,
        live_price: liveArea[params.delivery_type],
        sheet_cell: googleSheetUpdate.cell_range,
        repaired_invalid_id_count: repairedInvalidIds.length,
        spreadsheet_id: googleSheetUpdate.spreadsheet_id,
        profile_id: googleSheetUpdate.profile_id,
        profile_email: googleSheetUpdate.profile_email,
        active_source: status.active_source,
        published_path: status.published_path,
        last_updated: nextData.last_updated,
      },
      {
        google_sheet_update: googleSheetUpdate,
        google_sheet_id_repairs: repairedInvalidIds,
        pricing_source: status,
        pricing_data: nextData,
        updated_area: liveArea,
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const needsReauth = /insufficient authentication scopes|insufficient permissions|permission denied/i.test(
      message,
    );
    return createTextResult(
      errorPayload(
        needsReauth
          ? new Error(
              `${message} Re-run Google Sheets OAuth login for this agent so the credential includes write access, then retry the admin update.`,
            )
          : googleSheetUpdate
            ? new Error(`${message} The Google Sheet cell was already updated, but live pricing publish did not complete.`)
            : err,
      ),
      googleSheetUpdate || repairedInvalidIds.length
        ? {
            ...(googleSheetUpdate ? { google_sheet_update: googleSheetUpdate } : {}),
            ...(repairedInvalidIds.length ? { google_sheet_id_repairs: repairedInvalidIds } : {}),
          }
        : undefined,
    );
  }
}

async function executeAdminAddPricingAreaToGoogleSheet(
  ctx: any,
  params: {
    area_id?: number | null;
    governorate: string;
    name_en: string;
    name_ar: string;
    sedan_normal?: number | null;
    sedan_fast?: number | null;
    cooled_van_normal?: number | null;
    cooled_van_fast?: number | null;
    van_normal?: number | null;
    van_fast?: number | null;
    helper_standard?: number | null;
    profile_id?: string | null;
    header_map?: Record<string, string> | null;
    header_map_json?: string | null;
  },
) {
  let googleSheetAppend:
    | {
        spreadsheet_id: string;
        sheet_name: string;
        profile_id: string;
        profile_email: string | null;
        assigned_area_id: number;
        row_number: number;
        appended_values: Array<string | number>;
        append_result: {
          tableRange?: string;
          updatedRange?: string;
          updatedRows?: number;
          updatedColumns?: number;
          updatedCells?: number;
        };
      }
    | null = null;
  let repairedInvalidIds: Array<{
    row_number: number;
    previous_value: unknown;
    assigned_id: number;
    cell_range: string;
    update_result: {
      updatedRange?: string;
      updatedRows?: number;
      updatedColumns?: number;
      updatedCells?: number;
    };
  }> = [];
  let clearedMalformedRows: Array<{
    row_number: number;
    cell_range: string;
    previous_value: unknown;
    clear_result: {
      clearedRange?: string;
    };
  }> = [];

  try {
    assertPricingAdminAuthorized(ctx);
    const rawFallback = await loadPricingFallbackData();
    const headerMap = resolveSheetHeaderMapInput(params);
    const sheetPreparation = await ensurePricingSheetIdsValidForPublish({
      profileId: params.profile_id,
      headerMap,
    });
    repairedInvalidIds = sheetPreparation.repairs;
    let session = sheetPreparation.session;
    clearedMalformedRows = await clearMatchingMalformedPricingSheetRows({
      session,
      area: {
        governorate: params.governorate,
        name_en: params.name_en,
        name_ar: params.name_ar,
      },
      headerMap,
    });
    if (clearedMalformedRows.length) {
      session = await fetchPricingGoogleSheetTable(params.profile_id);
    }
    const assignedAreaId =
      params.area_id === null || params.area_id === undefined
        ? resolveNextPricingAreaIdFromSheetRows(session.table.rows, headerMap)
        : Math.trunc(params.area_id);

    if (!Number.isInteger(assignedAreaId) || assignedAreaId <= 0) {
      throw new Error("area_id must be a positive integer when provided.");
    }

    const draftArea = normalizePublishedPricingArea(
      {
        id: assignedAreaId,
        governorate: params.governorate,
        name_en: params.name_en,
        name_ar: params.name_ar,
        sedan_normal: params.sedan_normal ?? null,
        sedan_fast: params.sedan_fast ?? null,
        cooled_van_normal: params.cooled_van_normal ?? null,
        cooled_van_fast: params.cooled_van_fast ?? null,
        van_normal: params.van_normal ?? null,
        van_fast: params.van_fast ?? null,
        helper_standard: params.helper_standard ?? null,
      },
      0,
    );

    const existingRow = findGoogleSheetRowForArea(draftArea, session.table, headerMap);
    if (existingRow) {
      const existingArea = normalizePublishedPricingArea(
        buildPricingAreaCandidateFromSheetRow(existingRow.record, headerMap),
        Math.max(0, existingRow.row_number - session.sheetConfig.headerRow - 1),
      );
      if (!isSamePricingAreaIdentity(existingArea, draftArea)) {
        if (existingArea.id === assignedAreaId) {
          throw new Error(`Area id ${assignedAreaId} already exists in the Google Sheet.`);
        }
        throw new Error(
          `A Google Sheet row already exists for ${existingArea.name_en} in ${existingArea.governorate} on row ${existingRow.row_number}.`,
        );
      }

      const normalizedRows = normalizeSheetRowsToPublishedAreas(
        session.table.rows.map((item) => item.record),
        headerMap,
      );
      const nextData = buildPublishedPricingData(
        {
          areas: normalizedRows.areas,
        },
        rawFallback,
      );
      await writePublishedPricing(nextData);

      const liveArea = resolveAdminPricingArea({ area_id: existingArea.id }, nextData.areas);
      const status = await getPricingSourceStatus();
      return createTextResult(
        {
          status: "ok",
          message: "Google Sheet pricing area already existed and was published successfully.",
          updated_by_sender: normalizeAdminSenderId(ctx.requesterSenderId) || null,
          area_id: liveArea.id,
          area_name_en: liveArea.name_en,
          area_name_ar: liveArea.name_ar,
          governorate: liveArea.governorate,
          repaired_invalid_id_count: repairedInvalidIds.length,
          cleared_malformed_row_count: clearedMalformedRows.length,
          spreadsheet_id: session.sheetConfig.spreadsheetId,
          profile_id: session.profile_id,
          profile_email: session.profile_email,
          active_source: status.active_source,
          published_path: status.published_path,
          last_updated: nextData.last_updated,
        },
        {
          google_sheet_existing_row: {
            row_number: existingRow.row_number,
            area: existingArea,
          },
          google_sheet_id_repairs: repairedInvalidIds,
          cleared_malformed_rows: clearedMalformedRows,
          pricing_source: status,
          pricing_data: nextData,
          updated_area: liveArea,
        },
      );
    }

    const previewRows = [...session.table.rows.map((item) => item.record), buildPricingAreaSheetAppendRecord(draftArea)];
    const normalizedRows = normalizeSheetRowsToPublishedAreas(previewRows, headerMap);
    const nextData = buildPublishedPricingData(
      {
        areas: normalizedRows.areas,
      },
      rawFallback,
    );

    const appendValues = buildPricingAreaSheetAppendValues({
      headers: session.table.headers,
      area: draftArea,
      headerMap,
    });
    const appendResult = await appendGoogleSheetValues({
      spreadsheetId: session.sheetConfig.spreadsheetId,
      range: session.sheetConfig.range,
      accessToken: session.accessToken,
      values: [appendValues],
    });

    googleSheetAppend = {
      spreadsheet_id: session.sheetConfig.spreadsheetId,
      sheet_name: session.sheetConfig.sheetName,
      profile_id: session.profile_id,
      profile_email: session.profile_email,
      assigned_area_id: draftArea.id,
      row_number: session.table.input_row_count + 1,
      appended_values: appendValues,
      append_result: appendResult,
    };

    await writePublishedPricing(nextData);

    const liveArea = resolveAdminPricingArea({ area_id: draftArea.id }, nextData.areas);
    const status = await getPricingSourceStatus();
    return createTextResult(
      {
        status: "ok",
        message: "Google Sheet pricing area added and published successfully.",
        updated_by_sender: normalizeAdminSenderId(ctx.requesterSenderId) || null,
        area_id: liveArea.id,
        area_name_en: liveArea.name_en,
        area_name_ar: liveArea.name_ar,
        governorate: liveArea.governorate,
        repaired_invalid_id_count: repairedInvalidIds.length,
        cleared_malformed_row_count: clearedMalformedRows.length,
        spreadsheet_id: googleSheetAppend.spreadsheet_id,
        profile_id: googleSheetAppend.profile_id,
        profile_email: googleSheetAppend.profile_email,
        active_source: status.active_source,
        published_path: status.published_path,
        last_updated: nextData.last_updated,
      },
      {
        google_sheet_append: googleSheetAppend,
        google_sheet_id_repairs: repairedInvalidIds,
        cleared_malformed_rows: clearedMalformedRows,
        pricing_source: status,
        pricing_data: nextData,
        added_area: liveArea,
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return createTextResult(
      errorPayload(
        googleSheetAppend
          ? new Error(`${message} The Google Sheet row was already appended, but live pricing publish did not complete.`)
          : err,
      ),
      googleSheetAppend || repairedInvalidIds.length || clearedMalformedRows.length
        ? {
            ...(googleSheetAppend ? { google_sheet_append: googleSheetAppend } : {}),
            ...(repairedInvalidIds.length ? { google_sheet_id_repairs: repairedInvalidIds } : {}),
            ...(clearedMalformedRows.length ? { cleared_malformed_rows: clearedMalformedRows } : {}),
          }
        : undefined,
    );
  }
}

// hashPricingData moved to ./lib/config.ts (wave 1b).

async function maybeAutoSyncPricingFromGoogleSheet(options?: { force?: boolean }) {
  if (pricingSourceMode === "static_only" || pricingSourceMode === "google_sheet_live") {
    return;
  }

  if (!pricingGoogleAutoSyncEnabled) {
    return;
  }

  if (!pricingGoogleSheetSpreadsheetId || !pricingGoogleSheetName) {
    return;
  }

  const now = Date.now();
  if (
    !options?.force &&
    pricingGoogleLastSyncAttemptAt !== null &&
    now - pricingGoogleLastSyncAttemptAt < pricingGoogleAutoSyncMinIntervalMs
  ) {
    return;
  }

  if (pricingGoogleSyncInFlight) {
    await pricingGoogleSyncInFlight;
    return;
  }

  pricingGoogleLastSyncAttemptAt = now;
  pricingGoogleSyncInFlight = (async () => {
    try {
      const currentData = await loadPricing({ skipAutoSync: true });
      const rawRows = await fetchPricingRowsFromGoogleSheet();
      const normalizedRows = normalizeSheetRowsToPublishedAreas(rawRows, {});
      const rawFallback = await loadPricingFallbackData();
      const nextData = buildPublishedPricingData(
        {
          areas: normalizedRows.areas,
        },
        rawFallback,
      );
      const nextServed = await applyPricingResolverOverlayIfConfigured(nextData);

      const publishedPath = resolvePublishedPricingPath();
      const publishedExists = await pathExists(publishedPath);
      const nextFingerprint = hashPricingData(nextServed);
      const currentFingerprint = hashPricingData(currentData);

      if (!publishedExists || currentFingerprint !== nextFingerprint) {
        await writePublishedPricing(nextData);
      }

      pricingGoogleLastFingerprint = nextFingerprint;
      pricingGoogleLastSyncAt = Date.now();
      pricingGoogleLastSyncError = null;
    } catch (error) {
      pricingGoogleLastSyncError = error instanceof Error ? error.message : String(error);
      const publishedExists = await pathExists(resolvePublishedPricingPath());
      const staticExists = await pathExists(defaultPricingPath);
      if (!publishedExists && !staticExists) {
        throw error;
      }
    } finally {
      pricingGoogleSyncInFlight = null;
    }
  })();

  await pricingGoogleSyncInFlight;
}

// describePath and pathExists moved to ./lib/config.ts (wave 1b).

function resolvePublishedPricingPath(): string | URL {
  return pricingPublishedPathOverride || defaultPublishedPricingPath;
}

async function resolvePricingLoadTarget(): Promise<{
  path: string | URL;
  source: "google_sheet_live" | "static_json" | "published_snapshot";
}> {
  if (pricingSourceMode === "google_sheet_live") {
    const sheetConfig = resolvePricingGoogleSheetReadConfig();
    return {
      path: `google_sheet:${sheetConfig.spreadsheetId}/${sheetConfig.sheetName}`,
      source: "google_sheet_live",
    };
  }

  const publishedPath = resolvePublishedPricingPath();
  if (pricingSourceMode !== "static_only" && (await pathExists(publishedPath))) {
    return {
      path: publishedPath,
      source: "published_snapshot",
    };
  }
  return {
    path: defaultPricingPath,
    source: "static_json",
  };
}

async function writePublishedPricing(data: PricingData) {
  await fs.writeFile(resolvePublishedPricingPath(), `${JSON.stringify(data, null, 2)}\n`, "utf-8");
  clearPricingCache();
}

async function loadPricingBaseDataForStatus(): Promise<PricingData> {
  if (pricingSourceMode === "google_sheet_live") {
    const fallback = await loadPricingFallbackData();
    const rawRows = await fetchPricingRowsFromGoogleSheet();
    const normalizedRows = normalizeSheetRowsToPublishedAreas(rawRows, {});
    return buildPublishedPricingData(
      {
        areas: normalizedRows.areas,
      },
      fallback,
    );
  }

  const target = await resolvePricingLoadTarget();
  const raw = await fs.readFile(target.path, "utf-8");
  return JSON.parse(raw) as PricingData;
}

// summarizePricingResolver + resolvePricingResolverOverlayInput moved to ./lib/pricing-resolver.ts (wave 1b).

async function inspectPricingResolverOverlay(baseData: PricingData): Promise<{
  status: PricingResolverOverlayStatus;
  mergedResolver?: PricingResolverConfig;
}> {
  if (!pricingResolverOverlayPathOverride) {
    return {
      status: {
        configured: false,
        path: null,
        exists: false,
        state: "disabled",
        source_shape: null,
        error: null,
        aliases_count: 0,
        pricing_group_count: 0,
        ambiguity_group_count: 0,
        merged_aliases_count: null,
        merged_pricing_group_count: null,
        merged_ambiguity_group_count: null,
        alias_preview: [],
        pricing_group_ids: [],
        ambiguity_group_ids: [],
      },
    };
  }

  const overlayPath = pricingResolverOverlayPathOverride;
  if (!(await pathExists(overlayPath))) {
    return {
      status: {
        configured: true,
        path: describePath(overlayPath),
        exists: false,
        state: "missing",
        source_shape: null,
        error: `Resolver overlay file not found: ${describePath(overlayPath)}`,
        aliases_count: 0,
        pricing_group_count: 0,
        ambiguity_group_count: 0,
        merged_aliases_count: null,
        merged_pricing_group_count: null,
        merged_ambiguity_group_count: null,
        alias_preview: [],
        pricing_group_ids: [],
        ambiguity_group_ids: [],
      },
    };
  }

  try {
    const raw = await fs.readFile(overlayPath, "utf-8");
    const parsed = JSON.parse(raw) as unknown;
    const { resolverInput, sourceShape } = resolvePricingResolverOverlayInput(parsed, describePath(overlayPath));
    const overlayResolver = normalizePricingResolverConfig(resolverInput);
    if (!overlayResolver) {
      throw new Error(`Resolver overlay is empty: ${describePath(overlayPath)}`);
    }

    const mergedResolver = mergePricingResolverConfigs(baseData.resolver, overlayResolver);
    validatePricingResolverConfig(mergedResolver, baseData.areas);

    const overlaySummary = summarizePricingResolver(overlayResolver);
    const mergedSummary = summarizePricingResolver(mergedResolver);
    return {
      status: {
        configured: true,
        path: describePath(overlayPath),
        exists: true,
        state: "active",
        source_shape: sourceShape,
        error: null,
        aliases_count: overlaySummary.aliases_count,
        pricing_group_count: overlaySummary.pricing_group_count,
        ambiguity_group_count: overlaySummary.ambiguity_group_count,
        merged_aliases_count: mergedSummary.aliases_count,
        merged_pricing_group_count: mergedSummary.pricing_group_count,
        merged_ambiguity_group_count: mergedSummary.ambiguity_group_count,
        alias_preview: overlaySummary.alias_preview,
        pricing_group_ids: overlaySummary.pricing_group_ids,
        ambiguity_group_ids: overlaySummary.ambiguity_group_ids,
      },
      mergedResolver: mergedResolver || undefined,
    };
  } catch (error) {
    return {
      status: {
        configured: true,
        path: describePath(overlayPath),
        exists: true,
        state: "invalid",
        source_shape: null,
        error: error instanceof Error ? error.message : String(error),
        aliases_count: 0,
        pricing_group_count: 0,
        ambiguity_group_count: 0,
        merged_aliases_count: null,
        merged_pricing_group_count: null,
        merged_ambiguity_group_count: null,
        alias_preview: [],
        pricing_group_ids: [],
        ambiguity_group_ids: [],
      },
    };
  }
}

async function getPricingSourceStatus() {
  const publishedPath = resolvePublishedPricingPath();
  const target = await resolvePricingLoadTarget();
  const baseData = await loadPricingBaseDataForStatus();
  const overlay = await inspectPricingResolverOverlay(baseData);
  const activeResolver = overlay.mergedResolver ?? baseData.resolver;
  return {
    source_mode: pricingSourceMode,
    active_source: target.source,
    active_path: describePath(target.path),
    static_path: describePath(defaultPricingPath),
    published_path: describePath(publishedPath),
    published_exists: await pathExists(publishedPath),
    admin_allowlist_count: pricingAdminAllowlist.length,
    google_sheet: {
      configured: Boolean(pricingGoogleSheetSpreadsheetId && pricingGoogleSheetName),
      spreadsheet_id: pricingGoogleSheetSpreadsheetId || null,
      sheet_name: pricingGoogleSheetName || null,
      header_row: pricingGoogleSheetHeaderRow,
      auto_sync_enabled: pricingGoogleAutoSyncEnabled,
      auto_sync_min_interval_ms: pricingGoogleAutoSyncMinIntervalMs,
      gog_account: env.GOG_ACCOUNT?.trim() || null,
      gog_binary: resolveGogBinary(),
      last_sync_at:
        pricingGoogleLastSyncAt === null ? null : new Date(pricingGoogleLastSyncAt).toISOString(),
      last_sync_attempt_at:
        pricingGoogleLastSyncAttemptAt === null
          ? null
          : new Date(pricingGoogleLastSyncAttemptAt).toISOString(),
      last_sync_error: pricingGoogleLastSyncError,
      last_sync_fingerprint: pricingGoogleLastFingerprint || null,
    },
    pricing_resolver_overlay: overlay.status,
    resolver_source: overlay.status.state === "active" ? "base_plus_overlay" : "base",
    resolver: summarizePricingResolver(activeResolver),
    last_updated: baseData.last_updated,
    area_count: baseData.areas.length,
    currency: baseData.currency,
  };
}

// createEmptyBehaviorPolicy moved to ./lib/behavior-policy.ts (wave 1b).

function resolvePublishedBehaviorPolicyPath(): string | URL {
  return behaviorPublishedPathOverride || defaultBehaviorPolicyPath;
}

async function loadBehaviorPolicy(): Promise<BehaviorPolicy> {
  const publishedPath = resolvePublishedBehaviorPolicyPath();
  const targetKey = describePath(publishedPath);
  if (behaviorPolicyCache && behaviorPolicyCachePath === targetKey) {
    return behaviorPolicyCache;
  }
  if (!(await pathExists(publishedPath))) {
    const emptyPolicy = createEmptyBehaviorPolicy();
    behaviorPolicyCache = emptyPolicy;
    behaviorPolicyCachePath = targetKey;
    return emptyPolicy;
  }
  const raw = await fs.readFile(publishedPath, "utf-8");
  behaviorPolicyCache = normalizeBehaviorPolicyDocument(JSON.parse(raw) as unknown, createEmptyBehaviorPolicy());
  behaviorPolicyCachePath = targetKey;
  return behaviorPolicyCache;
}

async function writePublishedBehaviorPolicy(data: BehaviorPolicy) {
  await fs.writeFile(
    resolvePublishedBehaviorPolicyPath(),
    `${JSON.stringify(data, null, 2)}\n`,
    "utf-8",
  );
  clearBehaviorPolicyCache();
}

async function getBehaviorPolicyStatus() {
  const publishedPath = resolvePublishedBehaviorPolicyPath();
  const policy = await loadBehaviorPolicy();
  return {
    published_path: describePath(publishedPath),
    published_exists: await pathExists(publishedPath),
    admin_allowlist_count: Array.from(
      new Set([...pricingAdminAllowlist, ...behaviorAdminAllowlist]),
    ).length,
    version: policy.version,
    last_updated: policy.last_updated || null,
    updated_by: policy.updated_by,
    summary: policy.summary || null,
    live_instruction_count: policy.live_instructions.length,
    reply_correction_count: policy.reply_corrections.filter((rule) => rule.enabled).length,
    flow_rule_count: policy.flow_rules.filter((rule) => rule.enabled).length,
    phrase_guard_count: policy.phrase_guards.filter((rule) => rule.enabled).length,
  };
}

async function loadGovernorates(): Promise<GeoGovernorate[]> {
  if (governoratesCache) return governoratesCache;
  const payload = await ridersGridRequest("GET", "/geo/govs");
  governoratesCache = Array.isArray(payload.data)
    ? payload.data.map((item: any) => ({
        id: Number(item.id),
        name: String(item.name || ""),
        lat: typeof item.lat === "string" ? item.lat : null,
        lng: typeof item.lng === "string" ? item.lng : null,
      }))
    : [];
  return governoratesCache;
}

async function loadGeoAreas(governorateId: number): Promise<GeoArea[]> {
  const cached = geoAreasCache.get(governorateId);
  if (cached) return cached;

  const payload = await ridersGridRequest(
    "GET",
    `/geo/areas?governorate_id=${encodeURIComponent(String(governorateId))}`,
  );

  const areas = Array.isArray(payload.data)
    ? payload.data.map((item: any) => ({
        id: Number(item.id),
        objectid: typeof item.objectid === "string" ? item.objectid : null,
        name: String(item.name || ""),
        lat: typeof item.lat === "string" ? item.lat : null,
        lng: typeof item.lng === "string" ? item.lng : null,
        governorate_id: governorateId,
        governorate_name: "",
        shipping_methods: Array.isArray(item.shipping_methods)
          ? item.shipping_methods.map((method: any) => ({
              id: Number(method.id),
              name: String(method.name || ""),
              type: typeof method.type === "string" ? method.type : null,
              default_price:
                typeof method.default_price === "string" || typeof method.default_price === "number"
                  ? method.default_price
                  : null,
              price: typeof method.price === "number" ? method.price : null,
            }))
          : [],
      }))
    : [];

  geoAreasCache.set(governorateId, areas);
  return areas;
}

function stripHtmlToPlainText(value: string | null | undefined): string | null {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }

  const text = value
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim();
  return text || null;
}

async function loadRidersGridLiveSettingsSummary(): Promise<RidersGridLiveSettingsSummary> {
  if (
    ridersGridLiveSettingsCache &&
    Date.now() - ridersGridLiveSettingsCache.loadedAtMs < RIDERS_GRID_SETTINGS_CACHE_TTL_MS
  ) {
    return ridersGridLiveSettingsCache.value;
  }

  const payload = await ridersGridRequest("GET", "/settings");
  const data = isRecord(payload.data) ? payload.data : {};
  const siteOptions = isRecord(data.site_options) ? data.site_options : {};
  const maintenance = isRecord(data.maintenance) ? data.maintenance : {};
  const orderSettings = isRecord(data.order_settings) ? data.order_settings : {};
  const freezer = isRecord(orderSettings.freezer) ? orderSettings.freezer : {};
  const assistant = isRecord(orderSettings.assistant) ? orderSettings.assistant : {};

  const nextValue = {
    freezer_enabled: typeof freezer.enabled === "boolean" ? freezer.enabled : null,
    assistant_enabled: typeof assistant.enabled === "boolean" ? assistant.enabled : null,
    site_order_mode: typeof siteOptions.order_mode === "boolean" ? siteOptions.order_mode : null,
    site_maintenance_mode:
      typeof siteOptions.maintenance_mode === "boolean" ? siteOptions.maintenance_mode : null,
    maintenance_mode: typeof maintenance.mode === "boolean" ? maintenance.mode : null,
    maintenance_message: stripHtmlToPlainText(
      typeof maintenance.message === "string" ? maintenance.message : null,
    ),
  };
  ridersGridLiveSettingsCache = {
    value: nextValue,
    loadedAtMs: Date.now(),
  };
  return nextValue;
}

// ---------------------------------------------------------------------------
// Voyage 4 embedding engine
// ---------------------------------------------------------------------------

/** Cached embedding vector for an area (both Arabic and English names). */
interface AreaEmbeddingEntry {
  areaIndex: number;       // index into PricingArea[]
  label: string;           // the text that was embedded
  vector: number[];        // embedding vector
}

/** In-memory embedding cache keyed by a pricing-data fingerprint. */
let areaEmbeddingCache: {
  fingerprint: string;
  entries: AreaEmbeddingEntry[];
} | null = null;

/** Call Voyage embedding API. Returns array of float[] vectors. */
async function voyageEmbed(texts: string[], inputType: "document" | "query" | null, modelOverride?: string): Promise<number[][]> {
  if (!voyageApiKey) throw new Error("VOYAGE_API_KEY is not configured.");
  const payload: Record<string, unknown> = { input: texts, model: modelOverride || voyageModel };
  if (inputType) payload.input_type = inputType;
  const res = await fetch("https://api.voyageai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${voyageApiKey}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Voyage API ${res.status}: ${body.slice(0, 200)}`);
  }
  const json = (await res.json()) as {
    data: { embedding: number[]; index: number }[];
  };
  // Sort by index to maintain order
  return json.data.sort((a, b) => a.index - b.index).map((d) => d.embedding);
}

/** Cosine similarity between two vectors. */
function cosineSim(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

/**
 * Build or return the cached area embedding index.
 * Embeds every area's Arabic name + English name as separate entries.
 * Called lazily on first findArea miss, then cached until pricing changes.
 */
async function getAreaEmbeddings(areas: PricingArea[], fingerprint: string): Promise<AreaEmbeddingEntry[]> {
  if (areaEmbeddingCache?.fingerprint === fingerprint) {
    return areaEmbeddingCache.entries;
  }

  // Build text list: [area0_ar, area0_en, area1_ar, area1_en, ...]
  const texts: string[] = [];
  const meta: { areaIndex: number; label: string }[] = [];
  for (let i = 0; i < areas.length; i++) {
    const a = areas[i];
    if (a.name_ar) {
      texts.push(a.name_ar);
      meta.push({ areaIndex: i, label: a.name_ar });
    }
    if (a.name_en) {
      texts.push(a.name_en);
      meta.push({ areaIndex: i, label: a.name_en });
    }
  }

  // Use voyage-4-large for area labels (one-time cache, best quality)
  // Voyage 4 series share embedding space, so queries via voyage-4 are compatible
  const labelModel = voyageModelLarge;
  const allVectors: number[][] = [];
  const BATCH = 128;
  for (let start = 0; start < texts.length; start += BATCH) {
    const batch = texts.slice(start, start + BATCH);
    const vectors = await voyageEmbed(batch, "document", labelModel);
    allVectors.push(...vectors);
  }

  const entries: AreaEmbeddingEntry[] = meta.map((m, idx) => ({
    ...m,
    vector: allVectors[idx],
  }));

  areaEmbeddingCache = { fingerprint, entries };
  console.log(`[voyage] Embedded ${entries.length} area labels (${areas.length} areas) using ${labelModel}`);
  return entries;
}

/** Minimum reranker relevance score to accept a match. */
const RERANKER_RELEVANCE_THRESHOLD = 0.5;
const RERANKER_RELEVANCE_MARGIN = 0.05;
const MIN_EMBEDDING_SIMILARITY_FOR_RERANK = 0.6;
const RERANKER_MODEL = "rerank-2.5";

/** Call Voyage reranker API. Returns array of { index, relevance_score } sorted by score desc. */
async function voyageRerank(
  query: string,
  documents: string[],
  topK?: number,
): Promise<{ index: number; relevance_score: number }[]> {
  if (!voyageApiKey) throw new Error("VOYAGE_API_KEY is not configured.");
  const payload: Record<string, unknown> = {
    query,
    documents,
    model: RERANKER_MODEL,
    top_k: topK ?? documents.length,
  };
  const res = await fetch("https://api.voyageai.com/v1/rerank", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${voyageApiKey}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Voyage rerank API ${res.status}: ${body.slice(0, 200)}`);
  }
  const json = (await res.json()) as {
    data: { index: number; relevance_score: number }[];
  };
  return json.data.sort((a, b) => b.relevance_score - a.relevance_score);
}

/**
 * Layer 4+5: Embedding retrieval → Reranker verification.
 * Layer 4: Voyage embedding gets top-5 candidates (fast, cached).
 * Layer 5: Voyage rerank-2.5 re-scores the top-5 (accurate, cross-encoder).
 */
async function findAreaByEmbeddingWithGuards(
  query: string,
  areas: PricingArea[],
  fingerprint: string,
): Promise<{ area: PricingArea; prompt_ar: string; prompt_en: string } | null> {
  if (!voyageApiKey) return null;

  try {
    // ---- Layer 4: Embedding retrieval (top-5 candidates) ----
    const entries = await getAreaEmbeddings(areas, fingerprint);
    const [queryVec] = await voyageEmbed([query], "query");

    // Score all entries and pick top-5 unique areas
    const scored: { idx: number; sim: number }[] = [];
    for (let i = 0; i < entries.length; i++) {
      scored.push({ idx: i, sim: cosineSim(queryVec, entries[i].vector) });
    }
    scored.sort((a, b) => b.sim - a.sim);

    // Deduplicate by area index, keep best label per area
    const seenAreas = new Set<number>();
    const topCandidates: { entry: AreaEmbeddingEntry; sim: number; areaIndex: number }[] = [];
    for (const s of scored) {
      const entry = entries[s.idx];
      if (seenAreas.has(entry.areaIndex)) continue;
      seenAreas.add(entry.areaIndex);
      topCandidates.push({ entry, sim: s.sim, areaIndex: entry.areaIndex });
      if (topCandidates.length >= 5) break;
    }

    if (topCandidates.length === 0) {
      console.log(`[voyage] No embedding candidates available for "${query}"`);
      return null;
    }

    const rerankFloor = Math.max(
      MIN_EMBEDDING_SIMILARITY_FOR_RERANK,
      embeddingSimilarityThreshold - 0.15,
    );
    if (topCandidates[0].sim < rerankFloor) {
      const best = topCandidates[0];
      console.log(
        `[voyage] No embedding candidate for "${query}" above rerank floor ${rerankFloor.toFixed(2)}` +
        (best ? ` (best: "${best.entry.label}" sim=${best.sim.toFixed(4)})` : ""),
      );
      return null;
    }

    console.log(
      `[voyage] Embedding top-5 for "${query}": ${topCandidates.map((c) => `"${c.entry.label}" sim=${c.sim.toFixed(4)}`).join(", ")}`,
    );

    // ---- Layer 5: Reranker verification ----
    // Build document list: use Arabic name + English name for each candidate
    const rerankDocs = topCandidates.map((c) => {
      const area = areas[c.areaIndex];
      return `${area.name_ar} (${area.name_en})`;
    });

    const reranked = await voyageRerank(query, rerankDocs);

    if (reranked.length === 0) {
      console.log(`[voyage-rerank] No rerank results for "${query}"`);
      return null;
    }

    const best = reranked[0];
    const bestCandidate = topCandidates[best.index];
    const bestArea = areas[bestCandidate.areaIndex];

    // Check relevance threshold
    if (best.relevance_score < RERANKER_RELEVANCE_THRESHOLD) {
      console.log(
        `[voyage-rerank] REJECTED "${query}" — best rerank score ${best.relevance_score.toFixed(4)} < ${RERANKER_RELEVANCE_THRESHOLD} for "${bestArea.name_ar}" (${bestArea.name_en})`,
      );
      return null;
    }

    const runnerUp = reranked[1];
    if (
      runnerUp &&
      best.relevance_score - runnerUp.relevance_score < RERANKER_RELEVANCE_MARGIN
    ) {
      const runnerUpArea = areas[topCandidates[runnerUp.index].areaIndex];
      console.log(
        `[voyage-rerank] REJECTED "${query}" — best rerank margin ${(best.relevance_score - runnerUp.relevance_score).toFixed(4)} < ${RERANKER_RELEVANCE_MARGIN} between "${bestArea.name_ar}" and "${runnerUpArea.name_ar}"`,
      );
      return null;
    }

    // Log the full rerank result for debugging
    console.log(
      `[voyage-rerank] Verified "${query}" → "${bestArea.name_ar}" (${bestArea.name_en}) rerank_score=${best.relevance_score.toFixed(4)}` +
      (reranked.length > 1 ? ` runner_up="${areas[topCandidates[reranked[1].index].areaIndex].name_ar}" score=${reranked[1].relevance_score.toFixed(4)}` : ""),
    );

    const prompt_ar = `لم أتعرف على الاسم "${query}" بشكل مؤكد. هل تقصد "${bestArea.name_ar}"؟`;
    const prompt_en = `I couldn't confidently recognize "${query}". Did you mean "${bestArea.name_en}"?`;
    return {
      area: bestArea,
      prompt_ar,
      prompt_en,
    };
  } catch (err) {
    console.error(`[voyage] Embedding+rerank search failed: ${err instanceof Error ? err.message : err}`);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Area matching primitives moved to ./lib/area-matching.ts (wave 1b).
// ---------------------------------------------------------------------------

// PRICING_AREA_PRICE_KEYS moved to ./lib/pricing-resolver.ts (wave 1b).

// isNumericAreaSuffixToken, diffMeaningfulAreaTokens, diffMeaningfulEnTokens,
// stripTrailingNumericAreaSuffix, extractTrailingNumericAreaSuffix,
// stripFlexibleTrailingNumericAreaSuffix moved to ./lib/area-matching.ts (wave 1b).

function buildNumberedAreaAlias(query: string, areas: PricingArea[]): PricingArea | null {
  const q = query.trim();
  const qCanon = canonicalizeAreaName(q);
  if (!qCanon) return null;

  const grouped = areas.filter((area) => {
    const areaCanon = canonicalizeAreaName(area.name_ar);
    if (!areaCanon.startsWith(`${qCanon} `)) return false;
    const suffix = areaCanon.slice(qCanon.length).trim();
    return isNumericAreaSuffixToken(suffix);
  });
  if (grouped.length === 0) return null;

  const representative = grouped[0];
  const sameGovernorate = grouped.every(
    (area) =>
      normalizeForFuzzyMatch(area.governorate) === normalizeForFuzzyMatch(representative.governorate),
  );
  const samePricingProfile = grouped.every((area) =>
    PRICING_AREA_PRICE_KEYS.every((key) => area[key] === representative[key]),
  );
  if (!sameGovernorate || !samePricingProfile) {
    return null;
  }

  const alias: PricingArea = {
    ...representative,
    name_ar: q,
    name_en: stripTrailingNumericAreaSuffix(representative.name_en),
  };
  console.log(
    `[area-match] Numbered area alias match: "${query}" → "${alias.name_ar}" (${alias.name_en}) using ${grouped.length} numbered variants`,
  );
  return alias;
}

function buildNumberedFamilyAmbiguity(
  query: string,
  areas: PricingArea[],
): Extract<PricingAreaResolution, { status: "ambiguous" }> | null {
  const raw = query.trim();
  if (!raw) return null;

  const useArabic = containsArabicScript(raw);
  const normalizedQuery = useArabic
    ? stripFlexibleTrailingNumericAreaSuffix(canonicalizeAreaName(raw))
    : normalizeLatinAreaKey(stripFlexibleTrailingNumericAreaSuffix(raw));
  if (!normalizedQuery) return null;

  const queryTokens = (useArabic ? canonicalizeAreaName(raw) : normalizeEnSubstring(raw))
    .split(/\s+/)
    .filter(Boolean);
  if (queryTokens.length === 0 || isNumericAreaSuffixToken(queryTokens[queryTokens.length - 1] || "")) {
    return null;
  }

  const variants = areas
    .filter((area) => {
      const candidateLabel = useArabic ? area.name_ar : area.name_en;
      if (!candidateLabel) return false;

      const normalizedCandidate = useArabic
        ? stripFlexibleTrailingNumericAreaSuffix(canonicalizeAreaName(candidateLabel))
        : normalizeLatinAreaKey(stripFlexibleTrailingNumericAreaSuffix(candidateLabel));
      if (!normalizedCandidate) return false;

      const candidateTokens = (useArabic ? canonicalizeAreaName(candidateLabel) : normalizeEnSubstring(candidateLabel))
        .split(/\s+/)
        .filter(Boolean);
      if (candidateTokens.length <= queryTokens.length) return false;
      if (normalizedCandidate !== normalizedQuery) return false;

      const suffixTokens = candidateTokens.slice(queryTokens.length);
      return suffixTokens.length > 0 && suffixTokens.every(isNumericAreaSuffixToken);
    })
    .sort((left, right) => {
      const leftKey = useArabic ? canonicalizeAreaName(left.name_ar) : normalizeEnSubstring(left.name_en);
      const rightKey = useArabic ? canonicalizeAreaName(right.name_ar) : normalizeEnSubstring(right.name_en);
      const leftIndex = extractTrailingNumericAreaSuffix(leftKey) ?? Number.MAX_SAFE_INTEGER;
      const rightIndex = extractTrailingNumericAreaSuffix(rightKey) ?? Number.MAX_SAFE_INTEGER;
      return leftIndex - rightIndex || left.name_en.localeCompare(right.name_en);
    });

  if (variants.length < 2) return null;

  const namesAr = variants.map((area) => area.name_ar).join(" / ");
  const namesEn = variants.map((area) => area.name_en).join(" / ");
  console.log(`[area-match] Numbered family ambiguity: "${query}" → [${namesEn}]`);
  return {
    status: "ambiguous",
    ambiguity_group_id: `dynamic_numbered_family:${normalizedQuery}`,
    prompt_ar: `أقصد أي منطقة بالضبط؟ ${namesAr}`,
    prompt_en: `Which area did you mean? ${namesEn}`,
  };
}

type PricingAreaResolution =
  | { status: "resolved"; area: PricingArea }
  | { status: "ambiguous"; ambiguity_group_id: string; prompt_ar: string; prompt_en: string; options?: { area_id: number; name_en: string; name_ar: string }[] }
  | { status: "suggested"; area: PricingArea; prompt_ar: string; prompt_en: string; alternative_areas?: PricingArea[] }
  | { status: "not_found" };

type AreaResolutionCandidate = {
  area: PricingArea;
  source:
    | "resolver_metadata"
    | "exact"
    | "canonical"
    | "numbered_alias"
    | "substring"
    | "typo"
    | "voyage";
  prompt_ar?: string;
  prompt_en?: string;
  alternative_areas?: PricingArea[];
};

// buildResolverLookupKeys, matchesResolverAlias, buildPricingAreaFromResolverGroup
// moved to ./lib/pricing-resolver.ts (wave 1b).

function resolveAreaViaResolverMetadata(
  query: string,
  data: PricingData,
): PricingAreaResolution | null {
  const resolver = normalizePricingResolverConfig(data.resolver);
  if (!resolver) return null;

  const queryKeys = buildResolverLookupKeys(query);
  if (queryKeys.size === 0) return null;

  const pricingGroups = resolver.pricing_groups || [];
  const ambiguityGroups = resolver.ambiguity_groups || [];
  const explicitAliases = resolver.aliases || [];

  for (const group of ambiguityGroups) {
    for (const alias of group.aliases || []) {
      if (matchesResolverAlias(queryKeys, alias)) {
        return {
          status: "ambiguous",
          ambiguity_group_id: group.id,
          prompt_ar: group.prompt_ar,
          prompt_en: group.prompt_en,
          options: group.options,
        };
      }
    }
  }

  for (const group of pricingGroups) {
    for (const alias of group.aliases || []) {
      if (!matchesResolverAlias(queryKeys, alias)) continue;
      const area = buildPricingAreaFromResolverGroup(group, data.areas);
      if (area) {
        return { status: "resolved", area };
      }
    }
  }

  for (const aliasEntry of explicitAliases) {
    if (!matchesResolverAlias(queryKeys, aliasEntry.alias)) continue;

    if (aliasEntry.ambiguity_group_id) {
      const group = ambiguityGroups.find((entry) => entry.id === aliasEntry.ambiguity_group_id);
      if (group) {
        return {
          status: "ambiguous",
          ambiguity_group_id: group.id,
          prompt_ar: group.prompt_ar,
          prompt_en: group.prompt_en,
        };
      }
      continue;
    }

    if (aliasEntry.pricing_group_id) {
      const group = pricingGroups.find((entry) => entry.id === aliasEntry.pricing_group_id);
      if (!group) continue;
      const area = buildPricingAreaFromResolverGroup(group, data.areas);
      if (area) {
        return { status: "resolved", area };
      }
      continue;
    }

    if (aliasEntry.area_id) {
      const area = data.areas.find((entry) => entry.id === aliasEntry.area_id);
      if (area) {
        return { status: "resolved", area };
      }
    }
  }

  return null;
}

function collectDeterministicAreaCandidates(
  query: string,
  areas: PricingArea[],
): { candidates: AreaResolutionCandidate[]; substringPartialMatches: PricingArea[] } {
  const candidates: AreaResolutionCandidate[] = [];
  const seen = new Set<number>();

  const push = (
    source: AreaResolutionCandidate["source"],
    area: PricingArea | null | undefined,
  ) => {
    if (!area || seen.has(area.id)) return;
    seen.add(area.id);
    candidates.push({ area, source });
  };

  push("exact", findAreaExact(query, areas));
  push("canonical", findAreaCanonical(query, areas));
  push("numbered_alias", buildNumberedAreaAlias(query, areas));

  const subResult = findAreaSubstringEx(query, areas);
  push("substring", subResult.match);

  return { candidates, substringPartialMatches: subResult.partialMatches };
}

async function collectAreaResolutionCandidates(
  query: string,
  data: PricingData,
  fingerprint?: string,
): Promise<{
  ambiguity: Extract<PricingAreaResolution, { status: "ambiguous" }> | null;
  candidates: AreaResolutionCandidate[];
}> {
  const candidates: AreaResolutionCandidate[] = [];
  const seen = new Set<number>();
  const push = (candidate: AreaResolutionCandidate | null | undefined) => {
    if (!candidate || seen.has(candidate.area.id)) return;
    seen.add(candidate.area.id);
    candidates.push(candidate);
  };

  const metadataMatch = resolveAreaViaResolverMetadata(query, data);
  if (metadataMatch?.status === "ambiguous") {
    return { ambiguity: metadataMatch, candidates: [] };
  }
  if (metadataMatch?.status === "resolved") {
    push({ area: metadataMatch.area, source: "resolver_metadata" });
  }

  if (metadataMatch?.status !== "resolved") {
    const numberedFamilyAmbiguity = buildNumberedFamilyAmbiguity(query, data.areas);
    if (numberedFamilyAmbiguity) {
      return { ambiguity: numberedFamilyAmbiguity, candidates: [] };
    }
  }

  const deterministicResult = collectDeterministicAreaCandidates(query, data.areas);
  for (const candidate of deterministicResult.candidates) {
    push(candidate);
  }

  // If no safe substring match was found but areas partially matched,
  // surface dynamic ambiguity (2+) or a suggestion candidate (1).
  const hasSubstringHit = deterministicResult.candidates.some((c) => c.source === "substring");
  const hasDirectCandidate = candidates.some((candidate) => candidate.source !== "typo");
  if (!hasSubstringHit && !hasDirectCandidate && deterministicResult.substringPartialMatches.length >= 2) {
    const partials = deterministicResult.substringPartialMatches;
    const namesAr = partials.map((a) => a.name_ar).join(" / ");
    const namesEn = partials.map((a) => a.name_en).join(" / ");
    console.log(
      `[area-match] Dynamic ambiguity from partial substring matches: "${query}" → [${namesEn}]`,
    );
    return {
      ambiguity: {
        status: "ambiguous",
        ambiguity_group_id: `dynamic:${query}`,
        prompt_ar: `أقصد أي منطقة بالضبط؟ ${namesAr}`,
        prompt_en: `Which area did you mean? ${namesEn}`,
      },
      candidates: [],
    };
  }
  if (!hasSubstringHit && !hasDirectCandidate && deterministicResult.substringPartialMatches.length === 1) {
    const sole = deterministicResult.substringPartialMatches[0];
    console.log(
      `[area-match] Single partial substring suggestion: "${query}" → "${sole.name_en}"`,
    );
    push({
      area: sole,
      source: "substring",
      prompt_ar: `هل تقصد "${sole.name_ar}"؟`,
      prompt_en: `Did you mean "${sole.name_en}"?`,
    });
  }

  const nearMatch = findAreaNearTypoMatch(query, data.areas);
  if (nearMatch) {
    push({
      area: nearMatch.area,
      source: "typo",
      prompt_ar: nearMatch.prompt_ar,
      prompt_en: nearMatch.prompt_en,
      alternative_areas: nearMatch.alternative_areas,
    });
  }

  // Voyage embedding/reranker removed from area resolution pipeline.
  // The model now serves as the semantic/fuzzy layer — it interprets
  // messy input and passes a recognisable name. The deterministic layers
  // above (exact, alias, typo/Arabizi) verify. Voyage functions are
  // retained in the codebase for potential future non-area uses.

  console.log(
    `[area-resolution] query="${query}" candidates=${candidates.map((candidate) => `${candidate.source}:${candidate.area.name_en}`).join(", ") || "none"}`,
  );
  return { ambiguity: null, candidates };
}

function buildAreaResolutionTrace(
  query: string,
  result: {
    ambiguity: Extract<PricingAreaResolution, { status: "ambiguous" }> | null;
    candidates: AreaResolutionCandidate[];
  },
  decision: {
    status: PricingAreaResolution["status"];
    source?: AreaResolutionCandidate["source"] | "ambiguity_group";
    area?: PricingArea;
    ambiguity_group_id?: string;
    alternative_areas?: PricingArea[];
  },
) {
  const trace = {
    query,
    normalized: {
      has_arabic: containsArabicScript(query),
      fuzzy: normalizeForFuzzyMatch(query) || null,
      canonical: canonicalizeAreaName(query) || null,
      english: normalizeEn(query) || null,
      latin: normalizeLatinAreaKey(query) || null,
      lookup_keys: Array.from(buildResolverLookupKeys(query)).sort(),
    },
    candidates: result.candidates.map((candidate) => ({
      source: candidate.source,
      area_id: candidate.area.id,
      name_ar: candidate.area.name_ar,
      name_en: candidate.area.name_en,
      has_prompt: Boolean(candidate.prompt_ar || candidate.prompt_en),
      alternative_area_ids: candidate.alternative_areas?.map((area) => area.id) || [],
    })),
    decision: {
      status: decision.status,
      source: decision.source || null,
      area_id: decision.area?.id ?? null,
      name_ar: decision.area?.name_ar ?? null,
      name_en: decision.area?.name_en ?? null,
      ambiguity_group_id: decision.ambiguity_group_id || null,
      alternative_area_ids: decision.alternative_areas?.map((area) => area.id) || [],
    },
  };
  return trace;
}

function logAreaResolutionTrace(
  query: string,
  result: {
    ambiguity: Extract<PricingAreaResolution, { status: "ambiguous" }> | null;
    candidates: AreaResolutionCandidate[];
  },
  decision: {
    status: PricingAreaResolution["status"];
    source?: AreaResolutionCandidate["source"] | "ambiguity_group";
    area?: PricingArea;
    ambiguity_group_id?: string;
    alternative_areas?: PricingArea[];
  },
) {
  console.log(
    `[area-resolution-trace] ${JSON.stringify(buildAreaResolutionTrace(query, result, decision))}`,
  );
}

function decideAreaResolution(
  query: string,
  result: {
    ambiguity: Extract<PricingAreaResolution, { status: "ambiguous" }> | null;
    candidates: AreaResolutionCandidate[];
  },
): PricingAreaResolution {
  if (result.ambiguity) {
    logAreaResolutionTrace(query, result, {
      status: "ambiguous",
      source: "ambiguity_group",
      ambiguity_group_id: result.ambiguity.ambiguity_group_id,
    });
    return result.ambiguity;
  }

  const candidates = result.candidates;
  const resolvePriority: AreaResolutionCandidate["source"][] = [
    "resolver_metadata",
    "exact",
    "canonical",
    "numbered_alias",
    "substring",
  ];

  for (const source of resolvePriority) {
    const candidate = candidates.find((entry) => entry.source === source);
    if (candidate) {
      console.log(
        `[area-resolution] resolved "${query}" via ${candidate.source} -> "${candidate.area.name_en}"`,
      );
      logAreaResolutionTrace(query, result, {
        status: "resolved",
        source: candidate.source,
        area: candidate.area,
      });
      return { status: "resolved", area: candidate.area };
    }
  }

  const suggestion = candidates.find((entry) => entry.source === "typo");
  if (suggestion) {
    const hasAlternatives = suggestion.alternative_areas && suggestion.alternative_areas.length > 0;
    const typoCandidate = result.candidates.find((c) => c.source === "typo");
    const rawSimilarity = typoCandidate
      ? 1 - damerauLevenshteinDistance(
          compactLookupKey(containsArabicScript(query) ? canonicalizeAreaName(query) : normalizeLatinAreaKey(query)),
          compactLookupKey(containsArabicScript(typoCandidate.area.name_ar) ? canonicalizeAreaName(typoCandidate.area.name_ar) : normalizeLatinAreaKey(typoCandidate.area.name_en)),
        ) / Math.max(query.trim().length, (typoCandidate.area.name_en || "").length, 1)
      : 0;
    const isHighConfidence = !hasAlternatives && rawSimilarity >= 0.75;
    if (isHighConfidence) {
      console.log(
        `[area-resolution] auto-resolved "${query}" via confident typo -> "${suggestion.area.name_en}" similarity=${rawSimilarity.toFixed(4)}`,
      );
      logAreaResolutionTrace(query, result, {
        status: "resolved",
        source: "typo",
        area: suggestion.area,
      });
      return { status: "resolved", area: suggestion.area };
    }
    if (suggestion.prompt_ar && suggestion.prompt_en) {
      console.log(
        `[area-resolution] suggested "${query}" via ${suggestion.source} -> "${suggestion.area.name_en}"`,
      );
      logAreaResolutionTrace(query, result, {
        status: "suggested",
        source: suggestion.source,
        area: suggestion.area,
        alternative_areas: suggestion.alternative_areas,
      });
      return {
        status: "suggested",
        area: suggestion.area,
        prompt_ar: suggestion.prompt_ar,
        prompt_en: suggestion.prompt_en,
        ...(suggestion.alternative_areas?.length
          ? { alternative_areas: suggestion.alternative_areas }
          : {}),
      };
    }
  }

  console.log(`[area-resolution] not found "${query}"`);
  logAreaResolutionTrace(query, result, {
    status: "not_found",
  });
  return { status: "not_found" };
}

async function resolvePricingAreaQuery(
  query: string,
  data: PricingData,
  fingerprint?: string,
): Promise<PricingAreaResolution> {
  const result = await collectAreaResolutionCandidates(query, data, fingerprint);
  return decideAreaResolution(query, result);
}

/**
 * Token-conflict guard: returns true if the match should be REJECTED.
 * Checks if input and candidate have conflicting unique tokens — tokens present
 * in one but not the other that are NOT common filler words.
 */
// hasTokenConflict, normalizeEn, normalizeLatinAreaToken, normalizeLatinAreaKey,
// containsArabicScript, compactLookupKey, damerauLevenshteinDistance,
// normalizeGovernorateName moved to ./lib/area-matching.ts (wave 1b).

// normalizeAdminSenderId and buildAdminSenderIdCandidates moved to ./lib/config.ts (wave 1b).

function isPricingAdminSender(senderId: string | null | undefined) {
  const candidates = buildAdminSenderIdCandidates(senderId);
  return candidates.some((candidate) => pricingAdminAllowlist.includes(candidate));
}

function assertPricingAdminAuthorized(ctx: { requesterSenderId?: string; senderIsOwner?: boolean }) {
  if (ctx.senderIsOwner || isPricingAdminSender(ctx.requesterSenderId)) {
    return;
  }
  throw new Error("This pricing admin action is allowed only for authorized admin senders.");
}

function isBehaviorAdminSender(senderId: string | null | undefined) {
  const candidates = buildAdminSenderIdCandidates(senderId);
  return candidates.some(
    (candidate) => behaviorAdminAllowlist.includes(candidate) || pricingAdminAllowlist.includes(candidate),
  );
}

function assertBehaviorAdminAuthorized(ctx: { requesterSenderId?: string; senderIsOwner?: boolean }) {
  if (ctx.senderIsOwner || isBehaviorAdminSender(ctx.requesterSenderId)) {
    return;
  }
  throw new Error("This behavior admin action is allowed only for authorized admin senders.");
}

function isAdminSender(senderId: string | null | undefined) {
  return isPricingAdminSender(senderId) || isBehaviorAdminSender(senderId);
}

function assertAdminAuthorized(ctx: { requesterSenderId?: string; senderIsOwner?: boolean }) {
  if (ctx.senderIsOwner || isAdminSender(ctx.requesterSenderId)) {
    return;
  }
  throw new Error("This admin action is allowed only for authorized admin senders.");
}

function findAreaExact(query: string, areas: PricingArea[]): PricingArea | null {
  const q = query.trim();
  if (!q) return null;

  // 1. Exact match (Arabic or English)
  for (const a of areas) {
    if (a.name_ar === q || a.name_en === q) return a;
  }

  // 2. Case-insensitive English match
  const qLower = q.toLowerCase();
  for (const a of areas) {
    if (a.name_en.toLowerCase() === qLower) return a;
  }

  // 2.5 Deterministic Latin/Arabizi normalization (only if it resolves uniquely)
  const qLatin = normalizeLatinAreaKey(q);
  if (qLatin) {
    const latinMatches = areas.filter((area) => normalizeLatinAreaKey(area.name_en) === qLatin);
    if (latinMatches.length === 1) {
      console.log(`[area-match] Latin exact match: "${query}" → "${latinMatches[0].name_en}"`);
      return latinMatches[0];
    }
  }

  // 3. Normalized Arabic exact match (hamza/taa-marbouta insensitive)
  const qNorm = normalizeForFuzzyMatch(q);
  for (const a of areas) {
    if (normalizeForFuzzyMatch(a.name_ar) === qNorm) return a;
  }

  // 4. Arabic with ال stripped from each token (e.g. "منصورية" matches "المنصورية")
  const qStripped = stripArDefiniteArticle(qNorm);
  if (qStripped !== qNorm && qStripped.length >= 3) {
    const matches = areas.filter(
      (a) => stripArDefiniteArticle(normalizeForFuzzyMatch(a.name_ar)) === qStripped,
    );
    if (matches.length === 1) {
      console.log(`[area-match] Arabic ال-stripped match: "${query}" → "${matches[0].name_ar}" (${matches[0].name_en})`);
      return matches[0];
    }
  }

  return null;
}

/**
 * Layer 2: Canonical match — strip common prefixes, then exact compare.
 * Catches "ضاحية علي صباح السالم" → "علي صباح السالم" directly.
 */
function findAreaCanonical(query: string, areas: PricingArea[]): PricingArea | null {
  const qCanon = canonicalizeAreaName(query);
  if (!qCanon) return null;

  for (const a of areas) {
    if (canonicalizeAreaName(a.name_ar) === qCanon) {
      console.log(`[area-match] Canonical match: "${query}" → "${a.name_ar}" (${a.name_en})`);
      return a;
    }
    if (a.name_en && normalizeEn(a.name_en) === normalizeEn(qCanon)) {
      console.log(`[area-match] Canonical EN match: "${query}" → "${a.name_en}"`);
      return a;
    }
  }
  return null;
}

type SubstringMatchResult = {
  match: PricingArea | null;
  partialMatches: PricingArea[];
};

/**
 * Layer 3: Substring/contains match — the query contains an area name
 * or an area name contains the query (after canonicalization).
 * Works for both Arabic and English names.
 * Uses longest-match-first to avoid partial false positives.
 *
 * Returns { match, partialMatches } where:
 * - match: a single safe resolved area (extra tokens are only numeric suffixes)
 * - partialMatches: areas that substring-matched but had extra meaningful tokens
 *   (useful for dynamic ambiguity detection upstream)
 */
function findAreaSubstringEx(query: string, areas: PricingArea[]): SubstringMatchResult {
  const partialMatches: PricingArea[] = [];
  const partialSeen = new Set<number>();
  const addPartial = (area: PricingArea) => {
    if (partialSeen.has(area.id)) return;
    partialSeen.add(area.id);
    partialMatches.push(area);
  };

  const isEnglish = !containsArabicScript(query);

  // --- Arabic path (with ال-stripped fallback) ---
  const qCanon = canonicalizeAreaName(query);
  const qCanonStripped = qCanon ? stripArDefiniteArticle(qCanon) : "";

  if (qCanon && qCanon.length >= 3) {
    const sortedAr = areas
      .map((a) => ({
        area: a,
        canon: canonicalizeAreaName(a.name_ar),
        canonStripped: stripArDefiniteArticle(canonicalizeAreaName(a.name_ar)),
      }))
      .filter((e) => e.canon.length >= 3)
      .sort((a, b) => b.canon.length - a.canon.length);

    for (const entry of sortedAr) {
      if (!entry.canon.includes(qCanon) && !entry.canonStripped.includes(qCanonStripped)) continue;
      const { matchOnly } = diffMeaningfulAreaTokens(query, entry.area.name_ar);
      const unsafeExtraTokens = matchOnly.filter(
        (token) => !isNumericAreaSuffixToken(token) && token !== "ال",
      );
      if (unsafeExtraTokens.length > 0) {
        console.log(
          `[area-match] Partial substring (area contains query, AR): "${query}" x "${entry.area.name_ar}" extra=[${unsafeExtraTokens.join(", ")}]`,
        );
        addPartial(entry.area);
        continue;
      }
      console.log(
        `[area-match] Substring match (area contains query, AR): "${query}" → "${entry.area.name_ar}" (${entry.area.name_en})`,
      );
      return { match: entry.area, partialMatches: [] };
    }

    for (const entry of sortedAr) {
      if (!qCanon.includes(entry.canon) && !qCanonStripped.includes(entry.canonStripped)) continue;
      const { inputOnly } = diffMeaningfulAreaTokens(query, entry.area.name_ar);
      const unsafeExtraTokens = inputOnly.filter(
        (token) => !isNumericAreaSuffixToken(token) && token !== "ال",
      );
      if (unsafeExtraTokens.length > 0) {
        console.log(
          `[area-match] Partial substring (query contains area, AR): "${query}" x "${entry.area.name_ar}" extra=[${unsafeExtraTokens.join(", ")}]`,
        );
        addPartial(entry.area);
        continue;
      }
      console.log(
        `[area-match] Substring match (query contains area, AR): "${query}" → "${entry.area.name_ar}" (${entry.area.name_en})`,
      );
      return { match: entry.area, partialMatches: [] };
    }
  }

  // --- English path (strip "al"/"el" articles for better partial matching) ---
  if (isEnglish) {
    const qEn = normalizeEnSubstring(query);
    if (qEn && qEn.length >= 3) {
      const sortedEn = areas
        .filter((a) => !!a.name_en)
        .map((a) => ({ area: a, en: normalizeEnSubstring(a.name_en) }))
        .filter((e) => e.en.length >= 3)
        .sort((a, b) => b.en.length - a.en.length);

      for (const entry of sortedEn) {
        if (!entry.en.includes(qEn)) continue;
        const { matchOnly } = diffMeaningfulEnTokens(query, entry.area.name_en);
        const unsafeExtraTokens = matchOnly.filter((token) => !isNumericAreaSuffixToken(token));
        if (unsafeExtraTokens.length > 0) {
          console.log(
            `[area-match] Partial substring (area contains query, EN): "${query}" x "${entry.area.name_en}" extra=[${unsafeExtraTokens.join(", ")}]`,
          );
          addPartial(entry.area);
          continue;
        }
        console.log(
          `[area-match] Substring match (area contains query, EN): "${query}" → "${entry.area.name_en}"`,
        );
        return { match: entry.area, partialMatches: [] };
      }

      for (const entry of sortedEn) {
        if (!qEn.includes(entry.en)) continue;
        const { inputOnly } = diffMeaningfulEnTokens(query, entry.area.name_en);
        const unsafeExtraTokens = inputOnly.filter((token) => !isNumericAreaSuffixToken(token));
        if (unsafeExtraTokens.length > 0) {
          console.log(
            `[area-match] Partial substring (query contains area, EN): "${query}" x "${entry.area.name_en}" extra=[${unsafeExtraTokens.join(", ")}]`,
          );
          addPartial(entry.area);
          continue;
        }
        console.log(
          `[area-match] Substring match (query contains area, EN): "${query}" → "${entry.area.name_en}"`,
        );
        return { match: entry.area, partialMatches: [] };
      }
    }
  }

  return { match: null, partialMatches };
}

function findAreaSubstring(query: string, areas: PricingArea[]): PricingArea | null {
  return findAreaSubstringEx(query, areas).match;
}

function consonantSkeleton(text: string): string {
  return text.toLowerCase().replace(/[aeiou\s\-_''`]/g, "");
}

function findAreaByConsonantSkeleton(
  query: string,
  areas: PricingArea[],
): { area: PricingArea; alternatives: PricingArea[] } | null {
  if (containsArabicScript(query)) return null;

  const normalized = normalizeLatinAreaKey(query);
  const qSkeleton = consonantSkeleton(normalized);
  if (!qSkeleton || qSkeleton.length < 3) return null;

  const matches: { area: PricingArea; nameLen: number }[] = [];
  for (const area of areas) {
    if (!area.name_en) continue;
    const aSkeleton = consonantSkeleton(normalizeLatinAreaKey(area.name_en));
    if (!aSkeleton) continue;
    if (aSkeleton === qSkeleton) {
      matches.push({ area, nameLen: area.name_en.length });
    }
  }

  if (matches.length === 0) return null;

  // Also check skeleton with 1 edit distance for near-misses (e.g. doubled
  // consonant dropped). Only if we got zero exact skeleton hits.
  // For exact hits, sort by shortest name (most basic/parent area first).
  matches.sort((a, b) => a.nameLen - b.nameLen);

  const best = matches[0].area;
  const alternatives = matches.slice(1).map((m) => m.area);

  console.log(
    `[area-match] Consonant skeleton: "${query}" skeleton="${qSkeleton}" → "${best.name_en}"${alternatives.length ? ` (+${alternatives.length} alternatives)` : ""}`,
  );

  return { area: best, alternatives };
}

function findAreaNearTypoMatch(
  query: string,
  areas: PricingArea[],
): { area: PricingArea; prompt_ar: string; prompt_en: string; alternative_areas?: PricingArea[] } | null {
  const raw = query.trim();
  if (!raw) return null;

  const useArabic = containsArabicScript(raw);
  const normalizedQuery = compactLookupKey(
    useArabic ? canonicalizeAreaName(raw) : normalizeLatinAreaKey(raw),
  );
  if (!normalizedQuery || normalizedQuery.length < 4) return null;

  const maxDistance = normalizedQuery.length <= 6 ? 1 : 2;
  const candidates = new Map<
    number,
    { area: PricingArea; label: string; distance: number; similarity: number }
  >();

  for (const area of areas) {
    const label = useArabic ? area.name_ar : area.name_en;
    if (!label) continue;

    const normalizedLabel = compactLookupKey(
      useArabic ? canonicalizeAreaName(label) : normalizeLatinAreaKey(label),
    );
    if (!normalizedLabel || normalizedLabel === normalizedQuery) continue;
    if (Math.abs(normalizedLabel.length - normalizedQuery.length) > maxDistance) continue;

    const distance = damerauLevenshteinDistance(normalizedQuery, normalizedLabel);
    if (distance > maxDistance) continue;

    const similarity = 1 - distance / Math.max(normalizedQuery.length, normalizedLabel.length);
    const current = candidates.get(area.id);
    if (
      !current ||
      distance < current.distance ||
      (distance === current.distance && similarity > current.similarity)
    ) {
      candidates.set(area.id, { area, label, distance, similarity });
    }
  }

  const ranked = Array.from(candidates.values()).sort(
    (left, right) =>
      left.distance - right.distance ||
      right.similarity - left.similarity ||
      left.label.length - right.label.length,
  );
  if (ranked.length === 0) return null;

  const best = ranked[0];
  const runnerUp = ranked[1] || null;
  const closeAlternatives = ranked
    .slice(1, 3)
    .filter(
      (candidate) =>
        candidate.distance <= best.distance + 1 &&
        best.similarity - candidate.similarity < 0.12,
    )
    .map((candidate) => candidate.area);

  if (closeAlternatives.length > 0) {
    const options = [best.area, ...closeAlternatives];
    const prompt_ar = `لم أتعرف على الاسم "${query}" بشكل مؤكد. هل تقصد ${options.map((area) => `"${area.name_ar}"`).join(" أو ")}؟`;
    const prompt_en = `I couldn't confidently recognize "${query}". Did you mean ${options.map((area) => `"${area.name_en}"`).join(" or ")}?`;
    console.log(
      `[area-match] Typo clarification: "${query}" → options=${options.map((area) => area.name_en).join(", ")}`,
    );
    return {
      area: best.area,
      prompt_ar,
      prompt_en,
      alternative_areas: closeAlternatives,
    };
  }

  const prompt_ar = `لم أتعرف على الاسم "${query}" بشكل مؤكد. هل تقصد "${best.area.name_ar}"؟`;
  const prompt_en = `I couldn't confidently recognize "${query}". Did you mean "${best.area.name_en}"?`;
  console.log(
    `[area-match] Typo suggestion: "${query}" → "${best.area.name_ar}" (${best.area.name_en}) distance=${best.distance} similarity=${best.similarity.toFixed(4)}`,
  );

  return {
    area: best.area,
    prompt_ar,
    prompt_en,
  };
}

/**
 * Candidate collector for the graduated-response path.
 *
 * Unlike `findAreaNearTypoMatch` this never returns null and has no hard
 * distance cap — it always returns the top-K most-similar areas ranked by
 * `scoreAreaMatchSimilarity`. Used to:
 *  - show the LLM a shortlist when deterministic resolution fails
 *  - confirm plausibility when `verifyAreaEvidence` would otherwise reject
 *
 * Candidates with similarity below `minSimilarity` are dropped so the LLM
 * never sees pure noise. Default 0.25 is generous enough to surface
 * dropped-suffix Arabizi matches (e.g. "om il namel" → 0.667) while
 * excluding unrelated areas.
 */
export type AreaCandidate = {
  area: PricingArea;
  similarity: number;
};

function collectAreaCandidates(
  query: string,
  areas: PricingArea[],
  options: { topK?: number; minSimilarity?: number } = {},
): AreaCandidate[] {
  const topK = options.topK ?? 5;
  const minSimilarity = options.minSimilarity ?? 0.25;
  const raw = (query || "").trim();
  if (!raw || areas.length === 0) return [];

  const useArabic = containsArabicScript(raw);
  const scored: AreaCandidate[] = [];
  for (const area of areas) {
    const label = useArabic ? area.name_ar : area.name_en;
    if (!label) continue;
    const similarity = scoreAreaMatchSimilarity(raw, label);
    if (similarity < minSimilarity) continue;
    scored.push({ area, similarity });
  }

  scored.sort((a, b) => b.similarity - a.similarity);
  return scored.slice(0, topK);
}

/**
 * Confidence classifier for the graduated-response path. Used to tag
 * resolver outputs so the LLM knows whether to trust a match silently
 * ("high"), confirm with the customer ("medium"), or treat it as a
 * suggestion the customer must pick from ("low").
 */
type AreaMatchConfidence = "high" | "medium" | "low";

function confidenceFromSimilarity(similarity: number): AreaMatchConfidence {
  if (similarity >= 0.85) return "high";
  if (similarity >= 0.55) return "medium";
  return "low";
}

/**
 * Primary area lookup: deterministic-first pipeline with safe typo recovery.
 * Layer 1: Exact match
 * Layer 2: Canonical match (prefix-stripped)
 * Layer 2.5: Numeric-group alias match (e.g. "جنوب سعد العبدالله" → numbered sectors)
 * Layer 3: Substring/contains match
 * Layer 3.5: Deterministic typo/transliteration recovery
 * Layer 4: Voyage embedding retrieval
 * Layer 5: Voyage reranker verification
 */
async function findAreaAsync(
  query: string,
  areas: PricingArea[],
  fingerprint?: string,
): Promise<PricingAreaResolution> {
  // Layer 1 — exact string match
  const exactMatch = findAreaExact(query, areas);
  if (exactMatch) return { status: "resolved", area: exactMatch };

  // Layer 2 — canonical match (strip ضاحية/منطقة/جزيرة etc.)
  const canonMatch = findAreaCanonical(query, areas);
  if (canonMatch) return { status: "resolved", area: canonMatch };

  // Layer 2.5 — grouped numeric suffix match
  const numberedAliasMatch = buildNumberedAreaAlias(query, areas);
  if (numberedAliasMatch) return { status: "resolved", area: numberedAliasMatch };

  // Layer 3 — substring/contains match (bilingual, with dynamic ambiguity)
  const subResult = findAreaSubstringEx(query, areas);
  if (subResult.match) return { status: "resolved", area: subResult.match };
  if (subResult.partialMatches.length >= 2) {
    const namesAr = subResult.partialMatches.map((a) => a.name_ar).join(" / ");
    const namesEn = subResult.partialMatches.map((a) => a.name_en).join(" / ");
    return {
      status: "ambiguous",
      ambiguity_group_id: `dynamic:${query}`,
      prompt_ar: `أقصد أي منطقة بالضبط؟ ${namesAr}`,
      prompt_en: `Which area did you mean? ${namesEn}`,
    };
  }
  if (subResult.partialMatches.length === 1) {
    const sole = subResult.partialMatches[0];
    return {
      status: "suggested",
      area: sole,
      prompt_ar: `هل تقصد "${sole.name_ar}"؟`,
      prompt_en: `Did you mean "${sole.name_en}"?`,
    };
  }

  // Layer 3.5 — deterministic typo/transliteration recovery
  const nearMatch = findAreaNearTypoMatch(query, areas);
  if (nearMatch) {
    if (!nearMatch.alternative_areas?.length) {
      return { status: "resolved", area: nearMatch.area };
    }
    return {
      status: "suggested",
      area: nearMatch.area,
      prompt_ar: nearMatch.prompt_ar,
      prompt_en: nearMatch.prompt_en,
      alternative_areas: nearMatch.alternative_areas,
    };
  }

  // Layer 4 — Voyage embedding similarity (fallback)
  if (!voyageApiKey) {
    console.warn(`[voyage] VOYAGE_API_KEY not set; cannot resolve area "${query}"`);
    return { status: "not_found" };
  }
  const fp = fingerprint || createHash("sha256").update(JSON.stringify(areas.map((a) => a.name_en))).digest("hex");
  const embeddingResult = await findAreaByEmbeddingWithGuards(query, areas, fp);
  return embeddingResult
    ? {
        status: "suggested",
        area: embeddingResult.area,
        prompt_ar: embeddingResult.prompt_ar,
        prompt_en: embeddingResult.prompt_en,
      }
    : { status: "not_found" };
}

/** @deprecated Sync-only fallback kept for admin tools that don't need embedding. */
function findArea(query: string, areas: PricingArea[]): PricingArea | null {
  return findAreaExact(query, areas);
}

function formatPrice(value: number | null, currency: string): string {
  if (value === null || value === undefined) return "غير متوفر";
  return `${value.toFixed(3)} ${currency}`;
}

function splitFullName(fullName: string) {
  const parts = fullName
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (parts.length === 0) {
    return { first: "Customer", last: "Customer" };
  }

  if (parts.length === 1) {
    return { first: parts[0], last: parts[0] };
  }

  return {
    first: parts[0],
    last: parts.slice(1).join(" "),
  };
}

function normalizeLoosePhone(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  return value.replace(/[^\d+]/g, "").replace(/^\+/, "").trim();
}

function looksLikePhoneValue(value: string | null | undefined): boolean {
  const normalized = normalizeLoosePhone(value);
  return /^\d{7,20}$/.test(normalized);
}

function normalizeRouteComponent(value: string | null | undefined): string {
  return typeof value === "string" && value.trim() ? normalizeEn(value) : "";
}

function buildRouteKey(pickupArea: string | null | undefined, dropoffArea: string | null | undefined): string | null {
  const pickup = normalizeRouteComponent(pickupArea);
  const dropoff = normalizeRouteComponent(dropoffArea);
  if (!pickup || !dropoff) return null;
  return `${pickup}__${dropoff}`;
}

function hasLocationPinEvidence(value: string | null | undefined): boolean {
  if (typeof value !== "string" || !value.trim()) return false;
  return /location pin|pin provided|pin shared|shared by customer/i.test(value);
}

function hasCoordinateEvidence(latitude: unknown, longitude: unknown): boolean {
  return typeof latitude === "number" &&
    Number.isFinite(latitude) &&
    typeof longitude === "number" &&
    Number.isFinite(longitude);
}

function hasAnyAddressEvidence(params: {
  block?: string | null;
  street?: string | null;
  house?: string | null;
  notes?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}): boolean {
  return Boolean(
    (typeof params.block === "string" && params.block.trim()) ||
      (typeof params.street === "string" && params.street.trim()) ||
      (typeof params.house === "string" && params.house.trim()) ||
      hasLocationPinEvidence(params.notes) ||
      hasCoordinateEvidence(params.latitude, params.longitude),
  );
}

// Bilingual keyword map for Kuwait's 6 governorates.
// Keys are lowercase English stems; values are Arabic substrings to match.
const GOVERNORATE_EN_AR_MAP: [string, string][] = [
  ["capital", "عاصم"],
  ["hawalli", "حولي"],
  ["jahra", "جهرا"],
  ["farwaniya", "فروان"],
  ["ahmadi", "احمدي"],
  ["mubarak", "مبارك"],
];

function findGovernorateByName(
  governorateName: string,
  governorates: GeoGovernorate[],
): GeoGovernorate | null {
  const normalized = normalizeGovernorateName(governorateName);
  const normalizedAr = normalizeArabic(governorateName.replace(/محافظة/g, "").replace(/governorate/gi, ""));

  // 1. Exact normalized English match
  if (normalized) {
    for (const governorate of governorates) {
      const candidate = normalizeGovernorateName(governorate.name);
      if (candidate && candidate === normalized) {
        return governorate;
      }
    }
  }

  // 2. Exact normalized Arabic match
  if (normalizedAr) {
    for (const governorate of governorates) {
      const candidateAr = normalizeArabic(governorate.name.replace(/محافظة/g, ""));
      if (candidateAr && candidateAr === normalizedAr) {
        return governorate;
      }
    }
  }

  // 3. English includes (guard: skip empty strings)
  if (normalized) {
    for (const governorate of governorates) {
      const candidate = normalizeGovernorateName(governorate.name);
      if (candidate && (candidate.includes(normalized) || normalized.includes(candidate))) {
        return governorate;
      }
    }
  }

  // 4. Arabic includes (guard: skip empty strings)
  if (normalizedAr) {
    for (const governorate of governorates) {
      const candidateAr = normalizeArabic(governorate.name.replace(/محافظة/g, ""));
      if (candidateAr && (candidateAr.includes(normalizedAr) || normalizedAr.includes(candidateAr))) {
        return governorate;
      }
    }
  }

  // 5. Bilingual keyword fallback (English pricing name → Arabic geo name)
  for (const [enStem, arSubstring] of GOVERNORATE_EN_AR_MAP) {
    if (normalized.includes(enStem)) {
      const arNorm = normalizeArabic(arSubstring);
      for (const governorate of governorates) {
        if (normalizeArabic(governorate.name).includes(arNorm)) {
          return governorate;
        }
      }
    }
  }

  return null;
}

function resolveGeoAreaMatch(pricingArea: PricingArea, geoAreas: GeoArea[]): GeoArea | null {
  const objectid = pricingArea.geo?.objectid?.trim() || "";
  if (objectid) {
    const byObjectId = geoAreas.find((item) => item.objectid === objectid);
    if (byObjectId) {
      return byObjectId;
    }
  }

  const areaNameArCandidates = [
    pricingArea.geo?.area_name_ar || "",
    pricingArea.name_ar,
  ]
    .map((value) => normalizeArabic(value))
    .filter(Boolean);
  for (const areaNameAr of areaNameArCandidates) {
    const exactArabicMatch = geoAreas.find((item) => normalizeArabic(item.name) === areaNameAr);
    if (exactArabicMatch) {
      return exactArabicMatch;
    }
  }

  const areaNameEnCandidates = [
    pricingArea.geo?.area_name_en || "",
    pricingArea.name_en,
  ]
    .map((value) => normalizeEn(value))
    .filter(Boolean);
  for (const areaNameEn of areaNameEnCandidates) {
    const exactEnglishMatch = geoAreas.find((item) => normalizeEn(item.name) === areaNameEn);
    if (exactEnglishMatch) {
      return exactEnglishMatch;
    }
  }

  for (const areaNameAr of areaNameArCandidates) {
    const containsArabicMatch = geoAreas.find((item) => {
      const candidateAr = normalizeArabic(item.name);
      return candidateAr && (candidateAr.includes(areaNameAr) || areaNameAr.includes(candidateAr));
    });
    if (containsArabicMatch) {
      return containsArabicMatch;
    }
  }

  return null;
}

async function resolveAreaForOrdering(query: string) {
  const pricing = await loadPricing();
  const pricingAreaResolution = await resolvePricingAreaQuery(query, pricing);
  if (pricingAreaResolution.status !== "resolved") return null;
  const pricingArea = pricingAreaResolution.area;

  const targetGovernorateName = pricingArea.geo?.governorate || pricingArea.governorate;
  const governorates = await loadGovernorates();
  const governorate = findGovernorateByName(targetGovernorateName, governorates);
  if (!governorate) {
    throw new Error(`Governorate mapping not found for ${targetGovernorateName}`);
  }

  const geoAreas = await loadGeoAreas(governorate.id);
  const geoArea = resolveGeoAreaMatch(pricingArea, geoAreas);

  if (!geoArea) {
    throw new Error(
      `The area "${pricingArea.name_en}" (${pricingArea.name_ar}) is not currently available for online booking through Riders. Please suggest the customer contact Riders directly or choose a nearby area that is available.`,
    );
  }

  return {
    pricingArea,
    governorate,
    geoArea: {
      ...geoArea,
      governorate_name: governorate.name,
    },
  };
}

function getCommonShippingMethods(pickup: GeoShippingMethod[], dropoff: GeoShippingMethod[]) {
  const dropoffIds = new Set(dropoff.map((method) => method.id));
  const common = pickup.filter((method) => dropoffIds.has(method.id));
  if (common.length) return common;
  if (dropoff.length) return dropoff;
  return pickup;
}

function selectShippingMethod(
  methods: GeoShippingMethod[],
  deliveryType: BookableDeliveryType,
) {
  const isCar = deliveryType.startsWith("sedan");
  const isNormal = deliveryType.endsWith("_normal");

  const matchesVehicle = (name: string) => {
    const lower = name.toLowerCase();
    if (isCar) return lower.includes("car") || lower.includes("سياره") || lower.includes("سيارة") || lower.includes("سياره");
    return lower.includes("van") || lower.includes("بوكس");
  };

  const matchesSpeed = (method: GeoShippingMethod) => {
    const lower = method.name.toLowerCase();
    if (isNormal) return method.type === "normal" || lower.includes("standard") || lower.includes("عادي");
    return method.type === "quick" || lower.includes("super") || lower.includes("سوبر") || lower.includes("سريع");
  };

  // Exact match: vehicle + speed
  const exact = methods.find((m) => matchesVehicle(m.name) && matchesSpeed(m));
  if (exact) return exact;

  // Fallback: any method matching the vehicle type
  const vehicleFallback = methods.find((m) => matchesVehicle(m.name));
  return vehicleFallback ?? null;
}

function buildAddressPayload(
  resolvedArea: {
    governorate: GeoGovernorate;
    geoArea: GeoArea;
  },
  options: {
    block?: string | null;
    street?: string | null;
    house?: string | null;
    avenue?: string | null;
    extra?: string | null;
    notes?: string | null;
    latitude?: number | null;
    longitude?: number | null;
  },
) {
  const lat = hasCoordinateEvidence(options.latitude, options.longitude)
    ? Number(options.latitude)
    : (resolvedArea.geoArea.lat || resolvedArea.governorate.lat);
  const lng = hasCoordinateEvidence(options.latitude, options.longitude)
    ? Number(options.longitude)
    : (resolvedArea.geoArea.lng || resolvedArea.governorate.lng);

  if (!lat || !lng) {
    throw new Error(`Coordinates not available for ${resolvedArea.geoArea.name}`);
  }

  // Build a human-readable notes bag for the driver covering block/street,
  // avenue (when the customer gave one), and any free-form extra details
  // (floor, apartment, landmark, etc.). `avenue` also flows through as its
  // own structured field on the payload — the notes duplicate is belt-and-
  // suspenders so the driver UI shows it even if the backend hides the
  // structured avenue field.
  const noteParts: string[] = [];
  if (options.block) noteParts.push(`Block ${options.block}`);
  if (options.street) noteParts.push(`Street ${options.street}`);
  if (options.avenue) noteParts.push(`Avenue ${options.avenue}`);
  if (options.extra) noteParts.push(options.extra);
  if (options.notes) noteParts.push(options.notes);
  const combinedNotes = noteParts.length > 0 ? noteParts.join(", ") : null;

  return {
    coordinates: {
      lat,
      lng,
    },
    governorate_id: resolvedArea.governorate.id,
    area_id: resolvedArea.geoArea.id,
    block_id: null,
    street_id: null,
    avenue: options.avenue ?? null,
    house: options.house ?? null,
    notes: combinedNotes,
  };
}

function unavailableDeliveryTypeMessage(
  deliveryType: BookableDeliveryType,
  methods: GeoShippingMethod[],
) {
  const labels = {
    sedan_normal: "car standard",
    sedan_fast: "car express",
    van_normal: "van standard",
    van_fast: "van express",
  };

  const available =
    methods
      .map((method) => {
        const price = method.default_price ? ` (${method.default_price} KWD)` : "";
        return `${method.name}${price}`;
      })
      .join(", ") || "none";
  return `Requested ${labels[deliveryType]} is not available in the current Riders ordering API. Do not substitute a different delivery type automatically. Available live methods: ${available}`;
}

// parseNumericPrice + normalizePricingNumber moved to ./lib/pricing-resolver.ts (wave 1b).

// Behavior policy normalization helpers moved to ./lib/behavior-policy.ts (wave 1b).
// The wrapper below preserves the existing `buildNextBehaviorPolicy(policy, currentPolicy, senderId?)`
// signature used by register() + tools/admin-behavior.ts while delegating to the pure
// library implementation, which takes an explicit `normalizeAdminSenderId` collaborator.
function buildNextBehaviorPolicy(
  policy: BehaviorPolicy,
  currentPolicy: BehaviorPolicy,
  senderId?: string | null,
) {
  return libBuildNextBehaviorPolicy(
    policy,
    currentPolicy,
    senderId,
    normalizeAdminSenderId,
  );
}

function resolvePublishedAreasInput(params: {
  areas?: unknown;
  areas_json?: string | null;
}) {
  if (Array.isArray(params.areas)) {
    return params.areas;
  }

  if (typeof params.areas_json === "string" && params.areas_json.trim()) {
    const parsed = parseJsonInput("areas_json", params.areas_json);
    if (!Array.isArray(parsed)) {
      throw new Error("areas_json must decode to an array.");
    }
    return parsed;
  }

  throw new Error("Either areas or areas_json must be provided.");
}

function resolvePublishedColumnsInput(params: {
  columns?: unknown;
  columns_json?: string | null;
}) {
  if (params.columns === null || params.columns === undefined) {
    if (typeof params.columns_json === "string" && params.columns_json.trim()) {
      return parseJsonInput("columns_json", params.columns_json);
    }
    return null;
  }

  if (!isRecord(params.columns)) {
    throw new Error("columns must be an object when provided.");
  }

  return params.columns;
}

function resolvePublishedResolverInput(params: {
  resolver?: unknown;
  resolver_json?: string | null;
}) {
  if (params.resolver === null || params.resolver === undefined) {
    if (typeof params.resolver_json === "string" && params.resolver_json.trim()) {
      const parsed = parseJsonInput("resolver_json", params.resolver_json);
      if (!isRecord(parsed)) {
        throw new Error("resolver_json must decode to an object.");
      }
      return parsed;
    }
    return null;
  }

  if (!isRecord(params.resolver)) {
    throw new Error("resolver must be an object when provided.");
  }

  return params.resolver;
}

function resolveSheetRowsInput(params: {
  rows?: unknown;
  rows_json?: string | null;
}) {
  if (Array.isArray(params.rows)) {
    return params.rows;
  }

  if (typeof params.rows_json === "string" && params.rows_json.trim()) {
    const parsed = parseJsonInput("rows_json", params.rows_json);
    if (!Array.isArray(parsed)) {
      throw new Error("rows_json must decode to an array.");
    }
    return parsed;
  }

  throw new Error("Either rows or rows_json must be provided.");
}

function resolveSheetHeaderMapInput(params: {
  header_map?: unknown;
  header_map_json?: string | null;
}) {
  const raw =
    params.header_map === null || params.header_map === undefined
      ? typeof params.header_map_json === "string" && params.header_map_json.trim()
        ? parseJsonInput("header_map_json", params.header_map_json)
        : null
      : params.header_map;

  if (raw === null || raw === undefined) {
    return {} as Partial<Record<PricingAreaFieldKey, string>>;
  }

  if (!isRecord(raw)) {
    throw new Error("header_map must be an object when provided.");
  }

  const resolved: Partial<Record<PricingAreaFieldKey, string>> = {};
  for (const key of pricingAreaFieldKeys) {
    if (!(key in raw) || raw[key] === null || raw[key] === undefined) {
      continue;
    }

    const value = raw[key];
    if (typeof value !== "string" || !value.trim()) {
      throw new Error(`header_map.${key} must be a non-empty string when provided.`);
    }

    resolved[key] = value.trim();
  }

  return resolved;
}

// buildSheetHeaderFingerprints moved to ./lib/area-matching.ts (wave 1b).

function resolveSheetFieldValue(
  row: Record<string, unknown>,
  field: PricingAreaFieldKey,
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const aliases = headerMap[field] ? [headerMap[field] as string] : pricingSheetFieldAliases[field];
  const aliasFingerprints = new Set(aliases.flatMap((alias) => buildSheetHeaderFingerprints(alias)));

  for (const [key, value] of Object.entries(row)) {
    const keyFingerprints = buildSheetHeaderFingerprints(key);
    if (keyFingerprints.some((fingerprint) => aliasFingerprints.has(fingerprint))) {
      return value;
    }
  }

  return undefined;
}

function isSheetCellEmpty(value: unknown) {
  return value === null || value === undefined || (typeof value === "string" && !value.trim());
}

function isSkippableMalformedPricingSheetRow(
  candidate: Record<PricingAreaFieldKey, unknown>,
) {
  const parsedId = parseSheetAreaId(candidate.id);
  if (parsedId !== null) {
    return false;
  }

  const nonIdFields: PricingAreaFieldKey[] = [
    "governorate",
    "name_en",
    "name_ar",
    ...pricingColumnKeys,
  ];

  return (
    !isSheetCellEmpty(candidate.id) &&
    nonIdFields.every((field) => isSheetCellEmpty(candidate[field]))
  );
}

function normalizeSheetRowsToPublishedAreas(
  rows: unknown[],
  headerMap: Partial<Record<PricingAreaFieldKey, string>>,
) {
  const areas: PricingArea[] = [];
  let skippedRowCount = 0;

  rows.forEach((row, index) => {
    if (!isRecord(row)) {
      throw new Error(`rows[${index}] must be an object.`);
    }

    const candidate = buildPricingAreaCandidateFromSheetRow(row, headerMap);
    const relevantValues = pricingAreaFieldKeys.map((field) => candidate[field]);
    if (relevantValues.every((value) => isSheetCellEmpty(value))) {
      skippedRowCount += 1;
      return;
    }

    if (
      [candidate.id, candidate.governorate, candidate.name_en, candidate.name_ar].every((value) =>
        isSheetCellEmpty(value),
      )
    ) {
      skippedRowCount += 1;
      return;
    }

    if (isSkippableMalformedPricingSheetRow(candidate)) {
      skippedRowCount += 1;
      return;
    }

    areas.push(normalizePublishedPricingArea(candidate, index));
  });

  if (!areas.length) {
    throw new Error("No usable pricing rows were found in the provided sheet rows.");
  }

  return {
    areas,
    skipped_row_count: skippedRowCount,
  };
}

// normalizePricingText, normalizePublishedPricingValue, normalizePublishedPricingColumns,
// normalizePublishedPricingArea, normalizePricingGeoAreaHint moved to ./lib/pricing-resolver.ts (wave 1b).

// Resolver-config normalize/validate/merge helpers moved to ./lib/pricing-resolver.ts (wave 1b).

async function applyPricingResolverOverlayIfConfigured(data: PricingData): Promise<PricingData> {
  const inspection = await inspectPricingResolverOverlay(data);
  if (!inspection.status.configured) {
    return data;
  }

  if (inspection.status.state === "missing") {
    console.warn(
      `[pricing] RIDERS_PRICING_RESOLVER_OVERLAY_PATH / resolverOverlayPath not found: ${describePath(pricingResolverOverlayPathOverride)}`,
    );
    return data;
  }

  if (inspection.status.state === "invalid") {
    throw new Error(
      inspection.status.error ||
        `Resolver overlay is invalid: ${describePath(pricingResolverOverlayPathOverride)}`,
    );
  }

  if (!inspection.mergedResolver) {
    return data;
  }

  return { ...data, resolver: inspection.mergedResolver };
}

// buildPublishedPricingData, pricesMatch, maxPrice, getRouteSheetPrice,
// getBidirectionalRoutePrices moved to ./lib/pricing-resolver.ts (wave 1b).

function resolveAdminPricingArea(
  params: {
    area_id?: number | null;
    area_name?: string | null;
    governorate?: string | null;
  },
  areas: PricingArea[],
) {
  if (typeof params.area_id === "number" && Number.isFinite(params.area_id)) {
    const byId = areas.find((item) => item.id === params.area_id);
    if (!byId) {
      throw new Error(`Area ID not found: ${params.area_id}`);
    }
    return byId;
  }

  const areaName = typeof params.area_name === "string" ? params.area_name.trim() : "";
  if (!areaName) {
    throw new Error("Provide area_id or area_name.");
  }

  const governorateName = typeof params.governorate === "string" ? params.governorate.trim() : "";
  const candidateAreas = governorateName
    ? areas.filter((item) => {
        const itemGov = normalizeGovernorateName(item.governorate);
        const queryGov = normalizeGovernorateName(governorateName);
        return itemGov === queryGov || itemGov.includes(queryGov) || queryGov.includes(itemGov);
      })
    : areas;

  const match = findArea(areaName, candidateAreas);
  if (!match) {
    throw new Error(`Area not found: ${areaName}`);
  }
  return match;
}

// getDeliveryTypeLabels moved to ./lib/pricing-resolver.ts (wave 1b).

function summarizeLiveDeliveryOption(
  deliveryType: BookableDeliveryType,
  method: GeoShippingMethod | null,
  currency: string,
  gridBookable?: boolean,
) {
  const labels = getDeliveryTypeLabels(deliveryType);
  const livePrice = parseNumericPrice(method?.default_price) ?? parseNumericPrice(method?.price);

  return {
    delivery_type: deliveryType,
    label_ar: labels.ar,
    label_en: labels.en,
    available_for_direct_chat_booking: gridBookable ?? Boolean(method),
    shipping_method: method
      ? {
          id: method.id,
          name: method.name,
          type: method.type,
          default_price: method.default_price ?? null,
          formatted_price: livePrice === null ? null : formatPrice(livePrice, currency),
        }
      : null,
  };
}

function buildSpecialDeliveryCapability(
  deliveryType: SpecialQuoteableDeliveryType,
  settings: RidersGridLiveSettingsSummary | null,
  lookupError?: string | null,
): SpecialDeliveryCapabilitySummary {
  const labels = getDeliveryTypeLabels(deliveryType);
  const backendFeatureEnabled =
    deliveryType === "helper_standard"
      ? settings?.assistant_enabled ?? null
      : settings?.freezer_enabled ?? null;
  const directChatPathImplemented = DIRECT_CHAT_BOOKING_IMPLEMENTED_TYPES.has(deliveryType);

  if (backendFeatureEnabled === true && directChatPathImplemented) {
    return {
      delivery_type: deliveryType,
      available_for_direct_chat_booking: true,
      unavailable_status: "manual_confirmation_required",
      note: "This option is verified for direct chat booking on the current backend configuration.",
      backend_feature_enabled: backendFeatureEnabled,
    };
  }

  const note = lookupError
    ? `This option is priced in the approved Riders sheet, but live backend support could not be confirmed right now (${lookupError}). Quote it if the customer asks, but require manual confirmation before booking.`
    : backendFeatureEnabled === false
      ? `This option is priced in the approved Riders sheet, but the live Riders backend currently has ${labels.en.toLowerCase()} disabled for automated order creation. Quote it if the customer asks, but require manual confirmation before booking.`
      : backendFeatureEnabled === true
        ? `This option is enabled in the live Riders backend, but our current direct chat order path is not verified for ${labels.en.toLowerCase()} yet. Quote it if the customer asks, but require manual confirmation before booking.`
        : `This option is priced in the approved Riders sheet, but live backend support for ${labels.en.toLowerCase()} could not be confirmed. Quote it if the customer asks, but require manual confirmation before booking.`;

  return {
    delivery_type: deliveryType,
    available_for_direct_chat_booking: false,
    unavailable_status: "manual_confirmation_required",
    note,
    backend_feature_enabled: backendFeatureEnabled,
  };
}

async function getSpecialDeliveryCapabilities(): Promise<
  Record<SpecialQuoteableDeliveryType, SpecialDeliveryCapabilitySummary>
> {
  try {
    const settings = await loadRidersGridLiveSettingsSummary();
    return {
      cooled_van_normal: buildSpecialDeliveryCapability("cooled_van_normal", settings),
      cooled_van_fast: buildSpecialDeliveryCapability("cooled_van_fast", settings),
      helper_standard: buildSpecialDeliveryCapability("helper_standard", settings),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      cooled_van_normal: buildSpecialDeliveryCapability("cooled_van_normal", null, message),
      cooled_van_fast: buildSpecialDeliveryCapability("cooled_van_fast", null, message),
      helper_standard: buildSpecialDeliveryCapability("helper_standard", null, message),
    };
  }
}

function isOrderCreationBlockedByLiveMaintenance(
  settings: RidersGridLiveSettingsSummary | null | undefined,
): boolean {
  if (!settings) {
    return false;
  }
  return (
    settings.site_order_mode === false ||
    settings.site_maintenance_mode === true ||
    settings.maintenance_mode === true
  );
}

function extractMaintenanceResumeTime(message: string | null | undefined): string | null {
  if (typeof message !== "string") {
    return null;
  }
  const match = message.match(/\b(\d{1,2}:\d{2}\s*[AP]M)\b/i);
  return match ? match[1].toUpperCase() : null;
}

function buildCreateOrderMaintenanceResult(settings: RidersGridLiveSettingsSummary) {
  const liveNotice =
    settings.maintenance_message ||
    (settings.site_order_mode === false
      ? "The live Riders backend has order creation disabled right now."
      : "The live Riders backend is currently in maintenance mode.");
  const resumeTime = extractMaintenanceResumeTime(settings.maintenance_message);
  const customerMessageEn =
    resumeTime
      ? `Riders order creation is temporarily unavailable due to maintenance. Riders says requests will be received starting at ${resumeTime}.`
      : settings.maintenance_message
        ? `Riders order creation is temporarily unavailable due to maintenance. Live notice: ${settings.maintenance_message}`
        : "Riders order creation is temporarily unavailable due to maintenance. Please try again later.";
  const customerMessageAr =
    resumeTime
      ? `حالياً نظام إنشاء الطلبات لدى Riders غير متاح بسبب الصيانة. وحسب إشعار النظام سيبدأ استقبال الطلبات من ${resumeTime}.`
      : settings.maintenance_message
        ? `حالياً نظام إنشاء الطلبات لدى Riders غير متاح بسبب الصيانة. إشعار النظام: ${settings.maintenance_message}`
        : "حالياً نظام إنشاء الطلبات لدى Riders غير متاح بسبب الصيانة. يرجى المحاولة لاحقاً.";

  return createTextResult(
    {
      status: "maintenance",
      message:
        `Do not attempt create_simple_order right now. The live Riders backend is blocking order creation due to maintenance. ` +
        `Relay the customer maintenance message instead and wait until maintenance is lifted before retrying.`,
      maintenance: {
        site_order_mode: settings.site_order_mode,
        site_maintenance_mode: settings.site_maintenance_mode,
        maintenance_mode: settings.maintenance_mode,
        maintenance_message: settings.maintenance_message,
      },
      _customer_message: customerMessageEn,
      _customer_message_ar: customerMessageAr,
      _customer_message_en: customerMessageEn,
      _instruction:
        "RELAY the maintenance message to the customer as-is in the conversation language. Do NOT retry create_simple_order while maintenance is active.",
    },
    {
      live_notice: liveNotice,
    },
  );
}

function createTextResult(payload: unknown, details?: unknown) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2),
      },
    ],
    ...(details === undefined ? {} : { details }),
  };
}

function createAreaClarificationResult(params: {
  field: "pickup_area" | "dropoff_area" | "delivery_area";
  query: string;
  prompt_ar: string;
  prompt_en: string;
  options?: { area_id: number; name_en: string; name_ar: string }[];
}) {
  const { field, query, prompt_ar, prompt_en, options } = params;
  return createTextResult({
    status: "clarification_required",
    field,
    query,
    message: prompt_en,
    prompt_ar,
    prompt_en,
    ...(options?.length ? { options } : {}),
    _customer_message: prompt_en,
    _customer_message_ar: prompt_ar,
    _customer_message_en: prompt_en,
    _instruction:
      "Ask the customer to choose one of the options. When they reply, re-call get_price using the chosen option's area_id (e.g. pickup_area_id or dropoff_area_id) to bypass disambiguation. Use only one language in the customer-facing reply.",
  });
}

function getAreaFieldLabels(field: "pickup_area" | "dropoff_area" | "delivery_area") {
  switch (field) {
    case "pickup_area":
      return { ar: "منطقة الاستلام", en: "pickup area" };
    case "delivery_area":
      return { ar: "منطقة التوصيل", en: "delivery area" };
    default:
      return { ar: "منطقة التوصيل", en: "dropoff area" };
  }
}

function createAreaSuggestionResult(params: {
  field: "pickup_area" | "dropoff_area" | "delivery_area";
  query: string;
  suggestedArea: PricingArea;
  prompt_ar: string;
  prompt_en: string;
  alternativeAreas?: PricingArea[];
}) {
  const { field, query, suggestedArea, prompt_ar, prompt_en, alternativeAreas } = params;
  return createTextResult({
    status: "clarification_required",
    field,
    query,
    message: prompt_en,
    prompt_ar,
    prompt_en,
    suggested_area: {
      id: suggestedArea.id,
      name_ar: suggestedArea.name_ar,
      name_en: suggestedArea.name_en,
    },
    ...(alternativeAreas?.length
      ? {
          alternative_areas: alternativeAreas.map((area) => ({
            id: area.id,
            name_ar: area.name_ar,
            name_en: area.name_en,
          })),
        }
      : {}),
    _customer_message: prompt_en,
    _customer_message_ar: prompt_ar,
    _customer_message_en: prompt_en,
    _instruction:
      "Ask the customer to confirm the suggested area name before quoting or booking. Use only one language in the customer-facing reply.",
  });
}

function createAreaNotFoundResult(params: {
  field: "pickup_area" | "dropoff_area" | "delivery_area";
  query: string;
  /** Optional top-K similar areas computed by `collectAreaCandidates`. When
   * present, the LLM can use them on the next turn to either re-call
   * get_price with an area_id (if confident) or ask the customer a
   * candidate-based clarification ("did you mean one of these?"). */
  closestCandidates?: AreaCandidate[];
}) {
  const { field, query, closestCandidates } = params;
  const labels = getAreaFieldLabels(field);
  const prompt_ar = `لم أتعرف على اسم ${labels.ar} "${query}". يرجى إعادة اسم المنطقة أو إرسال منطقة قريبة معروفة.`;
  const prompt_en = `I couldn't recognize the ${labels.en} "${query}". Please send the area name again or share a nearby known area.`;
  const candidatePayload =
    closestCandidates && closestCandidates.length > 0
      ? {
          closest_candidates: closestCandidates.map((c) => ({
            area_id: c.area.id,
            name_en: c.area.name_en,
            name_ar: c.area.name_ar,
            similarity: Number(c.similarity.toFixed(3)),
          })),
        }
      : {};
  return createTextResult({
    status: "area_not_found",
    field,
    query,
    message: prompt_en,
    prompt_ar,
    prompt_en,
    ...candidatePayload,
    _customer_message: prompt_en,
    _customer_message_ar: prompt_ar,
    _customer_message_en: prompt_en,
    _instruction: closestCandidates && closestCandidates.length > 0
      ? "The area name could not be recognized with confidence. Review `closest_candidates` — if one is clearly what the customer meant (dialect, Arabizi, typo), re-call get_price with that area_id in pickup_area_id or dropoff_area_id. Otherwise ask the customer to confirm the top candidate by name, or pick from the list. Do not silently pick a candidate without confirmation when the top similarity is below 0.6."
      : "Tell the customer the area name could not be recognized yet. Ask them to restate the area or provide a nearby known area. Do not claim the service is unavailable unless a later tool result confirms that explicitly.",
  });
}

/**
 * Graduated-response result for `verifyAreaEvidence` `needs_clarification`.
 * The customer's raw token didn't resolve deterministically but has a
 * plausible link to the model's claimed area. We return the candidates and
 * let the LLM decide: re-call with an area_id (if it's confident) or
 * confirm with the customer using the top candidate's name (if unsure).
 * Never silently accept the model's claim — always require a verifiable
 * next step.
 */
function createAreaNeedsClarificationResult(params: {
  field: "pickup_area" | "dropoff_area" | "delivery_area";
  query: string;
  modelArea: PricingArea;
  modelSimilarity: number;
  matchConfidence: AreaMatchConfidence;
  closestCandidates: AreaCandidate[];
}) {
  const { field, query, modelArea, modelSimilarity, matchConfidence, closestCandidates } =
    params;
  const labels = getAreaFieldLabels(field);
  const topCandidate = closestCandidates[0]?.area ?? modelArea;
  const prompt_ar = `هل تقصد "${topCandidate.name_ar}" في ${labels.ar}؟`;
  const prompt_en = `Did you mean "${topCandidate.name_en}" for ${labels.en}?`;
  return createTextResult({
    status: "area_needs_clarification",
    field,
    query,
    message: prompt_en,
    prompt_ar,
    prompt_en,
    model_proposed: {
      area_id: modelArea.id,
      name_en: modelArea.name_en,
      name_ar: modelArea.name_ar,
      similarity: Number(modelSimilarity.toFixed(3)),
      match_confidence: matchConfidence,
    },
    closest_candidates: closestCandidates.map((c) => ({
      area_id: c.area.id,
      name_en: c.area.name_en,
      name_ar: c.area.name_ar,
      similarity: Number(c.similarity.toFixed(3)),
    })),
    _customer_message: prompt_en,
    _customer_message_ar: prompt_ar,
    _customer_message_en: prompt_en,
    _instruction:
      "The customer's raw word did not match an area exactly, but the top candidate looks close. " +
      "If `model_proposed.match_confidence` is 'high' you may re-call get_price with that area_id directly. " +
      "If 'medium' confirm with the customer using the top candidate's name before quoting. " +
      "If 'low' ask the customer to pick from `closest_candidates` or restate the area. " +
      "Use only one language in the customer-facing reply.",
  });
}

function assertRidersApiConfigured() {
  if (!ridersApiKey) {
    throw new Error("RIDERS_API_KEY is not configured");
  }
}

function assertWriteActionsEnabled() {
  if (!writeActionsEnabled) {
    throw new Error("WRITE_ACTIONS_ENABLED is disabled");
  }
}

async function ridersRequest(
  method: string,
  endpoint: string,
  body?: unknown,
): Promise<RidersApiPayload> {
  assertRidersApiConfigured();

  const headers: Record<string, string> = {
    Accept: "application/json",
    "x-api-key": ridersApiKey,
  };

  if (ridersBearerToken) {
    headers.Authorization = `Bearer ${ridersBearerToken}`;
  }

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  const timeoutMs = method === "POST" ? 55_000 : 30_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${ridersApiBaseUrl}${endpoint}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err: unknown) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      throw new RidersApiError(
        `Riders API request timed out after ${timeoutMs / 1000}s (${method} ${endpoint}). The upstream server may be slow. Please try again shortly.`,
        0,
        { timeout: true, method, endpoint },
      );
    }
    throw err;
  }
  clearTimeout(timer);

  const raw = await response.text();
  let payload: RidersApiPayload | null = null;

  if (raw) {
    try {
      payload = JSON.parse(raw) as RidersApiPayload;
    } catch {
      payload = {
        success: response.ok,
        message: raw,
        data: null,
      };
    }
  }

  if (!response.ok) {
    throw new RidersApiError(
      payload?.message || `Riders API request failed (${response.status})`,
      response.status,
      payload,
    );
  }

  return payload || {
    success: true,
    message: "ok",
    data: null,
  };
}

async function ridersGridRequest(
  method: string,
  endpoint: string,
  body?: unknown,
): Promise<RidersApiPayload> {
  if (!ridersGridApiKey) {
    throw new Error("RIDERS_GRID_API_KEY (or RIDERS_API_KEY) is not configured");
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    "x-api-key": ridersGridApiKey,
    Authorization: `Bearer ${ridersGridApiKey}`,
  };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  const timeoutMs = method === "POST" ? 55_000 : 30_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${ridersGridApiBaseUrl}${endpoint}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err: unknown) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      throw new RidersApiError(
        `Riders Grid API request timed out after ${timeoutMs / 1000}s (${method} ${endpoint}). The upstream server may be slow. Please try again shortly.`,
        0,
        { timeout: true, method, endpoint },
      );
    }
    throw err;
  }
  clearTimeout(timer);

  const raw = await response.text();
  let payload: RidersApiPayload | null = null;

  if (raw) {
    try {
      payload = JSON.parse(raw) as RidersApiPayload;
    } catch {
      payload = {
        success: response.ok,
        message: raw,
        data: null,
      };
    }
  }

  if (!response.ok) {
    throw new RidersApiError(
      payload?.message || `Riders Grid API request failed (${response.status})`,
      response.status,
      payload,
    );
  }

  return payload || {
    success: true,
    message: "ok",
    data: null,
  };
}

// Flatten a nested object into bracket-notation keys for multipart/form-data.
// e.g. { pickup_address: { coordinates: { lat: "29.0" } } }
//   → [["pickup_address[coordinates][lat]", "29.0"]]
function flattenToFormEntries(
  obj: Record<string, unknown>,
  prefix = "",
): [string, string][] {
  const entries: [string, string][] = [];

  for (const [key, value] of Object.entries(obj)) {
    const fieldKey = prefix ? `${prefix}[${key}]` : key;

    if (value === null || value === undefined) {
      continue;
    } else if (typeof value === "object" && !Array.isArray(value)) {
      entries.push(...flattenToFormEntries(value as Record<string, unknown>, fieldKey));
    } else {
      entries.push([fieldKey, String(value)]);
    }
  }

  return entries;
}

// Send a multipart/form-data request to the Riders API (order.store endpoint).
async function ridersFormDataRequest(
  method: string,
  endpoint: string,
  body: Record<string, unknown>,
): Promise<RidersApiPayload> {
  if (!ridersGridApiKey) {
    throw new Error("RIDERS_GRID_API_KEY (or RIDERS_API_KEY) is not configured");
  }

  const formData = new FormData();
  for (const [key, value] of flattenToFormEntries(body)) {
    formData.append(key, value);
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    "x-api-key": ridersGridApiKey,
    Authorization: `Bearer ${ridersGridApiKey}`,
  };

  const controller = new AbortController();
  const timeoutMs = 55_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response!: Response;
  const maxAttempts = 2;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      response = await fetch(`${ridersGridApiBaseUrl}${endpoint}`, {
        method,
        headers,
        body: formData,
        signal: controller.signal,
      });
      break;
    } catch (err: unknown) {
      if (attempt < maxAttempts && err instanceof Error && err.name !== "AbortError") {
        // Transient network error — wait briefly and retry once
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }
      clearTimeout(timer);
      if (err instanceof Error && err.name === "AbortError") {
        throw new RidersApiError(
          `Riders API request timed out after ${timeoutMs / 1000}s (${method} ${endpoint}).`,
          0,
          { timeout: true, method, endpoint },
        );
      }
      throw err;
    }
  }
  clearTimeout(timer);

  const raw = await response.text();
  let payload: RidersApiPayload | null = null;

  if (raw) {
    try {
      payload = JSON.parse(raw) as RidersApiPayload;
    } catch {
      payload = {
        success: response.ok,
        message: raw,
        data: null,
      };
    }
  }

  if (!response.ok) {
    throw new RidersApiError(
      payload?.message || `Riders API request failed (${response.status})`,
      response.status,
      payload,
    );
  }

  return payload || {
    success: true,
    message: "ok",
    data: null,
  };
}

function assertFleetrunnrConfigured() {
  if (!fleetrunnrBearerToken) {
    throw new Error("FLEETRUNNR_BEARER_TOKEN is not configured");
  }
}

function assertValidFleetrunnrOrderId(orderId: string) {
  if (!/^ORDER-[A-Za-z0-9-]+$/.test(orderId)) {
    throw new Error('Please provide a valid order number starting with "ORDER-".');
  }
}

async function fleetrunnrRequest(method: string, endpoint: string): Promise<any> {
  assertFleetrunnrConfigured();

  const response = await fetch(`${fleetrunnrApiBaseUrl}${endpoint}`, {
    method,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${fleetrunnrBearerToken}`,
    },
  });

  const raw = await response.text();
  let payload: any = null;

  if (raw) {
    try {
      payload = JSON.parse(raw) as any;
    } catch {
      payload = raw;
    }
  }

  if (!response.ok || (isRecord(payload) && payload.success === false)) {
    const message =
      (isRecord(payload) && asOptionalTrimmedString(payload.message)) ||
      `Fleetrunnr API request failed (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

function getNestedRecordValue(source: Record<string, unknown>, path: string[]): unknown {
  let current: unknown = source;
  for (const segment of path) {
    if (!isRecord(current)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
}

function getFirstTrackingString(records: Record<string, unknown>[], paths: string[][]) {
  for (const record of records) {
    for (const path of paths) {
      const value = getNestedRecordValue(record, path);
      const text = asOptionalTrimmedString(value);
      if (text) {
        return text;
      }
    }
  }
  return null;
}

function normalizeFleetrunnrTracking(payload: unknown, requestedOrderId: string) {
  const records = [
    payload,
    isRecord(payload) ? payload.data : null,
    isRecord(payload) && isRecord(payload.data) ? payload.data.order : null,
    isRecord(payload) ? payload.order : null,
  ].filter((value): value is Record<string, unknown> => isRecord(value));

  const orderId =
    getFirstTrackingString(records, [["order_id"], ["id"], ["uid"]]) || requestedOrderId;

  return {
    order_id: orderId,
    status: getFirstTrackingString(records, [
      ["status"],
      ["order_status"],
      ["delivery_status"],
      ["state"],
      ["attributes", "status"],
    ]),
    tracking_url: getFirstTrackingString(records, [
      ["tracking_url"],
      ["trackingUrl"],
      ["tracking", "url"],
      ["tracking", "tracking_url"],
      ["attributes", "tracking_url"],
    ]),
    agent_phone_number: getFirstTrackingString(records, [
      ["agent_phone_number"],
      ["agentPhoneNumber"],
      ["carrier", "agent_phone_number"],
      ["carrier", "agent"],
      ["driver_phone_number"],
      ["driverPhoneNumber"],
      ["agent", "phone_number"],
      ["agent", "phone"],
      ["driver", "phone_number"],
      ["driver", "phone"],
      ["courier", "phone_number"],
      ["courier", "phone"],
      ["attributes", "agent_phone_number"],
    ]),
  };
}

function normalizeOrder(order: any) {
  if (!order || typeof order !== "object") return null;

  return {
    id: order.id ?? null,
    uid: order.uid ?? null,
    status: order.status ?? null,
    payment_status: order.payment_status ?? null,
    payment_method: order.payment_method ?? null,
    payer: order.payer ?? null,
    total: order.total ?? null,
    subtotal: order.subtotal ?? null,
    discount: order.discount ?? null,
    sender_name: [order.sender_name_first, order.sender_name_last]
      .filter(Boolean)
      .join(" ") || null,
    sender_phone: order.sender_phone ?? null,
    recipient_name: [order.recipient_name_first, order.recipient_name_last]
      .filter(Boolean)
      .join(" ") || null,
    recipient_phone: order.recipient_phone ?? null,
    shipping_method: order.shipping_method
      ? {
          id: order.shipping_method.id ?? null,
          name: order.shipping_method.name ?? null,
          type: order.shipping_method.type ?? null,
          default_price: order.shipping_method.default_price ?? null,
        }
      : null,
    pickup_address: order.pickup_address ?? null,
    delivery_address: order.delivery_address ?? null,
  };
}

function errorPayload(err: unknown) {
  if (err instanceof RidersApiError) {
    return {
      status: "error",
      message: err.message,
      http_status: err.status,
      details: err.details,
    };
  }

  return {
    status: "error",
    message: err instanceof Error ? err.message : String(err),
  };
}

function getQuotedPriceForDeliveryType(
  prices: Pick<PricingArea, "sedan_normal" | "sedan_fast" | "cooled_van_normal" | "cooled_van_fast" | "van_normal" | "van_fast" | "helper_standard">,
  deliveryType: QuoteableDeliveryType,
) {
  switch (deliveryType) {
    case "sedan_normal":
      return prices.sedan_normal;
    case "sedan_fast":
      return prices.sedan_fast;
    case "cooled_van_normal":
      return prices.cooled_van_normal;
    case "cooled_van_fast":
      return prices.cooled_van_fast;
    case "van_normal":
      return prices.van_normal;
    case "van_fast":
      return prices.van_fast;
    case "helper_standard":
      return prices.helper_standard;
  }
}

function buildServiceCatalogEntry(
  deliveryType: QuoteableDeliveryType,
  quotedPrice: number | null,
  currency: string,
  options?: {
    visibility?: "default" | "available_on_request";
    liveOption?: LiveDeliveryOptionSummary | null;
    specialCapability?: SpecialDeliveryCapabilitySummary | null;
  },
): ServiceCatalogEntry {
  const labels = getDeliveryTypeLabels(deliveryType);

  if (options?.liveOption?.available_for_direct_chat_booking) {
    return {
      delivery_type: deliveryType,
      label_ar: labels.ar,
      label_en: labels.en,
      quoted_price: quotedPrice,
      formatted_price: formatPrice(quotedPrice, currency),
      visibility: options?.visibility ?? "available_on_request",
      direct_chat_booking_status: "verified",
      direct_chat_booking_note:
        "This option is verified for direct chat booking on the current route.",
    };
  }

  if (options?.liveOption) {
    return {
      delivery_type: deliveryType,
      label_ar: labels.ar,
      label_en: labels.en,
      quoted_price: quotedPrice,
      formatted_price: formatPrice(quotedPrice, currency),
      visibility: options?.visibility ?? "available_on_request",
      direct_chat_booking_status: "not_available",
      direct_chat_booking_note:
        "This option is priced in the approved Riders sheet but is not currently available for direct chat booking on the current route.",
    };
  }

  if (options?.specialCapability && quotedPrice != null) {
    return {
      delivery_type: deliveryType,
      label_ar: labels.ar,
      label_en: labels.en,
      quoted_price: quotedPrice,
      formatted_price: formatPrice(quotedPrice, currency),
      visibility: options?.visibility ?? "available_on_request",
      direct_chat_booking_status: options.specialCapability.available_for_direct_chat_booking
        ? "verified"
        : options.specialCapability.unavailable_status,
      direct_chat_booking_note: options.specialCapability.note,
    };
  }

  return {
    delivery_type: deliveryType,
    label_ar: labels.ar,
    label_en: labels.en,
    quoted_price: quotedPrice,
    formatted_price: formatPrice(quotedPrice, currency),
    visibility: options?.visibility ?? "available_on_request",
    direct_chat_booking_status: quotedPrice != null ? "verified" : "unknown",
    direct_chat_booking_note:
      quotedPrice != null
        ? "This option is verified for direct chat booking from the approved pricing sheet."
        : "Live direct chat booking availability for this option was not confirmed yet.",
  };
}

function buildBookableQuoteMapFromGetPricePayload(payload: any): Partial<Record<BookableDeliveryType, number>> {
  const prices: Partial<Record<BookableDeliveryType, number>> = {};
  const maybeAdd = (deliveryType: unknown, quotedPrice: unknown) => {
    if (
      (deliveryType === "sedan_normal" ||
        deliveryType === "sedan_fast" ||
        deliveryType === "van_normal" ||
        deliveryType === "van_fast") &&
      typeof quotedPrice === "number" &&
      Number.isFinite(quotedPrice)
    ) {
      prices[deliveryType] = quotedPrice;
    }
  };

  maybeAdd(payload?.recommended_customer_quote?.delivery_type, payload?.recommended_customer_quote?.quoted_price);
  maybeAdd(
    payload?.recommended_direct_chat_booking_option?.delivery_type,
    payload?.recommended_direct_chat_booking_option?.quoted_price,
  );
  if (Array.isArray(payload?.other_options_if_customer_asks)) {
    for (const option of payload.other_options_if_customer_asks) {
      maybeAdd(option?.delivery_type, option?.quoted_price);
    }
  }
  return prices;
}

function validateCreateSimpleOrderPreflight(params: {
  sender_name: string;
  sender_phone: string;
  recipient_name: string;
  recipient_phone: string;
  pickup_area: string;
  delivery_area: string;
  delivery_type: BookableDeliveryType;
  quoted_price: number;
  pickup_block?: string | null;
  pickup_street?: string | null;
  pickup_house?: string | null;
  pickup_avenue?: string | null;
  pickup_extra?: string | null;
  pickup_notes?: string | null;
  pickup_latitude?: number | null;
  pickup_longitude?: number | null;
  delivery_block?: string | null;
  delivery_street?: string | null;
  delivery_house?: string | null;
  delivery_avenue?: string | null;
  delivery_extra?: string | null;
  delivery_notes?: string | null;
  delivery_latitude?: number | null;
  delivery_longitude?: number | null;
}, options: {
  // `session` is the per-customer guard state owned by tools/guards.ts.
  // We reference it with `any` here because the concrete SessionGuardState
  // interface lives inside createGuardModule() and isn't re-exported; all
  // access in this helper is defensive (optional chaining on dynamic fields).
  session: any | null;
  pickupAreaNameEn: string;
  dropoffAreaNameEn: string;
}) {
  const senderName = params.sender_name.trim();
  const recipientName = params.recipient_name.trim();
  const senderPhone = normalizeLoosePhone(params.sender_phone);
  const recipientPhone = normalizeLoosePhone(params.recipient_phone);

  if (!senderName) {
    throw new Error("Sender name is required before creating the order.");
  }
  if (!recipientName) {
    throw new Error("Recipient name is required before creating the order.");
  }
  if (!senderPhone) {
    throw new Error("Sender phone is required before creating the order.");
  }
  if (!recipientPhone) {
    throw new Error("Recipient phone is required before creating the order.");
  }
  if (looksLikePhoneValue(senderName)) {
    throw new Error("Sender name looks like a phone number. Collect the sender's real name before creating the order.");
  }
  if (looksLikePhoneValue(recipientName)) {
    throw new Error("Recipient name looks like a phone number. Collect the recipient's real name before creating the order.");
  }
  if (normalizeLoosePhone(senderName) === senderPhone) {
    throw new Error("Sender name cannot be the same as the sender phone number. Confirm the sender's real name first.");
  }
  if (normalizeLoosePhone(recipientName) === recipientPhone) {
    throw new Error("Recipient name cannot be the same as the recipient phone number. Confirm the recipient's real name first.");
  }

  const hasPickupEvidence = hasAnyAddressEvidence({
    block: params.pickup_block,
    street: params.pickup_street,
    house: params.pickup_house,
    notes: params.pickup_notes,
    latitude: params.pickup_latitude,
    longitude: params.pickup_longitude,
  });
  const hasDeliveryEvidence = hasAnyAddressEvidence({
    block: params.delivery_block,
    street: params.delivery_street,
    house: params.delivery_house,
    notes: params.delivery_notes,
    latitude: params.delivery_latitude,
    longitude: params.delivery_longitude,
  });
  if (!hasPickupEvidence) {
    throw new Error(
      "Pickup address details are incomplete. Collect block, street, house/building, or a confirmed pickup location pin before creating the order.",
    );
  }
  if (!hasDeliveryEvidence) {
    throw new Error(
      "Delivery address details are incomplete. Collect block, street, house/building, or a confirmed delivery location pin before creating the order.",
    );
  }

  const sessionQuote = options.session?.lastQuotedRoute;
  if (!sessionQuote) {
    throw new Error("No recent verified quote was found in this conversation. Re-run get_price and confirm the route before creating the order.");
  }
  if (Date.now() - sessionQuote.quotedAt > CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS) {
    throw new Error("The latest quote in this conversation is too old. Re-run get_price and confirm the route again before creating the order.");
  }
  const routeKey = buildRouteKey(options.pickupAreaNameEn, options.dropoffAreaNameEn);
  if (!routeKey || sessionQuote.routeKey !== routeKey) {
    throw new Error("This order route does not match the latest quoted route in the conversation. Re-quote the route before creating the order.");
  }
  const quotedPriceForType = sessionQuote.pricesByType[params.delivery_type];
  if (quotedPriceForType == null) {
    throw new Error(`No recent verified quote was found for ${params.delivery_type} in this conversation. Quote that delivery type first before creating the order.`);
  }
  if (!pricesMatch(params.quoted_price, quotedPriceForType)) {
    throw new Error(
      `The provided quoted price does not match the latest verified conversation quote for ${params.delivery_type}. Re-quote before creating the order.`,
    );
  }
}

// ---------------------------------------------------------------------------
// Plugin registration
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Raw-text area pre-resolution helpers (sync — deterministic layers only)
// Used by the before_tool_call gate to catch model area-name misinterpretation.
// ---------------------------------------------------------------------------

const STRIP_AREA_FILLER_RE =
  /^(?:منطقة|ضاحية|مدينة|جزيرة|area|district|block|بلوك)\s+/gi;

function extractAreaTokensFromText(text: string): { pickup: string | null; dropoff: string | null } {
  if (!text || text.length > 300) return { pickup: null, dropoff: null };

  let s = text.trim();

  s = s.replace(/(?:بكم|بچم|كم|شلون|شنو)\s*(?:سعر\s*)?(?:التوصيل|الديليفري|توصيل|delivery)?\s*/gi, " ");
  s = s.replace(/(?:delivery|price|cost|how\s*much)\s*/gi, " ");
  s = s.replace(/[?؟!.,:;]+/g, " ");
  s = s.replace(/\s+/g, " ").trim();
  if (!s) return { pickup: null, dropoff: null };

  const separatorRe =
    /\s+(?:الى|إلى|الي|إلي|لـ|حق|to|->|←|→)\s+|\s+ل(?=\S)|\s+(?:من|from)\s+/i;

  s = s.replace(/^(?:من|from)\s+/i, "");

  const parts = s
    .split(separatorRe)
    .map((p) => p.replace(STRIP_AREA_FILLER_RE, "").trim())
    .filter((p) => p.length >= 2);

  if (parts.length >= 2) {
    return { pickup: parts[0], dropoff: parts[parts.length - 1] };
  }
  if (parts.length === 1 && parts[0].length >= 3) {
    return { pickup: parts[0], dropoff: null };
  }
  return { pickup: null, dropoff: null };
}

// Scan the full customer text for evidence of any area mention by resolving
// every 1–3 word n-gram through the same resolver the LLM uses. Returns the
// set of area IDs that appear anywhere in the message, regardless of
// surrounding filler words, conversational prefixes, or sentence structure.
//
// This is the grounding for the evidence-binding guard: if the LLM claims a
// pickup/dropoff area, and that area ID is in this set, it's verified — no
// regex gymnastics required. Handles typos (slwa → Salwa), Arabic/English
// mixing, and arbitrary prefixes ("Ok lets book ...", "please quote ...",
// "أبي أحجز ...") without needing to enumerate them.
function collectAreaEvidenceFromText(
  text: string,
  data: PricingData,
): Set<number> {
  const evidence = new Set<number>();
  if (!text || typeof text !== "string") return evidence;
  if (text.length > 300) return evidence;
  if (!data?.areas?.length) return evidence;

  const cleaned = text
    .replace(/[?؟!.,:;()"'`“”‘’]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return evidence;

  const words = cleaned.split(/\s+/).filter((w) => w.length >= 2);
  if (!words.length) return evidence;

  // Widest n-gram = widest area name in the catalog, in words, capped at a
  // safety ceiling. Derived from data so we auto-scale if the catalog ever
  // grows longer names (e.g. "Bar Al-Jahra Governorate Extension") — no
  // manual constant to drift out of sync.
  const MAX_NGRAM_CEILING = 6;
  let maxNgram = 1;
  for (const area of data.areas) {
    const enWords = (area.name_en || "").trim().split(/\s+/).filter(Boolean).length;
    const arWords = (area.name_ar || "").trim().split(/\s+/).filter(Boolean).length;
    const widest = Math.max(enWords, arWords);
    if (widest > maxNgram) maxNgram = widest;
  }
  maxNgram = Math.min(maxNgram, MAX_NGRAM_CEILING);

  const tried = new Set<string>();

  const tryResolve = (candidate: string): void => {
    const key = candidate.toLowerCase();
    if (tried.has(key)) return;
    tried.add(key);
    const res = resolveAreaDeterministicSync(candidate, data);
    if (res && res.status === "resolved" && res.area) {
      evidence.add(res.area.id);
    }
  };

  for (let i = 0; i < words.length; i++) {
    for (let n = 1; n <= maxNgram && i + n <= words.length; n++) {
      const gram = words.slice(i, i + n).join(" ");
      if (gram.length < 3) continue;
      tryResolve(gram);
    }
  }

  return evidence;
}

function resolveAreaDeterministicSync(
  query: string,
  data: PricingData,
): PricingAreaResolution | null {
  if (!query || !data?.areas?.length) return null;

  const metadataMatch = resolveAreaViaResolverMetadata(query, data);
  if (metadataMatch) return metadataMatch;

  const deterministicResult = collectDeterministicAreaCandidates(query, data.areas);
  for (const c of deterministicResult.candidates) {
    if (c.source === "exact" || c.source === "canonical" || c.source === "numbered_alias" || c.source === "substring") {
      return { status: "resolved", area: c.area };
    }
  }

  if (deterministicResult.substringPartialMatches.length >= 2) {
    const namesAr = deterministicResult.substringPartialMatches.map((a) => a.name_ar).join(" / ");
    const namesEn = deterministicResult.substringPartialMatches.map((a) => a.name_en).join(" / ");
    return {
      status: "ambiguous",
      ambiguity_group_id: `dynamic:${query}`,
      prompt_ar: `أقصد أي منطقة بالضبط؟ ${namesAr}`,
      prompt_en: `Which area did you mean? ${namesEn}`,
      options: deterministicResult.substringPartialMatches.map((a) => ({
        area_id: a.id,
        name_en: a.name_en,
        name_ar: a.name_ar,
      })),
    };
  }
  if (deterministicResult.substringPartialMatches.length === 1) {
    const sole = deterministicResult.substringPartialMatches[0];
    return {
      status: "suggested",
      area: sole,
      prompt_ar: `هل تقصد "${sole.name_ar}"؟`,
      prompt_en: `Did you mean "${sole.name_en}"?`,
    };
  }

  const nearMatch = findAreaNearTypoMatch(query, data.areas);
  if (nearMatch && !nearMatch.alternative_areas?.length) {
    return { status: "resolved", area: nearMatch.area };
  }

  return null;
}

function isAreaMismatch(
  resolverArea: PricingArea,
  modelAreaString: string,
  data: PricingData,
): boolean {
  if (!modelAreaString) return true;
  const modelResolution = resolveAreaDeterministicSync(modelAreaString, data);
  if (!modelResolution || modelResolution.status !== "resolved") return true;
  return modelResolution.area.id !== resolverArea.id;
}

/**
 * Evidence-binding verification for a single area field (pickup / dropoff).
 *
 * Given the customer's deterministically-extracted raw area token, the LLM's
 * proposed canonical area string, any explicit area_id override, and the
 * pricing data, return a decision:
 *
 *   - { action: "keep" }                  - LLM's claim is consistent with
 *                                           the customer's evidence; proceed.
 *   - { action: "override", value }       - Raw token resolves cleanly and
 *                                           disagrees with (or replaces) the
 *                                           LLM's claim; use raw.
 *   - { action: "reject", reason, ... }   - LLM asserted an area the
 *                                           customer's word cannot justify.
 *                                           Force clarification.
 *
 * The reject branch distinguishes two sub-cases:
 *   - reason="smuggle_suspected" + suggestedAreaId  → the matcher has a
 *     plausible typo-match for the raw token (different from what the LLM
 *     claimed). Caller should surface a suggestion to the customer.
 *   - reason="smuggle_not_found"                    → the matcher has no
 *     plausible match for the raw token. Caller should return area_not_found
 *     and force the customer to restate.
 *
 * Grounded in Waqas et al. (Nov 2025, arXiv:2512.00332) on provenance-aware
 * vulnerabilities in multi-turn tool-calling agents — specifically the
 * agent-sourced assertion case where the LLM silently substitutes a plausible
 * canonical name during argument construction.
 */
type AreaEvidenceDecision =
  | { action: "keep" }
  | { action: "override"; value: string; fromArea: PricingArea; toArea: PricingArea | null }
  | {
      action: "reject";
      reason: "smuggle_suspected" | "smuggle_not_found";
      rawToken: string;
      modelCanonical: string;
      modelArea: PricingArea | null;
      suggestedArea: PricingArea | null;
      suggestedAlternatives: PricingArea[];
      suggestedPromptAr: string | null;
      suggestedPromptEn: string | null;
    }
  | {
      // Graduated-response path. Raw token doesn't resolve deterministically,
      // but the model's claim and the raw token DO have a plausible similarity
      // link via `scoreAreaMatchSimilarity` (at least one of the top
      // candidates for the raw token matches what the model claimed, with
      // similarity above the graduated threshold). Preserves the smuggle
      // defense (we don't silently accept the model's claim) while giving the
      // LLM a path to self-correct on retry (read `closest_candidates`, decide
      // whether to re-call with `pickup_area_id` or confirm with the
      // customer).
      action: "needs_clarification";
      rawToken: string;
      modelCanonical: string;
      modelArea: PricingArea;
      modelSimilarity: number;
      closestCandidates: AreaCandidate[];
      matchConfidence: AreaMatchConfidence;
    };

// Graduated-response feature flag. Default ON: the new path only activates
// when the current code would reject as `smuggle_not_found`, and only when
// there's a plausible similarity link between the raw token and the model's
// claim. Set RIDERS_AREA_GRADUATED_RESPONSE=0 to revert to the strict
// binary reject/pass if any regression shows up in live traffic.
const AREA_GRADUATED_RESPONSE_ENABLED =
  String(process.env.RIDERS_AREA_GRADUATED_RESPONSE ?? "1").trim() !== "0";

// Minimum similarity for a candidate to count as a "plausible link" between
// the customer's raw token and the model's claimed area. Calibrated against
// representative Kuwaiti Arabizi misses (e.g. "om il namel" → 0.667,
// "7wly" → 0.833) while excluding spurious matches ("xxxxx" → 0).
const AREA_GRADUATED_MIN_LINK_SIMILARITY = 0.4;

function verifyAreaEvidence(params: {
  rawToken: string | null;
  modelValue: string;
  idOverride: number | null | undefined;
  data: PricingData;
}): AreaEvidenceDecision {
  const { rawToken, modelValue, idOverride, data } = params;

  if (typeof idOverride === "number") return { action: "keep" };
  if (!rawToken) return { action: "keep" };

  const modelRes = resolveAreaDeterministicSync(modelValue, data);
  const rawRes = resolveAreaDeterministicSync(rawToken, data);
  const modelResolved = modelRes?.status === "resolved" ? modelRes : null;
  const rawResolved = rawRes?.status === "resolved" ? rawRes : null;

  if (rawResolved && modelResolved && rawResolved.area.id === modelResolved.area.id) {
    return { action: "keep" };
  }

  if (rawResolved && modelResolved && rawResolved.area.id !== modelResolved.area.id) {
    return {
      action: "override",
      value: rawResolved.area.name_en,
      fromArea: modelResolved.area,
      toArea: rawResolved.area,
    };
  }

  if (rawResolved && !modelResolved) {
    return {
      action: "override",
      value: rawResolved.area.name_en,
      fromArea: null as unknown as PricingArea,
      toArea: rawResolved.area,
    };
  }

  if (!rawResolved && modelResolved) {
    const typoMatch = findAreaNearTypoMatch(rawToken, data.areas);
    if (typoMatch && typoMatch.area.id === modelResolved.area.id) {
      return { action: "keep" };
    }

    if (AREA_GRADUATED_RESPONSE_ENABLED) {
      // Graduated response: before rejecting as smuggle, check whether the
      // customer's raw token has a plausible similarity link to the model's
      // claimed area. If yes, the model is probably right about an area the
      // deterministic matcher missed (classic obscure-area + Arabizi case).
      // Emit needs_clarification with the top candidates so the LLM can
      // self-correct on the next turn (re-call with pickup_area_id or ask
      // the customer to confirm the top candidate).
      const candidates = collectAreaCandidates(rawToken, data.areas, { topK: 5 });
      const modelSimilarity = scoreAreaMatchSimilarity(rawToken, modelResolved.area.name_en);
      const arSimilarity = scoreAreaMatchSimilarity(rawToken, modelResolved.area.name_ar);
      const bestModelSimilarity = Math.max(modelSimilarity, arSimilarity);
      const topCandidateIsModel =
        candidates.length > 0 && candidates[0].area.id === modelResolved.area.id;
      const modelInCandidates = candidates.some(
        (c) => c.area.id === modelResolved.area.id,
      );

      const plausibleLink =
        bestModelSimilarity >= AREA_GRADUATED_MIN_LINK_SIMILARITY ||
        (topCandidateIsModel && candidates[0].similarity >= AREA_GRADUATED_MIN_LINK_SIMILARITY);

      if (plausibleLink) {
        console.log(
          `[area-evidence] needs_clarification raw="${rawToken}" model="${modelValue}" modelArea="${modelResolved.area.name_en}" modelSim=${bestModelSimilarity.toFixed(3)} topCandidate="${candidates[0]?.area.name_en ?? "-"}" topSim=${candidates[0]?.similarity.toFixed(3) ?? "0"} modelInCandidates=${modelInCandidates}`,
        );
        return {
          action: "needs_clarification",
          rawToken,
          modelCanonical: modelValue,
          modelArea: modelResolved.area,
          modelSimilarity: bestModelSimilarity,
          closestCandidates: candidates,
          matchConfidence: confidenceFromSimilarity(bestModelSimilarity),
        };
      }
      // No plausible link → fall through to strict reject (smuggle defense).
    }

    return {
      action: "reject",
      reason: typoMatch ? "smuggle_suspected" : "smuggle_not_found",
      rawToken,
      modelCanonical: modelValue,
      modelArea: modelResolved.area,
      suggestedArea: typoMatch?.area ?? null,
      suggestedAlternatives: typoMatch?.alternative_areas ?? [],
      suggestedPromptAr: typoMatch?.prompt_ar ?? null,
      suggestedPromptEn: typoMatch?.prompt_en ?? null,
    };
  }

  return { action: "keep" };
}

export const __resolverTestHooks = {
  buildPublishedPricingData,
  normalizePricingResolverConfig,
  resolvePricingAreaQuery,
  resolveGeoAreaMatch,
  extractAreaTokensFromText,
  collectAreaEvidenceFromText,
  resolveAreaDeterministicSync,
  isAreaMismatch,
  verifyAreaEvidence,
  collectAreaCandidates,
  confidenceFromSimilarity,
  scoreAreaMatchSimilarity,
};

export default function register(api: any) {
  applyPluginConfig(api.pluginConfig);

  // Guard module owns session state, the intent-gate helpers, and the
  // before/after_tool_call hook wiring. Build it first so every tool
  // registration gets the same set of closures (sessionState shared).
  const guardModule = createGuardModule({
    buildRouteKey,
    buildBookableQuoteMapFromGetPricePayload,
  });
  const guardHelpers = guardModule.helpers;

  // Shared dependency bundle passed to every extracted tool-registration
  // module (Wave 1a of the plugin split). Only helpers and live getters
  // live here; session state owned by guardModule is not plumbed through
  // deps directly — it flows via the intentGates / recordGuardState
  // closures that guardModule exposes.
  const deps: ToolDeps = {
    createTextResult,
    errorPayload,
    assertAdminAuthorized,
    assertPricingAdminAuthorized,
    isAdminSender,
    isRecord,
    runGogJsonCommand,
    getPricingGoogleSheetSpreadsheetId: () => pricingGoogleSheetSpreadsheetId,
    getPricingGoogleSheetName: () => pricingGoogleSheetName,
    intentGates: {
      isCustomerOctopusContext: guardHelpers.isCustomerOctopusContext,
      getVisibleCustomerText: guardHelpers.getVisibleCustomerText,
      getCustomerTurnActionHint: guardHelpers.getCustomerTurnActionHint,
      getNormalizedBookingAuthority: guardHelpers.getNormalizedBookingAuthority,
      isActiveBookingFlow: guardHelpers.isActiveBookingFlow,
      customerExplicitlyRequestsHuman: guardHelpers.customerExplicitlyRequestsHuman,
      assignAgentReasonLooksLegitimate: guardHelpers.assignAgentReasonLooksLegitimate,
      hasStrictTrackingOrderId: guardHelpers.hasStrictTrackingOrderId,
      hasFreshLastQuotedRoute: guardHelpers.hasFreshLastQuotedRoute,
      getSessionFromCtx: guardHelpers.getSessionFromCtx,
    },
    pricing: {
      getPricingSourceStatus,
      loadPricingBaseDataForStatus,
      inspectPricingResolverOverlay,
      summarizePricingResolver,
      clearPricingCache,
      loadPricing,
      loadPricingFallbackData,
      writePublishedPricing,
      buildPublishedPricingData,
      resolvePublishedAreasInput,
      resolvePublishedColumnsInput,
      resolvePublishedResolverInput,
      resolveSheetRowsInput,
      resolveSheetHeaderMapInput,
      normalizeSheetRowsToPublishedAreas,
      resolveAdminPricingArea,
      normalizePricingNumber,
      isPricingGoogleSheetConfigured,
      executeAdminAddPricingAreaToGoogleSheet,
      executeAdminGoogleSheetPriceUpdate,
    },
    quoting: {
      extractAreaTokensFromText,
      collectAreaEvidenceFromText,
      verifyAreaEvidence,
      createAreaSuggestionResult,
      createAreaNotFoundResult,
      createAreaNeedsClarificationResult,
      createAreaClarificationResult,
      collectAreaCandidates,
      resolvePricingAreaQuery,
      getBidirectionalRoutePrices,
      getSpecialDeliveryCapabilities,
      resolveAreaForOrdering,
      getCommonShippingMethods,
      selectShippingMethod,
      summarizeLiveDeliveryOption,
      parseNumericPrice,
      formatPrice,
      buildServiceCatalogEntry,
      getQuotedPriceForDeliveryType,
    },
    recordGuardState: guardHelpers.recordGuardState,
    booking: {
      resolveToolConversationId,
      resolveToolTurnId,
      asOptionalTrimmedString,
      splitFullName,
      buildAddressPayload,
      pricesMatch,
      getRouteSheetPrice,
      isOrderCreationBlockedByLiveMaintenance,
      buildCreateOrderMaintenanceResult,
      loadRidersGridLiveSettingsSummary,
      assertWriteActionsEnabled,
      assertValidFleetrunnrOrderId,
      fleetrunnrRequest,
      normalizeFleetrunnrTracking,
      ridersRequest,
      ridersFormDataRequest,
      normalizeOrder,
      validateCreateSimpleOrderPreflight,
      getDirectChatBookingBlockReason: guardHelpers.getDirectChatBookingBlockReason,
      buildCanonicalCreateOrderParamsFromController:
        guardHelpers.buildCanonicalCreateOrderParamsFromController,
      buildPendingOrderFingerprint: guardHelpers.buildPendingOrderFingerprint,
      isExplicitSummaryConfirmation: guardHelpers.isExplicitSummaryConfirmation,
      getTrackingProvider: () => trackingProvider,
      getActiveOffers: () => activeOffers,
      isRidersOneBrainEnabled: () => RIDERS_ONE_BRAIN_ENABLED,
      RidersApiError,
    },
    behavior: {
      assertBehaviorAdminAuthorized,
      loadBehaviorPolicy,
      getBehaviorPolicyStatus,
      clearBehaviorPolicyCache,
      writePublishedBehaviorPolicy,
      normalizeAdminSenderId,
      normalizeBehaviorPolicyDocument,
      buildNextBehaviorPolicy,
      resolveBehaviorPolicyInput,
      resolveBehaviorRequiredStepsInput,
      resolveBehaviorLiveInstructionsInput,
      normalizeBehaviorReplyCorrection,
      normalizeBehaviorFlowRule,
      normalizeBehaviorPhraseGuard,
      getNextBehaviorPriority,
      findBehaviorRuleLocation,
    },
  };

  // =========================================================================
  // QUOTE / PRICING TOOLS (get_price)
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/pricing.ts.

  registerPricingTools(api, deps);
  // =========================================================================
  // BOOKING / ORDER TOOLS
  //   track_order, create_simple_order, create_order, pay_order, cancel_order,
  //   shadow_extract_booking_fields, apply_booking_field, start_booking,
  //   confirm_summary, cancel_booking, request_handoff, offers
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/booking.ts.

  registerBookingTools(api, deps);

  // =========================================================================
  // PRICING ADMIN TOOLS
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/admin-pricing.ts. Registers all
  // eight admin_pricing_* / admin_*_area_price tools in one shot; the
  // original source spanned this block and a second block after the
  // behavior-admin registration.

  registerAdminPricingTools(api, deps);

  // =========================================================================
  // BEHAVIOR POLICY ADMIN TOOLS
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/admin-behavior.ts.

  registerAdminBehaviorTools(api, deps);

  // (admin_publish_pricing_snapshot, admin_publish_pricing_sheet_rows,
  //  admin_add_pricing_area_to_google_sheet,
  //  admin_update_area_price_in_google_sheet, admin_update_area_price are
  //  registered by registerAdminPricingTools() above.)
  // =========================================================================
  // Generic gog-backed Google Sheets admin tools
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/admin-sheets.ts.

  registerAdminSheetsTools(api, deps);

  // =========================================================================
  // CUSTOMER SUPPORT TOOLS (complains, assign_agent)
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/support.ts.

  registerCustomerSupportTools(api, deps);

  // =========================================================================
  // ADMIN WORKSPACE FILE MANAGEMENT TOOLS
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/admin-workspace.ts.

  registerAdminWorkspaceTools(api, deps);

  // =========================================================================
  // GUARD HOOKS + SESSION STATE (before/after_tool_call, globalThis bridge, GC)
  // =========================================================================
  // Extracted to plugins/riders-tools/tools/guards.ts. Must run AFTER all
  // tool registrations so before_tool_call fires after the tools exist, but
  // the `guardHelpers` reference used by `deps` above is the same module
  // instance (sessionState shared).

  guardModule.registerHooks(api);
}
