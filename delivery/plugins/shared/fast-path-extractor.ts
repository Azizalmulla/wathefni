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
// Phase 1 authority cut (2026-04-24): `validateName` and
// `isAcceptableSlotResponse` are no longer imported here. The free-form
// name branches that relied on them (sender-combined residual name,
// recipient combined name) have been removed — the LLM owns every
// sender/recipient name write via `apply_booking_field`. Both functions
// still run on the post-LLM side through `apply-boundary.ts`.

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

// ---------------------------------------------------------------------------
// Phase 2 disposition gate (2026-04-24).
//
// Pure decision helper: given the pre-LLM disposition and the gate mode,
// return whether the Phase-3 fast-path should be skipped.
//
// The gate's whole purpose is to honour the Phase 2 rule: "no pre-LLM write
// from state-shape alone; structured/explicit branches can stay, but only
// with meaning/disposition gating." The Phase-3 extractor writes address
// and phone fields by shape-matching — so it's gated here.
//
// The reuse-intent, pin-role, and declared-role-pin paths are explicit
// command whitelists (narrow regex / keyword matches) and are NOT routed
// through this gate; they're callsite-kept by the Phase 2 plan.
//
// Contract:
//   * `disposition` — string value from `computePromptShapingDisposition`.
//     When it is `null` (computation failed) the gate is fail-open (do not
//     skip) so the fast-path degrades safely to pre-Phase-2 behaviour.
//   * `mode` — `"on"` enforces, `"log"` observes only, `"off"` disables
//     the gate entirely.
// ---------------------------------------------------------------------------
export type FastPathDispositionGateMode = "on" | "log" | "off";

export function resolveFastPathDispositionGateMode(
  raw: string | undefined | null,
): FastPathDispositionGateMode {
  const normalized = String(raw ?? "").trim().toLowerCase();
  if (normalized === "off") return "off";
  if (normalized === "log") return "log";
  return "on";
}

export type FastPathDispositionGateDecision = {
  action: "run" | "skip" | "run_log_only";
  blocked_by_disposition: boolean;
  disposition: string;
  mode: FastPathDispositionGateMode;
};

export function decideFastPathDispositionGate(params: {
  disposition: string | null;
  mode: FastPathDispositionGateMode;
}): FastPathDispositionGateDecision {
  const disposition = params.disposition ?? "-";
  const mode = params.mode;
  // Fail-open: if disposition is null (computation failed / not applicable)
  // we never block. The Phase 2 rule only applies when we have a reliable
  // classification.
  const isContinueStep = disposition === "continue_step";
  const blocked = !isContinueStep && params.disposition !== null;

  if (mode === "off" || !blocked) {
    return {
      action: "run",
      blocked_by_disposition: false,
      disposition,
      mode,
    };
  }
  if (mode === "log") {
    return {
      action: "run_log_only",
      blocked_by_disposition: true,
      disposition,
      mode,
    };
  }
  return {
    action: "skip",
    blocked_by_disposition: true,
    disposition,
    mode,
  };
}

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
//
// Phase 1 authority cut (2026-04-24): the NAME branch of this extractor has
// been removed. Reading free-form letters+spaces as a person-name before the
// LLM runs is the exact pre-LLM authority pattern that wrote
// `sender_name = "No the avenues mall"` on 2026-04-24 12:48 (conv 20125).
// The LLM now owns every sender-name write; the fast-path keeps only the two
// unambiguous structured / explicit-command signals on this action:
//
//   • `use_whatsapp` keyword                     → phone_decision: "use_whatsapp"
//   • pure digit group 7–15 digits (no letters)  → phone_decision: "different",
//                                                  sender_phone: <digits>
//
// Anything else → `{patch: null, confidence: "none"}` and the LLM handles the
// turn through its `apply_booking_field` tool call. No name-shape predicate,
// no coherence gate, no residual name extraction — by design.
// ---------------------------------------------------------------------------

const DIFFERENT_NUMBER_RE_EN =
  /\b(?:different|new|another|other)\s+(?:phone|number|no\.?|num)\b/i;
const DIFFERENT_NUMBER_RE_AR = /(?:رقم\s*(?:ثاني|آخر|مختلف|غير|جديد|اخر|ثاني)|(?:رقم|نمبر)\s+(?:ثاني|آخر|مختلف))/i;

/**
 * Phone / decision only — no name extraction.
 *
 * See the section header above for rationale. If the message contains an
 * unambiguous `use_whatsapp` keyword OR a single 7–15 digit phone group
 * (and no conflicting markers), we emit a phone-only patch. In every other
 * case we return `none` and the LLM owns the turn.
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

  const useWaMatch =
    raw.match(USE_WHATSAPP_RE) || raw.match(USE_WHATSAPP_AR_RE);
  if (useWaMatch) {
    decision = "use_whatsapp";
    residual = residual.replace(USE_WHATSAPP_RE, " ").replace(USE_WHATSAPP_AR_RE, " ");
    reasons.push("use_whatsapp_marker");
  }

  const differentMatch =
    raw.match(DIFFERENT_NUMBER_RE_EN) || raw.match(DIFFERENT_NUMBER_RE_AR);
  if (differentMatch) {
    if (decision === "use_whatsapp") {
      reasons.push("conflicting_markers");
      return { patch: null, confidence: "none", reasons };
    }
    decision = "different";
    residual = residual
      .replace(DIFFERENT_NUMBER_RE_EN, " ")
      .replace(DIFFERENT_NUMBER_RE_AR, " ");
    reasons.push("different_marker");
  }

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
      reasons.push("phone_with_use_whatsapp");
      return { patch: null, confidence: "none", reasons };
    }
    senderPhone = digitMatches[0].replace(/\D+/g, "");
    if (!decision) decision = "different";
    reasons.push("phone_digits");
  }

  // Phase 1 cut: no name extraction. If we did not resolve an unambiguous
  // phone/decision signal, hand the turn to the LLM.
  if (!decision && !senderPhone) {
    reasons.push("no_structured_signal");
    return { patch: null, confidence: "none", reasons };
  }

  if (decision === "different" && !senderPhone) {
    reasons.push("different_without_phone");
    return { patch: null, confidence: "none", reasons };
  }

  const patch: BookingFieldPatch = {};
  if (decision) patch.phone_decision = decision;
  if (senderPhone) patch.sender_phone = senderPhone;

  return { patch, confidence: "high", reasons };
}

// ---------------------------------------------------------------------------
// Recipient combined (ASK_RECIPIENT_NAME_AND_PHONE)
//
// Phase 1 authority cut (2026-04-24): this extractor is fully disabled.
// Combined "name + phone" parsing is free-form enough that the LLM should
// own it end-to-end via `apply_booking_field`. The export is kept as a
// shim (returning `none`) so existing smoke-test imports do not break.
// Callers should prefer `extractForNextAction`, which routes
// `ASK_RECIPIENT_NAME_AND_PHONE` to `none` explicitly.
// ---------------------------------------------------------------------------

export function extractRecipientNameAndPhone(_params: {
  text: string;
}): FastPathResult {
  return {
    patch: null,
    confidence: "none",
    reasons: ["llm_owned_recipient_combined"],
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
      // Phone/decision only after Phase 1 — the combined extractor no
      // longer writes `sender_name`. See the section header on
      // `extractSenderNameAndDecision` for rationale.
      return extractSenderNameAndDecision({ text: params.text });
    case "ASK_SENDER_NAME":
      // Phase 1 cut (2026-04-24): free-form name extraction belongs to
      // the LLM. The combined extractor is phone/decision only, and a
      // name-only ask has nothing structured to offer the fast-path,
      // so we bail explicitly.
      return {
        patch: null,
        confidence: "none",
        reasons: ["llm_owned_name_extraction"],
      };
    case "ASK_RECIPIENT_NAME_AND_PHONE":
      // Phase 1 cut (2026-04-24): combined recipient name+phone belongs
      // to the LLM. See `extractRecipientNameAndPhone` for rationale.
      return {
        patch: null,
        confidence: "none",
        reasons: ["llm_owned_recipient_combined"],
      };
    default:
      return { patch: null, confidence: "none", reasons: ["action_not_handled"] };
  }
}
