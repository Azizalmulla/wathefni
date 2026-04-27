/**
 * Outbound reply verification loop (ONE-BRAIN).
 *
 * Phase-2 deterministic backstop for LLM reply drift. Even with strict tool
 * schemas, SKILL.md rules, and the `next_required_action` directive, the agent
 * can still emit shapes that break the experience — most notably:
 *   - STUB_SUMMARY: booking draft is complete but the reply is a one-liner
 *     that skips most fields ("all set, ready to confirm?").
 *   - ROUTE_PRICE_RECAP: mid-booking reply that's just "Delivery from X to Y,
 *     1.250 KWD" — a pre-booking shape reused after clarification turns.
 *   - STANDALONE_ACK: bare acknowledgement ("Sure", "Noted", "تمام") when the
 *     next action is known.
 *
 * This module classifies outbound replies using cheap regex / field-presence
 * heuristics (no LLM), and when a bad shape is detected in a state where we
 * know the correct output, substitutes a deterministic canonical reply built
 * from the booking draft. The customer never sees the stub; the LLM's job
 * gets easier on the next turn because the summary is already on the record.
 *
 * This is the pattern described in the 2026 "Output Verification Loop"
 * agentic-patterns guide, adapted for a slot-filling booking flow.
 */

import type {
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
} from "./conversation-policy";
import type { BookingTruthSnapshot } from "./booking-truth-snapshot";

export type OutboundReplyShape =
  | "ok"
  | "stub_summary"
  | "route_price_recap"
  | "route_zero_distance"
  | "standalone_ack"
  | "summary_fact_drift"
  | "clarifying_question"
  | "empty";

export type VerifyOutboundParams = {
  replyText: string;
  entry: PersistedConversationControllerEntry | null;
  missingFields: string[];
  language: "ar" | "en";
  summaryCompletionCheckpoint?: boolean;
  bookingTruthSnapshot?: BookingTruthSnapshot | null;
};

export type VerifyOutboundResult = {
  replyText: string;
  replaced: boolean;
  shape: OutboundReplyShape;
  reason: string | null;
};

const STANDALONE_ACK_RE =
  /^(?:sure|noted|understood|okay|ok|got it|we(?:'| a)?ll? proceed|will do|alright|fine|done|confirmed|acknowledged|received|تمام|حسنا|تم|حاضر|اكيد|اوكي|اوك)[\s.!؟?،,]*$/i;

function normalizeForCompare(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Class-15 detector: does the reply look like a free-composed area
 * clarification (LLM asking "what's the pickup/delivery area?" or "which
 * part of X?") on a turn where the server knows `get_price` was not
 * called?
 *
 * ## Why this exists
 *
 * On `stage=idle` + route-intent inbound (e.g. "delivery salmiya to
 * kuwait city pls"), the architectural contract is: the LLM calls
 * `get_price`, the tool returns `clarification_required` for the broad
 * leg, and the LLM relays the tool-owned clarification. When the LLM
 * instead free-composes an area ask WITHOUT calling `get_price`, no
 * responder-state ops are emitted — `pendingPickupAreaNameEn` /
 * `requestedSlot` stay null — so the next customer reply gets bound by
 * the LLM under no server-owned context and collapses the route
 * (symmetric-rebind class downstream).
 *
 * This detector matches the FORM of the drift (the free-composed
 * clarification question). The caller combines it with two facts it
 * already knows (`hasRouteEvidence(inbound) === true` and
 * `get_price` was NOT called this turn) to confirm a Class-15 bypass
 * and substitute a short server-composed repair that keeps the
 * conversation on track deterministically.
 *
 * ## Patterns matched
 *
 * Intentionally NARROW — short, question-shaped replies about
 * pickup / delivery / دwhich-part-of-X. Summary, recap, and generic
 * helper asks are deliberately excluded: those live in other shapes
 * (`route_price_recap`, `stub_summary`) and have their own handling.
 */
const FREE_COMPOSED_AREA_QUESTION_EN = [
  // "What's the pickup/delivery area?" / "What is the pickup area?"
  /\b(?:what(?:'s|\s+is)|which)\b[^?]{0,40}\b(?:pickup|delivery|dropoff|drop[\s-]?off)\s*(?:area|location|from|to)?\s*\??/i,
  // "Which part of <X>?" / "Where in <X>?"
  /\b(?:which\s+(?:part|area|neighbou?rhood|district)\s+of|where\s+in)\s+[A-Za-z'\- ]{3,40}\??/i,
  // "Please clarify the pickup/delivery area" / "Could you clarify ..."
  /\b(?:please\s+clarify|could\s+you\s+clarify|can\s+you\s+clarify|clarify\s+(?:the|your))\b[^?]{0,40}\b(?:pickup|delivery|dropoff|drop[\s-]?off|area)\b/i,
  // "Share/send the pickup and delivery areas" without a price, a grounded
  // recap, or a completed-booking signal (we gate context-sensitively in
  // the caller).
  /\b(?:send|share|tell\s+(?:me|us))\b[^?]{0,40}\b(?:pickup|delivery|dropoff|drop[\s-]?off)\s*(?:area|location)?\b/i,
];

const FREE_COMPOSED_AREA_QUESTION_AR = [
  // "شنو/ما هي/أي منطقة الاستلام/التوصيل"
  /(?:شنو|شو|ما\s*هي|ماهي|أي|اي|وين|فين|ايش)\s*[^؟?]{0,40}(?:منطقة\s*(?:الاستلام|التوصيل|الاستلام|الايصال|الايصال))/u,
  // "أي جزء من <X>؟"
  /(?:أي|اي)\s*(?:جزء|منطقة|حي)\s*من\s+[^؟?]{2,40}[؟?]/u,
  // "أرسل/عطنا منطقة الاستلام/التوصيل"
  /(?:أرسل|ارسل|عطنا|ابعت|ابعث)\s*[^؟?]{0,30}(?:منطقة\s*(?:الاستلام|التوصيل))/u,
];

const PRICE_TOKEN_RE = /\b\d+(?:[.,]\d{1,3})?\s*(?:kwd|kd|د\.?ك|دينار|dinars?)\b/i;

export function looksLikeFreeComposedAreaClarification(
  reply: string,
): boolean {
  if (!reply) return false;
  const text = reply.trim();
  if (text.length === 0 || text.length > 280) return false;
  // Replies that quote a price are NOT free-composed area questions —
  // those are route_price_recap / full-quote replies and have their own
  // handling path. Narrowing here keeps this detector scoped to the
  // "I'm asking for an area without talking to the tool" shape.
  if (PRICE_TOKEN_RE.test(text)) return false;
  // Require an interrogative token (Latin `?` or Arabic `؟`) OR a
  // clear imperative verb ("please send/share ..."). Otherwise the
  // caller's state-gating would carry the risk of suppressing
  // legitimate non-question replies.
  const hasQuestionMark = /[?؟]/.test(text);
  if (!hasQuestionMark) {
    // Imperative-only shapes still qualify if they name an area slot
    // explicitly — e.g. "Please share the pickup area".
    const imperativeWithArea =
      /\b(?:please\s+)?(?:send|share|tell)\b[^.!?؟]{0,40}\b(?:pickup|delivery|dropoff|drop[\s-]?off)\s*(?:area|location)\b/i.test(
        text,
      ) ||
      /(?:أرسل|ارسل|عطنا|ابعت|ابعث)\s*[^.!?؟]{0,30}(?:منطقة\s*(?:الاستلام|التوصيل))/u.test(
        text,
      );
    if (!imperativeWithArea) return false;
  }
  for (const re of FREE_COMPOSED_AREA_QUESTION_EN) {
    if (re.test(text)) return true;
  }
  for (const re of FREE_COMPOSED_AREA_QUESTION_AR) {
    if (re.test(text)) return true;
  }
  return false;
}

/**
 * Server-composed repair reply for the Class-15 bypass class (2026-04-21).
 *
 * Printed when the LLM free-composed an area clarification on a
 * route-intent turn without calling `get_price`. Tight invariants:
 *
 *   - Short (fits in one WhatsApp bubble) so the UX doesn't feel like
 *     a system error page.
 *   - Explicit about what the customer should do ("send pickup and
 *     delivery together") so the next turn contains a full route that
 *     will survive to the tool call, rather than a single-token answer
 *     that the server would have to re-interpret under a missing
 *     `requestedSlot`.
 *   - Deterministic phrasing — we do NOT pool across variants here.
 *     This reply is an exception path the customer should only ever
 *     see rarely; variability would just make the class harder to
 *     detect in logs.
 */
export function buildClass15BypassRepairReply(
  language: "ar" | "en",
): string {
  if (language === "ar") {
    return "لحظة — عطنا منطقة الاستلام ومنطقة التوصيل سوا في رسالة وحدة عشان نطلع السعر الصحيح.";
  }
  return "One moment — please send the pickup area and the delivery area together so I can quote the correct price.";
}

/**
 * Does the reply text look like a "route + price recap" with nothing else?
 * This shape is only legal as a pre-booking quote presentation. Once booking
 * has started, it's a stub. We detect by: short text (<= ~160 chars), AND
 * contains a price-like token AND a route-like token AND is missing any of
 * the key booking fields (sender/recipient name, phone) AND contains no
 * explicit next-step ask (a question mark or an imperative asking for the
 * next field). A recap-PLUS-ask is a legitimate first-collection turn, not
 * a bare recap, and must not be flagged.
 */
function looksLikeRoutePriceRecap(reply: string, draft: PersistedBookingDraft | null): boolean {
  const lineCount = reply.split(/\r?\n/).filter((l) => l.trim()).length;
  if (reply.length > 200 || lineCount > 3) return false;

  const priceLike = /(\d+(?:[.,]\d{1,3})?)\s*(?:kwd|kd|د\.?ك|دينار|dinars?)/i.test(reply);
  const routeLike = /(?:from|to|من|الى|إلى|→|->)/i.test(reply);
  if (!priceLike || !routeLike) return false;

  if (!draft) return false;

  // Recap + explicit next-step ask = legitimate first-collection turn, not a
  // bare recap. The LLM is correctly saying "price is X, send me the sender
  // info". Don't flag. We detect an ask via either a question mark or a
  // common imperative verb (send / share / please + Arabic equivalents).
  const hasExplicitAsk =
    /[?؟]/.test(reply) ||
    /\b(send|share|please|could\s+you|kindly)\b/i.test(reply) ||
    /(أرسل|ارسل|ابعت|ابعثي|شارك|تفضل|من\s*فضلك|لو\s*سمحت)/.test(reply);
  if (hasExplicitAsk) return false;

  const lower = reply.toLowerCase();
  const mentions = (value: string | null | undefined): boolean => {
    if (!value) return false;
    const v = value.trim().toLowerCase();
    if (v.length < 3) return false;
    return lower.includes(v);
  };

  // If the reply mentions any of the collected-customer-identity fields, it's
  // probably a proper summary (or a summary-plus-price), not a bare recap.
  const mentionsIdentity =
    mentions(draft.senderName) ||
    mentions(draft.recipientName) ||
    (draft.senderPhone ? lower.includes(draft.senderPhone.slice(-4)) : false) ||
    (draft.recipientPhone ? lower.includes(draft.recipientPhone.slice(-4)) : false);

  return !mentionsIdentity;
}

/**
 * Given a complete booking draft + quoted price, does the reply actually
 * look like a full, STRUCTURED customer-facing summary?
 *
 * Two bars, both required:
 *   (a) Content: at least 3 of { sender_name, recipient_name, last4 of a
 *       phone, price, service-type token } are mentioned. Any less and the
 *       LLM is clearly skipping fields.
 *   (b) Structure: at least 4 distinct "Label: value" rows on separate
 *       lines, OR at least 3 rows that start with a canonical summary label
 *       (Pickup / Delivery / Sender / Recipient / Service / Price / their
 *       Arabic equivalents). A run-on paragraph with all the facts baked
 *       into prose fails this bar and gets substituted with the canonical
 *       structured summary.
 *
 * The structural bar is what kicks us out of the "paragraph summary" trap
 * where the LLM dumps everything into one sentence like:
 *   "Delivery from Jabriya to Surra for Aziz (97485757) to Ahmad (62844738),
 *    sedan normal, 1.250 KWD. Confirm?"
 * That line has all the signals but reads as prose, not a summary. Customers
 * find it hard to verify at a glance — WhatsApp summaries need rows.
 */
function replyLooksLikeFullSummary(reply: string, entry: PersistedConversationControllerEntry): boolean {
  const draft = entry.bookingDraft;
  const lower = reply.toLowerCase();
  let signals = 0;

  if (draft.senderName && lower.includes(draft.senderName.toLowerCase())) signals++;
  if (draft.recipientName && lower.includes(draft.recipientName.toLowerCase())) signals++;
  if (draft.senderPhone && lower.includes(draft.senderPhone.slice(-4))) signals++;
  if (draft.recipientPhone && lower.includes(draft.recipientPhone.slice(-4))) signals++;

  if (entry.quotedPrice != null) {
    const priceStr = entry.quotedPrice.toFixed(3);
    const priceIntStr = entry.quotedPrice.toFixed(0);
    if (lower.includes(priceStr) || lower.includes(priceIntStr)) signals++;
  }

  if (entry.selectedDeliveryType) {
    const type = entry.selectedDeliveryType.toLowerCase();
    if (lower.includes(type.replace("_", " ")) || lower.includes(type.split("_")[0])) signals++;
  }

  if (signals < 3) return false;

  // Structural bar. A canonical summary has labeled rows on separate lines.
  const lines = reply.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length < 4) return false;

  // "Label: value" row detection — tolerant of WhatsApp-bold (*Label*), list
  // markers (-, •), and leading emoji. Label length cap keeps us from
  // matching sentences like "I'll check the address: ...".
  const labeledRowRe = /^[\*\-•\s>]*[A-Za-z\u0600-\u06FF][^:：\n]{0,40}[:：]\s*\S/;
  const labeledRows = lines.filter((l) => labeledRowRe.test(l)).length;
  if (labeledRows >= 4) return true;

  // Canonical-label fallback. Even with fewer generic labeled rows, a reply
  // that starts multiple lines with the canonical summary fields qualifies.
  const canonicalLabelRe =
    /^(?:[\*\-•\s>]*)(?:pickup|delivery|sender|recipient|service|price|from|to|الاستلام|التسليم|المرسل|المستلم|الخدمة|السعر|من|الى|إلى|نوع\s*الخدمة)\b/i;
  const canonicalRows = lines.filter((l) => canonicalLabelRe.test(l)).length;
  return canonicalRows >= 3;
}

/**
 * Fact-verification for summary-shape replies. Catches the subtle
 * failure mode where the LLM emits a structurally-correct summary (labeled
 * rows, ≥ 3 field signals) but with at least one factual drift — wrong
 * price, wrong phone-tail, wrong area name. Yesterday's incident had a
 * contributing factor of this class: the LLM's summary presented the
 * delivery address as complete when the server had it as incomplete.
 *
 * Tolerances:
 *   - Price: exact numeric match within 0.05 KWD (rounds "1.25" vs "1.250").
 *   - Phones: any 7+ digit sequence in the reply must match the tail of one
 *     of the two stored phones (sender or recipient). Shorter numeric tokens
 *     are treated as block/street/apt numbers and ignored.
 *   - Areas: pickup and dropoff canonical names (EN or AR) must each appear
 *     at least once when the summary mentions an area-labeled row. If a
 *     labeled row contains an area token that doesn't match the server's
 *     pickup OR dropoff area, that's a drift.
 *   - Names: stored sender / recipient names (trimmed, case-insensitive)
 *     must each appear somewhere in the reply when the stored value is
 *     present. Missing names in an otherwise-full summary = drift.
 *
 * Returns a list of mismatches; empty list = consistent. Callers treat a
 * non-empty list as a reason to substitute the canonical summary.
 */
export type SummaryFactMismatch = {
  field: "price" | "phone" | "area" | "name";
  mentioned: string;
  expected: string;
};

export type SummaryFactCheckResult = {
  consistent: boolean;
  mismatches: SummaryFactMismatch[];
};

const KWD_PRICE_RE = /(\d+(?:[.,]\d{1,3})?)\s*(?:kwd|kd|د\.?ك|دينار|dinars?)\b/gi;

const LONG_DIGIT_SEQ_RE = /(\d[\d\s-]{6,})/g;

function extractKwdPrices(reply: string): number[] {
  const out: number[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(KWD_PRICE_RE.source, KWD_PRICE_RE.flags);
  while ((m = re.exec(reply)) !== null) {
    const n = Number(m[1].replace(",", "."));
    if (Number.isFinite(n) && n > 0) out.push(n);
  }
  return out;
}

function extractPhoneCandidates(reply: string): string[] {
  const out: string[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(LONG_DIGIT_SEQ_RE.source, LONG_DIGIT_SEQ_RE.flags);
  while ((m = re.exec(reply)) !== null) {
    const digits = m[1].replace(/\D/g, "");
    if (digits.length >= 7) out.push(digits);
  }
  return out;
}

/**
 * Does one phone candidate look like the tail of a stored phone?
 * Matches by comparing the last N digits (min 7) of both. Handles the
 * variety of ways a phone can appear ("96597485757", "97485757",
 * "+965 97485757").
 */
function phoneCandidateMatchesStored(candidate: string, stored: string[]): boolean {
  const cand = candidate.replace(/\D/g, "");
  if (cand.length < 7) return false;
  const candTail = cand.slice(-7);
  for (const s of stored) {
    const sd = s.replace(/\D/g, "");
    if (sd.length < 7) continue;
    if (sd.slice(-7) === candTail) return true;
    // Also accept full-candidate == full-stored even when stored is longer.
    if (sd === cand || sd.endsWith(cand) || cand.endsWith(sd)) return true;
  }
  return false;
}

/**
 * Compact factual drift — Step-5 observational detector.
 *
 * Targets the remaining leak after Step-3 freed stylistic shapes: a SHORT
 * reply (stub / ack) that happens to make a FACTUAL CLAIM about a tracked
 * field and gets the value wrong. These don't pass
 * `replyLooksLikeFullSummary`'s structural bar, so `verifySummaryFacts` never
 * sees them — but the customer still reads them as authoritative.
 *
 * Example drift captured:
 *   stored recipient_phone = "+96562844738"
 *   LLM reply             = "Got it, sending to +96599991111. All set?"
 *
 * Policy (intentionally tight):
 *
 *  - Only two field kinds are checked: PHONE and NAME. Prices are already
 *    handled by the Region-A KWD whitelist. Areas and addresses require
 *    structural context we don't have in a compact reply, so they stay with
 *    the full-summary path.
 *
 *  - A NAME claim requires an attribution preposition directly preceding a
 *    capitalised / Arabic name-token ("to Ahmad", "for Sara", "sender Ali",
 *    "للمرسل فلان"). Bare capitalised tokens ("Sending your order now.") do
 *    NOT count — no attribution, no claim.
 *
 *  - A PHONE claim is any ≥ 7-digit run in the reply. Re-uses the same rule
 *    as `verifySummaryFacts` for consistency.
 *
 *  - A claim only counts as DRIFT if the value doesn't match ANY stored
 *    value for that field kind. This deliberately allows "sending to
 *    $sender" when the sender was the actual originator of the message —
 *    the name matches.
 *
 * This function is pure. It never substitutes; it just reports. Step-5
 * ships it as a log-only signal; a later step may promote to substitution
 * once prod frequency + false-positive rate are known.
 */
export type CompactFactKind = "phone" | "name";

export type CompactFactMismatch = {
  kind: CompactFactKind;
  /** The wrong value the reply claimed. */
  mentioned: string;
  /** Pipe-joined stored values for triage. */
  expected: string;
};

export type CompactFactCheckResult = {
  consistent: boolean;
  mismatches: CompactFactMismatch[];
};

const NAME_ATTRIBUTION_EN =
  "(?:to|for|from|sender|recipient|send(?:ing)?\\s+to|recv|receiver|To|For|From|Sender|Recipient|Send(?:ing)?\\s+To|Recv|Receiver)";
const NAME_ATTRIBUTION_AR =
  "(?:الى|إلى|لـ|من|المرسل|المستلم|إلي|الي)";

// Latin capitalised token (≥ 3 chars) OR Arabic word (≥ 3 Arabic letters).
// Deliberately ignores single-letter initials, lowercase tokens, and
// numeric tokens. Anchored to the attribution preposition so we don't
// pick up sentence-initial capitalisations. Flags are intentionally
// non-case-insensitive for the NAME token part so that "to confirm"
// never looks like "to [Name]" — only a real capitalised token counts.
const NAME_CLAIM_EN_RE = new RegExp(
  `\\b${NAME_ATTRIBUTION_EN}\\s+([A-Z][A-Za-z'\\-]{2,})\\b`,
  "gu",
);
const NAME_CLAIM_AR_RE = new RegExp(
  `${NAME_ATTRIBUTION_AR}\\s+([\\u0600-\\u06FF]{3,}(?:\\s+[\\u0600-\\u06FF]{3,})?)`,
  "gu",
);

/**
 * A small set of English stopwords that happen to start capitalised but
 * never refer to a person. Used to filter out matches like "to Confirm"
 * (sentence-start or bolded verb) so they don't get compared against a
 * stored name.
 */
const NAME_STOPWORDS = new Set([
  "confirm",
  "confirmed",
  "pickup",
  "delivery",
  "please",
  "order",
  "service",
  "sender",
  "recipient",
  "phone",
  "number",
  "name",
  "today",
  "tomorrow",
  "yes",
  "now",
  "the",
  "this",
  "that",
  "here",
  "there",
  "your",
  "our",
]);

function storedNameTokens(entry: PersistedConversationControllerEntry): string[] {
  const tokens: string[] = [];
  const draft = entry.bookingDraft;
  for (const name of [draft.senderName, draft.recipientName]) {
    if (!name) continue;
    const parts = name.trim().split(/\s+/);
    for (const p of parts) {
      const t = p.toLowerCase();
      if (t.length >= 3) tokens.push(t);
    }
  }
  return tokens;
}

function nameClaimMatchesStored(claim: string, storedTokens: string[]): boolean {
  const c = claim.trim().toLowerCase();
  if (c.length < 3) return true; // too short to be a reliable claim
  // Stopwords (verbs / prepositions / generic nouns that happen to
  // appear capitalised in a name-attribution context) are NEVER treated
  // as name claims — they match by default so the caller doesn't flag.
  if (NAME_STOPWORDS.has(c)) return true;
  for (const t of storedTokens) {
    if (t === c) return true;
    // Tolerate "Ahmad" vs "Ahmed" by comparing first 3 chars when both
    // are ≥ 4 long. Narrow enough to catch variant spellings without
    // false-matching unrelated short names.
    if (c.length >= 4 && t.length >= 4 && c.slice(0, 3) === t.slice(0, 3)) {
      return true;
    }
  }
  return false;
}

/**
 * Scan a compact reply for factual claims about tracked fields. Returns the
 * list of mismatches; empty list = no drift observed.
 *
 * Intended ONLY for replies that already failed `replyLooksLikeFullSummary`
 * — i.e. the caller has a `stub_summary` / `standalone_ack` / `ok` shape
 * and wants the narrow backstop. Calling on a full summary is safe (it
 * will just re-confirm what `verifySummaryFacts` already decided) but
 * wastes a pass.
 */
export function verifyCompactFactualClaims(
  reply: string,
  entry: PersistedConversationControllerEntry,
): CompactFactCheckResult {
  const mismatches: CompactFactMismatch[] = [];
  const draft = entry.bookingDraft;

  // --- PHONE claims --------------------------------------------------------
  const storedPhones: string[] = [];
  if (draft.senderPhone) storedPhones.push(draft.senderPhone);
  if (draft.recipientPhone) storedPhones.push(draft.recipientPhone);
  if (storedPhones.length > 0) {
    const phoneCandidates = extractPhoneCandidates(reply);
    for (const cand of phoneCandidates) {
      if (!phoneCandidateMatchesStored(cand, storedPhones)) {
        mismatches.push({
          kind: "phone",
          mentioned: cand,
          expected: storedPhones.join("|"),
        });
        break; // one drift is enough
      }
    }
  }

  // --- NAME claims ---------------------------------------------------------
  const storedTokens = storedNameTokens(entry);
  if (storedTokens.length > 0) {
    const claims: string[] = [];
    let m: RegExpExecArray | null;
    const reEn = new RegExp(NAME_CLAIM_EN_RE.source, NAME_CLAIM_EN_RE.flags);
    while ((m = reEn.exec(reply)) !== null) {
      if (m[1]) claims.push(m[1]);
    }
    const reAr = new RegExp(NAME_CLAIM_AR_RE.source, NAME_CLAIM_AR_RE.flags);
    while ((m = reAr.exec(reply)) !== null) {
      if (m[1]) claims.push(m[1]);
    }
    for (const claim of claims) {
      if (!nameClaimMatchesStored(claim, storedTokens)) {
        mismatches.push({
          kind: "name",
          mentioned: claim,
          expected: [draft.senderName, draft.recipientName].filter(Boolean).join(" / "),
        });
        break;
      }
    }
  }

  return { consistent: mismatches.length === 0, mismatches };
}

export function verifySummaryFacts(
  reply: string,
  entry: PersistedConversationControllerEntry,
  bookingTruthSnapshot?: BookingTruthSnapshot | null,
): SummaryFactCheckResult {
  const mismatches: SummaryFactMismatch[] = [];
  const draft = entry.bookingDraft;

  // 1. Price verification (only when a price is actually mentioned).
  const mentionedPrices = extractKwdPrices(reply);
  if (mentionedPrices.length > 0) {
    const selectedPrice =
      bookingTruthSnapshot?.quote.selected.price ?? entry.quotedPrice ?? null;
    const lowerReply = reply.toLowerCase();
    const mentionsCatalogOption = Boolean(
      bookingTruthSnapshot?.quote.optionCatalog.some((option) => {
        const labels = [option.label_en, option.label_ar, option.delivery_type]
          .map((value) => String(value || "").trim().toLowerCase())
          .filter(Boolean);
        return labels.some((label) => lowerReply.includes(label));
      }),
    );
    const acceptedPrices =
      mentionsCatalogOption &&
      (bookingTruthSnapshot?.quote.validQuotedPrices.length || 0) > 0
        ? bookingTruthSnapshot?.quote.validQuotedPrices ?? []
        : selectedPrice != null
          ? [selectedPrice]
          : [];
    const anyMatch = mentionedPrices.some((p) =>
      acceptedPrices.some((quoted) => Math.abs(p - quoted) <= 0.05),
    );
    if (acceptedPrices.length > 0 && !anyMatch) {
      mismatches.push({
        field: "price",
        mentioned: mentionedPrices.join(","),
        expected: acceptedPrices.map((price) => price.toFixed(3)).join("|"),
      });
    }
  }

  // 2. Phone verification.
  const storedPhones: string[] = [];
  if (draft.senderPhone) storedPhones.push(draft.senderPhone);
  if (draft.recipientPhone) storedPhones.push(draft.recipientPhone);
  if (storedPhones.length > 0) {
    const phoneCandidates = extractPhoneCandidates(reply);
    for (const cand of phoneCandidates) {
      if (!phoneCandidateMatchesStored(cand, storedPhones)) {
        mismatches.push({
          field: "phone",
          mentioned: cand,
          expected: storedPhones.join("|"),
        });
        break; // one phone drift is enough to substitute
      }
    }
  }

  // 3. Name verification — when both stored names are present, expect both
  // to appear in a full summary. If a name is missing AND we're in a
  // summary-shape reply (checked by caller), that's drift.
  const lowerReply = reply.toLowerCase();
  for (const [, name] of [
    ["sender_name", draft.senderName],
    ["recipient_name", draft.recipientName],
  ] as const) {
    if (!name) continue;
    const t = name.trim().toLowerCase();
    if (t.length < 2) continue;
    // Split on spaces — presence of any token of the name (≥ 3 chars)
    // counts as a match. Handles "Muhammad" vs "Mohammed", "Ahmad" vs
    // "Ahmed" by requiring the first token to be present for people who
    // use one name in daily life. Tolerant but catches outright missing.
    const first = t.split(/\s+/)[0];
    if (first.length >= 3 && !lowerReply.includes(first)) {
      mismatches.push({
        field: "name",
        mentioned: "<missing>",
        expected: name,
      });
    }
  }

  // 4. Area verification — both areas must appear (EN or AR form) when
  // the reply contains an area-like labeled row. We detect "area-like"
  // broadly: the reply contains a canonical pickup/delivery label line.
  const hasAreaRow =
    /(^|\n)[\*\-•\s>]*(?:pickup|delivery|from|to|الاستلام|التسليم|من|الى|إلى)\b/i.test(reply);
  if (hasAreaRow) {
    for (const [, en, ar] of [
      ["pickup_area", entry.quotePickupAreaNameEn, entry.quotePickupAreaNameAr],
      ["delivery_area", entry.quoteDropoffAreaNameEn, entry.quoteDropoffAreaNameAr],
    ] as const) {
      const enOk = en ? lowerReply.includes(en.toLowerCase()) : false;
      const arOk = ar ? reply.includes(ar) : false;
      if ((en || ar) && !enOk && !arOk) {
        mismatches.push({
          field: "area",
          mentioned: "<missing>",
          expected: [en, ar].filter(Boolean).join(" / "),
        });
      }
    }
  }

  return { consistent: mismatches.length === 0, mismatches };
}

/**
 * Does the reply look like the LLM is asking the customer to CLARIFY or
 * CONFIRM a specific field value, rather than emit a summary or a stub?
 *
 * This shape exists because the canonical-summary substitution path was
 * over-eagerly replacing LLM clarifications with the full summary. On
 * 2026-04-19 15:28, a historical poisoned `sender_name = "Is this the
 * cheapest option"` was carried into a complete draft; the customer
 * sent "hello"; the LLM correctly replied:
 *
 *   Hi, please confirm the sender name for the order. Is it "hello" or
 *   "Is this the cheapest option"?
 *
 * Structurally that isn't a `full_summary` shape (it lacks the
 * Pickup/Delivery/Service/Price lines), so without this detector it
 * was tagged `stub_summary` and substituted with the full summary —
 * re-surfacing the poisoned value the LLM was trying to repair.
 *
 * Detection rule: reply contains a question mark AND at least one of
 * the following repair phrases (EN / AR / Arabizi mix). The phrase
 * list is intentionally tight — we'd rather miss a clarification (it
 * gets substituted, mild annoyance) than mis-flag a real stub as a
 * clarification (it survives substitution, bad customer experience).
 */
// Clarifying questions have two distinguishing features vs a generic
// stub ("All set, ready to confirm?"):
//
//  (a) they reference a SPECIFIC FIELD being disputed
//      ("confirm the sender name", "clarify the pickup block"), or
//  (b) they present a BINARY CHOICE between two candidate values
//      ("Is it X or Y?", "did you mean A or B?"), or
//  (c) they explicitly ask the customer to resend / re-share / provide
//      a specific field ("could you resend the phone number?").
//
// The generic stub "ready to confirm?" matches none of these. The
// generic summary prompt "Shall I confirm this order?" is filtered
// explicitly in `looksLikeClarifyingQuestion`.
const FIELD_REFERENCE = "sender\\s+name|recipient\\s+name|sender\\s+phone|recipient\\s+phone|pickup|delivery|address|block|street|house|avenue|area|phone|number|name";

const CLARIFYING_QUESTION_PHRASES: RegExp[] = [
  // (a) Clarify / confirm + specific field reference.
  new RegExp(`\\b(?:please\\s+)?(?:confirm|clarify|correct|verify|double[-\\s]?check)\\b(?:\\s+\\w+){0,3}\\s+(?:${FIELD_REFERENCE})`, "iu"),
  // (b) Binary-choice forms.
  /\b(?:is\s+it|was\s+it|do\s+you\s+mean|did\s+you\s+mean|which\s+(?:one|name|number|is|value))\b/iu,
  // (c) Resend / provide a specific field.
  new RegExp(`\\b(?:could|can)\\s+you\\s+(?:confirm|resend|re[-\\s]?send|repeat|provide|share)\\b(?:\\s+\\w+){0,3}\\s+(?:${FIELD_REFERENCE})`, "iu"),
  // Arabic script equivalents — these are already specific enough to be
  // clarifications rather than bare stubs.
  /(?:من\s+فضلك\s+أكد|من\s+فضلك\s+اكد|ممكن\s+تأكد|ممكن\s+تاكد|أيهما\s+الصحيح|ايهما\s+الصحيح|هل\s+تقصد|تقصد)/u,
  // Arabizi equivalents (lightweight).
  /\b(?:akkid|akid|t2akkid|etha|yaa?3ni|ta3ni)\b/iu,
];

function looksLikeClarifyingQuestion(reply: string): boolean {
  if (!/[?؟]/.test(reply)) return false;
  // Guard against "Shall I confirm this order?" which appears in every
  // canonical summary — those aren't clarifications, they're the
  // normal confirmation prompt. Require a clarify phrase that's NOT
  // the standard "shall I confirm this order" line.
  const normalized = reply.replace(/\s+/g, " ").trim().toLowerCase();
  if (/shall\s+i\s+confirm\s+this\s+order\??$/i.test(normalized)) return false;
  // Multi-line summaries (Pickup: / Delivery: / Price: …) that happen
  // to include a trailing "Shall I confirm this order?" also have
  // their own handling and shouldn't be classified here.
  const looksLikeSummaryLines =
    /\bpickup\s*:/i.test(reply) &&
    /\bdelivery\s*:/i.test(reply) &&
    /\bprice\s*:/i.test(reply);
  if (looksLikeSummaryLines) return false;
  return CLARIFYING_QUESTION_PHRASES.some((rx) => rx.test(reply));
}

export function classifyOutboundReplyShape(params: VerifyOutboundParams): OutboundReplyShape {
  const reply = (params.replyText || "").trim();
  if (!reply) return "empty";

  // Clarifying questions are evaluated FIRST, before the stub /
  // standalone-ack heuristics, so they never get substituted away —
  // even when the draft is complete (which is exactly when the LLM
  // is most likely to repair a persisted field with a clarifying
  // question).
  if (looksLikeClarifyingQuestion(reply)) {
    return "clarifying_question";
  }

  const normalized = normalizeForCompare(reply);
  if (STANDALONE_ACK_RE.test(normalized)) return "standalone_ack";

  const entry = params.entry;
  const bookingStarted =
    entry != null &&
    entry.quotedPrice != null &&
    entry.selectedDeliveryType != null;

  if (!bookingStarted) return "ok";

  // Zero-distance route detection (2026-04-21 area-clarification
  // regression). When the quoted pickup area equals the quoted dropoff
  // area, the route is physically nonsensical and always the result of
  // a symmetric rebind upstream (e.g. `get_price(pickup=Mirqab,
  // dropoff=Mirqab)` after a single-word clarification answer for
  // dropoff was echoed on both legs). Surface this as a distinct shape
  // so the repair loop can actively reject instead of log-only passing
  // through a "Delivery from Mirqab to Mirqab" recap / summary. Fires
  // regardless of whether the reply text is a recap or a full summary —
  // the controller's state is already poisoned.
  if (
    entry.quotePickupAreaNameEn &&
    entry.quoteDropoffAreaNameEn &&
    entry.quotePickupAreaNameEn.trim().toLowerCase() ===
      entry.quoteDropoffAreaNameEn.trim().toLowerCase()
  ) {
    return "route_zero_distance";
  }

  const draftComplete = params.missingFields.length === 0;

  if (draftComplete) {
    if (!replyLooksLikeFullSummary(reply, entry)) {
      if (looksLikeRoutePriceRecap(reply, entry.bookingDraft)) return "route_price_recap";
      return "stub_summary";
    }
    // Full summary shape — now verify the facts inside it against server
    // state. Catches the subtle class where the LLM writes a structurally
    // correct summary with wrong price / wrong phone / wrong area / missing
    // stored name. Yesterday's incident had this pattern as a contributing
    // factor: LLM's earlier summary presented the apartment address as
    // complete when the server (pre-fix) had it as incomplete.
    const factCheck = verifySummaryFacts(reply, entry, params.bookingTruthSnapshot);
    if (!factCheck.consistent) return "summary_fact_drift";
    return "ok";
  }

  // Mid-booking (collection in progress). Flag bare route+price recaps.
  if (looksLikeRoutePriceRecap(reply, entry.bookingDraft)) return "route_price_recap";

  return "ok";
}

function formatPhoneForSummary(phone: string | null): string {
  if (!phone) return "—";
  return phone;
}

function normalizeWesternDigits(value: string | null | undefined): string {
  return String(value || "").replace(/[٠-٩۰-۹]/g, (digit) => {
    const map: Record<string, string> = {
      "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
      "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
      "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
      "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    };
    return map[digit] || digit;
  });
}

function interiorUnitNumbers(extra: string | null | undefined): Set<string> {
  const found = new Set<string>();
  const text = normalizeWesternDigits(extra);
  if (!text.trim()) return found;
  const patterns = [
    /\b(?:apt|appt|apartment|flat|unit|suite|office|room)\s*[:#-]?\s*([a-z0-9]{1,10})\b/gi,
    /(?:شقة|شقه|فلات|وحدة|وحده|مكتب|غرفة)\s*[:#-]?\s*([a-z0-9]{1,10})/gi,
  ];
  for (const pattern of patterns) {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      if (match[1]) found.add(match[1].trim().toLowerCase());
    }
  }
  return found;
}

function shouldRenderHouse(parts: { house: string | null; extra: string | null }): boolean {
  const house = normalizeWesternDigits(parts.house).trim().toLowerCase();
  if (!house) return false;
  return !interiorUnitNumbers(parts.extra).has(house);
}

function normalizeAddressExtraEn(extra: string | null): string | null {
  if (!extra) return null;
  return extra
    .split(",")
    .map((part) => {
      const trimmed = part.trim();
      if (!trimmed) return "";
      return trimmed
        .replace(/^(apt|appt|apartment)\b/i, "Apartment")
        .replace(/^flat\b/i, "Flat")
        .replace(/^floor\b/i, "Floor")
        .replace(/^door\b/i, "Door")
        .replace(/^unit\b/i, "Unit")
        .replace(/^office\b/i, "Office")
        .replace(/^gate\b/i, "Gate")
        .replace(/^suite\b/i, "Suite");
    })
    .filter(Boolean)
    .join(", ");
}

function joinAddressPartsEn(parts: {
  block: string | null;
  street: string | null;
  avenue: string | null;
  house: string | null;
  extra: string | null;
}): string {
  const pieces: string[] = [];
  if (parts.block) pieces.push(`Block ${parts.block}`);
  if (parts.street) pieces.push(`Street ${parts.street}`);
  if (parts.avenue) pieces.push(`Jedda ${parts.avenue}`);
  if (shouldRenderHouse(parts)) pieces.push(`House ${parts.house}`);
  const extra = normalizeAddressExtraEn(parts.extra);
  if (extra) pieces.push(extra);
  return pieces.length > 0 ? pieces.join(", ") : "—";
}

function joinAddressPartsAr(parts: {
  block: string | null;
  street: string | null;
  avenue: string | null;
  house: string | null;
  extra: string | null;
}): string {
  const pieces: string[] = [];
  if (parts.block) pieces.push(`قطعة ${parts.block}`);
  if (parts.street) pieces.push(`شارع ${parts.street}`);
  if (parts.avenue) pieces.push(`جادة ${parts.avenue}`);
  if (shouldRenderHouse(parts)) pieces.push(`منزل ${parts.house}`);
  if (parts.extra) pieces.push(parts.extra);
  return pieces.length > 0 ? pieces.join("، ") : "—";
}

const SERVICE_LABELS_EN: Record<string, string> = {
  sedan_normal: "Standard sedan",
  sedan_fast: "Express sedan",
  van_normal: "Standard van",
  van_fast: "Express van",
};

const SERVICE_LABELS_AR: Record<string, string> = {
  sedan_normal: "سيدان عادي",
  sedan_fast: "سيدان سريع",
  van_normal: "فان عادي",
  van_fast: "فان سريع",
};

/**
 * Build a canonical, customer-facing full order summary from the booking
 * draft + live quote. Used as both:
 *
 *   (a) the deterministic substitute when the LLM emits a stub summary
 *       despite a complete draft (C-drift backstop — pre-Phase 3), and
 *   (b) the primary Phase-3 server-rendered summary invoked by the
 *       directive registry when `WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED`
 *       fires (current).
 *
 * After Phase 3 the same function produces the summary on every turn the
 * directive is active, so the C-drift path reduces to a regression alarm
 * — it should no longer fire under steady-state operation. Intentionally
 * left in place so any future LLM-authored summary (edge cases, prompt
 * regressions) still gets caught and substituted.
 *
 * Service label preference:
 *   - Prefer the entry's live catalog label (`selectedQuoteOptionLabel*`)
 *     when present — covers refrigerated-van / helper variants and any
 *     future catalog expansion without a table update.
 *   - Fall back to the static `SERVICE_LABELS_*` table for known types.
 *   - Final fallback is the raw `selectedDeliveryType` key or an em-dash.
 */
/**
 * Recovery reply for zero-distance routes. Fires when the controller
 * has `quotePickupAreaNameEn == quoteDropoffAreaNameEn` — always a
 * symmetric-rebind bug upstream. We drop the LLM's reply (which is
 * typically "Delivery from X to X, <price>"), surface the ambiguity to
 * the customer, and re-ask both areas. The deterministic reconciler
 * upstream (pricing.ts symmetric-rebind guard + drain stage promotion
 * + directive renderers) should prevent this from ever firing in a
 * clean flow; if it does, this is the belt-and-braces safety net.
 */
export function buildZeroDistanceRouteRecovery(params: {
  entry: PersistedConversationControllerEntry;
  language: "ar" | "en";
}): string {
  const { language } = params;
  if (language === "ar") {
    return "صار التباس في المناطق. ممكن تعيد إرسال منطقة الاستلام ومنطقة التوصيل؟";
  }
  return "Looks like the pickup and delivery areas got mixed up. Could you resend the pickup area and the delivery area?";
}

export function buildDeterministicOrderSummary(params: {
  entry: PersistedConversationControllerEntry;
  language: "ar" | "en";
}): string {
  const { entry, language } = params;
  const draft = entry.bookingDraft;

  const pickupArea =
    (language === "ar"
      ? entry.quotePickupAreaNameAr || entry.quotePickupAreaNameEn
      : entry.quotePickupAreaNameEn || entry.quotePickupAreaNameAr) || "—";
  const deliveryArea =
    (language === "ar"
      ? entry.quoteDropoffAreaNameAr || entry.quoteDropoffAreaNameEn
      : entry.quoteDropoffAreaNameEn || entry.quoteDropoffAreaNameAr) || "—";
  const serviceKey = entry.selectedDeliveryType || "";
  const priceStr = entry.quotedPrice != null ? entry.quotedPrice.toFixed(3) : "—";

  const resolveServiceLabel = (lang: "ar" | "en"): string => {
    if (lang === "ar") {
      return (
        entry.selectedQuoteOptionLabelAr ||
        SERVICE_LABELS_AR[serviceKey] ||
        entry.selectedQuoteOptionLabelEn ||
        serviceKey ||
        "—"
      );
    }
    return (
      entry.selectedQuoteOptionLabelEn ||
      SERVICE_LABELS_EN[serviceKey] ||
      entry.selectedQuoteOptionLabelAr ||
      serviceKey ||
      "—"
    );
  };

  if (language === "ar") {
    const pickupAddr = joinAddressPartsAr({
      block: draft.pickupBlock,
      street: draft.pickupStreet,
      avenue: draft.pickupAvenue,
      house: draft.pickupHouse,
      extra: draft.pickupExtra,
    });
    const deliveryAddr = joinAddressPartsAr({
      block: draft.deliveryBlock,
      street: draft.deliveryStreet,
      avenue: draft.deliveryAvenue,
      house: draft.deliveryHouse,
      extra: draft.deliveryExtra,
    });
    const service = resolveServiceLabel("ar");
    const lines = [
      `*ملخص الطلب*`,
      `الاستلام: ${pickupArea} — ${pickupAddr}`,
      `التسليم: ${deliveryArea} — ${deliveryAddr}`,
      `المرسل: ${draft.senderName || "—"} — ${formatPhoneForSummary(draft.senderPhone)}`,
      `المستلم: ${draft.recipientName || "—"} — ${formatPhoneForSummary(draft.recipientPhone)}`,
      `الخدمة: ${service}`,
      `السعر: ${priceStr} د.ك`,
      ``,
      `تبي تأكد الطلب؟`,
    ];
    return lines.join("\n");
  }

  const pickupAddr = joinAddressPartsEn({
    block: draft.pickupBlock,
    street: draft.pickupStreet,
    avenue: draft.pickupAvenue,
    house: draft.pickupHouse,
    extra: draft.pickupExtra,
  });
  const deliveryAddr = joinAddressPartsEn({
    block: draft.deliveryBlock,
    street: draft.deliveryStreet,
    avenue: draft.deliveryAvenue,
    house: draft.deliveryHouse,
    extra: draft.deliveryExtra,
  });
  const service = resolveServiceLabel("en");

  const lines = [
    `*Order summary*`,
    `Pickup: ${pickupArea} — ${pickupAddr}`,
    `Delivery: ${deliveryArea} — ${deliveryAddr}`,
    `Sender: ${draft.senderName || "—"} — ${formatPhoneForSummary(draft.senderPhone)}`,
    `Recipient: ${draft.recipientName || "—"} — ${formatPhoneForSummary(draft.recipientPhone)}`,
    `Service: ${service}`,
    `Price: ${priceStr} KWD`,
    ``,
    `Shall I confirm this order?`,
  ];
  return lines.join("\n");
}

export function buildDeterministicOrderSummaryFromSnapshot(params: {
  snapshot: BookingTruthSnapshot;
  language: "ar" | "en";
}): string {
  const { snapshot, language } = params;
  const draft = snapshot.draft;
  const selected = snapshot.quote.selected;
  const serviceKey = snapshot.quote.selectedService || selected.deliveryType || "";
  const price =
    selected.price != null && Number.isFinite(Number(selected.price))
      ? Number(selected.price).toFixed(3)
      : selected.formattedPrice || "—";

  const service =
    language === "ar"
      ? selected.labelAr ||
        SERVICE_LABELS_AR[serviceKey] ||
        selected.labelEn ||
        serviceKey ||
        "—"
      : selected.labelEn ||
        SERVICE_LABELS_EN[serviceKey] ||
        selected.labelAr ||
        serviceKey ||
        "—";

  const pickupArea =
    (language === "ar"
      ? snapshot.route.pickup.nameAr || snapshot.route.pickup.nameEn
      : snapshot.route.pickup.nameEn || snapshot.route.pickup.nameAr) || "—";
  const deliveryArea =
    (language === "ar"
      ? snapshot.route.dropoff.nameAr || snapshot.route.dropoff.nameEn
      : snapshot.route.dropoff.nameEn || snapshot.route.dropoff.nameAr) || "—";

  if (language === "ar") {
    const pickupAddr = joinAddressPartsAr({
      block: draft?.pickupBlock ?? null,
      street: draft?.pickupStreet ?? null,
      avenue: draft?.pickupAvenue ?? null,
      house: draft?.pickupHouse ?? null,
      extra: draft?.pickupExtra ?? null,
    });
    const deliveryAddr = joinAddressPartsAr({
      block: draft?.deliveryBlock ?? null,
      street: draft?.deliveryStreet ?? null,
      avenue: draft?.deliveryAvenue ?? null,
      house: draft?.deliveryHouse ?? null,
      extra: draft?.deliveryExtra ?? null,
    });
    return [
      `*ملخص الطلب*`,
      `الاستلام: ${pickupArea} — ${pickupAddr}`,
      `التسليم: ${deliveryArea} — ${deliveryAddr}`,
      `المرسل: ${draft?.senderName || "—"} — ${formatPhoneForSummary(draft?.senderPhone ?? null)}`,
      `المستلم: ${draft?.recipientName || "—"} — ${formatPhoneForSummary(draft?.recipientPhone ?? null)}`,
      `الخدمة: ${service}`,
      `السعر: ${price} د.ك`,
      ``,
      `تبي تأكد الطلب؟`,
    ].join("\n");
  }

  const pickupAddr = joinAddressPartsEn({
    block: draft?.pickupBlock ?? null,
    street: draft?.pickupStreet ?? null,
    avenue: draft?.pickupAvenue ?? null,
    house: draft?.pickupHouse ?? null,
    extra: draft?.pickupExtra ?? null,
  });
  const deliveryAddr = joinAddressPartsEn({
    block: draft?.deliveryBlock ?? null,
    street: draft?.deliveryStreet ?? null,
    avenue: draft?.deliveryAvenue ?? null,
    house: draft?.deliveryHouse ?? null,
    extra: draft?.deliveryExtra ?? null,
  });

  return [
    `*Order summary*`,
    `Pickup: ${pickupArea} — ${pickupAddr}`,
    `Delivery: ${deliveryArea} — ${deliveryAddr}`,
    `Sender: ${draft?.senderName || "—"} — ${formatPhoneForSummary(draft?.senderPhone ?? null)}`,
    `Recipient: ${draft?.recipientName || "—"} — ${formatPhoneForSummary(draft?.recipientPhone ?? null)}`,
    `Service: ${service}`,
    `Price: ${price} KWD`,
    ``,
    `Shall I confirm this order?`,
  ].join("\n");
}

/**
 * Main entry point. Classifies the outbound reply and, when a bad shape is
 * detected in a state where we can produce a deterministic substitute,
 * replaces the reply with a canonical one.
 *
 * Substitution policy (Step-3 narrowing):
 *
 *   Only `summary_fact_drift` triggers a substitute. Fact drift means the
 *   reply claims a price / phone tail / stored name / area name that
 *   disagrees with authoritative server state — a transactional mismatch
 *   the customer could act on.
 *
 *   All other detected shapes (`stub_summary`, `route_price_recap`,
 *   `standalone_ack`) are **log-only**. Under the "free natural phrasing /
 *   strict on facts" policy, a short or differently-structured summary is
 *   acceptable UX; the LLM's natural wording often reads better than the
 *   rigid labeled-row canonical template. The `next_required_action`
 *   directive on the next turn keeps the flow on track if the reply was
 *   genuinely sub-par.
 *
 *   Clarifying questions are NEVER substituted — see
 *   `looksLikeClarifyingQuestion` for the detection rule. That branch
 *   survives the narrowing as a belt-and-braces safety net.
 *
 * Never throws. Returns the (possibly substituted) reply text along with a
 * `replaced` flag and reason so the caller can log the interception.
 */
export function verifyAndRepairOutbound(params: VerifyOutboundParams): VerifyOutboundResult {
  const shape = classifyOutboundReplyShape(params);
  if (shape === "ok" || shape === "empty") {
    return { replyText: params.replyText, replaced: false, shape, reason: null };
  }
  // Clarifying questions are the LLM doing repair work on the persisted
  // state (e.g. "Is the sender name X or Y?"). Never substitute these
  // with the canonical summary — that's exactly what suppresses the
  // repair and re-surfaces the poisoned value. See
  // `looksLikeClarifyingQuestion` for the detection rule.
  if (shape === "clarifying_question") {
    return {
      replyText: params.replyText,
      replaced: false,
      shape,
      reason: "preserved_clarifying_question",
    };
  }

  const entry = params.entry;
  const draftComplete = params.missingFields.length === 0;

  // Zero-distance route detection — Z2-V1 demotion (2026-04-24).
  //
  // History: this path used to substitute the LLM's reply with a canned
  // "صار التباس في المناطق" ask whenever the controller had
  // `quotePickupAreaNameEn === quoteDropoffAreaNameEn`. The intent was
  // to catch state that was poisoned upstream by a bad tool call.
  //
  // Why demote: Z1-P0 closed the main poisoning path at the source —
  // `get_price` now rejects cold-start symmetric calls and returns an
  // instructional error instead of writing `set_pending_area` ops. With
  // that in place, this substitution path is (a) mostly unreachable in
  // the intended cases and (b) actively harmful when it DOES fire,
  // because it stomps the LLM's (usually correct) coverage-question
  // reply with an accusatory recovery ask that blames the customer
  // ("resend pickup and delivery areas"). Observed on 2026-04-24 with
  // "توصلون لي فروانية؟" / Farwaniya, where the LLM correctly replied
  // "نوصل لفروانية، بس عطنا منطقة الاستلام" but got overwritten.
  //
  // Behaviour change: keep the detection (valuable observability — if
  // this shape fires post-Z1-P0, something else is still poisoning
  // state and we want the log), but stop authoring customer-facing
  // text. The LLM's reply goes out as-authored.
  //
  // Flag: `RIDERS_OUTBOUND_ZERO_DISTANCE_SUBSTITUTE=on` re-enables the
  // old substitute path for emergency rollback. Default OFF = demoted.
  if (entry && shape === "route_zero_distance") {
    const rollbackRaw = (globalThis as any).process?.env
      ?.RIDERS_OUTBOUND_ZERO_DISTANCE_SUBSTITUTE;
    const rollbackEnabled =
      typeof rollbackRaw === "string" &&
      ["on", "1", "true", "yes", "enabled"].includes(
        rollbackRaw.trim().toLowerCase(),
      );
    try {
      console.log(
        `[metric] outbound_verify.zero_distance_detected` +
          ` quotePickup="${entry.quotePickupAreaNameEn ?? ""}"` +
          ` quoteDropoff="${entry.quoteDropoffAreaNameEn ?? ""}"` +
          ` stage=${(entry as any).stage ?? "unknown"}` +
          ` action=${rollbackEnabled ? "substitute_rollback" : "log_only"}`,
      );
    } catch {}
    if (rollbackEnabled) {
      const substitute = buildZeroDistanceRouteRecovery({
        entry,
        language: params.language,
      });
      return {
        replyText: substitute,
        replaced: true,
        shape,
        reason: "substituted_zero_distance_route_recovery",
      };
    }
    return {
      replyText: params.replyText,
      replaced: false,
      shape,
      reason: "detected_route_zero_distance_log_only",
    };
  }

  // Summary checkpoint guard: when server state proves the booking just
  // reached the summary step, a compact ack/stub must not ask for another
  // missing field. Outside this narrow checkpoint these shapes stay log-only
  // so normal LLM phrasing remains free.
  if (
    entry &&
    params.summaryCompletionCheckpoint === true &&
    draftComplete &&
    entry.quotedPrice != null &&
    entry.selectedDeliveryType &&
    (shape === "stub_summary" ||
      shape === "standalone_ack" ||
      shape === "route_price_recap")
  ) {
    const substitute = buildDeterministicOrderSummary({ entry, language: params.language });
    return {
      replyText: substitute,
      replaced: true,
      shape,
      reason: "substituted_summary_completion_checkpoint",
    };
  }

  // Only factual drift triggers substitution. A reply is classified as
  // `summary_fact_drift` ONLY after passing the "full summary" structural
  // bar AND then failing `verifySummaryFacts` (wrong price / wrong phone
  // tail / missing stored name / wrong area). That is a transactional
  // mismatch where the customer could act on wrong information, so we
  // replace it with the authoritative data-driven summary.
  //
  // All other shapes — `stub_summary`, `route_price_recap`,
  // `standalone_ack` — are treated as log-only stylistic observations
  // under the Step-3 "free phrasing, strict facts" policy.
  if (
    entry &&
    draftComplete &&
    entry.quotedPrice != null &&
    entry.selectedDeliveryType &&
    shape === "summary_fact_drift"
  ) {
    const substitute = buildDeterministicOrderSummary({ entry, language: params.language });
    return {
      replyText: substitute,
      replaced: true,
      shape,
      reason: `substituted_full_summary:${shape}`,
    };
  }

  // Log-only for every other detected shape. The stylistic shapes
  // (stub_summary / route_price_recap / standalone_ack) used to be
  // substituted with the canonical labeled-row summary; that made the
  // system feel robotic and overwrote perfectly-valid natural phrasings.
  // We keep the detection so production logs still surface shape drift
  // for observability, but we trust the LLM's wording.
  return {
    replyText: params.replyText,
    replaced: false,
    shape,
    reason: `detected_${shape}_log_only`,
  };
}
