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
import {
  getEffectiveDeliveryAreaName,
  getEffectivePickupAreaName,
} from "./conversation-policy";
import type { DialogState, SlotName } from "./dialog-state";
import { buildDeterministicOrderSummary } from "./outbound-verify";
import {
  renderDirectiveReply,
  isRegisteredDirectiveAction,
  type DirectiveReplyRendererContext,
} from "./directive-reply-registry";

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
  /**
   * All valid quoted prices for the active route, including the currently
   * selected option AND every other bookable/manual-confirmation option the
   * customer has the right to hear about. Passed in by the caller (the
   * octopus channel already has `activeQuotedRoute.pricesByType` in scope
   * at the point it invokes the guard).
   *
   * The guard uses this to decide whether a `price_mismatch` is real:
   * a mentioned price is only flagged when it falls OUTSIDE this whole set,
   * not just when it differs from the scalar `entry.quotedPrice` (which
   * tracks only the currently-selected option).
   *
   * Background — 2026-04-19 20:49:49 live incident:
   *   Customer: "is there other options"
   *   LLM:      "Yes, we also have Express sedan at 1.750 KWD, Standard
   *              box van at 1.750 KWD, and Express box van at 2.250 KWD…"
   *   Guard:    blocked=true reason=price_mismatch mentioned=1.75,1.75,2.25
   *              quoted=1.25 → substituted ASK_SENDER_NAME_AND_PHONE_DECISION.
   *
   * All three "mismatched" prices were real, persisted, active quoted
   * options. The guard should not have fired. With this field populated
   * from `activeQuotedRoute.pricesByType`, it no longer does.
   *
   * Optional; when absent the guard falls back to the legacy
   * `entry.quotedPrice`-only comparison for backwards compatibility with
   * callers that don't yet plumb this through. New callers MUST pass it.
   */
  activeQuotedPrices?: number[];
  /**
   * When set, the server-side cancel guard has determined that the LLM's
   * `cancel_booking` op was contradicted by the same utterance naming one
   * of the currently quoted options (the canonical "nvm pls standard
   * sedan" class — `nvm` read as cancel, `pls standard sedan` ignored).
   * The cancel op is NOT applied in that case, and the reply guard uses
   * this signal to suppress any "we've cancelled" text and substitute a
   * disambiguating re-ask.
   *
   * `optionLabel` is the customer-facing label of the option the customer
   * seems to be switching to, used to personalize the clarification.
   */
  cancelContradicted?: { optionLabel: string } | null;
};

export type HallucinationKind =
  | "field_rejection_hallucination"
  | "price_mismatch"
  | "order_placed_hallucination"
  | "cancel_misclassification"
  | "state_write_hallucination"
  | "stale_missing_field_ask";

export type HallucinationGuardDecision = {
  replyText: string;
  blocked: boolean;
  /** Claims detected (for logging / metrics). Multiple claims can fire on
   *  the same reply; only the highest-priority one dictates the substitute. */
  claims: HallucinationKind[];
  reason: string | null;
  /** Source of the substitute reply, for log triage.
   *
   *  `price_repair` is the neutral clarification used when `price_mismatch`
   *  fires — see §"Guards must not advance the flow" comment near
   *  `PRICE_REPAIR_TEMPLATE`. This source is distinct from
   *  `next_required_action` because a price-mismatch repair MUST NOT
   *  silently advance the conversation to the next slot ask; it repairs
   *  in place. */
  substitutedFrom:
    | "none"
    | "next_required_action"
    | "order_summary"
    | "generic_nudge"
    | "price_repair"
    | "cancel_repair"
    | "state_truth_repair";
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
  dialogState?: DialogState | null;
}): boolean {
  if (params.rejections.length > 0) return true;
  const draft = params.draft;
  if (!draft) return true; // no draft → we don't know; give benefit of the doubt

  // DST defense: if every core slot the LLM might be complaining about is
  // marked `filled` in the dialog state and we recorded no rejection for
  // this turn, the "please re-send X" claim is definitionally ungrounded.
  // DST status is stricter than legacy `isValidPhone/isValidName` checks
  // because it tracks explicit accept/reject history — a value that was
  // filled by the customer and never invalidated is trustworthy evidence.
  const dst = params.dialogState ?? null;
  if (dst) {
    const coreSlots: SlotName[] = [
      "sender_name",
      "sender_phone",
      "recipient_name",
      "recipient_phone",
    ];
    let anyConflict = false;
    let anyUnfilled = false;
    for (const name of coreSlots) {
      const slot = dst.slots[name];
      if (!slot) { anyUnfilled = true; continue; }
      if (slot.status === "conflict") anyConflict = true;
      else if (slot.status !== "filled") anyUnfilled = true;
    }
    // Conflict on a core slot → the LLM is legitimately asking the customer
    // to disambiguate. Don't flag the claim regardless of what the draft
    // mirror shows (mirror keeps the last-known-good value on conflict, so
    // the legacy validator would wrongly say "all valid").
    if (anyConflict) {
      return true;
    }
    // All filled + no conflict → claim is ungrounded.
    if (!anyUnfilled) {
      return false;
    }
    // anyUnfilled → fall through to the legacy draft-level check below.
  }

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

// Assertions that the booking/order has been cancelled. Paired with the
// server-side `cancelContradicted` signal so the guard fires only when
// the cancel op itself was rejected as a misclassification ("nvm pls
// standard sedan" class — see Bug 2 2026-04-20). Questions and offers
// about cancelling are intentionally NOT flagged.
const CANCEL_CLAIM_PATTERNS: RegExp[] = [
  /\b(?:we(?:'ve)?|i(?:'ve)?)\s+cancell?ed\b/i,
  /\byour\s+(?:booking|order|request)\s+(?:is|has\s+been)\s+cancell?ed\b/i,
  /\b(?:booking|order|request)\s+cancell?ed\b/i,
  /\bcancellation\s+(?:is\s+)?(?:done|complete|confirmed)\b/i,
  /(?:تم|تمت)\s+(?:الإلغاء|إلغاء)\s*(?:الطلب|الحجز)?/,
  /(?:الطلب|الحجز)\s+(?:تم\s+إلغاؤه|ملغى|ملغاة)/,
  /\bألغي(?:نا|ت|ناها)\b/,
  /\bبطل(?:ت|نا|نه)\b/,
];

export function looksLikeCancellationClaim(reply: string): boolean {
  if (/\b(?:do\s+you\s+want(?:\s+to)?|would\s+you\s+like\s+(?:me\s+)?to|shall\s+i|should\s+i)\s+cancel\b/i.test(reply)) {
    return false;
  }
  for (const re of CANCEL_CLAIM_PATTERNS) {
    if (re.test(reply)) return true;
  }
  return false;
}

type StateWriteClaimKind =
  | "pickup_area"
  | "delivery_area"
  | "sender_name"
  | "sender_phone"
  | "recipient_name"
  | "recipient_phone"
  | "pickup_pin"
  | "delivery_pin"
  | "delivery_option";

type StateWriteClaim = {
  kind: StateWriteClaimKind;
  value: string | null;
};

function normalizeStateClaimValue(value: string | null | undefined): string {
  return String(value || "")
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function trimClaimValue(raw: string | null | undefined): string | null {
  const value = String(raw || "")
    .split(/\b(?:send|share|please|pls|then|next|and\s+i(?:'|’)ll|so\s+i(?:'|’)ll)\b/i)[0]
    .replace(/^[\s:,-]+|[\s:,-]+$/g, "")
    .trim();
  return value.length >= 2 ? value : null;
}

function valueMatchesStoredClaim(
  claimed: string | null,
  stored: string | null | undefined,
): boolean {
  const storedNorm = normalizeStateClaimValue(stored);
  if (!storedNorm) return false;
  const claimedNorm = normalizeStateClaimValue(claimed);
  if (!claimedNorm) return true;
  return (
    storedNorm === claimedNorm ||
    storedNorm.includes(claimedNorm) ||
    claimedNorm.includes(storedNorm)
  );
}

function phoneClaimMatchesStored(
  claimed: string | null,
  stored: string | null | undefined,
): boolean {
  const storedDigits = String(stored || "").replace(/\D/g, "");
  if (!storedDigits) return false;
  const claimedDigits = String(claimed || "").replace(/\D/g, "");
  if (!claimedDigits) return true;
  return (
    storedDigits === claimedDigits ||
    storedDigits.endsWith(claimedDigits) ||
    claimedDigits.endsWith(storedDigits)
  );
}

const DELIVERY_OPTION_PROOF_ALIASES: Record<string, string[]> = {
  sedan_normal: [
    "standard sedan",
    "normal sedan",
    "regular sedan",
    "sedan normal",
    "standard car",
    "normal car",
  ],
  sedan_fast: [
    "express sedan",
    "fast sedan",
    "urgent sedan",
    "sedan fast",
    "express car",
    "fast car",
  ],
  van_normal: [
    "standard box van",
    "normal box van",
    "standard van",
    "normal van",
    "van normal",
  ],
  van_fast: [
    "express box van",
    "fast box van",
    "box van express",
    "box van fast",
    "express van",
    "fast van",
    "van fast",
  ],
  van_box_normal: [
    "standard box van",
    "normal box van",
    "standard van",
    "normal van",
    "box van normal",
  ],
  van_box_fast: [
    "express box van",
    "fast box van",
    "box van express",
    "box van fast",
    "express van",
    "fast van",
  ],
  cooled_van_normal: [
    "standard refrigerated van",
    "normal refrigerated van",
    "standard cooled van",
    "normal cooled van",
    "standard cold van",
    "normal cold van",
    "refrigerated van normal",
    "cooled van normal",
  ],
  cooled_van_fast: [
    "express refrigerated van",
    "fast refrigerated van",
    "express cooled van",
    "fast cooled van",
    "express cold van",
    "fast cold van",
    "refrigerated van fast",
    "cooled van fast",
  ],
  helper_standard: [
    "helper",
    "helper option",
    "with helper",
    "standard helper",
  ],
};

function deliveryOptionProofAliases(
  entry: PersistedConversationControllerEntry,
): string[] {
  const rawValues = [
    entry.selectedDeliveryType,
    entry.selectedQuoteOptionLabelEn,
    entry.selectedQuoteOptionLabelAr,
  ];
  const aliases = new Set<string>();
  for (const raw of rawValues) {
    const normalized = normalizeStateClaimValue(raw);
    if (normalized) aliases.add(normalized);
  }
  const typeKey = String(entry.selectedDeliveryType || "").trim();
  const fromType = DELIVERY_OPTION_PROOF_ALIASES[typeKey] || [];
  for (const alias of fromType) {
    const normalized = normalizeStateClaimValue(alias);
    if (normalized) aliases.add(normalized);
  }
  return [...aliases];
}

const DELIVERY_OPTION_PHRASE =
  "(?:(?:standard|normal|regular|express|fast|urgent)\\s+(?:sedan|car|box\\s+van|van|refrigerated\\s+van|cooled\\s+van|cold\\s+van)|(?:sedan|box\\s+van|van|refrigerated\\s+van|cooled\\s+van|cold\\s+van)\\s+(?:standard|normal|regular|express|fast|urgent)|helper)";

function extractClaimedDeliveryOption(reply: string): string | null {
  const patterns = [
    new RegExp(
      `\\b(?:selected|chosen|set|confirmed|marked)\\b[^.!?؟،\\n]{0,30}\\b(${DELIVERY_OPTION_PHRASE})\\b`,
      "i",
    ),
    new RegExp(
      `\\b(${DELIVERY_OPTION_PHRASE})\\b[^.!?؟،\\n]{0,40}\\b(?:selected|chosen|set|confirmed|marked)\\b`,
      "i",
    ),
  ];
  for (const pattern of patterns) {
    const match = pattern.exec(reply);
    const value = trimClaimValue(match?.[1] || null);
    if (value) return value;
  }
  return null;
}

function collectStateWriteClaims(reply: string): StateWriteClaim[] {
  const claims: StateWriteClaim[] = [];
  const text = reply.trim();
  if (!text) return claims;

  const add = (kind: StateWriteClaimKind, value?: string | null) => {
    claims.push({ kind, value: trimClaimValue(value) });
  };

  const areaPatterns: Array<[StateWriteClaimKind, RegExp[]]> = [
    [
      "pickup_area",
      [
        /\b(?:pickup|pick\s*up)\s+(?:area|location)?\s*(?:is\s+)?(?:noted|saved|set|marked|confirmed)\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
        /\b(?:noted|saved|set|marked|confirmed)\s+(?:the\s+)?(?:pickup|pick\s*up)\s+(?:area|location)?\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
      ],
    ],
    [
      "delivery_area",
      [
        /\b(?:delivery|drop\s*off|dropoff)\s+(?:area|location)?\s*(?:is\s+)?(?:noted|saved|set|marked|confirmed)\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
        /\b(?:noted|saved|set|marked|confirmed)\s+(?:the\s+)?(?:delivery|drop\s*off|dropoff)\s+(?:area|location)?\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
      ],
    ],
  ];
  for (const [kind, patterns] of areaPatterns) {
    for (const pattern of patterns) {
      const match = pattern.exec(text);
      if (match) {
        add(kind, match[1] || null);
        break;
      }
    }
  }

  const identityPatterns: Array<[StateWriteClaimKind, RegExp[]]> = [
    [
      "sender_name",
      [
        /\bsender(?:'s)?\s+name\s+(?:is\s+|(?:noted|saved|set|confirmed|marked)\s*(?:as|to)?\s*)([^.!?؟،,\n—]*)/i,
        /\b(?:noted|saved|set|confirmed|marked)\s+(?:sender(?:'s)?\s+)?name\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
      ],
    ],
    [
      "recipient_name",
      [
        /\brecipient(?:'s)?\s+name\s+(?:is\s+|(?:noted|saved|set|confirmed|marked)\s*(?:as|to)?\s*)([^.!?؟،,\n—]*)/i,
        /\b(?:noted|saved|set|confirmed|marked)\s+(?:recipient(?:'s)?\s+)?name\s*(?:as|to)?\s*([^.!?؟،,\n—]*)/i,
      ],
    ],
    [
      "sender_phone",
      [
        /\bsender(?:'s)?\s+(?:phone|number)\s+(?:is\s+|(?:noted|saved|set|confirmed|marked)\s*(?:as|to)?\s*)([\d\s+().-]{4,})?/i,
        /\b(?:noted|saved|set|confirmed|marked)\s+(?:sender(?:'s)?\s+)?(?:phone|number)\s*(?:as|to)?\s*([\d\s+().-]{4,})?/i,
      ],
    ],
    [
      "recipient_phone",
      [
        /\brecipient(?:'s)?\s+(?:phone|number)\s+(?:is\s+|(?:noted|saved|set|confirmed|marked)\s*(?:as|to)?\s*)([\d\s+().-]{4,})?/i,
        /\b(?:noted|saved|set|confirmed|marked)\s+(?:recipient(?:'s)?\s+)?(?:phone|number)\s*(?:as|to)?\s*([\d\s+().-]{4,})?/i,
      ],
    ],
  ];
  for (const [kind, patterns] of identityPatterns) {
    for (const pattern of patterns) {
      const match = pattern.exec(text);
      if (match) {
        add(kind, match[1] || null);
        break;
      }
    }
  }

  if (
    /\b(?:got|saved|received|have|marked|noted)\b[^.!?]{0,60}\b(?:pickup|pick\s*up)\b[^.!?]{0,30}\b(?:pin|location)\b/i.test(
      text,
    )
  ) {
    add("pickup_pin", null);
  }
  if (
    /\b(?:got|saved|received|have|marked|noted)\b[^.!?]{0,60}\b(?:delivery|drop\s*off|dropoff)\b[^.!?]{0,30}\b(?:pin|location)\b/i.test(
      text,
    )
  ) {
    add("delivery_pin", null);
  }
  if (
    /\b(?:selected|chosen|set|confirmed|marked)\b[^.!?]{0,50}\b(?:standard|express|sedan|van|box|helper)\b/i.test(
      text,
    ) ||
    /\b(?:standard|express|sedan|van|box|helper)\b[^.!?]{0,50}\b(?:selected|chosen|set|confirmed)\b/i.test(
      text,
    )
  ) {
    add("delivery_option", extractClaimedDeliveryOption(text));
  }

  return claims;
}

function deliveryOptionHasProof(
  claimed: string | null,
  entry: PersistedConversationControllerEntry | null,
): boolean {
  if (!entry) return false;
  const selected = deliveryOptionProofAliases(entry);
  if (selected.length === 0) return false;
  const claimNorm = normalizeStateClaimValue(claimed);
  if (!claimNorm) return true;
  return selected.some(
    (value) => claimNorm.includes(value) || value.includes(claimNorm),
  );
}

function stateWriteClaimHasProof(
  claim: StateWriteClaim,
  entry: PersistedConversationControllerEntry | null,
): boolean {
  const draft = entry?.bookingDraft || null;
  switch (claim.kind) {
    case "pickup_area":
      return valueMatchesStoredClaim(
        claim.value,
        getEffectivePickupAreaName(draft, entry),
      );
    case "delivery_area":
      return valueMatchesStoredClaim(
        claim.value,
        getEffectiveDeliveryAreaName(draft, entry),
      );
    case "sender_name":
      return valueMatchesStoredClaim(claim.value, draft?.senderName);
    case "recipient_name":
      return valueMatchesStoredClaim(claim.value, draft?.recipientName);
    case "sender_phone":
      return phoneClaimMatchesStored(claim.value, draft?.senderPhone);
    case "recipient_phone":
      return phoneClaimMatchesStored(claim.value, draft?.recipientPhone);
    case "pickup_pin":
      return !!draft?.pickupLocation;
    case "delivery_pin":
      return !!draft?.deliveryLocation;
    case "delivery_option":
      return deliveryOptionHasProof(claim.value, entry);
    default:
      return false;
  }
}

function findUnsupportedStateWriteClaim(
  reply: string,
  entry: PersistedConversationControllerEntry | null,
): StateWriteClaim | null {
  const claims = collectStateWriteClaims(reply);
  for (const claim of claims) {
    if (!stateWriteClaimHasProof(claim, entry)) {
      return claim;
    }
  }
  return null;
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

// A 0.05 KWD tolerance covers rounding variants ("1.25" vs "1.250")
// and bidi-digit normalization slop we see in Arabic-script replies.
const PRICE_MATCH_TOLERANCE_KWD = 0.05;

function pricesApproximatelyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) <= PRICE_MATCH_TOLERANCE_KWD;
}

/**
 * Decide whether any mentioned price is NOT accounted for by the active
 * route's valid price set.
 *
 * Pre-2026-04-19: this function compared every mentioned price against a
 * single scalar `entry.quotedPrice` — the currently-selected option's
 * price. That meant a legitimate "here are your other options" reply
 * (which mentions the non-selected options' prices) registered as a
 * price_mismatch on all of them. See the inline note on
 * `activeQuotedPrices` in `HallucinationGuardInputs` for the live
 * incident reference.
 *
 * New behavior:
 *   - Build the full set of valid prices from (a) every non-null value in
 *     `activeQuotedPrices` plus (b) the scalar `entry.quotedPrice` if
 *     present (belt-and-braces — selected price is almost always already
 *     in the full set, but we tolerate a caller that only passes one).
 *   - A mismatch fires only when at least one mentioned price is NOT in
 *     that full set (within tolerance). If every mentioned price is
 *     accounted for, the reply is grounded.
 *   - When the caller passed no set at all AND no scalar, we have no
 *     ground truth and cannot make the call — return `false` (no
 *     mismatch), erring on the side of letting the reply through. The
 *     outbound verify pass and the order-guard both fire separately on
 *     the create_simple_order boundary, so this is a safe no-op.
 */
function priceDisagrees(
  mentioned: number[],
  validSet: number[],
): boolean {
  if (mentioned.length === 0) return false;
  const cleanedValid = validSet.filter(
    (v) => typeof v === "number" && Number.isFinite(v) && v > 0,
  );
  if (cleanedValid.length === 0) return false;
  for (const m of mentioned) {
    if (!cleanedValid.some((v) => pricesApproximatelyEqual(m, v))) {
      return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Deterministic fallbacks
//
// Phase-B unification (2026-04-22): the guard-repair path and the normal
// directive-render path MUST produce the same ask for the same state.
// The guard delegates to `renderDirectiveReply` (moved to
// `shared/directive-reply-registry.ts` so guards can legally depend on
// it) for every ASK_* directive whose registry entry is server-rendered.
//
// Exceptions that stay guard-local:
//
//   - `GENERIC_NUDGE` — fires when we don't have a confident
//     `nextRequiredAction`. The registry has no matching directive because
//     the directive computer only emits a known action string (it never
//     says "I don't know what to ask next").
//
//   - `PRICE_REPAIR_TEMPLATE` — neutral in-place repair for
//     `price_mismatch`. Also has no registry equivalent: it's not a
//     server-ask directive, it's a don't-advance safety net.
//
//   - `cancelRepairText` — parameterised by the option label the customer
//     appears to be switching to (Bug 2, 2026-04-20). Not a registry
//     directive; parameterised fallback only.
//
//   - `POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF` — the registry
//     marks this directive `llm_owned` (post-order intent is context-
//     dependent), so `renderDirectiveReply` returns `{ kind: "llm_owned" }`.
//     The guard needs its own deterministic string for the "LLM
//     hallucinated an order-placed state" repair path, so this one entry
//     stays. All other ASK_* templates have been removed from the guard.
// ---------------------------------------------------------------------------

type NextStepTemplate = {
  en: string;
  ar: string;
};

const POST_ORDER_NUDGE: NextStepTemplate = {
  en: "Your order is already placed. Track it, cancel it, or connect with our team?",
  ar: "طلبك مسجل بالفعل. تتبّعه، إلغاؤه، أو التواصل مع فريقنا؟",
};

const GENERIC_NUDGE: NextStepTemplate = {
  en: "Let me double-check — could you confirm the pickup and delivery areas?",
  ar: "للتأكد — ممكن تأكد لنا منطقة الاستلام ومنطقة التوصيل؟",
};

// -----------------------------------------------------------------------
// Guards must not advance the flow.
//
// When a hallucination check fires, the safety net should REPAIR IN PLACE
// — it should not silently push the conversation to the next slot. The
// pre-2026-04-19 behavior routed every blocked reply through
// `deterministicSubstitute(next_required_action)`, which meant a
// false-positive price-mismatch on a legitimate "here are the other
// options" answer produced the sender-phone ask as the customer-visible
// repair. That is the wrong blast radius: the customer's question was
// never answered, and the booking state jumped forward.
//
// The price-mismatch repair is deliberately a neutral re-ask that keeps
// the conversation parked on the price question. If the guard misfires,
// the customer sees "let me re-check — which option are you asking
// about?", not the next slot ask.
//
// `field_rejection_hallucination` stays on the ASK_* path on purpose:
// when the LLM falsely claims a customer-provided field is invalid,
// the correct repair IS to re-ask the real next required slot — the
// LLM's claim was about the wrong field, so the server's ground truth
// of what's actually missing is the right thing to render.
// -----------------------------------------------------------------------
const PRICE_REPAIR_TEMPLATE: NextStepTemplate = {
  en: "Sorry, let me re-check that — which option are you asking about?",
  ar: "عذراً، دعني أتأكد من ذلك — عن أي خيار تسأل تحديداً؟",
};

const STATE_TRUTH_REPAIR_TEMPLATE: NextStepTemplate = {
  en: "Sorry, I don’t have that saved yet. Please send that detail again and I’ll continue.",
  ar: "عذراً، ما انحفظت عندي للحين. ارسل المعلومة مرة ثانية ونكمل.",
};

const STATE_WRITE_CLAIM_LABELS: Record<StateWriteClaimKind, NextStepTemplate> = {
  pickup_area: { en: "pickup area", ar: "منطقة الاستلام" },
  delivery_area: { en: "delivery area", ar: "منطقة التوصيل" },
  sender_name: { en: "sender name", ar: "اسم المرسل" },
  sender_phone: { en: "sender phone", ar: "رقم المرسل" },
  recipient_name: { en: "recipient name", ar: "اسم المستلم" },
  recipient_phone: { en: "recipient phone", ar: "رقم المستلم" },
  pickup_pin: { en: "pickup location pin", ar: "لوكيشن الاستلام" },
  delivery_pin: { en: "delivery location pin", ar: "لوكيشن التوصيل" },
  delivery_option: { en: "delivery option", ar: "خيار التوصيل" },
};

function stateTruthRepairText(
  claim: StateWriteClaim | null,
  language: HallucinationGuardLanguage,
): string {
  if (!claim) return STATE_TRUTH_REPAIR_TEMPLATE[language];
  const label = STATE_WRITE_CLAIM_LABELS[claim.kind]?.[language];
  if (!label) return STATE_TRUTH_REPAIR_TEMPLATE[language];
  if (language === "ar") {
    return `عذراً، ما قدرت أتأكد من ${label}. ارسله مرة ثانية ونكمل.`;
  }
  return `Sorry, I couldn't verify the ${label}. Please send that detail again and I’ll continue.`;
}

type AddressSubfieldAsk = {
  side: "pickup" | "delivery";
  subfield: "address" | "block" | "street_or_avenue" | "house_or_unit";
};

const ADDRESS_REQUEST_RE =
  /\b(?:still\s+need|need|missing|send|provide|give|what(?:'s|\s+is)|please|pls)\b|[?؟]|(?:ارسل|أرسل|نحتاج|احتاج|شنو|ما هو|ماهي)/i;

const ADDRESS_SIDE_RE: Record<AddressSubfieldAsk["side"], RegExp> = {
  pickup: /\b(?:pickup|pick\s*up|sender)\b|(?:استلام|المرسل)/i,
  delivery: /\b(?:delivery|drop\s*off|dropoff|recipient)\b|(?:توصيل|تسليم|المستلم)/i,
};

const ADDRESS_SUBFIELD_RE: Record<AddressSubfieldAsk["subfield"], RegExp> = {
  address: /\b(?:address|details?)\b|(?:عنوان|تفاصيل)/i,
  block: /\bblock\b|(?:قطعة|قطعه|بلوك)/i,
  street_or_avenue: /\b(?:street|avenue|jadda|jedda)\b|(?:شارع|جادة|جاده)/i,
  house_or_unit:
    /\b(?:house|building|bldg|tower|villa|apartment|apartement|apt|appt|flat|floor|door|unit|office|gate)\b|(?:بيت|منزل|بناية|بنايه|عمارة|عماره|برج|فيلا|شقة|شقه|دور|طابق|باب|وحدة|وحده|مكتب|بوابة|بوابه)/i,
};

function findStaleAddressSubfieldAsk(
  reply: string,
  missingFields: string[],
): AddressSubfieldAsk | null {
  const askClauses = reply
    .split(/(?:[.!؟\n]+|[?]+)/)
    .map((part) => part.trim())
    .filter((part) => part && ADDRESS_REQUEST_RE.test(part));
  if (askClauses.length === 0) return null;
  for (const side of ["pickup", "delivery"] as const) {
    if (missingFields.includes(`${side}.address`)) continue;
    for (const clause of askClauses) {
      if (!ADDRESS_SIDE_RE[side].test(clause)) continue;
      for (const subfield of [
        "block",
        "street_or_avenue",
        "house_or_unit",
        "address",
      ] as const) {
        if (!ADDRESS_SUBFIELD_RE[subfield].test(clause)) continue;
        const marker =
          subfield === "address" ? `${side}.address` : `${side}.${subfield}`;
        if (!missingFields.includes(marker)) {
          return { side, subfield };
        }
      }
    }
  }
  return null;
}

// -----------------------------------------------------------------------
// Cancel-vs-switch repair.
//
// Fires when the server-side cancel guard flagged this turn's
// `cancel_booking` op as contradicted by an option mention in the same
// utterance (Bug 2, 2026-04-20 — "nvm pls standard sedan" was
// classified as cancel). The LLM's reply typically contains cancel
// language ("we've cancelled the booking"), which is now ungrounded
// because the server refused to apply the cancel. The substitute is a
// disambiguating re-ask that names the option the customer seems to be
// switching to, so the customer can confirm or correct without losing
// their current quoted route.
//
// Why parameterised: the option label comes from the route's
// `label_en`/`label_ar` so the customer sees the same wording the
// server uses everywhere else.
// -----------------------------------------------------------------------
function cancelRepairText(
  optionLabel: string,
  language: HallucinationGuardLanguage,
): string {
  const safeLabel = (optionLabel || "").trim() || (language === "ar" ? "هذا الخيار" : "that option");
  if (language === "ar") {
    return `تكرماً، للتوضيح — تبي تبدل إلى "${safeLabel}" لنفس المسار، أو إلغاء الطلب كلياً؟`;
  }
  return `Just to confirm — would you like to switch to "${safeLabel}" for this route, or cancel the booking entirely?`;
}

function getConflictDirectiveContext(
  entry: PersistedConversationControllerEntry | null,
): {
  conflictingSlot: string | null;
  conflictValues: { incoming: string; existing: string } | null;
} {
  const slots = entry?.dialogState?.slots || {};
  for (const [slot, rec] of Object.entries(slots)) {
    if (!rec || rec.status !== "conflict") continue;
    const incoming = rec.conflictCandidate || null;
    const existing = rec.value || null;
    return {
      conflictingSlot: slot,
      conflictValues: incoming && existing ? { incoming, existing } : null,
    };
  }
  return { conflictingSlot: null, conflictValues: null };
}

/**
 * Pick a deterministic substitute based on next-required-action + the
 * granular missing sub-fields the address model now emits. Falls back to
 * a generic nudge when we don't have a confident ask.
 *
 * Phase-B unification (2026-04-22): for every ASK_* directive whose
 * registry entry is `{ kind: "server" }`, this function delegates to
 * `renderDirectiveReply` so the guard-repair path and the normal
 * directive-render path produce IDENTICAL text for identical state.
 *
 * The address-subfield specialization (block / street_or_avenue /
 * house_or_unit) is kept as a refinement IN FRONT of the registry call:
 * when `missingFields` names specific sub-fields the customer hasn't
 * filled, the guard surfaces just those instead of the generic
 * "block, street, building/apartment?" ask. This is a strict superset of
 * what the registry alone can express, and it uses evidence the registry
 * doesn't receive (`missingFields`).
 */
function deterministicSubstitute(params: {
  nextRequiredAction: string | null;
  missingFields: string[];
  entry: PersistedConversationControllerEntry | null;
  language: HallucinationGuardLanguage;
}): { text: string; source: HallucinationGuardDecision["substitutedFrom"] } {
  const { nextRequiredAction, missingFields, entry, language } = params;

  // Refine address asks using the granular sub-field markers. This
  // lives IN FRONT of the registry delegation because the registry
  // renderers don't see `missingFields`.
  if (nextRequiredAction === "ASK_PICKUP_ADDRESS" || nextRequiredAction === "ASK_DELIVERY_ADDRESS") {
    const side: "pickup" | "delivery" = nextRequiredAction === "ASK_PICKUP_ADDRESS" ? "pickup" : "delivery";
    const subs: string[] = [];
    if (missingFields.includes(`${side}.block`)) subs.push(language === "ar" ? "القطعة" : "block");
    if (missingFields.includes(`${side}.street_or_avenue`)) subs.push(language === "ar" ? "الشارع أو الجادة" : "street or avenue");
    if (missingFields.includes(`${side}.house_or_unit`)) subs.push(language === "ar" ? "رقم المبنى أو الشقة" : "building number or apartment/tower");
    if (subs.length > 0) {
      const sideLabel = language === "ar"
        ? (side === "pickup" ? "الاستلام" : "التوصيل")
        : side;
      const text = language === "ar"
        ? `${subs.join("، ")} لعنوان ${sideLabel}؟`
        : `${subs.join(" and ")} for the ${sideLabel} address?`;
      return { text, source: "next_required_action" };
    }
    // Fall through to registry delegation when no sub-fields are named.
  }

  // Registry delegation. Single source of truth: the same text the
  // directive-render path would produce for this state.
  if (nextRequiredAction && entry && isRegisteredDirectiveAction(nextRequiredAction)) {
    const conflictCtx =
      nextRequiredAction === "CONFIRM_SLOT_CONFLICT"
        ? getConflictDirectiveContext(entry)
        : { conflictingSlot: null, conflictValues: null };
    const ctx: DirectiveReplyRendererContext = {
      language,
      draft: entry.bookingDraft,
      entry,
      conflictingSlot: conflictCtx.conflictingSlot,
      conflictValues: conflictCtx.conflictValues,
      // Seed is irrelevant post-Phase-B-trim for all ASK_* directives
      // (single phrasing each), but the registry still accepts it.
      // Stable per-entry so that any future reintroduction of a pool
      // stays deterministic per conversation.
      turnSeed: String(entry.lastActivityTs ?? 0),
    };
    const res = renderDirectiveReply(nextRequiredAction, ctx);
    if (res.kind === "render") {
      const sourceTag: HallucinationGuardDecision["substitutedFrom"] =
        nextRequiredAction === "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED"
          ? "order_summary"
          : "next_required_action";
      return { text: res.text, source: sourceTag };
    }
    // `llm_owned` / `existing` / `unknown_action` fall through to the
    // guard-local fallbacks below.
  }

  // Legacy summary branch — covers the case where `entry` is present but
  // the registry returned a non-render result (shouldn't normally
  // happen, but preserves the prior behavior as a safety net).
  if (nextRequiredAction === "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED" && entry) {
    return { text: buildDeterministicOrderSummary({ entry, language }), source: "order_summary" };
  }

  // Post-order intent is `llm_owned` in the registry. Use the guard's
  // own deterministic repair here because we CAN'T let a hallucinated
  // order-placed claim go out with LLM-generated repair text.
  if (nextRequiredAction === "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF") {
    return { text: POST_ORDER_NUDGE[language], source: "next_required_action" };
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
      dialogState: inputs.entry?.dialogState ?? null,
    });
    if (!hasEvidence) {
      claims.push("field_rejection_hallucination");
      reasons.push("field_rejection_claim_without_evidence");
    }
  }

  // ----- Claim 2b: cancel-misclassification -----
  //
  // Only fires when BOTH (a) the reply asserts a cancellation (not asks
  // / offers one) AND (b) the caller has signalled that the server-side
  // cancel guard rejected this turn's cancel op as contradicted by an
  // option mention in the same utterance. Without the (b) signal the
  // guard stays silent — legitimate post-cancel acknowledgements are
  // still passed through.
  if (inputs.cancelContradicted && looksLikeCancellationClaim(reply)) {
    claims.push("cancel_misclassification");
    reasons.push("cancel_claim_with_server_contradicted_intent");
  }

  // ----- Claim 2c: state-write hallucination -----
  //
  // The LLM can word the reply, but it cannot claim a transactional fact was
  // saved unless the post-drain controller state proves that fact exists.
  // This catches replies like "Pickup area noted as Zahra" when get_price /
  // set_pending_area never fired and the controller is still idle.
  let unsupportedStateClaim: StateWriteClaim | null = findUnsupportedStateWriteClaim(reply, inputs.entry);
  if (unsupportedStateClaim) {
    claims.push("state_write_hallucination");
    reasons.push(
      `state_write_claim_without_evidence kind=${unsupportedStateClaim.kind}` +
        (unsupportedStateClaim.value
          ? ` value=${unsupportedStateClaim.value}`
          : ""),
    );
  }

  // ----- Claim 2d: stale missing-field ask -----
  //
  // `missingFields` is the server-computed truth after this turn's writes.
  // If the reply asks for an address subfield on a side whose address is no
  // longer missing, the LLM is reasoning from raw nulls (e.g. house=null)
  // instead of the satisfaction predicate (e.g. extra=Apartment/Floor/Door).
  const staleAddressAsk = findStaleAddressSubfieldAsk(reply, inputs.missingFields);
  if (staleAddressAsk) {
    claims.unshift("stale_missing_field_ask");
    reasons.unshift(
      `address_subfield_ask_without_missing side=${staleAddressAsk.side} subfield=${staleAddressAsk.subfield}`,
    );
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
  //
  // The valid set is the union of:
  //   - every non-null price from the active route's quoted options
  //     (`activeQuotedPrices` — passed in by the caller from
  //     `activeQuotedRoute.pricesByType`), and
  //   - the scalar `entry.quotedPrice` (the currently-selected option's
  //     price — almost always already in the set above, but we tolerate
  //     the legacy path where only the scalar is available).
  //
  // A mismatch fires only when a mentioned price falls OUTSIDE the
  // whole set, not just when it differs from the selected scalar.
  const mentioned = extractMentionedPrices(reply);
  if (mentioned.length > 0) {
    const validSet: number[] = [];
    if (Array.isArray(inputs.activeQuotedPrices)) {
      for (const p of inputs.activeQuotedPrices) {
        if (typeof p === "number" && Number.isFinite(p) && p > 0) {
          validSet.push(p);
        }
      }
    }
    const selectedScalar = inputs.entry?.quotedPrice ?? null;
    if (selectedScalar != null && Number.isFinite(selectedScalar)) {
      validSet.push(selectedScalar);
    }
    if (validSet.length > 0 && priceDisagrees(mentioned, validSet)) {
      claims.push("price_mismatch");
      reasons.push(
        `price_mismatch mentioned=${mentioned.join(",")} valid=${validSet.join(",")}`,
      );
    }
  }

  if (claims.length === 0) {
    return { replyText: inputs.replyText, blocked: false, claims: [], reason: null, substitutedFrom: "none" };
  }

  // Blocking policy. Priority order matches claims[] ordering above.
  //
  //   - field_rejection_hallucination → deterministic next-required-step.
  //     The LLM's false claim was "your field is invalid"; the correct
  //     server-grounded repair is to re-ask the slot the server actually
  //     needs. This is the one case where the substitute legitimately
  //     advances to the next ask.
  //
  //   - order_placed_hallucination → summary (if ready) or generic nudge.
  //     Safe because neither advances the flow past the confirmation
  //     step — the LLM falsely claimed "placed", so we re-present the
  //     summary (still pre-submit) or nudge.
  //
  //   - price_mismatch → neutral in-place repair. MUST NOT substitute
  //     with `next_required_action`. See the block comment on
  //     `PRICE_REPAIR_TEMPLATE` above for the full rationale.
  const primary = claims[0];

  // Cancel-misclassification dispatch. Highest priority when present:
  // the customer's intent was misread by the LLM, the server has
  // refused to apply the cancel, and the reply must not go out
  // asserting a cancellation that did not happen. Substitute with a
  // neutral re-ask that names the option the customer appears to be
  // switching to. See `cancelRepairText`.
  if (claims.includes("cancel_misclassification") && inputs.cancelContradicted) {
    return {
      replyText: cancelRepairText(inputs.cancelContradicted.optionLabel, inputs.language),
      blocked: true,
      claims,
      reason: reasons.join("|"),
      substitutedFrom: "cancel_repair",
    };
  }

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

  if (primary === "price_mismatch") {
    // Neutral in-place repair — do NOT advance to the next slot ask.
    // See `PRICE_REPAIR_TEMPLATE` block comment for the "guards are not
    // advancement engines" principle.
    return {
      replyText: PRICE_REPAIR_TEMPLATE[inputs.language],
      blocked: true,
      claims,
      reason: reasons.join("|"),
      substitutedFrom: "price_repair",
    };
  }

  if (primary === "state_write_hallucination") {
    const entry = inputs.entry;
    if (
      entry &&
      inputs.missingFields.length === 0 &&
      entry.quotedPrice != null &&
      entry.selectedDeliveryType
    ) {
      return {
        replyText: buildDeterministicOrderSummary({ entry, language: inputs.language }),
        blocked: true,
        claims,
        reason: reasons.join("|"),
        substitutedFrom: "order_summary",
      };
    }
    if (inputs.nextRequiredAction) {
      const sub = deterministicSubstitute({
        nextRequiredAction: inputs.nextRequiredAction,
        missingFields: inputs.missingFields,
        entry: inputs.entry,
        language: inputs.language,
      });
      if (sub.source !== "generic_nudge") {
        return {
          replyText: sub.text,
          blocked: true,
          claims,
          reason: reasons.join("|"),
          substitutedFrom: sub.source,
        };
      }
    }
    return {
      replyText: stateTruthRepairText(unsupportedStateClaim, inputs.language),
      blocked: true,
      claims,
      reason: reasons.join("|"),
      substitutedFrom: "state_truth_repair",
    };
  }

  if (primary === "stale_missing_field_ask") {
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

  // field_rejection_hallucination → deterministic next-required-step
  // substitute. Legitimately advances, because the LLM's false claim was
  // about a field being invalid, and re-asking the actual next slot is
  // the correct server-grounded repair.
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
