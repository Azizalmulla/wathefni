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
  const matches = options
    .map((option) => ({ option, score: scoreQuotedOptionMatch(normalizedText, option) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score);
  if (matches.length > 0) {
    return {
      kind: "switch_option",
      option: matches[0].option,
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
