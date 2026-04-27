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
//  11. State-write claims ("noted/saved/selected") require controller proof.
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
// Case 7: price mismatch — mentioned price is OUTSIDE the full quoted set
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
    // Even when the full valid set is passed, 5.000 is still out of it.
    activeQuotedPrices: [1.25, 1.75, 2.25],
  });
  assert(decision.blocked, "case7: price mismatch must be blocked");
  assert(decision.claims.includes("price_mismatch"), "case7: must detect price_mismatch");
  // B: price_mismatch must substitute with the neutral price_repair, NOT
  // the next_required_action. That's the whole point of "guards don't
  // advance the flow".
  assert(
    decision.substitutedFrom === "price_repair",
    `case7: substitute must be price_repair, got: ${decision.substitutedFrom}`,
  );
  assert(
    !/sender|phone|name/i.test(decision.replyText),
    `case7: repair must not ask for sender/phone/name, got: ${decision.replyText}`,
  );
  assert(
    /re-check|option/i.test(decision.replyText),
    `case7: repair must be a neutral re-ask about which option, got: ${decision.replyText}`,
  );
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

// -----------------------------------------------------------------------
// Case 15: 2026-04-19 "is there other options" incident.
//
// After a price quote, the LLM answered a legitimate option inquiry by
// listing the OTHER quoted options and their real quoted prices. The
// pre-fix guard compared each mentioned price against the single scalar
// `entry.quotedPrice` (the currently-selected option) and flagged them
// all as price_mismatch, then substituted ASK_SENDER_NAME_AND_PHONE.
//
// With the full active-quote price set plumbed through, the mention of
// every quoted option's real price must pass the guard untouched.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: 1.25 });
  const decision = runHallucinationGuard({
    replyText:
      "Yes, we have other options too. Express sedan is 1.750 KWD, Standard box van is 1.750 KWD, and Express box van is 2.250 KWD. Would you like to switch?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: [1.25, 1.75, 2.25],
  });
  assert(
    !decision.blocked,
    `case15: legit other-options reply must pass — got blocked=${decision.blocked} claims=${decision.claims.join(",")} reason=${decision.reason}`,
  );
  assert(
    decision.claims.length === 0,
    `case15: no claims expected; got ${decision.claims.join(",")}`,
  );
}

// -----------------------------------------------------------------------
// Case 16: mentioned price outside the full set still blocks.
//
// Valid set is {1.25, 1.75, 2.25}. Reply quotes 9.000 KWD — not in set.
// Guard must fire AND substitute the price_repair (not an ASK_*).
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: 1.25 });
  const decision = runHallucinationGuard({
    replyText: "Sedan is 1.750 KWD, and box van is 9.000 KWD.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: [1.25, 1.75, 2.25],
  });
  assert(decision.blocked, "case16: out-of-set price must block");
  assert(
    decision.claims.includes("price_mismatch"),
    "case16: must detect price_mismatch",
  );
  assert(
    decision.substitutedFrom === "price_repair",
    `case16: substitute must be price_repair, got ${decision.substitutedFrom}`,
  );
  assert(
    !/sender|name|phone/i.test(decision.replyText),
    `case16: repair must not advance to slot ask, got: ${decision.replyText}`,
  );
}

// -----------------------------------------------------------------------
// Case 17: rounding tolerance — "1.75" and "1.750" are the same price.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: 1.25 });
  const decision = runHallucinationGuard({
    replyText: "Express sedan is 1.75 KWD.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: [1.25, 1.75, 2.25],
  });
  assert(
    !decision.blocked,
    `case17: 1.75 must match 1.750 via tolerance — got ${JSON.stringify(decision)}`,
  );
}

// -----------------------------------------------------------------------
// Case 18: field_rejection_hallucination still advances to next ASK_*.
//
// The "guards don't advance the flow" principle is scoped to
// price_mismatch (where the LLM's false claim isn't about a specific
// slot). When the LLM falsely claims a customer-provided field is
// invalid, the correct repair IS to re-ask the server's real next slot.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const decision = runHallucinationGuard({
    replyText:
      "The phone numbers need to be resent in a valid format. Send the sender and recipient phone numbers again, digits only.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    activeQuotedPrices: [1.25],
  });
  assert(decision.blocked, "case18: field rejection hallucination must still block");
  assert(
    decision.substitutedFrom === "next_required_action" ||
      decision.substitutedFrom === "order_summary" ||
      decision.substitutedFrom === "generic_nudge",
    `case18: field-rejection substitute must stay on the legitimate-advance path, got ${decision.substitutedFrom}`,
  );
  assert(
    decision.substitutedFrom !== "price_repair",
    "case18: field-rejection must NOT be squashed into price_repair",
  );
}

// -----------------------------------------------------------------------
// Case 19: backwards compatibility — when no activeQuotedPrices is
// passed, legacy scalar-only behavior still works (uses entry.quotedPrice).
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft()); // quotedPrice 1.25
  const decision = runHallucinationGuard({
    replyText: "The price is 1.250 KWD. Shall I confirm?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    // No activeQuotedPrices — legacy caller.
  });
  assert(!decision.blocked, "case19: scalar-only match must pass (legacy path)");
}
{
  const entry = buildEntry(buildCompleteDraft()); // quotedPrice 1.25
  const decision = runHallucinationGuard({
    replyText: "The price is 9.000 KWD.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    // No activeQuotedPrices — legacy caller.
  });
  assert(
    decision.blocked && decision.claims.includes("price_mismatch"),
    "case19b: scalar-only out-of-set price still blocks (legacy path)",
  );
  assert(
    decision.substitutedFrom === "price_repair",
    "case19b: legacy blocked price_mismatch must still route to price_repair",
  );
}

// -----------------------------------------------------------------------
// Case 20: empty activeQuotedPrices + null entry.quotedPrice = no signal,
// do not fire price_mismatch. Err on the side of letting the reply
// through; create_simple_order and outbound-verify will catch real bugs.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: null });
  const decision = runHallucinationGuard({
    replyText: "The price is 9.000 KWD.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    activeQuotedPrices: [],
  });
  assert(
    !decision.claims.includes("price_mismatch"),
    "case20: no ground truth = no price_mismatch claim",
  );
}

// -----------------------------------------------------------------------
// Case 21: manual-confirmation option price ("Helper service" etc.).
//
// 2026-04-19 second incident regression: the caller unions
// `activeQuotedRoute.pricesByType` (bookable options) with
// `activeQuotedRoute.optionCatalog[*].quoted_price` (options the
// customer is allowed to hear a price for — including manual-confirm).
// Helper service is the canonical manual-confirm option: not in
// `pricesByType`, but in `optionCatalog` at 3.250 KWD.
//
// A reply that mentions "Helper service at 3.250 KWD" alongside the
// bookable options must pass — the price IS grounded in the quote,
// just in the option catalog rather than the bookable bucket.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: 1.25 });
  const activeQuotedPrices = [1.25, 1.75, 2.25, 3.25];
  const decision = runHallucinationGuard({
    replyText:
      "Yes, we also have Helper service at 3.250 KWD (manual confirmation required), or Express sedan at 1.750 KWD and Express box van at 2.250 KWD.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices,
  });
  assert(
    !decision.blocked,
    `case21: manual-confirm Helper price must pass — got blocked=${decision.blocked} claims=${decision.claims.join(",")}`,
  );
  assert(
    decision.claims.length === 0,
    `case21: no claims expected, got ${decision.claims.join(",")}`,
  );
}

// Companion: same union set, but the reply drifts to a price that is
// NOT in the catalog → still blocks, and still uses price_repair (not
// an ASK_* advancement).
{
  const entry = buildEntry(buildCompleteDraft(), { quotedPrice: 1.25 });
  const decision = runHallucinationGuard({
    replyText:
      "Helper service is 5.000 KWD (manual confirmation).",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: [1.25, 1.75, 2.25, 3.25],
  });
  assert(decision.blocked, "case21b: Helper-price drift must still block");
  assert(
    decision.claims.includes("price_mismatch"),
    "case21b: price_mismatch expected",
  );
  assert(
    decision.substitutedFrom === "price_repair",
    `case21b: substitute must be price_repair, got ${decision.substitutedFrom}`,
  );
  assert(
    !/sender|name|phone/i.test(decision.replyText),
    `case21b: repair must not advance to slot ask, got: ${decision.replyText}`,
  );
}

// -----------------------------------------------------------------------
// Case 22: LLM claims pickup area was noted, but server state has no pickup.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(createEmptyBookingDraft(), {
    stage: "idle",
    bookingStep: "none",
    quotePickupAreaNameEn: null,
    quotePickupAreaNameAr: null,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    quoteDropoffAreaNameEn: null,
    quoteDropoffAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedDeliveryType: null,
    quotedPrice: null,
  });
  const decision = runHallucinationGuard({
    replyText:
      "Yes, Sulaibikhat is covered. Pickup area noted as Zahra — send me the delivery area and I’ll quote it.",
    entry,
    missingFields: ["pickup.area", "delivery.area"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "idle",
    language: "en",
    nextRequiredAction: "ASK_MISSING_AREAS",
  });
  assert(decision.blocked, "case22: unsupported pickup noted claim must be blocked");
  assert(
    decision.claims.includes("state_write_hallucination"),
    "case22: must detect state_write_hallucination",
  );
  assert(
    !/pickup area noted as Zahra/i.test(decision.replyText),
    `case22: false state claim must not be sent, got ${decision.replyText}`,
  );
  assert(
    decision.substitutedFrom === "state_truth_repair" ||
      decision.substitutedFrom === "next_required_action",
    `case22: state write hallucination should use a specific repair or real next step, got ${decision.substitutedFrom}`,
  );
  assert(
    !/that detail/i.test(decision.replyText),
    `case22: state-truth repair must not be a vague "that detail" dead end, got ${decision.replyText}`,
  );
}

// -----------------------------------------------------------------------
// Case 23: same pickup-area wording is allowed when pending pickup exists.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(createEmptyBookingDraft(), {
    pendingPickupAreaNameEn: "Zahra",
    pendingPickupAreaNameAr: "الزهراء",
    quotePickupAreaNameEn: null,
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: null,
    quoteDropoffAreaNameAr: null,
    selectedDeliveryType: null,
    quotedPrice: null,
  });
  const decision = runHallucinationGuard({
    replyText: "Pickup area noted as Zahra. Please send the delivery area.",
    entry,
    missingFields: ["delivery.area"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "idle",
    language: "en",
    nextRequiredAction: "ASK_DELIVERY_AREA",
  });
  assert(!decision.blocked, "case23: grounded pickup noted claim must pass");
}

// -----------------------------------------------------------------------
// Case 24: sender-name state claim requires draft.senderName.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(createEmptyBookingDraft(), {
    quotePickupAreaNameEn: "Zahra",
    quoteDropoffAreaNameEn: "Sulaibikhat",
  });
  const decision = runHallucinationGuard({
    replyText: "Got it, sender name is Ahmed. Please send the sender phone.",
    entry,
    missingFields: ["sender.name", "sender.phone"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
  });
  assert(decision.blocked, "case24: unsupported sender-name claim must block");
  assert(
    decision.claims.includes("state_write_hallucination"),
    "case24: sender-name claim must be state_write_hallucination",
  );
}

// -----------------------------------------------------------------------
// Case 25: pickup location pin claim requires draft.pickupLocation.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(createEmptyBookingDraft());
  const decision = runHallucinationGuard({
    replyText: "I’ve got the pickup location pin. Please send the delivery address.",
    entry,
    missingFields: ["pickup.address"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_PICKUP_ADDRESS",
  });
  assert(decision.blocked, "case25: unsupported pickup pin claim must block");
}

// -----------------------------------------------------------------------
// Case 26: selected option claim requires selectedDeliveryType/label.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft(), {
    selectedDeliveryType: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionLabelAr: null,
  });
  const decision = runHallucinationGuard({
    replyText: "Selected standard sedan. Please send the sender name.",
    entry,
    missingFields: ["sender.name"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: [1.25],
  });
  assert(decision.blocked, "case26: unsupported selected-option claim must block");
}

// -----------------------------------------------------------------------
// Case 27: selected option proof understands canonical delivery-type IDs.
//
// Live all-in-one regression: server selected `sedan_fast`, LLM said
// "Express sedan is selected", and the state-truth guard falsely blocked
// because it compared raw `sedan_fast` text instead of canonical option
// identity.
// -----------------------------------------------------------------------
{
  const draft = buildCompleteDraft();
  draft.senderName = "Abdulaziz Almulla";
  draft.senderPhone = "96599338566";
  draft.recipientName = "Ahmad Basha";
  draft.recipientPhone = "99278765";
  draft.pickupBlock = "2";
  draft.pickupStreet = "7";
  draft.pickupHouse = "19";
  draft.deliveryBlock = "2";
  draft.deliveryStreet = "9";
  draft.deliveryHouse = null;
  draft.deliveryExtra = "Apartment 11, floor 4, door 2";
  const entry = buildEntry(draft, {
    stage: "summary_shown",
    bookingStep: "summary_pending",
    quotePickupAreaNameEn: "Sulaibikhat",
    quoteDropoffAreaNameEn: "Zahra",
    selectedDeliveryType: "sedan_fast",
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionLabelAr: null,
    quotedPrice: 1.75,
  });
  const reply = [
    "Got it. Express sedan is selected for Sulaibikhat to Zahra at 1.750 KWD.",
    "",
    "Summary:",
    "Sender, Abdulaziz Almulla, 96599338566.",
    "Recipient, Ahmad Basha, 99278765.",
    "Pickup, block 2, street 7, house 19.",
    "Delivery, block 2, street 9, apartment 11, floor 4, door 2.",
  ].join("\n");
  const decision = runHallucinationGuard({
    replyText: reply,
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "idle",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    activeQuotedPrices: [1.25, 1.75],
  });
  assert(
    !decision.blocked,
    `case27: express sedan must prove selectedDeliveryType=sedan_fast; got blocked=${decision.blocked} claims=${decision.claims.join(",")} reason=${decision.reason}`,
  );
}

// -----------------------------------------------------------------------
// Case 28: canonical summaries with address lines are not stale address asks.
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, apartment 19, floor 8, door 11",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "",
    "Shall I confirm this order?",
  ].join("\n");
  const decision = runHallucinationGuard({
    replyText: reply,
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "awaiting_confirmation",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    activeQuotedPrices: [1.25],
  });
  assert(
    !decision.claims.includes("stale_missing_field_ask"),
    `case28: canonical summary must not look like stale address ask; got ${decision.claims.join(",")}`,
  );
}

// -----------------------------------------------------------------------
// Case 29: guard repair carries conflict values into CONFIRM_SLOT_CONFLICT.
// -----------------------------------------------------------------------
{
  const draft = buildCompleteDraft();
  const entry = buildEntry(draft, {
    dialogState: {
      version: 1,
      requestedSlot: { name: "sender_name", options: null, askedTs: Date.now() },
      slots: {
        sender_name: {
          value: "Abdulaziz almulla",
          status: "conflict",
          lastSetTs: Date.now(),
          lastSource: "llm_apply",
          conflictCandidate: "Rawan al ajmi",
        },
      },
    },
  });
  const decision = runHallucinationGuard({
    replyText: "I still need the pickup block.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "awaiting_confirmation",
    language: "en",
    nextRequiredAction: "CONFIRM_SLOT_CONFLICT",
    activeQuotedPrices: [1.25],
  });
  assert(decision.blocked, "case29: stale pickup block ask should be blocked");
  assert(
    /Abdulaziz almulla/.test(decision.replyText) && /Rawan al ajmi/.test(decision.replyText),
    `case29: conflict repair must include both values, got ${decision.replyText}`,
  );
  assert(
    !/that field/i.test(decision.replyText),
    `case29: conflict repair must not use vague fallback, got ${decision.replyText}`,
  );
}

console.log("ok: all 29 hallucination-guard smoke cases passed");
