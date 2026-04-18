#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the reply-hallucination guard.
//
// The guard is a deterministic post-LLM defense layer that scans every
// outbound reply for claims that aren't supported by the server-side state
// (field-rejection claims without real rejections, price mentions that
// disagree with the authoritative quote, "order placed" assertions without
// a submitted-stage transition). This test covers:
//
//   1. Valid reply passes through untouched.
//   2. Field-rejection hallucination from the 2026-04-17 incident is
//      blocked and substituted with a deterministic next-step ask.
//   3. Field-rejection claim WITH real evidence (rejection op this turn)
//      is NOT blocked — the LLM is correctly surfacing the rejection.
//   4. Field-rejection claim when a stored field actually IS invalid
//      (e.g. phone missing) is NOT blocked.
//   5. Order-placed hallucination (stage never reached submitted) is
//      blocked.
//   6. Legitimate post-order recap (stage already submitted before turn)
//      is NOT blocked.
//   7. Price mismatch (reply says 5 KWD, quote is 1.250) is blocked.
//   8. Matching price (reply says 1.250 KWD, quote is 1.250) passes.
//   9. Granular missing sub-fields produce a targeted substitute.
//  10. Env-flag off disables the whole guard.
// ---------------------------------------------------------------------------

import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const {
  runHallucinationGuard,
  looksLikeFieldRejectionClaim,
  looksLikeOrderPlacedClaim,
  extractMentionedPrices,
  isHallucinationGuardEnabled,
} = await loadTsModule("plugins/shared/reply-hallucination-guard.ts");
const { createEmptyBookingDraft } = await loadTsModule("plugins/shared/conversation-policy.ts");

function buildCompleteDraft() {
  const d = createEmptyBookingDraft();
  d.senderName = "Aziz";
  d.senderPhone = "96597485757";
  d.recipientName = "Ahmed";
  d.recipientPhone = "96562844738";
  d.pickupBlock = "6";
  d.pickupStreet = "9";
  d.pickupHouse = "17";
  d.deliveryBlock = "2";
  d.deliveryStreet = "9";
  d.deliveryExtra = "Apartment 19, floor 8, door 11";
  return d;
}

function buildEntry(draft, overrides = {}) {
  return {
    stage: "collecting_booking_details",
    bookingStep: "summary_pending",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    ...overrides,
  };
}

// -----------------------------------------------------------------------
// Case 1: valid reply passes through
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const decision = runHallucinationGuard({
    replyText: "Got it — I'll confirm and place the order now.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(!decision.blocked, "case1: valid reply must pass through");
  assert(decision.claims.length === 0, "case1: no claims on valid reply");
}

// -----------------------------------------------------------------------
// Case 2: the 2026-04-17 incident exactly — field-rejection hallucination
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const decision = runHallucinationGuard({
    replyText:
      "The phone numbers need to be resent in a valid format. Send the sender and recipient phone numbers again, digits only.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [], // no rejection happened this turn
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(decision.blocked, "case2: 2026-04-17 incident payload must be blocked");
  assert(
    decision.claims.includes("field_rejection_hallucination"),
    "case2: must detect field_rejection_hallucination",
  );
  assert(
    decision.replyText !== "The phone numbers need to be resent in a valid format. Send the sender and recipient phone numbers again, digits only.",
    "case2: reply must be substituted",
  );
}

// -----------------------------------------------------------------------
// Case 3: field-rejection claim WITH real rejection is NOT blocked
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const decision = runHallucinationGuard({
    replyText: "The sender phone looked wrong — please resend it, digits only.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [
      { field: "sender_phone", reason: "not_digits_only", received: "the number is 97485757" },
    ],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_SENDER_PHONE",
  });
  assert(
    !decision.blocked,
    "case3: genuine rejection means the claim is grounded; do not block",
  );
}

// -----------------------------------------------------------------------
// Case 4: stored phone is actually invalid → don't block (LLM is right)
// -----------------------------------------------------------------------
{
  const draft = buildCompleteDraft();
  draft.recipientPhone = null; // actually missing
  const entry = buildEntry(draft);
  const decision = runHallucinationGuard({
    replyText: "Please send the recipient phone number, digits only.",
    entry,
    missingFields: ["recipient.phone"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_RECIPIENT_NAME_AND_PHONE",
  });
  assert(
    !decision.blocked,
    "case4: actually-missing field means ask is legitimate",
  );
}

// -----------------------------------------------------------------------
// Case 5: order-placed hallucination
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { stage: "summary_shown" });
  const decision = runHallucinationGuard({
    replyText: "Your order has been placed! Reference: AB123. A rider is on the way.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "summary_shown",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(decision.blocked, "case5: order-placed without submitted stage must be blocked");
  assert(
    decision.claims.includes("order_placed_hallucination"),
    "case5: must detect order_placed_hallucination",
  );
  // Should substitute the order summary (since draft is complete + quoted)
  assert(
    /Order summary|ملخص الطلب/i.test(decision.replyText) ||
      /confirm|تأكيد/i.test(decision.replyText),
    `case5: substitute must be summary or confirmation nudge, got: ${decision.replyText.slice(0, 80)}`,
  );
}

// -----------------------------------------------------------------------
// Case 6: legit post-order recap — stage already submitted
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { stage: "order_submitted" });
  const decision = runHallucinationGuard({
    replyText: "Your order was placed earlier. Want me to track it?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "order_submitted",
    language: "en",
    nextRequiredAction: "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
  });
  assert(
    !decision.blocked,
    "case6: post-order recap with submitted stage must not be blocked",
  );
}

// -----------------------------------------------------------------------
// Case 7: price mismatch
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft()); // quoted 1.250
  const decision = runHallucinationGuard({
    replyText: "The price is 5.000 KWD. Shall I confirm?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(decision.blocked, "case7: price mismatch must be blocked");
  assert(decision.claims.includes("price_mismatch"), "case7: must detect price_mismatch");
}

// -----------------------------------------------------------------------
// Case 8: matching price passes
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft()); // quoted 1.250
  const decision = runHallucinationGuard({
    replyText: "The price is 1.250 KWD. Shall I confirm?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(!decision.blocked, "case8: matching price must not be blocked");
}

// -----------------------------------------------------------------------
// Case 9: granular address sub-field substitution
// -----------------------------------------------------------------------
{
  const draft = buildCompleteDraft();
  draft.deliveryBlock = null;
  draft.deliveryStreet = null;
  draft.deliveryHouse = null;
  draft.deliveryExtra = null;
  const entry = buildEntry(draft);
  const decision = runHallucinationGuard({
    replyText:
      "Please resend the address in a valid format — it wasn't recognized.",
    entry,
    missingFields: [
      "delivery.address",
      "delivery.block",
      "delivery.street_or_avenue",
      "delivery.house_or_unit",
    ],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_DELIVERY_ADDRESS",
  });
  // Only blocks if detected as hallucination. The claim is "address in a
  // valid format ... wasn't recognized" — this matches our field-rejection
  // patterns. But draft has recipient phone/name etc all valid, and no
  // rejections this turn, so hallucination detected → block.
  assert(
    decision.blocked,
    `case9: should block hallucinated address rejection, got: ${JSON.stringify(decision)}`,
  );
  assert(
    /block|street|avenue|building|apartment|tower/i.test(decision.replyText),
    `case9: substitute must ask for specific sub-fields, got: ${decision.replyText}`,
  );
}

// -----------------------------------------------------------------------
// Case 10: env flag off disables the guard
// -----------------------------------------------------------------------
{
  const prev = process.env.RIDERS_HALLUCINATION_GUARD_ENABLED;
  process.env.RIDERS_HALLUCINATION_GUARD_ENABLED = "0";
  assert(!isHallucinationGuardEnabled(), "case10: env=0 must disable");
  process.env.RIDERS_HALLUCINATION_GUARD_ENABLED = "1";
  assert(isHallucinationGuardEnabled(), "case10: env=1 must enable");
  delete process.env.RIDERS_HALLUCINATION_GUARD_ENABLED;
  assert(isHallucinationGuardEnabled(), "case10: env unset must default-enable");
  if (prev != null) process.env.RIDERS_HALLUCINATION_GUARD_ENABLED = prev;
}

// -----------------------------------------------------------------------
// Case 11: Arabic field-rejection hallucination
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const decision = runHallucinationGuard({
    replyText: "الرقم غير صحيح، يرجى إعادة إرسال الرقم مرة أخرى.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "ar",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(decision.blocked, "case11: Arabic field-rejection hallucination must be blocked");
}

// -----------------------------------------------------------------------
// Case 12: "shall I confirm" is an offer, not an order-placed claim
// -----------------------------------------------------------------------
{
  assert(
    !looksLikeOrderPlacedClaim("Shall I confirm the order?"),
    "case12: offer to confirm is not a placed-claim",
  );
  assert(
    !looksLikeOrderPlacedClaim("Do you want me to place the order now?"),
    "case12b: offer to place is not a placed-claim",
  );
}

// -----------------------------------------------------------------------
// Case 13: price extraction tolerance
// -----------------------------------------------------------------------
{
  const prices = extractMentionedPrices("Total is 1.250 KWD, delivered by 3 KD.");
  assert(prices.length === 2, `case13: two prices expected, got ${prices.length}`);
  assert(prices.includes(1.25), "case13: must include 1.25");
  assert(prices.includes(3), "case13: must include 3");
}

// -----------------------------------------------------------------------
// Case 14: sanity — detector negatives for benign content
// -----------------------------------------------------------------------
{
  assert(
    !looksLikeFieldRejectionClaim("I'll use your WhatsApp number for the sender."),
    "case14: benign mention of 'number' must not trigger rejection detector",
  );
  assert(
    !looksLikeFieldRejectionClaim("Please send the sender's full name."),
    "case14b: 'please send name' without 'again/resend' must not trigger",
  );
}

console.log("ok: all 14 hallucination-guard smoke cases passed");
