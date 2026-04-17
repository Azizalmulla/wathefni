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

export type OutboundReplyShape =
  | "ok"
  | "stub_summary"
  | "route_price_recap"
  | "standalone_ack"
  | "empty";

export type VerifyOutboundParams = {
  replyText: string;
  entry: PersistedConversationControllerEntry | null;
  missingFields: string[];
  language: "ar" | "en";
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

export function classifyOutboundReplyShape(params: VerifyOutboundParams): OutboundReplyShape {
  const reply = (params.replyText || "").trim();
  if (!reply) return "empty";

  const normalized = normalizeForCompare(reply);
  if (STANDALONE_ACK_RE.test(normalized)) return "standalone_ack";

  const entry = params.entry;
  const bookingStarted =
    entry != null &&
    entry.quotedPrice != null &&
    entry.selectedDeliveryType != null;

  if (!bookingStarted) return "ok";

  const draftComplete = params.missingFields.length === 0;

  if (draftComplete) {
    if (!replyLooksLikeFullSummary(reply, entry)) {
      if (looksLikeRoutePriceRecap(reply, entry.bookingDraft)) return "route_price_recap";
      return "stub_summary";
    }
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
  if (parts.house) pieces.push(`House ${parts.house}`);
  if (parts.extra) pieces.push(parts.extra);
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
  if (parts.house) pieces.push(`منزل ${parts.house}`);
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
 * draft + live quote. Used as the deterministic substitute when the LLM
 * emits a stub summary despite a complete draft.
 */
export function buildDeterministicOrderSummary(params: {
  entry: PersistedConversationControllerEntry;
  language: "ar" | "en";
}): string {
  const { entry, language } = params;
  const draft = entry.bookingDraft;

  const pickupArea = entry.quotePickupAreaNameEn || entry.quotePickupAreaNameAr || "—";
  const deliveryArea = entry.quoteDropoffAreaNameEn || entry.quoteDropoffAreaNameAr || "—";
  const serviceKey = entry.selectedDeliveryType || "";
  const priceStr = entry.quotedPrice != null ? entry.quotedPrice.toFixed(3) : "—";

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
    const service = SERVICE_LABELS_AR[serviceKey] || serviceKey || "—";
    const lines = [
      `*ملخص الطلب*`,
      `الاستلام: ${pickupArea} — ${pickupAddr}`,
      `التسليم: ${deliveryArea} — ${deliveryAddr}`,
      `المرسل: ${draft.senderName || "—"} — ${formatPhoneForSummary(draft.senderPhone)}`,
      `المستلم: ${draft.recipientName || "—"} — ${formatPhoneForSummary(draft.recipientPhone)}`,
      `الخدمة: ${service}`,
      `السعر: ${priceStr} د.ك`,
      ``,
      `أأكد الطلب؟`,
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
  const service = SERVICE_LABELS_EN[serviceKey] || serviceKey || "—";

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

/**
 * Main entry point. Classifies the outbound reply and, when a bad shape is
 * detected in a state where we can produce a deterministic substitute,
 * replaces the reply with the canonical summary.
 *
 * Never throws. Returns the (possibly substituted) reply text along with a
 * `replaced` flag and reason so the caller can log the interception.
 */
export function verifyAndRepairOutbound(params: VerifyOutboundParams): VerifyOutboundResult {
  const shape = classifyOutboundReplyShape(params);
  if (shape === "ok" || shape === "empty") {
    return { replyText: params.replyText, replaced: false, shape, reason: null };
  }

  const entry = params.entry;
  const draftComplete = params.missingFields.length === 0;

  // Only attempt deterministic substitution when we have everything needed to
  // build a full summary. For stub_summary or route_price_recap in a complete
  // state, we synthesize the canonical summary.
  if (
    entry &&
    draftComplete &&
    entry.quotedPrice != null &&
    entry.selectedDeliveryType &&
    (shape === "stub_summary" || shape === "route_price_recap")
  ) {
    const substitute = buildDeterministicOrderSummary({ entry, language: params.language });
    return {
      replyText: substitute,
      replaced: true,
      shape,
      reason: `substituted_full_summary:${shape}`,
    };
  }

  // Otherwise: don't interfere. Log-only. Keeps us safe from false positives
  // during collection turns and avoids customer confusion from reply swaps we
  // aren't confident about.
  return {
    replyText: params.replyText,
    replaced: false,
    shape,
    reason: `detected_${shape}_no_safe_substitute`,
  };
}
