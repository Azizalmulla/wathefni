// ---------------------------------------------------------------------------
// Wave 1b extraction: riders-tools shared types.
// Extracted from the original `plugins/riders-tools/index.ts` lines 71-285 and
// 567-611 (pure type/interface declarations, no runtime behavior).
// ---------------------------------------------------------------------------

export interface PricingArea {
  id: number;
  governorate: string;
  name_en: string;
  name_ar: string;
  sedan_normal: number | null;
  sedan_fast: number | null;
  cooled_van_normal: number | null;
  cooled_van_fast: number | null;
  van_normal: number | null;
  van_fast: number | null;
  helper_standard: number | null;
  geo?: PricingGeoAreaHint;
}

export interface PricingGeoAreaHint {
  governorate?: string;
  area_name_ar?: string;
  area_name_en?: string;
  objectid?: string;
}

export interface PricingResolverAliasEntry {
  alias: string;
  area_id?: number;
  pricing_group_id?: string;
  ambiguity_group_id?: string;
}

export interface PricingResolverPricingGroup {
  id: string;
  name_ar?: string;
  name_en?: string;
  area_ids: number[];
  aliases?: string[];
  geo?: PricingGeoAreaHint;
}

export interface PricingResolverAmbiguityGroup {
  id: string;
  prompt_ar: string;
  prompt_en: string;
  aliases?: string[];
  options?: { area_id: number; name_en: string; name_ar: string }[];
}

export interface PricingResolverConfig {
  aliases?: PricingResolverAliasEntry[];
  pricing_groups?: PricingResolverPricingGroup[];
  ambiguity_groups?: PricingResolverAmbiguityGroup[];
}

export interface PricingData {
  currency: string;
  last_updated: string;
  columns: Record<string, string>;
  areas: PricingArea[];
  resolver?: PricingResolverConfig;
}

export interface PricingResolverSummary {
  aliases_count: number;
  pricing_group_count: number;
  ambiguity_group_count: number;
  alias_preview: string[];
  pricing_group_ids: string[];
  ambiguity_group_ids: string[];
}

export interface PricingResolverOverlayStatus {
  configured: boolean;
  path: string | null;
  exists: boolean;
  state: "disabled" | "missing" | "invalid" | "active";
  source_shape: "resolver_wrapper" | "resolver_fields" | null;
  error: string | null;
  aliases_count: number;
  pricing_group_count: number;
  ambiguity_group_count: number;
  merged_aliases_count: number | null;
  merged_pricing_group_count: number | null;
  merged_ambiguity_group_count: number | null;
  alias_preview: string[];
  pricing_group_ids: string[];
  ambiguity_group_ids: string[];
}

export interface GeoGovernorate {
  id: number;
  name: string;
  lat: string | null;
  lng: string | null;
}

export interface GeoShippingMethod {
  id: number;
  name: string;
  type: string | null;
  default_price?: string | number | null;
  price?: number | null;
}

export interface GeoArea {
  id: number;
  objectid: string | null;
  name: string;
  lat: string | null;
  lng: string | null;
  governorate_id: number;
  governorate_name: string;
  shipping_methods: GeoShippingMethod[];
}

export type RidersApiPayload = {
  success?: boolean;
  message?: string;
  data?: any;
};

export type BookableDeliveryType =
  | "sedan_normal"
  | "sedan_fast"
  | "van_normal"
  | "van_fast";

export type PricingSourceMode =
  | "google_sheet_live"
  | "published_preferred"
  | "static_only";

export type TrackingProvider = "riders" | "fleetrunnr";

export type QuoteableDeliveryType =
  | BookableDeliveryType
  | "cooled_van_normal"
  | "cooled_van_fast"
  | "helper_standard";

export type SpecialQuoteableDeliveryType = Exclude<
  QuoteableDeliveryType,
  BookableDeliveryType
>;

export interface LiveDeliveryOptionSummary {
  delivery_type: BookableDeliveryType;
  label_ar: string;
  label_en: string;
  available_for_direct_chat_booking: boolean;
  shipping_method: {
    id: number;
    name: string;
    type: string | null;
    default_price: string | number | null;
    formatted_price: string | null;
  } | null;
}

export interface SpecialDeliveryCapabilitySummary {
  delivery_type: SpecialQuoteableDeliveryType;
  available_for_direct_chat_booking: boolean;
  unavailable_status: "manual_confirmation_required" | "not_available";
  note: string;
  backend_feature_enabled: boolean | null;
}

export interface RidersGridLiveSettingsSummary {
  freezer_enabled: boolean | null;
  assistant_enabled: boolean | null;
  site_order_mode: boolean | null;
  site_maintenance_mode: boolean | null;
  maintenance_mode: boolean | null;
  maintenance_message: string | null;
}

export interface ServiceCatalogEntry {
  delivery_type: QuoteableDeliveryType;
  label_ar: string;
  label_en: string;
  quoted_price: number | null;
  formatted_price: string;
  visibility: "default" | "available_on_request";
  direct_chat_booking_status:
    | "verified"
    | "not_available"
    | "manual_confirmation_required"
    | "unknown";
  direct_chat_booking_note: string;
}

export interface RidersToolsPluginConfig {
  pricing?: {
    sourceMode?: PricingSourceMode;
    publishedPath?: string;
    /** Merges resolver metadata from this JSON file over the loaded pricing snapshot (env: RIDERS_PRICING_RESOLVER_OVERLAY_PATH). */
    resolverOverlayPath?: string;
    adminAllowlist?: string[];
    googleSheet?: {
      spreadsheetId?: string;
      sheetName?: string;
      headerRow?: number;
      autoSync?: {
        enabled?: boolean;
        minIntervalMs?: number;
      };
    };
  };
  behavior?: {
    publishedPath?: string;
    adminAllowlist?: string[];
  };
  embedding?: {
    voyageApiKey?: string;
    model?: string;
    similarityThreshold?: number;
  };
}

export type PricingAreaFieldKey = Exclude<keyof PricingArea, "geo">;

export type BehaviorLanguageScope = "any" | "arabic" | "english";
export type BehaviorPhraseGuardKind = "blocked" | "required";

export interface BehaviorReplyCorrection {
  id: string;
  title: string;
  situation: string;
  preferred_reply: string;
  wrong_reply: string | null;
  guidance: string | null;
  language_scope: BehaviorLanguageScope;
  priority: number;
  enabled: boolean;
}

export interface BehaviorFlowRule {
  id: string;
  title: string;
  situation: string;
  required_steps: string[];
  guidance: string | null;
  priority: number;
  enabled: boolean;
}

export interface BehaviorPhraseGuard {
  id: string;
  kind: BehaviorPhraseGuardKind;
  phrase: string;
  applies_when: string | null;
  guidance: string | null;
  priority: number;
  enabled: boolean;
}

export interface BehaviorPolicy {
  version: number;
  last_updated: string;
  updated_by: string | null;
  summary: string;
  live_instructions: string[];
  reply_corrections: BehaviorReplyCorrection[];
  flow_rules: BehaviorFlowRule[];
  phrase_guards: BehaviorPhraseGuard[];
}
