import type { DialogState } from "./dialog-state.js";

export type ConversationFlowStage =
  | "idle"
  | "quoted"
  | "collecting_booking_details"
  | "summary_shown"
  | "awaiting_confirmation"
  | "order_submitted";

export type BookingCollectionStep =
  | "none"
  | "sender"
  | "recipient"
  | "pickup_address"
  | "delivery_address"
  | "summary_pending"
  | "awaiting_summary_confirmation";

export type PersistedBookingLocation = {
  source: "location_pin" | "map_link";
  latitude: number;
  longitude: number;
  name: string | null;
  address: string | null;
  resolvedAreaName: string | null;
};

export type PersistedBookingDraft = {
  senderName: string | null;
  senderPhone: string | null;
  senderPhoneRejected?: boolean;
  recipientName: string | null;
  recipientPhone: string | null;
  pickupBlock: string | null;
  pickupStreet: string | null;
  pickupHouse: string | null;
  // Kuwait address extensions. `pickupAvenue` is a first-class field because
  // many Kuwait areas use "جادة / jadda / jedda / avenue" as a distinct road
  // designation (NOT a street). `pickupExtra` is a free-form human-readable
  // string for floor, apartment, office, landmark, or any useful address note
  // the customer volunteers ("Floor 3, Apt 12, next to the mosque").
  pickupAvenue: string | null;
  pickupExtra: string | null;
  pickupLocation: PersistedBookingLocation | null;
  deliveryBlock: string | null;
  deliveryStreet: string | null;
  deliveryHouse: string | null;
  deliveryAvenue: string | null;
  deliveryExtra: string | null;
  deliveryLocation: PersistedBookingLocation | null;
  pendingLocation: PersistedBookingLocation | null;
};

export type CustomerIntent =
  | "greeting"
  | "service_inquiry"
  | "route_service_inquiry"
  | "passenger_transport_request"
  | "pricing_request"
  | "booking_followup"
  | "language_switch"
  | "tracking"
  | "general_support";

export type PersistedConversationControllerEntry = {
  lastActivityTs: number;
  language: "ar" | "en";
  explicitLanguage: "ar" | "en" | null;
  stage: ConversationFlowStage;
  bookingStep: BookingCollectionStep;
  conversationId: string;
  replyTarget: string;
  accountId: string;
  quoteRouteKey: string | null;
  quoteTs: number | null;
  quotePickupAreaNameEn: string | null;
  quotePickupAreaNameAr: string | null;
  quoteDropoffAreaNameEn: string | null;
  quoteDropoffAreaNameAr: string | null;
  // Pending (in-progress) area resolutions. Populated by get_price as soon as
  // an area resolves deterministically, BEFORE a full quote is produced.
  // Used to preserve mid-conversation progress when one leg resolved but the
  // other is still ambiguous — so a follow-up turn answering the ambiguity
  // doesn't accidentally trigger a smuggle-guard false-positive on the leg
  // that was already settled. Cleared when the quote is produced (promoted
  // to `quote*`), when the area is replaced with a different value, or when
  // the order is submitted / cancelled.
  //
  // Optional for backwards compat with pre-existing persisted entries; code
  // that reads these MUST treat undefined and null identically.
  pendingPickupAreaNameEn?: string | null;
  pendingPickupAreaNameAr?: string | null;
  pendingDropoffAreaNameEn?: string | null;
  pendingDropoffAreaNameAr?: string | null;
  selectedQuoteOptionType: string | null;
  selectedQuoteOptionLabelAr: string | null;
  selectedQuoteOptionLabelEn: string | null;
  selectedQuoteOptionPrice: number | null;
  selectedQuoteOptionDirectChatBookingStatus: string | null;
  selectedDeliveryType: string | null;
  quotedPrice: number | null;
  bookingDraft: PersistedBookingDraft;
  pendingReplyText?: string | null;
  quotePresentedToCustomer?: boolean;
  // Set when stage transitions to "order_submitted" so the post-order
  // correction flow can reference the order the customer just placed.
  // Cleared whenever stage moves away from "order_submitted".
  submittedOrderUid?: string | null;
  // Dialog State Tracking layer — typed slot register with requested_slot and
  // conflict detection. Optional for backwards compat with pre-DST persisted
  // entries; the controller seeds an empty state on first read.
  dialogState?: DialogState;
};

export function createEmptyBookingDraft(): PersistedBookingDraft {
  return {
    senderName: null,
    senderPhone: null,
    recipientName: null,
    recipientPhone: null,
    pickupBlock: null,
    pickupStreet: null,
    pickupHouse: null,
    pickupAvenue: null,
    pickupExtra: null,
    pickupLocation: null,
    deliveryBlock: null,
    deliveryStreet: null,
    deliveryHouse: null,
    deliveryAvenue: null,
    deliveryExtra: null,
    deliveryLocation: null,
    pendingLocation: null,
  };
}

// ---------------------------------------------------------------------------
// Effective pickup / delivery area resolution.
//
// A single area slot can be populated by three different upstream
// signals, in descending order of authority:
//
//   (1) `entry.quote*AreaNameEn` — the area inside an active `get_price`
//       quote. Highest authority; invariant with the current price.
//
//   (2) `entry.pending*AreaNameEn` — an area that resolved
//       deterministically (typed area name, area-alias match, or pin
//       assignment) but has not yet been priced via `get_price`.
//
//   (3) `draft.pickupLocation.resolvedAreaName` /
//       `draft.deliveryLocation.resolvedAreaName` — the nearest-area
//       name that the pin resolver produced when the customer shared
//       a WhatsApp location pin and explicitly bound it to pickup or
//       delivery.
//
// Historically only (1) satisfied the "pickup.area" / "delivery.area"
// slot, so the 2026-04-19 pin flow produced the bug where the customer
// pinned a location (resolver said "Mirqab"), the agent asked role
// ("pickup"), the controller moved the pin into `pickupLocation` with
// `resolvedAreaName = "Mirqab"` — but the LLM still saw
// `missing_fields: [pickup.area ...]` because `quotePickupAreaNameEn`
// was null. The LLM honestly asked "Which pickup area is it from?",
// even though Mirqab was sitting right there in the pin.
//
// Centralizing the fallback here means three call sites agree:
//   - `applyPendingLocationRoleSelection` lifts (3) → (2) on assignment.
//   - `computeOneBrainMissingFields` reads the effective area to decide
//     whether "pickup.area" / "delivery.area" belongs in the missing
//     list.
//   - The LLM context-block surface formats the effective area (not
//     just the quote field) so the draft line reads
//     `pickup: { area: "Mirqab", ..., pin: "Mirqab" }`.
//
// The quote → pending → pin priority is preserved in both getters so
// a later `get_price` promoting pending → quote still wins, and a
// subsequent customer correction (typing a different area) flows
// through the normal apply-boundary path.
// ---------------------------------------------------------------------------

export function getEffectivePickupAreaName(
  draft: PersistedBookingDraft | null | undefined,
  entry: PersistedConversationControllerEntry | null | undefined,
): string | null {
  const quoted = entry?.quotePickupAreaNameEn;
  if (typeof quoted === "string" && quoted.trim()) return quoted.trim();
  const pending = entry?.pendingPickupAreaNameEn;
  if (typeof pending === "string" && pending.trim()) return pending.trim();
  const pin = draft?.pickupLocation?.resolvedAreaName;
  if (typeof pin === "string" && pin.trim()) return pin.trim();
  return null;
}

export function getEffectiveDeliveryAreaName(
  draft: PersistedBookingDraft | null | undefined,
  entry: PersistedConversationControllerEntry | null | undefined,
): string | null {
  const quoted = entry?.quoteDropoffAreaNameEn;
  if (typeof quoted === "string" && quoted.trim()) return quoted.trim();
  const pending = entry?.pendingDropoffAreaNameEn;
  if (typeof pending === "string" && pending.trim()) return pending.trim();
  const pin = draft?.deliveryLocation?.resolvedAreaName;
  if (typeof pin === "string" && pin.trim()) return pin.trim();
  return null;
}

const ARABIC_CHAR_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;
export const CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS = 30 * 60_000;

export function normalizeIntentText(text: string | null): string {
  return (text || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s']/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function detectConversationLanguage(text: string | null): "ar" | "en" {
  if (!text) return "en";
  const chars = text.replace(/\s/g, "");
  if (!chars) return "en";
  let arabicCount = 0;
  for (const ch of chars) {
    if (ARABIC_CHAR_RE.test(ch)) arabicCount++;
  }
  return arabicCount / chars.length > 0.3 ? "ar" : "en";
}

export function detectExplicitLanguageRequest(text: string | null): "ar" | "en" | null {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return null;
  }
  const englishMarkers = [
    "english",
    "english pl",
    "english please",
    "speak english",
    "in english",
    "reply in english",
  ];
  if (englishMarkers.includes(normalized)) {
    return "en";
  }
  const arabicMarkers = [
    "arabic",
    "arabic pl",
    "arabic please",
    "speak arabic",
    "in arabic",
    "reply in arabic",
    "عربي",
    "بالعربي",
    "بالعربية",
    "تكلم عربي",
    "رد بالعربي",
    "رد بالعربية",
  ];
  if (arabicMarkers.includes(normalized)) {
    return "ar";
  }
  return null;
}

export function hasVisibleArabic(text: string | null): boolean {
  return ARABIC_CHAR_RE.test(text || "");
}

export function hasVisibleLatin(text: string | null): boolean {
  return /[A-Za-z]/.test(text || "");
}

/**
 * Customer's script/register mode for this turn. Orthogonal to the binary
 * `ar | en` language used by the deterministic canonicals — the LLM reads
 * this mode to decide whether to reply in Arabic script, Arabizi (Latin
 * letters with digit-for-letter substitutions), or English. Used as a
 * hidden signal in the one-brain system context; never exposed to the
 * customer directly.
 */
export type CustomerScriptMode = "english" | "arabic" | "arabizi";

// Kuwaiti Arabizi signal words. When a latin-only input contains any of
// these tokens (whole-word match) we tag the turn as Arabizi mode so the
// LLM mirrors script and register back to the customer. Keep this list
// narrow and highly specific to avoid false positives on English:
// – Digit-for-letter words (`3laikm`, `7awalli`, `9bya`, `5aldya`, …).
// – Common Kuwaiti Arabic words that are frequently romanised without
//   digits (`shlon`, `shlonk`, `shlonkm`, `abshr`, `hala`, `hala wallah`,
//   `yallah`, `inshallah`, `mashallah`, `akeed`, `zain`, `7adi`, …).
const ARABIZI_DIGIT_TOKEN_RE = /(?:^|\s|[.,!?;:()"'\u2014\u2013-])[A-Za-z]*[23567][A-Za-z0-9]*(?=$|[\s.,!?;:()"'\u2014\u2013-])/;
const ARABIZI_WORD_TOKENS = [
  "shlon", "shlonk", "shlonkm", "shlonich", "shlonich",
  "hala", "halla", "halla walla", "hala wallah", "shakhbark", "shakhbarkm",
  "slam", "slamm", "salam",
  "abshr", "abshur", "abshir",
  "yallah", "yalla",
  "inshallah", "inshalla", "isa", "insha allah",
  "mashallah", "masha allah",
  "akeed", "akid",
  "zain", "zein",
  "walla", "wallah", "walah",
  "mskeen", "meskeen",
  "5osh", "khosh",
  "shino", "shnoo", "shnu", "shino hay",
  "laish", "laysh", "lesh",
  "wain", "ween", "feen",
  "kaifik", "kaifak", "keefak", "keefik",
  "habibi", "habibti",
  "3ad",
  "agool", "agul",
  "abi", "abghi", "abgha",
  "6ayeb", "tayeb",
  "ma3a", "m3a", "ma3ak", "ma3ach",
  "mub", "mo",
  "bas", "bass",
  "3leik", "3leich", "3laikm", "3alaikum",
  "wa3laikm", "w3laikm",
  "bkm", "bkm il", "kam",
  "tws6eel", "tws3eel", "toseel", "tawseel",
  "msklah", "mashkla", "mushkila",
  "wayed", "wajed", "wayd",
  "trawani", "treed", "tabi",
];

function isProbablyArabizi(text: string): boolean {
  if (!text) return false;
  const hasArabic = hasVisibleArabic(text);
  const hasLatin = hasVisibleLatin(text);
  // Arabizi only applies when the customer is typing in Latin script.
  if (!hasLatin) return false;
  // A mixed-script message with real Arabic takes the Arabic-script path;
  // any Latin in that message is probably a brand/area name, not Arabizi.
  if (hasArabic) return false;
  // Digit-for-letter tokens are the strongest signal. `3laikm`, `7awalli`,
  // `9bya`, `5aldya`, `6aima`, `2shbilya` all match. We require a digit
  // embedded in an otherwise-alphabetic token, not a standalone number or
  // a phone fragment (those are usually separated by punctuation/spaces).
  if (ARABIZI_DIGIT_TOKEN_RE.test(` ${text} `)) return true;
  // Fallback to a narrow wordlist for digit-less Arabizi.
  const lower = text.toLowerCase();
  for (const token of ARABIZI_WORD_TOKENS) {
    const re = new RegExp(`(?:^|[^a-z])${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:$|[^a-z])`, "i");
    if (re.test(lower)) return true;
  }
  return false;
}

/**
 * Classify the customer's turn into one of the mirroring modes we actually
 * reply in. Orthogonal to the binary `ar | en` language returned by
 * `resolveCustomerReplyLanguage`.
 *
 * NOTE: We intentionally do NOT return `"arabizi"` here, even though
 * `isProbablyArabizi` can detect it. Kuwaiti customers who type Arabizi
 * prefer English replies over back-transliterated Arabizi (which reads
 * as artificial / machine-generated to a native speaker). So Arabizi
 * input routes to the `"english"` reply mode. The `"arabizi"` variant is
 * kept in the union type for backward compatibility only — nothing
 * downstream should ever receive it.
 */
export function resolveCustomerScriptMode(params: {
  visibleText: string | null;
  explicitLanguage: "ar" | "en" | null;
  fallbackLanguage: "ar" | "en";
}): CustomerScriptMode {
  const text = (params.visibleText || "").trim();
  if (!text) {
    return params.fallbackLanguage === "ar" ? "arabic" : "english";
  }
  const hasArabic = hasVisibleArabic(text);
  const hasLatin = hasVisibleLatin(text);
  if (hasArabic && !hasLatin) {
    return "arabic";
  }
  // Arabizi input → English reply (see note above). Return before the
  // generic Latin check so we don't need a separate Arabizi branch.
  if (isProbablyArabizi(text)) {
    return "english";
  }
  if (hasLatin && !hasArabic) {
    return "english";
  }
  // Letterless turns (digits, whitespace, punctuation, emoji only) carry
  // zero script signal. They must NOT flip the conversation's script
  // mode — inheriting the controller's fallback is the only correct
  // behavior. Without this branch, the function used to fall through
  // to the "mixed-script default Arabic" line below, which is what
  // produced the 2026-04-19 transcript where an English conversation
  // suddenly got an Arabic reply ("أرسل اسم المستلم ورقمه.") after the
  // customer typed the bare number "99338566". The sibling function
  // `resolveCustomerReplyLanguage` already handles this for the binary
  // ar/en signal; mirroring the rule here keeps the two resolvers from
  // drifting apart. See `smoke-test-letterless-language-stability.mjs`.
  if (!hasArabic && !hasLatin) {
    return params.fallbackLanguage === "ar" ? "arabic" : "english";
  }
  // Mixed-script (rare): prefer Arabic-script to preserve the primary
  // language unless we have an explicit English signal.
  if (params.explicitLanguage === "en") return "english";
  return "arabic";
}

export function resolveCustomerReplyLanguage(params: {
  visibleText: string | null;
  explicitLanguage: "ar" | "en" | null;
  fallbackLanguage: "ar" | "en";
  preferFallbackForAudioTranscript?: boolean;
  preferFallbackForLowSignalText?: boolean;
}): "ar" | "en" {
  if (params.explicitLanguage) {
    return params.explicitLanguage;
  }
  const text = params.visibleText || "";
  const hasArabic = hasVisibleArabic(text);
  const hasLatin = hasVisibleLatin(text);
  if (hasArabic && !hasLatin) {
    return "ar";
  }
  if (hasLatin && !hasArabic) {
    return "en";
  }
  // Letterless turns (digits, whitespace, punctuation, emoji only) carry
  // zero language signal. Inheriting the conversation's previous language
  // is the only correct behavior — the alternative is letting a single
  // bare number like "929" flip the reply language, which is what caused
  // the 2026-04-19 transcript where an English conversation suddenly
  // got an Arabic error message after the customer typed "929". The
  // `preferFallbackForLowSignalText` flag used to be the opt-in lever for
  // this, but we now apply it unconditionally: there is no caller for
  // which "guess language from a numbers-only string" is the right call.
  if (text.trim() && !hasArabic && !hasLatin) {
    return params.fallbackLanguage;
  }
  if (text.trim()) {
    return detectConversationLanguage(text);
  }
  return params.fallbackLanguage;
}

export function isSimpleGreeting(text: string): boolean {
  const normalized = normalizeIntentText(text);
  return [
    "hi",
    "hello",
    "hey",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "السلام عليكم",
    "سلام",
    "مرحبا",
    "هلا",
    "هلا والله",
    "اهلا",
    "أهلا",
  ].includes(normalized);
}

// Minimal safety-net for when the turn-interpreter LLM fails (network error,
// timeout, refusal). Kept intentionally tiny — the interpreter is the source
// of truth for acceptance classification. Do NOT grow this list to handle
// natural-language variations; fix the interpreter prompt instead.
export function isBookingStartIntent(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  return [
    "ok",
    "okay",
    "yes",
    "yep",
    "sure",
    "book",
    "proceed",
    "continue",
    "go ahead",
    "احجز",
    "اكمل",
    "كمل",
    "نعم",
    "تمام",
    "اوكي",
  ].includes(normalized);
}

export function hasRouteEvidence(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  const routePatterns = [
    /\bfrom\b.+\bto\b/i,
    /\b(?:price|how much|quote|cost)\b.+\bto\b/i,
    /\b[a-z][a-z\s]{2,}\b\s+to\s+\b[a-z][a-z\s]{2,}\b/i,
    /\bمن\b.+\b(?:الى|إلى|ل)\b/u,
    /\b(?:سعر|كم|تكلفة)\b.+\b(?:الى|إلى)\b/u,
    /nearest riders area:/i,
  ];
  return routePatterns.some((pattern) => pattern.test(normalized));
}

export function isGeneralServiceInquiry(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  const phrases = [
    "what services",
    "what service",
    "what do you offer",
    "what can you do",
    "services",
    "service list",
    "service menu",
    "شنو الخدمات",
    "ما هي الخدمات",
    "شنو عندكم",
    "الخدمات",
    "شنو تقدمون",
  ];
  return phrases.some((phrase) => normalized.includes(phrase));
}

export function isPassengerTransportRequest(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  const passengerMarkers = [
    "drop me",
    "take me",
    "pick me up",
    "ride to airport",
    "airport ride",
    "drive me",
    "taxi",
    "transport me",
    "وصلني",
    "ودني",
    "خذني",
    "وصلني المطار",
    "ودني المطار",
    "ابي سيارة للمطار",
    "أبي سيارة للمطار",
    "ابي توصلني",
    "أبي توصلني",
  ];
  const packageMarkers = [
    "package",
    "parcel",
    "shipment",
    "deliver package",
    "send package",
    "item",
    "items",
    "order",
    "طلب",
    "شحنة",
    "طرود",
    "غرض",
    "اغراض",
  ];
  const looksPassenger = passengerMarkers.some((phrase) => normalized.includes(phrase));
  if (!looksPassenger) {
    return false;
  }
  const looksPackage = packageMarkers.some((phrase) => normalized.includes(phrase));
  return !looksPackage;
}

export function extractTrackingOrderId(text: string): string | null {
  const match = text.match(/\bORDER-[A-Za-z0-9-]+\b/i);
  return match ? match[0].toUpperCase() : null;
}

export function isTrackingIntent(text: string): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  const trackingMarkers = [
    "track",
    "tracking",
    "order status",
    "status update",
    "تتبع",
    "تابع",
    "متابعة الطلب",
    "حالة الطلب",
    "حالة طلبي",
    "وين طلبي",
    "تحديث الطلب",
  ];
  return trackingMarkers.some((marker) => normalized.includes(marker));
}

export function hasFreshQuotedState(entry: PersistedConversationControllerEntry | null): boolean {
  return !!entry?.quoteTs && (Date.now() - entry.quoteTs) <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS;
}

export function hasQuotedBookingAuthority(entry: PersistedConversationControllerEntry | null): boolean {
  return Boolean(
    entry &&
    entry.stage === "quoted" &&
    entry.quoteRouteKey &&
    entry.selectedDeliveryType &&
    entry.quotedPrice != null,
  );
}

export function hasActiveQuotedBookingAuthority(entry: PersistedConversationControllerEntry | null): boolean {
  return hasFreshQuotedState(entry) && hasQuotedBookingAuthority(entry);
}

export function isExplicitOrderConfirmation(text: string | null): boolean {
  const normalized = normalizeIntentText(text);
  if (!normalized) {
    return false;
  }
  return [
    "yes",
    "yes please",
    "yes confirm",
    "confirm",
    "confirmed",
    "i confirm",
    "confirm it",
    "go ahead",
    "proceed",
    "continue",
    "confirmed proceed",
    "confirmed go ahead",
    "ok confirm",
    "okay confirm",
    "نعم",
    "اي",
    "ايي",
    "اي نعم",
    "مؤكد",
    "أكد",
    "اكده",
    "أكيد",
  ].includes(normalized);
}

export function classifyCustomerIntent(params: {
  visibleText: string | null;
  explicitLanguage: "ar" | "en" | null;
  controllerEntry: PersistedConversationControllerEntry | null;
}): CustomerIntent | null {
  const text = params.visibleText || "";
  if (params.explicitLanguage) {
    return "language_switch";
  }
  if (
    params.controllerEntry &&
    (
      params.controllerEntry.stage === "awaiting_confirmation" ||
      params.controllerEntry.bookingStep === "awaiting_summary_confirmation"
    ) &&
    isExplicitOrderConfirmation(text)
  ) {
    return "booking_followup";
  }
  if (isPassengerTransportRequest(text)) {
    return "passenger_transport_request";
  }
  if (extractTrackingOrderId(text)) {
    return "tracking";
  }
  if (isTrackingIntent(text)) {
    return "tracking";
  }
  if (hasActiveQuotedBookingAuthority(params.controllerEntry) && isBookingStartIntent(text)) {
    return "booking_followup";
  }
  if (isSimpleGreeting(text)) {
    return "greeting";
  }
  if (isGeneralServiceInquiry(text)) {
    return "service_inquiry";
  }
  return null;
}

export function buildConversationControllerKey(accountId: string, conversationId: string): string {
  return `${String(accountId || "").trim()}::${String(conversationId || "").trim()}`;
}

export function resolveSessionIdentityKey(ctx: any): string {
  return (
    ctx?.ControllerStateKey ||
    ctx?.controllerStateKey ||
    ctx?.SessionKey ||
    ctx?.sessionKey ||
    ctx?.ConversationId ||
    ctx?.conversationId ||
    ctx?.sessionId ||
    "__global__"
  );
}
