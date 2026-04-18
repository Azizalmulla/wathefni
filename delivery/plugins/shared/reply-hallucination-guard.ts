// ---------------------------------------------------------------------------
// Reply Hallucination Guard
//
// Deterministic post-LLM defense layer that scans the outbound reply for
// factually-ungrounded claims and either rewrites them (via a canonical
// template) or blocks the send and substitutes a safe fallback.
//
// This module is the *factual-claim* axis of outbound verification. It is
// orthogonal to `outbound-verify.ts`, which handles *structural shape*
// (stub-summary / bare-ack / route-recap). Both run on every outbound reply.
//
// Scope (v1):
//   1. field_rejection_hallucination — reply claims a phone/name/address
//      is invalid when no validator actually rejected those fields this
//      turn and the stored values are present + well-formed.
//   2. price_mismatch — reply mentions a KWD price that differs from the
//      live quoted price.
//   3. order_placed_hallucination — reply states the order is placed /
//      confirmed / submitted when the controller stage is not yet
//      `order_submitted`.
//
// Out of scope for v1 (harder, lower-impact):
//   - Area-name hallucination (distinguishing a mention from a claim is
//     non-trivial; area evidence already has its own graduated-response
//     guard inside `get_price`).
//
// Design constraints:
//   - Pure module. No I/O. All inputs passed in.
//   - Never throws. Callers treat the module like a passthrough — if
//     anything unexpected happens, the original reply goes out.
//   - Default-on; single env flag (`RIDERS_HALLUCINATION_GUARD_ENABLED=0`)
//     to disable the whole layer for emergency rollback.
//   - All substitutions are data-driven templates; no hand-written wording
//     that would drift against SKILL.md.
// ---------------------------------------------------------------------------

import type {
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
} from "./conversation-policy";
import { buildDeterministicOrderSummary } from "./outbound-verify";

export type HallucinationGuardLanguage = "ar" | "en";

export type FieldRejection = {
  field: string;
  reason: string;
  received?: string;
};

export type HallucinationGuardInputs = {
  replyText: string;
  entry: PersistedConversationControllerEntry | null;
  /** `missing_fields` AFTER this turn's responder ops were applied. */
  missingFields: string[];
  /** Field rejections captured during this turn's `apply_booking_field` ops. */
  rejectionsThisTurn: FieldRejection[];
  /** Stage at the START of this turn, before any ops applied. Used to tell
   *  whether an "order placed" claim is legitimate (stage transitioned this
   *  turn) or hallucinated (stage is still pre-submit). */
  stageAtTurnStart: string | null;
  language: HallucinationGuardLanguage;
  /** Optional hook for callers that already compute next-required-action.
   *  If absent, the guard falls back to a safe generic nudge. */
  nextRequiredAction?: string | null;
};

export type HallucinationKind =
  | "field_rejection_hallucination"
  | "price_mismatch"
  | "order_placed_hallucination";

export type HallucinationGuardDecision = {
  replyText: string;
  blocked: boolean;
  /** Claims detected (for logging / metrics). Multiple claims can fire on
   *  the same reply; only the highest-priority one dictates the substitute. */
  claims: HallucinationKind[];
  reason: string | null;
  /** Source of the substitute reply, for log triage. */
  substitutedFrom: "none" | "next_required_action" | "order_summary" | "generic_nudge";
};

// ---------------------------------------------------------------------------
// Claim detectors
// ---------------------------------------------------------------------------

/**
 * Does the reply claim a customer-provided field is invalid / needs resend?
 * We detect on multiple surface forms because WhatsApp replies are informal
 * and the LLM varies its wording. False positives here are ACCEPTABLE —
 * we'll only block when the evidence side also clears (i.e. no actual
 * rejection occurred), and the substitute is a coherent next-step ask.
 *
 * Cases intentionally NOT flagged:
 *   - "the phone number is 97485757" (stating a value, not rejecting one)
 *   - "could I get the phone number?" (asking, not rejecting)
 *   - "please resend the address" (ambiguous — might be legit if address
 *     genuinely didn't parse; but in that case rejectionsThisTurn will be
 *     non-empty, so the guard won't fire)
 */
// A "rejection" claim is one that asserts a previously-provided field was
// unacceptable. Key discriminator: it refers to RE-sending / sending AGAIN,
// or it asserts the field IS invalid. A plain "please send the name" is
// just a collection ask and must NOT match (avoids suppressing normal
// slot-filling turns).
const FIELD_REJECTION_PATTERNS: RegExp[] = [
  // "phone/number/name/address is invalid / not valid / wrong / incorrect"
  /\b(?:phone|number|name|address|sender|recipient)\s+(?:number\s+)?(?:is\s+|appears\s+|seems\s+|look[s]?\s+)?(?:not\s+valid|invalid|wrong|incorrect|malformed)\b/i,
  // Explicit re-send language ("resend", "send again", "send X again",
  // "send X once more", "send X one more time", "send X back"). Must be
  // paired with a field noun. "please send X" WITHOUT a re-send signal is
  // intentionally excluded — that's normal slot filling.
  /\b(?:resend|re-send|please\s+resend|send\s+(?:it\s+|them\s+|the\s+\w+\s+)?again|send\s+(?:it\s+|them\s+|the\s+\w+\s+)?once\s+more|send\s+(?:it\s+|them\s+|the\s+\w+\s+)?one\s+more\s+time)\b/i,
  // "needs to be resent / must be resent / sent again"
  /\b(?:needs?\s+to\s+be\s+resent|must\s+be\s+resent|needs?\s+to\s+be\s+sent\s+again)\b/i,
  // "in a valid format / in valid format / in the correct format"
  /\b(?:phone|number|name|address)\b.{0,40}\bin\s+(?:a\s+|the\s+)?(?:valid|correct|proper|right)\s+format\b/i,
  /\b(?:valid|correct|proper|right)\s+format\b.{0,40}\b(?:phone|number|name|address)\b/i,
  // "digits only" + phone-ish context (this is the signature repair-hint
  // the LLM surfaces when it thinks a phone was malformed)
  /\b(?:digits\s+only|numbers\s+only)\b.{0,40}\b(?:phone|number)\b/i,
  /\b(?:phone|number)\b.{0,40}\b(?:digits\s+only|numbers\s+only)\b/i,
  // Arabic: "الرقم/الاسم/العنوان غير صحيح/خاطئ/غير صالح"
  /(?:الرقم|الاسم|العنوان|رقم|اسم|عنوان)[^.!؟\n]{0,25}(?:غير\s*صحيح|خاطئ|غير\s*صالح|ليس\s*صحيح)/,
  // Arabic: "يرجى إعادة إرسال الرقم / اسم"
  /(?:يرجى|من\s*فضلك|لو\s*سمحت)?[^.!؟\n]{0,15}(?:إعادة\s*إرسال|إرسال\s*مرة\s*أخرى|ارسال\s*مرة\s*اخرى|ارسله?\s*مرة\s*اخرى|ارسلي?\s*مرة\s*اخرى)/,
];

export function looksLikeFieldRejectionClaim(reply: string): boolean {
  for (const re of FIELD_REJECTION_PATTERNS) {
    if (re.test(reply)) return true;
  }
  return false;
}

/**
 * Does the stored evidence (this turn's rejections + draft field presence)
 * justify a field-rejection claim? If any of these are true, the LLM's
 * claim is grounded and we do NOT flag.
 */
function fieldRejectionHasEvidence(params: {
  rejections: FieldRejection[];
  draft: PersistedBookingDraft | null;
  missingFields: string[];
}): boolean {
  if (params.rejections.length > 0) return true;
  const draft = params.draft;
  if (!draft) return true; // no draft → we don't know; give benefit of the doubt

  // Phone sanity — 8+ digits after stripping non-digits. Matches upstream
  // validator. If the LLM says "phone is invalid" and the stored phone
  // actually fails this bar, don't block.
  const isValidPhone = (p: string | null): boolean => {
    if (!p) return false;
    const digits = p.replace(/\D/g, "");
    return digits.length >= 8;
  };
  // Name sanity — at least 2 chars, no digits. Matches upstream validator.
  const isValidName = (n: string | null): boolean => {
    if (!n) return false;
    const t = n.trim();
    if (t.length < 2) return false;
    if (/\d/.test(t)) return false;
    return true;
  };

  // If a NAME or PHONE the LLM might be complaining about is genuinely
  // missing or invalid, let the claim through — the LLM is right, we just
  // didn't capture a rejection op (because the LLM is asking preemptively).
  if (
    !draft.senderName || !isValidName(draft.senderName) ||
    !draft.senderPhone || !isValidPhone(draft.senderPhone) ||
    !draft.recipientName || !isValidName(draft.recipientName) ||
    !draft.recipientPhone || !isValidPhone(draft.recipientPhone)
  ) {
    return true;
  }

  return false;
}

/**
 * Does the reply state the order is placed / confirmed / submitted?
 * Assertive patterns only — we skip replies that are asking ("shall I
 * confirm?", "do you want me to place it?").
 */
const ORDER_PLACED_PATTERNS: RegExp[] = [
  /\b(?:your\s+)?(?:order|booking|delivery|request)\s+(?:has\s+been|is|was)\s+(?:placed|created|submitted|confirmed|booked|registered|logged)\b/i,
  /\b(?:we(?:'ve|\s+have)|i(?:'ve|\s+have))\s+(?:placed|created|submitted|confirmed|booked|registered)\b[^.!?\n]{0,40}\b(?:order|booking|delivery|request)\b/i,
  /\b(?:order|booking)\s+(?:id|#|number|reference|uid)\s*[:=-]?\s*[A-Za-z0-9][-A-Za-z0-9]{3,}/i,
  /\b(?:on\s+its\s+way|rider\s+is\s+(?:assigned|on\s+the\s+way)|driver\s+is\s+(?:assigned|on\s+the\s+way))\b/i,
  /(?:تم|تمت)\s+(?:تأكيد|إنشاء|تسجيل|إرسال|حجز)\s+(?:الطلب|الحجز|طلبك|حجزك)/,
  /(?:الطلب|الحجز)\s+(?:تم\s+تأكيده|تم\s+تسجيله|تم\s+إنشاؤه|في\s+الطريق)/,
];

export function looksLikeOrderPlacedClaim(reply: string): boolean {
  // Skip if the reply is a question / offer (not an assertion).
  if (/\b(?:shall\s+i|should\s+i|do\s+you\s+want\s+me\s+to|want\s+me\s+to\s+(?:place|confirm|submit|create))\b/i.test(reply)) {
    return false;
  }
  for (const re of ORDER_PLACED_PATTERNS) {
    if (re.test(reply)) return true;
  }
  return false;
}

/**
 * Extract mentioned KWD-like prices from the reply. Returns numbers,
 * normalized. Very tolerant of KWD / KD / د.ك / دينار suffixes.
 */
const PRICE_TOKEN_RE = /(\d+(?:[.,]\d{1,3})?)\s*(?:kwd|kd|د\.?ك|دينار|dinars?)\b/gi;

export function extractMentionedPrices(reply: string): number[] {
  const out: number[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(PRICE_TOKEN_RE.source, PRICE_TOKEN_RE.flags);
  while ((m = re.exec(reply)) !== null) {
    const n = Number(m[1].replace(",", "."));
    if (Number.isFinite(n) && n > 0) out.push(n);
  }
  return out;
}

function priceDisagrees(mentioned: number[], quoted: number | null): boolean {
  if (quoted == null || !Number.isFinite(quoted)) return false;
  if (mentioned.length === 0) return false;
  // A 0.05 KWD tolerance covers rounding variants ("1.25" vs "1.250").
  return mentioned.every((p) => Math.abs(p - quoted) > 0.05);
}

// ---------------------------------------------------------------------------
// Deterministic fallbacks
// ---------------------------------------------------------------------------

type NextStepTemplate = {
  en: string;
  ar: string;
};

const NEXT_STEP_TEMPLATES: Record<string, NextStepTemplate> = {
  ASK_SENDER_NAME_AND_PHONE_DECISION: {
    en: "Could you share the sender's full name, and let me know if I should use this WhatsApp number or a different one?",
    ar: "تكرماً، ما هو الاسم الكامل للمرسل؟ وهل أستخدم رقم الواتساب هذا أم رقم آخر؟",
  },
  ASK_SENDER_PHONE: {
    en: "What's the best phone number for the sender?",
    ar: "ما هو أفضل رقم لتواصل مع المرسل؟",
  },
  ASK_RECIPIENT_NAME_AND_PHONE: {
    en: "Could you share the recipient's full name and phone number?",
    ar: "تكرماً، ما هو الاسم الكامل ورقم هاتف المستلم؟",
  },
  ASK_PICKUP_ADDRESS: {
    en: "Could you share the pickup address — block, street (or avenue), and a building / apartment / tower identifier?",
    ar: "تكرماً، ما هو عنوان الاستلام — القطعة والشارع (أو الجادة) ورقم المبنى أو الشقة أو البرج؟",
  },
  ASK_DELIVERY_ADDRESS: {
    en: "Could you share the delivery address — block, street (or avenue), and a building / apartment / tower identifier?",
    ar: "تكرماً، ما هو عنوان التسليم — القطعة والشارع (أو الجادة) ورقم المبنى أو الشقة أو البرج؟",
  },
  POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF: {
    en: "Your order has already been placed. Would you like me to track it, cancel it, or connect you with our team?",
    ar: "طلبك مسجل بالفعل. هل تود متابعته، إلغاؤه، أو التواصل مع فريقنا؟",
  },
};

const GENERIC_NUDGE: NextStepTemplate = {
  en: "Let me double-check your request. Could you confirm the pickup and delivery areas again?",
  ar: "تكرماً، هل يمكنك تأكيد منطقة الاستلام ومنطقة التسليم مرة أخرى؟",
};

/**
 * Pick a deterministic substitute based on next-required-action + the
 * granular missing sub-fields the address model now emits. Falls back to
 * a generic nudge when we don't have a confident ask.
 */
function deterministicSubstitute(params: {
  nextRequiredAction: string | null;
  missingFields: string[];
  entry: PersistedConversationControllerEntry | null;
  language: HallucinationGuardLanguage;
}): { text: string; source: HallucinationGuardDecision["substitutedFrom"] } {
  const { nextRequiredAction, missingFields, entry, language } = params;

  // Refine address asks using the granular sub-field markers.
  if (nextRequiredAction === "ASK_PICKUP_ADDRESS" || nextRequiredAction === "ASK_DELIVERY_ADDRESS") {
    const side: "pickup" | "delivery" = nextRequiredAction === "ASK_PICKUP_ADDRESS" ? "pickup" : "delivery";
    const subs: string[] = [];
    if (missingFields.includes(`${side}.block`)) subs.push(language === "ar" ? "القطعة" : "block");
    if (missingFields.includes(`${side}.street_or_avenue`)) subs.push(language === "ar" ? "الشارع أو الجادة" : "street or avenue");
    if (missingFields.includes(`${side}.house_or_unit`)) subs.push(language === "ar" ? "رقم المبنى أو الشقة" : "building number or apartment/tower");
    if (subs.length > 0) {
      const sideLabel = language === "ar"
        ? (side === "pickup" ? "الاستلام" : "التسليم")
        : side;
      const text = language === "ar"
        ? `تكرماً، ${subs.join("، ")} لعنوان ${sideLabel}؟`
        : `Could you share the ${subs.join(" and ")} for the ${sideLabel} address?`;
      return { text, source: "next_required_action" };
    }
  }

  if (nextRequiredAction === "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED" && entry) {
    return { text: buildDeterministicOrderSummary({ entry, language }), source: "order_summary" };
  }

  if (nextRequiredAction && NEXT_STEP_TEMPLATES[nextRequiredAction]) {
    return { text: NEXT_STEP_TEMPLATES[nextRequiredAction][language], source: "next_required_action" };
  }

  return { text: GENERIC_NUDGE[language], source: "generic_nudge" };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

export function runHallucinationGuard(inputs: HallucinationGuardInputs): HallucinationGuardDecision {
  const reply = (inputs.replyText || "").trim();
  if (!reply) {
    return { replyText: inputs.replyText, blocked: false, claims: [], reason: null, substitutedFrom: "none" };
  }

  const claims: HallucinationKind[] = [];
  const reasons: string[] = [];

  // ----- Claim 1: field-rejection hallucination -----
  if (looksLikeFieldRejectionClaim(reply)) {
    const hasEvidence = fieldRejectionHasEvidence({
      rejections: inputs.rejectionsThisTurn,
      draft: inputs.entry?.bookingDraft || null,
      missingFields: inputs.missingFields,
    });
    if (!hasEvidence) {
      claims.push("field_rejection_hallucination");
      reasons.push("field_rejection_claim_without_evidence");
    }
  }

  // ----- Claim 2: order-placed hallucination -----
  if (looksLikeOrderPlacedClaim(reply)) {
    const stageNow = inputs.entry?.stage ?? null;
    const stageBefore = inputs.stageAtTurnStart;
    // Legitimate iff the controller is at `order_submitted` now. If the
    // stage transitioned THIS turn (before != submitted, now == submitted)
    // that's fine — the claim is grounded. If stage never reached
    // `order_submitted`, the claim is hallucinated.
    if (stageNow !== "order_submitted") {
      // Tolerate the case where stageBefore was already `order_submitted`
      // and the LLM is recapping a prior order (post-order chat). That's
      // also grounded.
      if (stageBefore !== "order_submitted") {
        claims.push("order_placed_hallucination");
        reasons.push("order_placed_claim_without_submitted_stage");
      }
    }
  }

  // ----- Claim 3: price mismatch -----
  const mentioned = extractMentionedPrices(reply);
  if (mentioned.length > 0) {
    const quoted = inputs.entry?.quotedPrice ?? null;
    if (quoted != null && priceDisagrees(mentioned, quoted)) {
      claims.push("price_mismatch");
      reasons.push(`price_mismatch mentioned=${mentioned.join(",")} quoted=${quoted}`);
    }
  }

  if (claims.length === 0) {
    return { replyText: inputs.replyText, blocked: false, claims: [], reason: null, substitutedFrom: "none" };
  }

  // Blocking policy. Priority order matches claims[] ordering above.
  //   - field_rejection_hallucination → substitute deterministic next step
  //   - order_placed_hallucination → substitute safe "still reviewing" ask
  //   - price_mismatch → substitute with order-summary if possible (fresh
  //     price from the authoritative entry), else generic nudge
  const primary = claims[0];

  if (primary === "order_placed_hallucination") {
    // We never pretend an order was placed. Fallback is a generic nudge
    // asking the customer to confirm the summary so the REAL order flow
    // can run.
    const entry = inputs.entry;
    if (entry && inputs.missingFields.length === 0 && entry.quotedPrice != null && entry.selectedDeliveryType) {
      const summary = buildDeterministicOrderSummary({ entry, language: inputs.language });
      return {
        replyText: summary,
        blocked: true,
        claims,
        reason: reasons.join("|"),
        substitutedFrom: "order_summary",
      };
    }
    return {
      replyText: GENERIC_NUDGE[inputs.language],
      blocked: true,
      claims,
      reason: reasons.join("|"),
      substitutedFrom: "generic_nudge",
    };
  }

  // field_rejection or price_mismatch → deterministic next-step substitute
  const sub = deterministicSubstitute({
    nextRequiredAction: inputs.nextRequiredAction ?? null,
    missingFields: inputs.missingFields,
    entry: inputs.entry,
    language: inputs.language,
  });
  return {
    replyText: sub.text,
    blocked: true,
    claims,
    reason: reasons.join("|"),
    substitutedFrom: sub.source,
  };
}

// ---------------------------------------------------------------------------
// Env-flag helper
// ---------------------------------------------------------------------------

export function isHallucinationGuardEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = env.RIDERS_HALLUCINATION_GUARD_ENABLED;
  if (raw == null) return true; // default ON
  const normalized = String(raw).trim().toLowerCase();
  if (["0", "false", "off", "no", "disabled"].includes(normalized)) return false;
  return true;
}
