// ---------------------------------------------------------------------------
// Wave 4 extraction: pure quoted-route option helpers.
// Reading, matching, scoring, selecting, and rendering options from an active
// `StoredQuotedRoute`. All helpers here are pure; they either derive a value
// from inputs or return a new `PersistedConversationControllerEntry` without
// touching module-scoped state. Extracted from
// `plugins/octopus-channel/index.ts`.
// ---------------------------------------------------------------------------

import type { PersistedConversationControllerEntry } from "../../shared/conversation-policy";
import {
  extractTrackingOrderId,
  hasActiveQuotedBookingAuthority,
  hasRouteEvidence,
  isBookingStartIntent,
  isGeneralServiceInquiry,
  isPassengerTransportRequest,
  isSimpleGreeting,
  normalizeIntentText,
} from "../../shared/conversation-policy";

export type RouteQuoteOption = {
  delivery_type: string;
  label_ar: string;
  label_en: string;
  quoted_price: number | null;
  formatted_price: string | null;
  visibility: string | null;
  direct_chat_booking_status: string | null;
  direct_chat_booking_note: string | null;
};

export type StoredQuotedRoute = {
  routeKey: string;
  pickupAreaNameAr: string;
  pickupAreaNameEn: string;
  dropoffAreaNameAr: string;
  dropoffAreaNameEn: string;
  pricesByType: Record<string, number>;
  optionCatalog: RouteQuoteOption[];
  serviceDiscovery?: {
    default_prompt_ar?: string | null;
    default_prompt_en?: string | null;
  } | null;
};

export type SameRouteQuoteFollowupAction =
  | { kind: "switch_option"; option: RouteQuoteOption }
  | { kind: "confirm_selected_option"; option: RouteQuoteOption }
  | { kind: "show_other_options" }
  | null;

export const BOOKABLE_QUOTED_OPTION_TYPES = new Set([
  "sedan_normal",
  "sedan_fast",
  "van_normal",
  "van_fast",
  "cooled_van_normal",
  "cooled_van_fast",
  "helper_standard",
]);

export const DELIVERY_TYPE_ALIASES: Record<string, string[]> = {
  sedan_normal: ["standard", "normal", "regular", "عادي", "عادية", "العادي", "ستاندرد"],
  sedan_fast: ["express", "fast", "urgent", "سريع", "السريع", "مستعجل", "اكسبرس"],
  van_normal: ["box", "van", "box van", "بوكس", "البوكس"],
  van_fast: ["box express", "express box", "fast box", "van express", "بوكس سريع", "البوكس السريع"],
  cooled_van_normal: ["refrigerated", "cooled", "cold", "مبرد", "المبرد"],
  cooled_van_fast: ["refrigerated express", "cooled express", "cold express", "مبرد سريع", "المبرد السريع"],
  helper_standard: ["helper", "assistant", "مساعد", "مع مساعد"],
};

// ---------------------------------------------------------------------------
// Class + tier classification (Bug 3, 2026-04-20 option-match drift incident).
//
// Problem being modelled: loose substring scoring on `DELIVERY_TYPE_ALIASES`
// accepts a tier-only hit ("express") as a full option match even when a
// class discriminator in the same utterance ("ref" for refrigerated) is
// unknown to the alias table. Example incident: `"express ref van"` scored
// `sedan_fast = 7` and `cooled_van_fast = 0`, so the matcher picked Express
// sedan instead of Express refrigerated van.
//
// The fix decomposes each option's identity into:
//   - class: sedan / van / cooled_van / helper
//   - tier : normal / fast (single-tier classes get "standard" as the tier)
//
// The new `matchQuotedOptionDiscriminated` helper is the architectural
// replacement for raw `scoreQuotedOptionMatch` at the controller commit
// point. It requires a class token in the text before committing a match,
// so tier-only utterances ("express", "fast") fall through to the
// clarify-before-proceed gate instead of silently defaulting.
// ---------------------------------------------------------------------------

export type QuotedOptionClass = "sedan" | "van" | "cooled_van" | "helper";
export type QuotedOptionTier = "normal" | "fast" | "standard";

export type QuotedOptionClassification = {
  class: QuotedOptionClass;
  tier: QuotedOptionTier;
};

const DELIVERY_TYPE_CLASSIFICATION: Record<string, QuotedOptionClassification> = {
  sedan_normal: { class: "sedan", tier: "normal" },
  sedan_fast: { class: "sedan", tier: "fast" },
  van_normal: { class: "van", tier: "normal" },
  van_fast: { class: "van", tier: "fast" },
  cooled_van_normal: { class: "cooled_van", tier: "normal" },
  cooled_van_fast: { class: "cooled_van", tier: "fast" },
  helper_standard: { class: "helper", tier: "standard" },
};

/**
 * Tier tokens — markers that identify the "normal vs fast" dimension of
 * an option. Normalized to lowercase for English entries; Arabic entries
 * are matched against the raw text (Arabic normalization is identity).
 *
 * These tokens are ORTHOGONAL to class tokens below. A reply like "express"
 * alone identifies a tier but not a class, so the matcher must refuse to
 * auto-select and fall through to the clarify gate.
 */
export const OPTION_TIER_TOKENS: Record<QuotedOptionTier, string[]> = {
  normal: [
    "standard",
    "normal",
    "regular",
    "std",
    "reg",
    "عادي",
    "عادية",
    "العادي",
    "ستاندرد",
  ],
  fast: [
    "express",
    "fast",
    "urgent",
    "quick",
    "rapid",
    "rush",
    "asap",
    "سريع",
    "السريع",
    "مستعجل",
    "اكسبرس",
    "اكسبريس",
  ],
  standard: [],
};

/**
 * Class tokens — markers that identify the vehicle/service class dimension.
 *
 * `cooled_van` intentionally includes the common abbreviations `ref` and
 * `refrig` so that `"express ref van"` resolves class=cooled_van + tier=fast.
 * Without these abbreviations the matcher cannot distinguish a refrigerated
 * van from a plain van in the canonical customer phrasing the 2026-04-20
 * incident surfaced.
 *
 * `van` is intentionally excluded from `cooled_van` tokens — a bare "van"
 * is ambiguous between `van_*` and `cooled_van_*`, and the matcher
 * (see `matchQuotedOptionDiscriminated`) uses `"van"` only as a neutral
 * class hint which requires additional disambiguating evidence.
 */
export const OPTION_CLASS_TOKENS: Record<QuotedOptionClass, string[]> = {
  sedan: ["sedan", "car", "سيدان", "سيارة", "سياره"],
  van: ["box", "box van", "بوكس", "البوكس"],
  cooled_van: [
    "refrigerated",
    "refrig",
    "ref van",
    "ref",
    "cooled",
    "cold",
    "chilled",
    "مبرد",
    "المبرد",
    "مبرده",
    "مبردة",
  ],
  helper: ["helper", "assistant", "مساعد", "مع مساعد"],
};

/**
 * Public accessor: returns the `{ class, tier }` classification for a
 * known delivery type, or `null` for an unknown id. Lets other modules
 * (tests, future guards) reuse the same mapping without reaching into
 * the constant table directly.
 */
export function getOptionClassification(
  deliveryType: string | null | undefined,
): QuotedOptionClassification | null {
  const normalized = String(deliveryType || "").trim().toLowerCase();
  if (!normalized) return null;
  return DELIVERY_TYPE_CLASSIFICATION[normalized] || null;
}

function hasTokenHit(normalizedText: string, token: string): boolean {
  if (!token) return false;
  if (normalizedText === token) return true;
  // Prefer whole-word matches for short Latin tokens so that "box"
  // doesn't leak into unrelated substrings (e.g. "boxing"). Arabic
  // tokens are matched via substring because `normalizeIntentText`
  // leaves Arabic characters untouched and Arabic word boundaries are
  // well-preserved by our surrounding whitespace check.
  const isLatin = /^[a-z]+( [a-z]+)*$/i.test(token);
  if (isLatin) {
    const re = new RegExp(`(^|[^a-z0-9])${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z0-9]|$)`, "i");
    return re.test(normalizedText);
  }
  return normalizedText.includes(token);
}

/**
 * Collect the set of classes and tiers that appear in the normalized
 * input text. Order of token iteration is longest-first per dimension so
 * that, e.g., "ref van" wins over the shorter "ref" inside the
 * `cooled_van` class list (irrelevant for correctness but keeps the
 * matched-token telemetry intuitive when we log it).
 */
function detectOptionDimensionsInText(normalizedText: string): {
  classes: Set<QuotedOptionClass>;
  tiers: Set<QuotedOptionTier>;
} {
  const classes = new Set<QuotedOptionClass>();
  const tiers = new Set<QuotedOptionTier>();
  if (!normalizedText) return { classes, tiers };
  for (const [cls, tokens] of Object.entries(OPTION_CLASS_TOKENS) as [
    QuotedOptionClass,
    string[],
  ][]) {
    const sorted = [...tokens].sort((a, b) => b.length - a.length);
    for (const tok of sorted) {
      if (hasTokenHit(normalizedText, tok)) {
        classes.add(cls);
        break;
      }
    }
  }
  for (const [tier, tokens] of Object.entries(OPTION_TIER_TOKENS) as [
    QuotedOptionTier,
    string[],
  ][]) {
    if (tier === "standard") continue;
    const sorted = [...tokens].sort((a, b) => b.length - a.length);
    for (const tok of sorted) {
      if (hasTokenHit(normalizedText, tok)) {
        tiers.add(tier);
        break;
      }
    }
  }
  return { classes, tiers };
}

/**
 * Outcome of the class+tier discriminated matcher.
 *
 *   - `match`       : unique option identified, safe to commit
 *   - `ambiguous`   : multiple options consistent with the input (e.g.
 *                     "express van" without "cooled"/"ref") — caller must
 *                     fall through to the clarify-before-proceed gate
 *   - `underspecified`: tier alone, or empty signal — caller falls through
 *   - `none`        : no class/tier token detected at all
 */
export type QuotedOptionMatchResult =
  | { kind: "match"; option: RouteQuoteOption; reason: "full_label" | "class_and_tier" | "class_only_unique" }
  | { kind: "ambiguous"; candidates: RouteQuoteOption[] }
  | { kind: "underspecified"; hasTier: boolean; hasClass: boolean }
  | { kind: "none" };

/**
 * Discriminated class+tier matcher. Replaces raw `scoreQuotedOptionMatch`
 * at the controller commit point (`resolveSameRouteQuoteFollowupAction`)
 * and the LLM-side clarify-gate explicit-mention check
 * (`detectExplicitOptionMention`).
 *
 * Decision ladder (first match wins):
 *   1. Full-label substring hit — the customer typed one of the option's
 *      English or Arabic labels verbatim. This is always unambiguous
 *      because labels are unique per option catalog.
 *   2. Exactly one priced option satisfies both `class` and `tier`
 *      detected in the text → commit.
 *   3. No tier token in the text, but exactly one priced option matches
 *      the detected class (e.g. bare "helper") → commit. Single-tier
 *      classes like `helper_standard` win here even though the catalog
 *      may include a manual-confirm flavor.
 *   4. Multiple options consistent with the detected dimensions →
 *      ambiguous; caller falls through to the clarify gate.
 *   5. Tier-only or empty signal → underspecified.
 */
export function matchQuotedOptionDiscriminated(params: {
  normalizedText: string;
  options: RouteQuoteOption[];
}): QuotedOptionMatchResult {
  const { normalizedText, options } = params;
  if (!normalizedText || options.length === 0) {
    return { kind: "none" };
  }
  const priced = options.filter((o) => o.quoted_price != null);
  if (priced.length === 0) {
    return { kind: "none" };
  }

  // Tier 1: full-label substring hit. Iterate by longest label first so
  // "Express refrigerated van" beats "Express sedan" when the customer
  // types the long label in a longer utterance.
  const labelMatches: { option: RouteQuoteOption; length: number }[] = [];
  for (const option of priced) {
    const labels = [
      normalizeIntentText(option.label_en || ""),
      normalizeIntentText(option.label_ar || ""),
    ].filter(Boolean);
    let longest = 0;
    for (const lbl of labels) {
      if (lbl && normalizedText.includes(lbl) && lbl.length > longest) {
        longest = lbl.length;
      }
    }
    if (longest > 0) {
      labelMatches.push({ option, length: longest });
    }
  }
  if (labelMatches.length > 0) {
    labelMatches.sort((a, b) => b.length - a.length);
    // A label hit is authoritative even against other label hits: the
    // longest label wins (e.g. "Express refrigerated van" contains
    // "Express sedan"? no — guaranteed disjoint; but the sort is defensive).
    return { kind: "match", option: labelMatches[0].option, reason: "full_label" };
  }

  const { classes, tiers } = detectOptionDimensionsInText(normalizedText);

  if (classes.size === 0 && tiers.size === 0) {
    return { kind: "none" };
  }

  // Tier 2/3/4: class-driven disambiguation.
  if (classes.size > 0) {
    const candidatesByClass = priced.filter((opt) => {
      const cls = getOptionClassification(opt.delivery_type);
      return cls != null && classes.has(cls.class);
    });
    if (candidatesByClass.length === 0) {
      return { kind: "underspecified", hasTier: tiers.size > 0, hasClass: false };
    }

    if (tiers.size > 0) {
      const narrowed = candidatesByClass.filter((opt) => {
        const cls = getOptionClassification(opt.delivery_type);
        return cls != null && tiers.has(cls.tier);
      });
      if (narrowed.length === 1) {
        return { kind: "match", option: narrowed[0], reason: "class_and_tier" };
      }
      if (narrowed.length > 1) {
        return { kind: "ambiguous", candidates: narrowed };
      }
      // narrowed.length === 0 — tier is asserted but no candidate in the
      // class list has that tier (e.g. "express helper" when only
      // helper_standard exists). Fall back to class-only narrowing.
    }

    if (candidatesByClass.length === 1) {
      return { kind: "match", option: candidatesByClass[0], reason: "class_only_unique" };
    }
    return { kind: "ambiguous", candidates: candidatesByClass };
  }

  // Tier 5: tier-only signal with no class — always underspecified.
  return { kind: "underspecified", hasTier: tiers.size > 0, hasClass: false };
}

// ---------------------------------------------------------------------------
// LLM-side structured option interpretation (Phase 1, 2026-04-20).
//
// The LLM emits this via the `propose_option_interpretation` responder op
// (see `plugins/shared/responder-state-ops.ts`). It is the Layer 2
// proposal. The orchestrator feeds it into `resolveOptionFromProposals`
// alongside the Layer 1 deterministic raw-text outcome and commits /
// clarifies based on a reconciliation ladder.
//
// Only the shape we consume here is typed; the wire format may carry
// additional fields (`qualifiers`, `turn_id`, `op`) that this resolver
// ignores.
// ---------------------------------------------------------------------------

export type LlmOptionInterpretation = {
  class: QuotedOptionClass | null;
  tier: QuotedOptionTier | null;
  source_quote: string;
  confidence: "high" | "low";
};

/**
 * Reconciled outcome of combining the deterministic raw-text match with
 * the LLM's structured interpretation. The discriminated source field
 * tells the caller *why* a particular option was chosen (or rejected),
 * which is what makes per-turn attribution metrics possible in Phase 5.
 *
 *   - `commit_fast_path`        : only the deterministic matcher resolved;
 *                                 LLM proposal absent / low-confidence / null.
 *   - `commit_llm`              : only the LLM proposal resolved uniquely;
 *                                 deterministic matcher was underspecified /
 *                                 ambiguous. LLM "disambiguated" the text.
 *   - `commit_both_agree`       : both resolved to the same option — safest
 *                                 possible commit path.
 *   - `clarify_disagreement`    : both resolved to DIFFERENT unique options;
 *                                 the system deliberately commits nothing
 *                                 this turn and hands off to the clarify
 *                                 gate. This is the architectural tripwire
 *                                 that catches drift between the two
 *                                 proposer layers.
 *   - `clarify_ambiguous`       : at least one side returned `ambiguous`
 *                                 (multiple candidates) with no unique
 *                                 winner; clarify gate takes over.
 *   - `none`                    : no useful signal from either proposer.
 */
export type ReconciledOptionOutcome =
  | { kind: "commit"; option: RouteQuoteOption; source: "commit_fast_path" | "commit_llm" | "commit_both_agree" }
  | {
      kind: "clarify";
      source: "clarify_disagreement" | "clarify_ambiguous";
      fastPathCandidate?: RouteQuoteOption | null;
      llmCandidate?: RouteQuoteOption | null;
      candidates?: RouteQuoteOption[];
    }
  | { kind: "none" };

/**
 * Resolve the LLM's structured interpretation against the catalog alone
 * — no regex over raw text, no alias tables. This is the "single source
 * of truth" property Phase 1 delivers: the LLM proposes class+tier, the
 * server looks up the catalog, and that's it. Low-confidence proposals
 * return `{ kind: "none" }` — they are never committed solo, only used
 * as a tiebreaker / observability signal.
 */
export function matchLlmOptionInterpretation(params: {
  interpretation: LlmOptionInterpretation | null;
  options: RouteQuoteOption[];
}): QuotedOptionMatchResult {
  const { interpretation, options } = params;
  if (!interpretation) return { kind: "none" };
  if (interpretation.confidence !== "high") return { kind: "none" };
  const priced = options.filter((o) => o.quoted_price != null);
  if (priced.length === 0) return { kind: "none" };

  const { class: llmClass, tier: llmTier } = interpretation;
  if (llmClass === null && llmTier === null) return { kind: "none" };

  if (llmClass === null) {
    // Tier-only LLM proposal — mirrors raw-text underspecified outcome.
    // Refuse to auto-commit; clarify takes over.
    return { kind: "underspecified", hasTier: true, hasClass: false };
  }

  const candidatesByClass = priced.filter((opt) => {
    const cls = getOptionClassification(opt.delivery_type);
    return cls != null && cls.class === llmClass;
  });
  if (candidatesByClass.length === 0) {
    return { kind: "underspecified", hasTier: llmTier != null, hasClass: false };
  }

  if (llmTier !== null) {
    const narrowed = candidatesByClass.filter((opt) => {
      const cls = getOptionClassification(opt.delivery_type);
      return cls != null && cls.tier === llmTier;
    });
    if (narrowed.length === 1) {
      return { kind: "match", option: narrowed[0], reason: "class_and_tier" };
    }
    if (narrowed.length > 1) {
      return { kind: "ambiguous", candidates: narrowed };
    }
    // tier absent on every catalog entry for this class — defensive
    // fallthrough to class-only.
  }
  if (candidatesByClass.length === 1) {
    return { kind: "match", option: candidatesByClass[0], reason: "class_only_unique" };
  }
  return { kind: "ambiguous", candidates: candidatesByClass };
}

/**
 * Phase 1 reconciliation. Combines the Layer 1 (deterministic raw-text)
 * and Layer 2 (LLM structured) outcomes into a single commit-or-clarify
 * decision. This is the single chokepoint the orchestrator calls from
 * both the pre-dispatch commit path and the post-drain reconciliation
 * path — so the rules are in one place and the attribution is uniform.
 *
 * Reconciliation ladder (first row wins):
 *
 *   fastPath | llm        | outcome
 *   -------- | ---------- | ------------------------------------------
 *   match A  | match A    | commit A, source=commit_both_agree
 *   match A  | match B    | clarify, source=clarify_disagreement
 *   match A  | none       | commit A, source=commit_fast_path
 *   match A  | underspec. | commit A, source=commit_fast_path
 *   match A  | ambiguous  | clarify, source=clarify_ambiguous (ambiguous LLM
 *                           is a contradiction signal — do NOT commit A
 *                           just because the regex landed)
 *   ambig.   | match B    | commit B, source=commit_llm (LLM disambiguated)
 *   underspec| match B    | commit B, source=commit_llm
 *   none     | match B    | commit B, source=commit_llm
 *   ambig.   | ambig.     | clarify, source=clarify_ambiguous
 *   any else | any else   | { kind: "none" }
 *
 * The "match A + ambiguous LLM" row is intentionally conservative: if
 * the LLM thinks the utterance could be more than one option, the
 * deterministic matcher's commit is suspect — it probably landed on a
 * tier-plus-class hit while the customer was genuinely ambiguous. Let
 * clarify adjudicate.
 */
export function resolveOptionFromProposals(params: {
  rawTextOutcome: QuotedOptionMatchResult;
  llmOutcome: QuotedOptionMatchResult;
}): ReconciledOptionOutcome {
  const { rawTextOutcome, llmOutcome } = params;

  const fastMatch =
    rawTextOutcome.kind === "match" ? rawTextOutcome.option : null;
  const llmMatch = llmOutcome.kind === "match" ? llmOutcome.option : null;

  if (fastMatch && llmMatch) {
    if (fastMatch.delivery_type === llmMatch.delivery_type) {
      return { kind: "commit", option: fastMatch, source: "commit_both_agree" };
    }
    return {
      kind: "clarify",
      source: "clarify_disagreement",
      fastPathCandidate: fastMatch,
      llmCandidate: llmMatch,
    };
  }

  if (fastMatch && llmOutcome.kind === "ambiguous") {
    return {
      kind: "clarify",
      source: "clarify_ambiguous",
      fastPathCandidate: fastMatch,
      candidates: llmOutcome.candidates,
    };
  }

  if (fastMatch) {
    return { kind: "commit", option: fastMatch, source: "commit_fast_path" };
  }

  if (llmMatch) {
    return { kind: "commit", option: llmMatch, source: "commit_llm" };
  }

  if (rawTextOutcome.kind === "ambiguous" || llmOutcome.kind === "ambiguous") {
    const candidates = [
      ...(rawTextOutcome.kind === "ambiguous" ? rawTextOutcome.candidates : []),
      ...(llmOutcome.kind === "ambiguous" ? llmOutcome.candidates : []),
    ];
    return { kind: "clarify", source: "clarify_ambiguous", candidates };
  }

  return { kind: "none" };
}

export const SAME_ROUTE_OTHER_OPTIONS_MARKERS = [
  "other options",
  "other option",
  "anything else",
  "what else",
  "what other options",
  "any other options",
  "is that the only car",
  "is that the only vehicle",
  "is that the only option",
  "thats the only car",
  "that's the only car",
  "thats the only vehicle",
  "that's the only vehicle",
  "only car",
  "only vehicle",
  "only option",
  "وشنو غيره",
  "وشنو غيرها",
  "شنو غيره",
  "شنو غيرها",
  "غيره",
  "غيرها",
];

export const SAME_ROUTE_CONFIRM_CURRENT_MARKERS = [
  "only",
  "only standard",
  "just this",
  "thats it",
  "that's it",
  "بس",
  "فقط",
  "بس بس",
];

export function isBookableQuotedOptionType(deliveryType: string | null | undefined): boolean {
  return BOOKABLE_QUOTED_OPTION_TYPES.has(String(deliveryType || "").trim().toLowerCase());
}

export function getQuotedRouteDefaultOption(
  route: StoredQuotedRoute | null | undefined,
): RouteQuoteOption | null {
  if (!route) {
    return null;
  }
  const options = route.optionCatalog.filter((entry) => entry.quoted_price != null);
  return (
    route.optionCatalog.find((entry) => entry.delivery_type === "sedan_normal" && entry.quoted_price != null) ||
    options[0] ||
    null
  );
}

export function getQuotedRouteOption(
  route: StoredQuotedRoute | null | undefined,
  deliveryType: string | null | undefined,
): RouteQuoteOption | null {
  const normalizedDeliveryType = String(deliveryType || "").trim().toLowerCase();
  if (!route || !normalizedDeliveryType) {
    return null;
  }
  return route.optionCatalog.find((entry) => entry.delivery_type === normalizedDeliveryType) || null;
}

export function getActiveSelectedQuotedOption(
  route: StoredQuotedRoute | null | undefined,
  controllerEntry: PersistedConversationControllerEntry | null | undefined,
): RouteQuoteOption | null {
  return (
    getQuotedRouteOption(route, controllerEntry?.selectedQuoteOptionType) ||
    getQuotedRouteOption(route, controllerEntry?.selectedDeliveryType) ||
    getQuotedRouteDefaultOption(route)
  );
}

export function formatQuotedOptionLabel(
  option: RouteQuoteOption | null | undefined,
  language: "ar" | "en",
): string {
  if (!option) {
    return language === "ar" ? "الخيار الحالي" : "current option";
  }
  if (language === "ar") {
    return option.label_ar || option.label_en || option.delivery_type;
  }
  return option.label_en || option.label_ar || option.delivery_type;
}

export function formatQuotedOptionPrice(option: RouteQuoteOption | null | undefined): string {
  if (!option) {
    return "-";
  }
  if (option.formatted_price) {
    return option.formatted_price;
  }
  if (typeof option.quoted_price === "number" && Number.isFinite(option.quoted_price)) {
    return `${option.quoted_price.toFixed(3)} KWD`;
  }
  return "-";
}

export function applySelectedQuotedOptionToController(
  controllerEntry: PersistedConversationControllerEntry,
  option: RouteQuoteOption | null,
): PersistedConversationControllerEntry {
  if (!option) {
    return {
      ...controllerEntry,
      selectedQuoteOptionType: null,
      selectedQuoteOptionLabelAr: null,
      selectedQuoteOptionLabelEn: null,
      selectedQuoteOptionPrice: null,
      selectedQuoteOptionDirectChatBookingStatus: null,
      selectedDeliveryType: null,
      quotedPrice: null,
    };
  }
  const selectedQuoteOptionPrice =
    typeof option.quoted_price === "number" && Number.isFinite(option.quoted_price)
      ? option.quoted_price
      : null;
  const nextEntry: PersistedConversationControllerEntry = {
    ...controllerEntry,
    selectedQuoteOptionType: option.delivery_type,
    selectedQuoteOptionLabelAr: option.label_ar || null,
    selectedQuoteOptionLabelEn: option.label_en || null,
    selectedQuoteOptionPrice,
    selectedQuoteOptionDirectChatBookingStatus: option.direct_chat_booking_status || null,
  };
  if (isBookableQuotedOptionType(option.delivery_type) && selectedQuoteOptionPrice != null) {
    nextEntry.selectedDeliveryType = option.delivery_type;
    nextEntry.quotedPrice = selectedQuoteOptionPrice;
  } else {
    nextEntry.selectedDeliveryType = null;
    nextEntry.quotedPrice = null;
  }
  return nextEntry;
}

export function syncControllerSelectionFromQuotedRoute(
  controllerEntry: PersistedConversationControllerEntry | null,
  route: StoredQuotedRoute | null | undefined,
): { entry: PersistedConversationControllerEntry | null; changed: boolean } {
  if (!controllerEntry || !route) {
    return { entry: controllerEntry, changed: false };
  }
  const selectedOption = getActiveSelectedQuotedOption(route, controllerEntry);
  if (!selectedOption) {
    return { entry: controllerEntry, changed: false };
  }
  const nextEntry = applySelectedQuotedOptionToController(controllerEntry, selectedOption);
  const changed =
    nextEntry.selectedQuoteOptionType !== controllerEntry.selectedQuoteOptionType ||
    nextEntry.selectedQuoteOptionPrice !== controllerEntry.selectedQuoteOptionPrice ||
    nextEntry.selectedQuoteOptionLabelAr !== controllerEntry.selectedQuoteOptionLabelAr ||
    nextEntry.selectedQuoteOptionLabelEn !== controllerEntry.selectedQuoteOptionLabelEn ||
    nextEntry.selectedQuoteOptionDirectChatBookingStatus !==
      controllerEntry.selectedQuoteOptionDirectChatBookingStatus ||
    nextEntry.selectedDeliveryType !== controllerEntry.selectedDeliveryType ||
    nextEntry.quotedPrice !== controllerEntry.quotedPrice;
  return {
    entry: changed ? nextEntry : controllerEntry,
    changed,
  };
}

export function buildQuotedOptionAliases(option: RouteQuoteOption): string[] {
  const aliases = new Set((DELIVERY_TYPE_ALIASES[option.delivery_type] || []).map((value) => normalizeIntentText(value)));
  const normalizedLabelEn = normalizeIntentText(option.label_en || "");
  const normalizedLabelAr = normalizeIntentText(option.label_ar || "");
  if (normalizedLabelEn) {
    aliases.add(normalizedLabelEn);
  }
  if (normalizedLabelAr) {
    aliases.add(normalizedLabelAr);
  }
  return [...aliases].filter(Boolean).sort((a, b) => b.length - a.length);
}

export function scoreQuotedOptionMatch(normalizedText: string, option: RouteQuoteOption): number {
  let score = 0;
  for (const alias of buildQuotedOptionAliases(option)) {
    if (!alias) {
      continue;
    }
    if (normalizedText === alias) {
      score = Math.max(score, alias.length + 100);
      continue;
    }
    if (normalizedText.includes(alias)) {
      score = Math.max(score, alias.length);
    }
  }
  return score;
}

/**
 * Detect the "cancel + option in same utterance" misclassification.
 *
 * Background (Bug 2, 2026-04-20 incident):
 *   Customer: "nvm pls standard sedan"
 *   LLM:      emits `cancel_booking` with source_quote="nvm pls standard sedan"
 *   Server:   applies the cancel, replies "we've cancelled the booking"
 *   Customer: lost the quote because they actually wanted to switch
 *             from an earlier selection back to `sedan_normal`.
 *
 * The tell is local and deterministic: the customer's own source quote
 * names one of the currently quoted options, which contradicts a
 * cancellation. Cancel reads like "nvm", "cancel", "never mind", etc.,
 * but when the same utterance also contains a known option alias
 * ("standard sedan", "express box", "سريع", "مساعد", …) it is an
 * option switch, not a cancellation.
 *
 * Returns `{ contradicted: true, optionLabel }` when an option mention
 * is detected. `optionLabel` is the customer-facing English label of
 * the matched option (falls back to the delivery_type id), used by the
 * reply guard to render a disambiguating substitute.
 *
 * Runs deterministically — no LLM, no scoring heuristic beyond the
 * existing alias map used everywhere else for option matching. The
 * threshold is "any positive match score" because these aliases are
 * already tuned for exact / substring hits.
 */
export function detectCancelContradictsOptionMention(params: {
  sourceQuote: string | null | undefined;
  route: StoredQuotedRoute | null | undefined;
}): { contradicted: boolean; optionLabel: string | null; optionType: string | null } {
  const quote = (params.sourceQuote || "").trim();
  const route = params.route || null;
  if (!quote || !route || !Array.isArray(route.optionCatalog) || route.optionCatalog.length === 0) {
    return { contradicted: false, optionLabel: null, optionType: null };
  }
  const normalized = normalizeIntentText(quote);
  if (!normalized) {
    return { contradicted: false, optionLabel: null, optionType: null };
  }
  let best: { score: number; option: RouteQuoteOption | null } = { score: 0, option: null };
  for (const opt of route.optionCatalog) {
    if (opt.quoted_price == null) continue;
    const score = scoreQuotedOptionMatch(normalized, opt);
    if (score > best.score) {
      best = { score, option: opt };
    }
  }
  if (best.score <= 0 || !best.option) {
    return { contradicted: false, optionLabel: null, optionType: null };
  }
  const label = best.option.label_en || best.option.label_ar || best.option.delivery_type;
  return { contradicted: true, optionLabel: label, optionType: best.option.delivery_type };
}

/**
 * Vague "proceed" signal detector (Bug 1, 2026-04-20 manual-confirm incident).
 *
 * Matches generic go-ahead markers ("proceed", "go ahead", "let's do it",
 * "book it", "yes please", "اكمل", "نعم", "تمام", …) that DO NOT name a
 * specific option. When the active route has a mix of bookable and
 * manual-confirm options, a vague proceed is ambiguous — the customer could
 * mean the currently-selected option OR the one the bot just mentioned
 * (e.g. "Helper service, 3.250 KWD"). The caller is expected to pair this
 * with `detectExplicitOptionMention` to decide whether clarification is
 * needed.
 *
 * Returns false as soon as an option alias is found inside the text so this
 * helper alone can answer "vague AND no explicit option named". Kept
 * deterministic (no LLM, no scoring tricks) and aligned with the marker
 * lists used elsewhere in the quoted-options module.
 */
const VAGUE_PROCEED_MARKERS_EN = [
  "go ahead",
  "go ahead with it",
  "go ahead with that",
  "go ahead with this",
  "let us do it",
  "let's do it",
  "lets do it",
  "let us go",
  "let's go",
  "lets go",
  "book it",
  "book this",
  "book that",
  "proceed",
  "proceed with it",
  "proceed with that",
  "proceed with this",
  "continue",
  "yes please",
  "yes",
  "yep",
  "yeah",
  "ok",
  "okay",
  "sure",
  "fine",
  "confirm",
  "can we go ahead",
  "can we proceed",
  "can we go",
  "shall we proceed",
  "shall we go ahead",
  "do it",
  "let us book",
  "let's book",
  "lets book",
];

const VAGUE_PROCEED_MARKERS_AR = [
  "اكمل",
  "أكمل",
  "اطلب",
  "اطلبه",
  "اطلبها",
  "نعم",
  "ايوه",
  "ايوا",
  "أيوه",
  "ايه",
  "تمام",
  "اوكي",
  "اوك",
  "ماشي",
  "موافق",
  "موافقه",
  "موافقة",
  "زين",
  "طيب",
  "يلا",
  "يلا نكمل",
  "خلاص",
  "تفضل",
  "كمل",
  "خذ",
  "خذها",
  "خذه",
];

export function detectVagueProceedSignal(text: string | null | undefined): boolean {
  const raw = (text || "").trim();
  if (!raw) return false;
  if (raw.length > 120) return false;
  const normalized = normalizeIntentText(raw);
  if (!normalized) return false;
  for (const marker of VAGUE_PROCEED_MARKERS_EN) {
    if (normalized === marker) return true;
    if (normalized.includes(marker)) return true;
  }
  for (const marker of VAGUE_PROCEED_MARKERS_AR) {
    if (raw === marker) return true;
    if (raw.includes(marker)) return true;
  }
  return false;
}

/**
 * Positive option-mention detector. Pure positive half of
 * `detectCancelContradictsOptionMention`: returns the matched option when
 * the customer's text names a known option by any of its aliases or
 * labels, otherwise null. Used by the clarify-before-proceed gate to
 * decide whether a "proceed" signal is unambiguous.
 */
export function detectExplicitOptionMention(params: {
  text: string | null | undefined;
  route: StoredQuotedRoute | null | undefined;
}): RouteQuoteOption | null {
  const text = (params.text || "").trim();
  const route = params.route || null;
  if (!text || !route || !Array.isArray(route.optionCatalog) || route.optionCatalog.length === 0) {
    return null;
  }
  const normalized = normalizeIntentText(text);
  if (!normalized) return null;
  // Bug 3 (2026-04-20 option-match drift): use the class+tier discriminated
  // matcher so tier-only signals ("express", "fast") and abbreviated inputs
  // ("express ref van") return null/ambiguous, which keeps the clarify-
  // before-proceed gate in charge. The legacy `scoreQuotedOptionMatch` ladder
  // above is preserved for callers that still need a purely permissive hit.
  const outcome = matchQuotedOptionDiscriminated({
    normalizedText: normalized,
    options: route.optionCatalog,
  });
  if (outcome.kind === "match") {
    return outcome.option;
  }
  return null;
}

/**
 * True when the active route has at least one option flagged as
 * `manual_confirmation_required` in its option catalog AND at least one
 * OTHER option (manual-confirm or otherwise) with a quoted price. Single-
 * option catalogs are by definition unambiguous on a vague "proceed".
 */
export function routeHasManualConfirmOption(route: StoredQuotedRoute | null | undefined): boolean {
  if (!route || !Array.isArray(route.optionCatalog)) return false;
  const priced = route.optionCatalog.filter((o) => o.quoted_price != null);
  if (priced.length < 2) return false;
  return priced.some(
    (o) => String(o.direct_chat_booking_status || "").trim().toLowerCase() === "manual_confirmation_required",
  );
}

/**
 * Deterministic clarify-before-proceed reply builder. Used as the
 * server-composed substitute when the customer sends a vague proceed
 * signal on a route that contains a manual-confirm option. Lists the
 * priced options with their labels + prices and asks the customer to
 * name one explicitly. Flags manual-confirm options in-line so the
 * customer knows which require a human handoff.
 *
 * Kept short (one question, bullet list) so it composes cleanly with the
 * same-route-quote-options reply and doesn't re-state the route header
 * the customer already saw.
 */
export function buildDeterministicClarifyOptionBeforeProceedReply(params: {
  language: "ar" | "en";
  route: StoredQuotedRoute;
}): string {
  const priced = params.route.optionCatalog.filter((o) => o.quoted_price != null);
  if (params.language === "ar") {
    const header = "أي خيار تفضل نكمل فيه؟";
    const bullets = priced.map((option) => {
      const label = formatQuotedOptionLabel(option, "ar");
      const price = formatQuotedOptionPrice(option);
      const status = String(option.direct_chat_booking_status || "").toLowerCase();
      const suffix = status === "manual_confirmation_required" ? " (يحتاج تأكيد يدوي)" : "";
      return `- ${label}: ${price}${suffix}`;
    });
    return [header, ...bullets].join("\n");
  }
  const header = "Which option would you like to go ahead with?";
  const bullets = priced.map((option) => {
    const label = formatQuotedOptionLabel(option, "en");
    const price = formatQuotedOptionPrice(option);
    const status = String(option.direct_chat_booking_status || "").toLowerCase();
    const suffix = status === "manual_confirmation_required" ? " (needs manual confirmation)" : "";
    return `- ${label}: ${price}${suffix}`;
  });
  return [header, ...bullets].join("\n");
}

export function resolveSameRouteQuoteFollowupAction(params: {
  visibleText: string;
  controllerEntry: PersistedConversationControllerEntry | null;
  route: StoredQuotedRoute | null | undefined;
}): SameRouteQuoteFollowupAction {
  const normalizedText = normalizeIntentText(params.visibleText);
  if (
    !normalizedText ||
    !params.route ||
    !params.controllerEntry ||
    params.controllerEntry.stage !== "quoted" ||
    !hasActiveQuotedBookingAuthority(params.controllerEntry) ||
    hasRouteEvidence(normalizedText) ||
    extractTrackingOrderId(normalizedText) ||
    isBookingStartIntent(normalizedText) ||
    isSimpleGreeting(normalizedText) ||
    isPassengerTransportRequest(normalizedText) ||
    isGeneralServiceInquiry(normalizedText)
  ) {
    return null;
  }
  if (
    SAME_ROUTE_OTHER_OPTIONS_MARKERS.some((marker) => normalizedText === marker || normalizedText.includes(marker))
  ) {
    return { kind: "show_other_options" };
  }
  const options = params.route.optionCatalog.filter((entry) => entry.quoted_price != null);
  // Bug 3 (2026-04-20 option-match drift): commit a `switch_option` only
  // when the class+tier discriminated matcher returns a unique match.
  // Underspecified / ambiguous inputs are handed off to the clarify gate
  // so the controller never auto-commits to the wrong option (historic
  // failure mode: "express ref van" → sedan_fast via tier-only hit). The
  // legacy scoring ladder is intentionally NOT consulted as a fallback;
  // if the discriminated matcher cannot resolve uniqueness, we want the
  // clarify-before-proceed directive to engage instead of a second-best
  // guess.
  const outcome = matchQuotedOptionDiscriminated({
    normalizedText,
    options,
  });
  if (outcome.kind === "match") {
    return {
      kind: "switch_option",
      option: outcome.option,
    };
  }
  const currentOption = getActiveSelectedQuotedOption(params.route, params.controllerEntry);
  if (
    currentOption &&
    SAME_ROUTE_CONFIRM_CURRENT_MARKERS.some((marker) => normalizedText === marker || normalizedText.includes(marker))
  ) {
    return {
      kind: "confirm_selected_option",
      option: currentOption,
    };
  }
  return null;
}

export function buildDeterministicSelectedQuotedOptionReply(params: {
  language: "ar" | "en";
  route: StoredQuotedRoute;
  option: RouteQuoteOption;
}): string {
  const pickupArea = params.language === "ar" ? params.route.pickupAreaNameAr : params.route.pickupAreaNameEn;
  const dropoffArea = params.language === "ar" ? params.route.dropoffAreaNameAr : params.route.dropoffAreaNameEn;
  const label = formatQuotedOptionLabel(params.option, params.language);
  const price = formatQuotedOptionPrice(params.option);
  if (params.language === "ar") {
    const lines = [
      `التوصيل من ${pickupArea} إلى ${dropoffArea} السعر: ${price} (${label})`,
    ];
    if (params.option.direct_chat_booking_status === "manual_confirmation_required") {
      lines.push("هذا الخيار يحتاج تأكيد يدوي قبل الحجز المباشر.");
    } else if (params.option.direct_chat_booking_status === "not_available") {
      lines.push("هذا الخيار غير متاح حالياً للحجز المباشر في المحادثة.");
    }
    return lines.join("\n");
  }
  const lines = [
    `Delivery from ${pickupArea} to ${dropoffArea} price: ${price} (${label})`,
  ];
  if (params.option.direct_chat_booking_status === "manual_confirmation_required") {
    lines.push("This option needs manual confirmation before direct chat booking.");
  } else if (params.option.direct_chat_booking_status === "not_available") {
    lines.push("This option is not currently available for direct chat booking.");
  }
  return lines.join("\n");
}

/**
 * Manual-confirm address-ask reply (Bug 4, 2026-04-20 manual-confirm
 * signal drop incident).
 *
 * When the customer has explicitly selected a `manual_confirmation_required`
 * option on a quoted route, the server must compose the address-collection
 * prompt directly so the "needs manual confirmation by our team" signal is
 * never dropped from the outbound text. Previously the LLM generated this
 * reply free-hand — the hard prompt rule held in some turns but drifted in
 * others, making the flow indistinguishable from a direct-booking address
 * ask. This builder makes the signal deterministic.
 *
 * The `side` parameter controls which address the reply requests next:
 *   - `"pickup"`   → used when only `delivery.address` is present
 *   - `"delivery"` → used when only `pickup.address` is present
 *
 * When BOTH addresses are missing we ask for pickup first (matches the
 * existing controller ordering). When BOTH addresses are already present
 * the caller switches to the handoff builder instead.
 */
export function buildDeterministicManualConfirmAddressAskReply(params: {
  language: "ar" | "en";
  route: StoredQuotedRoute;
  option: RouteQuoteOption;
  side: "pickup" | "delivery";
}): string {
  const label = formatQuotedOptionLabel(params.option, params.language);
  const price = formatQuotedOptionPrice(params.option);
  if (params.language === "ar") {
    const recap = `${label} ${price}. هذا الخيار يحتاج تأكيد يدوي من فريقنا قبل تثبيت الحجز.`;
    const ask =
      params.side === "pickup"
        ? "ممكن ترسل لنا عنوان الاستلام (المنطقة، القطعة، الشارع، والمبنى/الشقة)؟"
        : "ممكن ترسل لنا عنوان التوصيل (المنطقة، القطعة، الشارع، والمبنى/الشقة)؟";
    return `${recap}\n${ask}`;
  }
  const recap = `${label} is ${price}. This option needs manual confirmation by our team before we can confirm the booking.`;
  const ask =
    params.side === "pickup"
      ? "Could you share the pickup address (area, block, street, and building/apartment)?"
      : "Could you share the delivery address (area, block, street, and building/apartment)?";
  return `${recap}\n${ask}`;
}

/**
 * Manual-confirm handoff reply (Bug 4 companion builder).
 *
 * When the customer has selected a `manual_confirmation_required` option
 * AND both pickup + delivery addresses are already collected, the server
 * emits this deterministic handoff message. The accompanying
 * `REQUEST_HANDOFF_FOR_MANUAL_CONFIRM` directive tells the LLM to also
 * emit a `request_handoff` op; this builder guarantees the customer-
 * facing text is consistent regardless of the op pipeline.
 */
export function buildDeterministicManualConfirmHandoffReply(params: {
  language: "ar" | "en";
  route: StoredQuotedRoute;
  option: RouteQuoteOption;
}): string {
  const label = formatQuotedOptionLabel(params.option, params.language);
  const price = formatQuotedOptionPrice(params.option);
  if (params.language === "ar") {
    return [
      `${label} ${price}.`,
      "هذا الخيار يحتاج تأكيد يدوي من فريقنا. استلمنا العناوين، وراح يتواصل معك أحد الموظفين لتأكيد الحجز.",
    ].join("\n");
  }
  return [
    `${label} is ${price}.`,
    "This option needs manual confirmation by our team. We have your addresses — one of our agents will reach out shortly to confirm the booking.",
  ].join("\n");
}

export function buildQuotedRouteContextLines(
  route: StoredQuotedRoute | null | undefined,
  controllerEntry: PersistedConversationControllerEntry | null | undefined,
): string[] {
  if (!route) return [];
  const options = route.optionCatalog.filter((entry) => entry.quoted_price != null);
  const defaultOption = getQuotedRouteDefaultOption(route);
  const selectedOption = getActiveSelectedQuotedOption(route, controllerEntry);
  const lines = [
    `active_quoted_route_pickup_en: ${route.pickupAreaNameEn}`,
    `active_quoted_route_dropoff_en: ${route.dropoffAreaNameEn}`,
  ];
  if (defaultOption) {
    lines.push(
      `active_quoted_default_option: ${defaultOption.delivery_type} | ${defaultOption.label_en} | label_ar=${defaultOption.label_ar} | ${defaultOption.formatted_price ?? `${defaultOption.quoted_price?.toFixed(3)} KWD`} | bookable=${defaultOption.direct_chat_booking_status || "-"}`,
    );
  }
  if (selectedOption) {
    lines.push(
      `active_selected_quoted_option: ${selectedOption.delivery_type} | ${selectedOption.label_en} | label_ar=${selectedOption.label_ar} | ${formatQuotedOptionPrice(selectedOption)} | bookable=${selectedOption.direct_chat_booking_status || "-"}`,
    );
    lines.push(
      `active_selected_quoted_option_direct_chat_booking_status: ${selectedOption.direct_chat_booking_status || "-"}`,
    );
  }
  if (options.length > 0) {
    lines.push("active_quoted_options:");
    for (const option of options) {
      lines.push(
        `- ${option.delivery_type} | ${option.label_en} | label_ar=${option.label_ar} | ${option.formatted_price ?? `${option.quoted_price?.toFixed(3)} KWD`} | bookable=${option.direct_chat_booking_status || "-"}`,
      );
    }
  }
  lines.push(
    "Quote-state rule: If the customer is still asking about this same active quoted route and did not change pickup/dropoff, answer from these quoted options instead of calling get_price again.",
  );
  lines.push(
    "Quote-state rule: Treat active_selected_quoted_option as the current selected option for this turn unless the customer clearly asks for a different quoted option.",
  );
  lines.push(
    "Quote-state rule: If active_selected_quoted_option_direct_chat_booking_status is manual_confirmation_required or not_available, do not start direct chat booking for that option. Explain that manual confirmation or human follow-up is required instead.",
  );
  lines.push(
    "Quote-state rule: Only call get_price again if the customer changed the route or there is no active quoted route context.",
  );
  // Answering rule (added 2026-04-18 after incident where the LLM, in
  // quoted state, replied with only the stored route+price and failed to
  // address the customer's actual question — e.g. customer asked \"is this
  // the cheapest?\" and got back only \"Delivery from X to Y, Price: 2.500
  // KWD\"). The preceding rules tell the LLM what NOT to do (don't
  // re-call get_price, don't switch options unprompted, etc.) but were
  // silent on how to construct the reply, which the model interpreted as
  // \"just restate the quote\". This rule closes that gap: answer the
  // customer's question directly, then reference the quoted option if
  // helpful — never the other way around.
  lines.push(
    "Quote-state rule: \"Answer from these quoted options\" means use them as GROUNDING for a natural reply to the customer's actual question — it does NOT mean re-emit the route+price as the entire reply. Always address what the customer asked (e.g. \"is this the cheapest?\", \"what else do you have?\", \"how long does it take?\") in a direct, conversational sentence first, and only then reference the relevant option or price from the stored quote if it helps. Never reply with only the route and price when the customer asked a question.",
  );
  return lines;
}

export function buildDeterministicOtherQuotedOptionsReply(params: {
  language: "ar" | "en";
  route: StoredQuotedRoute;
  controllerEntry: PersistedConversationControllerEntry | null;
}): string | null {
  const selectedOptionType =
    params.controllerEntry?.selectedQuoteOptionType || params.controllerEntry?.selectedDeliveryType || null;
  const alternatives = params.route.optionCatalog.filter(
    (option) => option.quoted_price != null && option.delivery_type !== selectedOptionType,
  );
  if (alternatives.length === 0) {
    return null;
  }
  const preview = alternatives.slice(0, 4);
  if (params.language === "ar") {
    return [
      "الخيارات الثانية لنفس المشوار:",
      ...preview.map((option) => `- ${formatQuotedOptionLabel(option, "ar")}: ${formatQuotedOptionPrice(option)}`),
    ].join("\n");
  }
  return [
    "Other options for the same route:",
    ...preview.map((option) => `- ${formatQuotedOptionLabel(option, "en")}: ${formatQuotedOptionPrice(option)}`),
  ].join("\n");
}
