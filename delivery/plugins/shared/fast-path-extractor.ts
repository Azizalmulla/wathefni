/**
 * Phase-3 deterministic fast-path extractor (pre-LLM).
 *
 * The LLM is excellent at understanding intent and writing replies, but it is
 * a probabilistic component when it comes to *extracting* structured fields
 * from a short customer message. Even with strict tool schemas, the model can
 * occasionally transpose digits, drop the leading 9 of a Kuwait phone, or
 * pick the wrong `address_role`.
 *
 * When the controller is in a specific collection step (`ASK_PICKUP_ADDRESS`,
 * `ASK_SENDER_PHONE`, etc.) and the customer's message has an unambiguous
 * deterministic parse, we should NOT gamble on the LLM — we should parse in
 * code, apply the patch, and let the LLM focus on generating the natural
 * language reply against an already-updated state.
 *
 * This module never interferes when the parse is ambiguous. It returns
 * `confidence: "none"` and the LLM runs as usual.
 *
 * Design principles:
 *   1. Step-constrained: we only extract fields the current next_required_action
 *      is asking for. This kills whole classes of false positives.
 *   2. High-confidence or nothing: we never emit a "maybe" patch; we either
 *      fully parse the message or leave it to the LLM.
 *   3. Idempotent with the LLM: even if the LLM later calls apply_booking_field
 *      with the same values, the merge is a no-op. Zero double-write risk.
 */

import type { BookingFieldPatch } from "./booking-draft";
import { validateName } from "./responder-state-ops";
import { isAcceptableSlotResponse } from "./slot-response-coherence";

export type FastPathAction =
  | "ASK_SENDER_NAME_AND_PHONE_DECISION"
  | "ASK_SENDER_NAME"
  | "ASK_SENDER_PHONE"
  | "ASK_RECIPIENT_NAME_AND_PHONE"
  | "ASK_PICKUP_ADDRESS"
  | "ASK_DELIVERY_ADDRESS";

export type FastPathResult = {
  patch: BookingFieldPatch | null;
  confidence: "high" | "none";
  reasons: string[];
};

const ARABIC_DIGIT_MAP: Record<string, string> = {
  "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
  "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
  "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
};

export function normalizeArabicDigits(text: string): string {
  return text.replace(/[٠-٩۰-۹]/g, (d) => ARABIC_DIGIT_MAP[d] || d);
}

function squash(text: string): string {
  return normalizeArabicDigits(text).replace(/\s+/g, " ").trim();
}

// ---------------------------------------------------------------------------
// Address triplet (ASK_PICKUP_ADDRESS / ASK_DELIVERY_ADDRESS)
// ---------------------------------------------------------------------------

const ADDRESS_PART_EN = {
  block: /\bblock\s*[:#]?\s*([a-z0-9]{1,10})\b/i,
  street: /\bstreet\s*[:#]?\s*([a-z0-9]{1,10})\b/i,
  avenue: /\b(?:avenue|jedda|jaddah|jada)\s*[:#]?\s*([a-z0-9]{1,10})\b/i,
  house: /\b(?:house|villa|tower|building|bldg|bld|bd)\s*[:#]?\s*([a-z0-9]{1,10})\b/i,
};

const ADDRESS_PART_AR = {
  block: /(?:قطعة|قطعه)\s*[:#]?\s*([a-z0-9]{1,10})/i,
  street: /(?:شارع)\s*[:#]?\s*([a-z0-9]{1,10})/i,
  avenue: /(?:جادة|جاده|جدة)\s*[:#]?\s*([a-z0-9]{1,10})/i,
  house: /(?:منزل|بيت|فيلا|برج|عمارة|عماره|مبنى)\s*[:#]?\s*([a-z0-9]{1,10})/i,
};

const INTERIOR_RE_EN = /\b(apt|apartment|flat|floor|fl|office|door|gate|suite|unit)\s*[:#]?\s*([a-z0-9]{1,10})\b/gi;
const INTERIOR_RE_AR = /(?:شقة|شقه|فلات|دور|طابق|باب|مكتب|بوابة)\s*[:#]?\s*([a-z0-9]{1,10})/gi;

// Mirror of `hasSubstantiveAddressExtra` in
// `plugins/octopus-channel/lib/booking-flow.ts`. Kept inline to preserve
// the shared → octopus-channel layering (shared never imports plugin-
// local code). The smoke test in
// `scripts/smoke-test-fast-path-address-extra.mjs` asserts the two
// predicates agree on a curated fixture so drift is caught.
const EXTRA_LOCATOR_EN = [
  "apartment", "apt", "flat", "floor", "fl", "door", "gate",
  "suite", "unit", "office", "villa", "tower", "building",
  "bldg", "bld", "bd",
];
const EXTRA_LOCATOR_AR = [
  "شقة", "شقه", "دور", "طابق", "بوابة", "بوابه",
  "مكتب", "فيلا", "برج", "عمارة", "عماره", "وحدة", "وحده",
];
function isSubstantiveExtra(extra: string | null | undefined): boolean {
  if (!extra) return false;
  const t = extra.trim();
  if (t.length < 3) return false;
  if (/\d/.test(t) || /[\u0660-\u0669]/.test(t)) return true;
  const lower = t.toLowerCase();
  for (const kw of EXTRA_LOCATOR_EN) if (lower.includes(kw)) return true;
  for (const kw of EXTRA_LOCATOR_AR) if (t.includes(kw)) return true;
  return false;
}

function tryAddressLabeled(text: string): {
  block: string | null;
  street: string | null;
  avenue: string | null;
  house: string | null;
  extra: string | null;
} | null {
  const s = squash(text);
  const block =
    s.match(ADDRESS_PART_EN.block)?.[1] || s.match(ADDRESS_PART_AR.block)?.[1] || null;
  const street =
    s.match(ADDRESS_PART_EN.street)?.[1] || s.match(ADDRESS_PART_AR.street)?.[1] || null;
  const avenue =
    s.match(ADDRESS_PART_EN.avenue)?.[1] || s.match(ADDRESS_PART_AR.avenue)?.[1] || null;
  const house =
    s.match(ADDRESS_PART_EN.house)?.[1] || s.match(ADDRESS_PART_AR.house)?.[1] || null;

  const matchedCount = [block, street, avenue, house].filter(Boolean).length;
  if (matchedCount < 2) return null;

  const interiorParts: string[] = [];
  const gi1 = new RegExp(INTERIOR_RE_EN.source, "gi");
  let m;
  while ((m = gi1.exec(s)) !== null) {
    interiorParts.push(m[0].trim());
  }
  const gi2 = new RegExp(INTERIOR_RE_AR.source, "gi");
  while ((m = gi2.exec(s)) !== null) {
    interiorParts.push(m[0].trim());
  }
  const extra = interiorParts.length > 0 ? interiorParts.join(", ") : null;

  return { block, street, avenue, house, extra };
}

function tryAddressBareTriplet(text: string): {
  block: string | null;
  street: string | null;
  avenue: string | null;
  house: string | null;
  extra: string | null;
} | null {
  const s = squash(text);
  // Pure digits+commas+spaces+slashes only (no letters except digits/alnum-like
  // house numbers are covered by the labeled variant). This is the classic
  // "5,7,19" case.
  if (!/^[\d,\s/\-،.]+$/.test(s)) return null;
  const parts = s.split(/[,\s/\-،.]+/).filter(Boolean);
  if (parts.length < 3 || parts.length > 4) return null;
  // Each part must be 1-6 chars, all digits.
  for (const p of parts) {
    if (!/^\d{1,6}$/.test(p)) return null;
  }
  if (parts.length === 3) {
    return { block: parts[0], street: parts[1], avenue: null, house: parts[2], extra: null };
  }
  // 4 parts → block, street, avenue, house
  return { block: parts[0], street: parts[1], avenue: parts[2], house: parts[3], extra: null };
}

export function extractAddressForRole(params: {
  text: string;
  role: "pickup" | "delivery";
}): FastPathResult {
  const reasons: string[] = [];
  const labeled = tryAddressLabeled(params.text);
  if (labeled) {
    // Completeness rule — must match the downstream predicate in
    // `hasCompleteTextAddress` (plugins/octopus-channel/lib/booking-flow.ts)
    // so the fast-path doesn't bail on addresses the completeness gate
    // would accept. Any divergence becomes a silent UX regression: the
    // LLM re-asks for a field the customer already provided.
    //
    //   block        - always required
    //   street OR avenue - at least one required
    //   house OR substantive-extra (apartment / floor / door / etc.)
    //                - at least one required
    const hasBlock = Boolean(labeled.block);
    const hasStreetOrAvenue = Boolean(labeled.street || labeled.avenue);
    const hasHouseOrExtra =
      Boolean(labeled.house) || isSubstantiveExtra(labeled.extra);
    if (!hasBlock || !hasStreetOrAvenue || !hasHouseOrExtra) {
      // Granular bail reasons (log-only — decision stays the same).
      // These drive the address-shape coverage dashboard: recurring
      // miss patterns here tell us which shape-classes to add support
      // for next (interior-locator words, alternative labels, etc.).
      if (!hasBlock) reasons.push("labeled_missing_block");
      if (!hasStreetOrAvenue) reasons.push("labeled_missing_street_or_avenue");
      if (!hasHouseOrExtra) reasons.push("labeled_missing_house_or_extra");
      reasons.push("labeled_address_partial_ignored");
      return { patch: null, confidence: "none", reasons };
    }
    reasons.push(
      labeled.house
        ? "labeled_address_complete"
        : "labeled_address_complete_via_extra",
    );
    return {
      patch: {
        address_role: params.role,
        address_block: labeled.block,
        address_street: labeled.street,
        address_avenue: labeled.avenue,
        address_house: labeled.house,
        address_extra: labeled.extra,
      },
      confidence: "high",
      reasons,
    };
  }

  const bare = tryAddressBareTriplet(params.text);
  if (bare) {
    reasons.push(bare.avenue ? "bare_quad" : "bare_triplet");
    return {
      patch: {
        address_role: params.role,
        address_block: bare.block,
        address_street: bare.street,
        address_avenue: bare.avenue,
        address_house: bare.house,
        address_extra: null,
      },
      confidence: "high",
      reasons,
    };
  }

  // Neither labeled nor bare-triplet/quad shape matched. The LLM will
  // have to parse this free-form. Tag for coverage triage so we can see
  // which shape-classes are eluding both extractors.
  reasons.push("no_labeled_or_bare_shape");
  return { patch: null, confidence: "none", reasons };
}

// ---------------------------------------------------------------------------
// Phone-only (ASK_SENDER_PHONE)
// ---------------------------------------------------------------------------

const USE_WHATSAPP_RE =
  /\b(?:use\s+(?:my\s+)?whatsapp|same\s+(?:as\s+)?(?:my\s+)?whatsapp|this\s+(?:is\s+)?fine|use\s+this(?:\s+number)?)\b/i;
const USE_WHATSAPP_AR_RE = /(?:نفس\s*(?:رقم\s*)?(?:الواتس|الواتساب|هذا)|استخدم\s*(?:رقم\s*)?الواتس|هذا\s*الرقم)/i;

function digitsOnly(text: string): string {
  return normalizeArabicDigits(text).replace(/\D+/g, "");
}

/**
 * Returns a normalized phone string if the input looks like ONLY a phone
 * number (digits + separators + optional country code), else null.
 */
function extractIfPurePhone(text: string): string | null {
  const s = normalizeArabicDigits(text).trim();
  // Only allow digits, spaces, +, -, parentheses, and up to one label prefix
  // like "number:" / "phone:" / "my phone is ".
  const labelStripped = s.replace(
    /^\s*(?:my\s+(?:phone|number|no\.?)\s+is\s+|phone\s*[:#]?\s*|number\s*[:#]?\s*|tel\s*[:#]?\s*|رقم[يي]?\s*[:#]?\s*)/i,
    "",
  );
  if (!/^[\d+\-()\s]+$/.test(labelStripped)) return null;
  const digits = labelStripped.replace(/\D+/g, "");
  if (digits.length < 7 || digits.length > 15) return null;
  return digits;
}

export function extractSenderPhone(params: {
  text: string;
  whatsappNumber: string | null;
}): FastPathResult {
  const reasons: string[] = [];
  const s = squash(params.text);
  if (USE_WHATSAPP_RE.test(s) || USE_WHATSAPP_AR_RE.test(s)) {
    reasons.push("use_whatsapp_shortcut");
    return {
      patch: { phone_decision: "use_whatsapp" },
      confidence: "high",
      reasons,
    };
  }
  const phone = extractIfPurePhone(params.text);
  if (phone) {
    reasons.push("pure_phone");
    return {
      patch: { phone_decision: "different", sender_phone: phone },
      confidence: "high",
      reasons,
    };
  }
  return { patch: null, confidence: "none", reasons };
}

// ---------------------------------------------------------------------------
// Sender combined (ASK_SENDER_NAME_AND_PHONE_DECISION)
// ---------------------------------------------------------------------------

const DIFFERENT_NUMBER_RE_EN =
  /\b(?:different|new|another|other)\s+(?:phone|number|no\.?|num)\b/i;
const DIFFERENT_NUMBER_RE_AR = /(?:رقم\s*(?:ثاني|آخر|مختلف|غير|جديد|اخر|ثاني)|(?:رقم|نمبر)\s+(?:ثاني|آخر|مختلف))/i;

const NAME_ONLY_RE = /^[a-z\u0600-\u06ff][a-z\u0600-\u06ff'\s.-]{1,58}$/i;

function stripTrailingPunct(s: string): string {
  return s.replace(/[\s,،.;:/\-]+$/g, "").replace(/^[\s,،.;:/\-]+/g, "").trim();
}

function looksLikeValidName(candidate: string): boolean {
  const trimmed = stripTrailingPunct(candidate);
  if (!trimmed) return false;
  // Defer to the apply-boundary `validateName` so the pre-LLM fast-path
  // and the post-LLM tool-op validator share a single shape policy. This
  // closes the gap that let "Is this the cheapest option" be written to
  // sender_name on 2026-04-19 13:42 — the fast-path's old standalone
  // predicate accepted any letters+spaces string of length 2–60.
  return validateName(trimmed) === null;
}

/**
 * Combined sender turn. The model is asked for BOTH the sender's name AND
 * a phone decision (use WhatsApp vs different number). Customers typically
 * pack both into one reply, and the exact shape varies widely. We only
 * emit a high-confidence patch when we can cleanly separate the parts:
 *
 *   "Aziz Almulla, use my whatsapp"           → name + use_whatsapp
 *   "Use whatsapp, Aziz Almulla"              → same
 *   "Aziz Almulla different number 94728472"  → name + different + phone
 *   "94728472, Aziz Almulla"                  → same (order flipped)
 *   "Aziz Almulla"                            → name only (decision unresolved)
 *   "use whatsapp"                            → decision only (name unresolved)
 *
 * Ambiguous cases (bare digit strings that can't be a clear phone, mixed
 * alphanumerics, multiple digit groups) fall through to "none" and the LLM
 * handles them.
 */
export function extractSenderNameAndDecision(params: {
  text: string;
}): FastPathResult {
  const reasons: string[] = [];
  const raw = normalizeArabicDigits(params.text).trim();
  if (!raw) return { patch: null, confidence: "none", reasons };

  let residual = raw;
  let decision: "use_whatsapp" | "different" | null = null;
  let senderPhone: string | null = null;

  // 1) use_whatsapp marker
  const useWaMatch =
    raw.match(USE_WHATSAPP_RE) || raw.match(USE_WHATSAPP_AR_RE);
  if (useWaMatch) {
    decision = "use_whatsapp";
    residual = residual.replace(USE_WHATSAPP_RE, " ").replace(USE_WHATSAPP_AR_RE, " ");
    reasons.push("use_whatsapp_marker");
  }

  // 2) "different number" marker + digits
  const differentMatch =
    raw.match(DIFFERENT_NUMBER_RE_EN) || raw.match(DIFFERENT_NUMBER_RE_AR);
  if (differentMatch) {
    if (decision === "use_whatsapp") {
      // Contradictory markers. Let the LLM handle it.
      reasons.push("conflicting_markers");
      return { patch: null, confidence: "none", reasons };
    }
    decision = "different";
    residual = residual
      .replace(DIFFERENT_NUMBER_RE_EN, " ")
      .replace(DIFFERENT_NUMBER_RE_AR, " ");
    reasons.push("different_marker");
  }

  // 3) Pull out a single phone-shaped digit group.
  const digitMatches: string[] = [];
  const digitRe = /[\d+\-()\s]{7,}/g;
  let m;
  while ((m = digitRe.exec(residual)) !== null) {
    const clean = m[0].replace(/\D+/g, "");
    if (clean.length >= 7 && clean.length <= 15) {
      digitMatches.push(m[0]);
    }
  }
  if (digitMatches.length > 1) {
    reasons.push("multiple_phone_candidates");
    return { patch: null, confidence: "none", reasons };
  }
  if (digitMatches.length === 1) {
    if (decision === "use_whatsapp") {
      // Phone provided alongside "use whatsapp" → ambiguous intent.
      reasons.push("phone_with_use_whatsapp");
      return { patch: null, confidence: "none", reasons };
    }
    senderPhone = digitMatches[0].replace(/\D+/g, "");
    residual = residual.replace(digitMatches[0], " ");
    if (!decision) decision = "different";
    reasons.push("phone_digits");
  }

  // 4) Whatever's left after stripping markers and digits is the name.
  //
  // Two-layer gate: the residual must (a) pass the same shape rules
  // the apply-boundary uses (`validateName` via `looksLikeValidName`)
  // AND (b) be coherent with `sender_name` per the slot-response
  // coherence policy. The coherence layer catches conversational
  // fragments that are letter-only but not actually a name (e.g.
  // questions, topic changes). Without it, the fast-path's own shape
  // predicate accepts any letters+spaces string of length 2–60 — which
  // is how "Is this the cheapest option" reached `sender_name` in
  // production on 2026-04-19 13:42 (live).
  const nameCandidate = stripTrailingPunct(
    residual.replace(/[,،;:]+/g, " ").replace(/\s+/g, " "),
  );
  let senderName: string | null = null;
  if (looksLikeValidName(nameCandidate)) {
    const coherence = isAcceptableSlotResponse({
      text: nameCandidate,
      slot: "sender_name",
    });
    if (coherence.acceptable) {
      senderName = nameCandidate;
      reasons.push("name_residual");
    } else {
      reasons.push(`name_rejected_by_coherence:${coherence.decision.kind}:${coherence.decision.reason}`);
    }
  }

  // Require at least ONE deterministically-extracted signal. If we got
  // nothing (no decision, no phone, no name), bail.
  if (!decision && !senderPhone && !senderName) {
    return { patch: null, confidence: "none", reasons };
  }

  // If we got a "different" decision but no phone, reject — incomplete intent
  // (customer said "different number" but didn't include the number). Let the
  // LLM clarify.
  if (decision === "different" && !senderPhone) {
    reasons.push("different_without_phone");
    return { patch: null, confidence: "none", reasons };
  }

  const patch: BookingFieldPatch = {};
  if (senderName) patch.sender_name = senderName;
  if (decision) patch.phone_decision = decision;
  if (senderPhone) patch.sender_phone = senderPhone;

  return { patch, confidence: "high", reasons };
}

// ---------------------------------------------------------------------------
// Recipient combined (ASK_RECIPIENT_NAME_AND_PHONE)
// ---------------------------------------------------------------------------

export function extractRecipientNameAndPhone(params: {
  text: string;
}): FastPathResult {
  const reasons: string[] = [];
  const normalized = normalizeArabicDigits(params.text);
  // Extract all digit-groups of length >= 7.
  const digitGroups: Array<{ match: string; start: number; end: number }> = [];
  const re = /[\d\s+\-()]{7,}/g;
  let m;
  while ((m = re.exec(normalized)) !== null) {
    const clean = m[0].replace(/\D+/g, "");
    if (clean.length >= 7 && clean.length <= 15) {
      digitGroups.push({ match: m[0], start: m.index, end: m.index + m[0].length });
    }
  }
  if (digitGroups.length !== 1) {
    if (digitGroups.length > 1) reasons.push("multiple_phone_candidates");
    return { patch: null, confidence: "none", reasons };
  }
  const { match: phoneMatch, start, end } = digitGroups[0];
  const rawNamePart = (normalized.slice(0, start) + " " + normalized.slice(end))
    .replace(/[,،.;:/\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  // Label detection uses Unicode-aware whole-word lookarounds rather
  // than `\b` because JavaScript's `\b` is ASCII-only and silently
  // fails to anchor Arabic tokens (conv 19399 — "اسم احمد باشا رقم
  // 5207777" passed the old `\b(...|رقم)\b` guard and corrupted
  // recipient_name). We also accept `اسم`/`الاسم`/`name` so labeled
  // answers like "اسم احمد باشا رقم 5207777" can be stripped and
  // re-parsed instead of being dropped into the LLM's lap.
  const LABEL_RE = /(?<![\p{L}\p{N}])(?:phone|number|tel|no\.?|name|رقم|رقمه|الرقم|اسم|الاسم)(?![\p{L}\p{N}])/iu;
  let namePart = rawNamePart;
  if (LABEL_RE.test(rawNamePart)) {
    // Strip every label occurrence and re-validate. If the stripped
    // residual still has a reasonable name shape, use it; otherwise
    // fall back to "too ambiguous, let the LLM try".
    const LABEL_RE_GLOBAL = new RegExp(LABEL_RE.source, "giu");
    const stripped = rawNamePart
      .replace(LABEL_RE_GLOBAL, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!stripped || stripped.length < 2 || !/[a-z\u0600-\u06ff]/i.test(stripped)) {
      reasons.push("contains_labels_only");
      return { patch: null, confidence: "none", reasons };
    }
    namePart = stripped;
    reasons.push("labels_stripped");
  }
  const phoneClean = phoneMatch.replace(/\D+/g, "");
  if (phoneClean.length < 7 || phoneClean.length > 15) {
    return { patch: null, confidence: "none", reasons };
  }
  // Name must have at least one letter (Latin or Arabic).
  if (!/[a-z\u0600-\u06ff]/i.test(namePart)) {
    reasons.push("no_letters_in_name_part");
    return { patch: null, confidence: "none", reasons };
  }
  // Name must be reasonable length (2-60 chars) and not start/end with dangling
  // single letters that are artifacts of partial extraction.
  if (namePart.length < 2 || namePart.length > 60) {
    return { patch: null, confidence: "none", reasons };
  }
  // Coherence gate against `recipient_name`. Same rationale as the
  // sender-combined extractor above: shape alone cannot tell a person
  // name from a conversational fragment. Without this gate, a message
  // like "Is this cheapest 99118375" would have written the question to
  // `recipient_name`. With it, the name drops and we bail on the whole
  // extraction (since phone-only recipient writes aren't supported by
  // this path — the LLM will re-ask coherently).
  const nameCoherence = isAcceptableSlotResponse({
    text: namePart,
    slot: "recipient_name",
  });
  if (!nameCoherence.acceptable) {
    reasons.push(`name_rejected_by_coherence:${nameCoherence.decision.kind}:${nameCoherence.decision.reason}`);
    return { patch: null, confidence: "none", reasons };
  }
  reasons.push("name_plus_phone");
  return {
    patch: {
      recipient_name: namePart,
      recipient_phone: phoneClean,
    },
    confidence: "high",
    reasons,
  };
}

// ---------------------------------------------------------------------------
// Top-level: resolve based on next_required_action
// ---------------------------------------------------------------------------

export function extractForNextAction(params: {
  text: string;
  action: FastPathAction | null | undefined;
  whatsappNumber: string | null;
}): FastPathResult {
  if (!params.text || !params.action) {
    return { patch: null, confidence: "none", reasons: ["no_text_or_action"] };
  }
  switch (params.action) {
    case "ASK_PICKUP_ADDRESS":
      return extractAddressForRole({ text: params.text, role: "pickup" });
    case "ASK_DELIVERY_ADDRESS":
      return extractAddressForRole({ text: params.text, role: "delivery" });
    case "ASK_SENDER_PHONE":
      return extractSenderPhone({ text: params.text, whatsappNumber: params.whatsappNumber });
    case "ASK_SENDER_NAME_AND_PHONE_DECISION":
      return extractSenderNameAndDecision({ text: params.text });
    case "ASK_SENDER_NAME":
      // Narrow name-only ask. The customer is expected to answer with a
      // name; occasionally they volunteer the phone too. Reuse the
      // combined extractor — it already handles "name only" and
      // "name + phone/decision" cleanly, and the apply-boundary will
      // drop any stray phone on a name-requested turn unless a valid
      // name is also in the same patch (see
      // `apply-boundary.ts::applyRequestedSlotNameScope`).
      return extractSenderNameAndDecision({ text: params.text });
    case "ASK_RECIPIENT_NAME_AND_PHONE":
      return extractRecipientNameAndPhone({ text: params.text });
    default:
      return { patch: null, confidence: "none", reasons: ["action_not_handled"] };
  }
}
