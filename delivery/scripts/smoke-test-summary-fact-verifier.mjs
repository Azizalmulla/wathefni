#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the summary-fact verifier in outbound-verify.ts.
//
// The verifier extends the existing outbound-verify shape classifier with a
// factual check over summary-shape replies: even if the LLM's reply is
// structurally a valid order summary (labeled rows + ≥ 3 signals), we now
// reject it when any of its factual claims contradict server-side state
// (price / phone tail / stored names / pickup-and-delivery area) and
// substitute the canonical server-rendered summary.
//
// Scenarios covered:
//   1. Correct summary → ok (no drift, no substitution).
//   2. Wrong price in summary → summary_fact_drift → substitute.
//   3. Wrong phone in summary → summary_fact_drift → substitute.
//   4. Missing sender name in summary → summary_fact_drift → substitute.
//   5. Wrong delivery area in summary → summary_fact_drift → substitute.
//   6. Arabic summary matching state → ok.
//   7. Stub summary still classified as stub_summary (regression).
//   8. Mid-booking reply that mentions a "wrong" price is NOT a summary
//      — verifier only runs in draft-complete state (regression).
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

const { classifyOutboundReplyShape, verifyAndRepairOutbound, verifySummaryFacts } =
  await loadTsModule("plugins/shared/outbound-verify.ts");
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
    stage: "summary_shown",
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
// Case 1: correct summary → ok
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19, floor 8, door 11",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "",
    "Shall I confirm this order?",
  ].join("\n");
  const shape = classifyOutboundReplyShape({ replyText: reply, entry, missingFields: [], language: "en" });
  assert(shape === "ok", `case1: correct summary must be ok, got ${shape}`);
  const verify = verifySummaryFacts(reply, entry);
  assert(verify.consistent, `case1: no mismatches, got ${JSON.stringify(verify.mismatches)}`);
}

// -----------------------------------------------------------------------
// Case 2: wrong price (5.000 vs 1.250) → drift
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 5.000 KWD",
    "Confirm?",
  ].join("\n");
  const shape = classifyOutboundReplyShape({ replyText: reply, entry, missingFields: [], language: "en" });
  assert(shape === "summary_fact_drift", `case2: wrong price must drift, got ${shape}`);
  const decision = verifyAndRepairOutbound({ replyText: reply, entry, missingFields: [], language: "en" });
  assert(decision.replaced, "case2: must be substituted");
  assert(
    decision.replyText.includes("1.250"),
    `case2: substitute must contain authoritative price 1.250, got: ${decision.replyText.slice(0, 200)}`,
  );
  assert(
    !decision.replyText.includes("5.000"),
    "case2: substitute must NOT contain the wrong price",
  );
}

// -----------------------------------------------------------------------
// Case 3: wrong phone → drift
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96512345678", // wrong
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const shape = classifyOutboundReplyShape({ replyText: reply, entry, missingFields: [], language: "en" });
  assert(shape === "summary_fact_drift", `case3: wrong phone must drift, got ${shape}`);
}

// -----------------------------------------------------------------------
// Case 4: missing sender name → drift
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: — 96597485757", // name missing
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const verify = verifySummaryFacts(reply, entry);
  // Aziz appears nowhere → drift expected
  assert(
    !verify.consistent,
    `case4: missing sender name must flag drift, got ${JSON.stringify(verify.mismatches)}`,
  );
  assert(verify.mismatches.some((m) => m.field === "name"), "case4: mismatch must be a 'name' field");
}

// -----------------------------------------------------------------------
// Case 5: wrong delivery area → drift
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Jabriya — Block 2, Street 9, Apartment 19", // wrong area
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const verify = verifySummaryFacts(reply, entry);
  assert(
    !verify.consistent,
    `case5: wrong delivery area must flag drift, got ${JSON.stringify(verify.mismatches)}`,
  );
  assert(
    verify.mismatches.some((m) => m.field === "area"),
    "case5: mismatch must include area",
  );
}

// -----------------------------------------------------------------------
// Case 6: Arabic summary matching state → ok
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*ملخص الطلب*",
    "الاستلام: حولي — قطعة 6، شارع 9، منزل 17",
    "التسليم: السالمية — قطعة 2، شارع 9، شقة 19",
    "المرسل: Aziz — 96597485757",
    "المستلم: Ahmed — 96562844738",
    "الخدمة: سيدان عادي",
    "السعر: 1.250 د.ك",
    "",
    "أأكد الطلب؟",
  ].join("\n");
  const shape = classifyOutboundReplyShape({ replyText: reply, entry, missingFields: [], language: "ar" });
  assert(shape === "ok", `case6: Arabic matching summary must be ok, got ${shape}`);
}

// -----------------------------------------------------------------------
// Case 7: stub summary regression — still classified as stub_summary
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const shape = classifyOutboundReplyShape({
    replyText: "All set, ready to confirm?",
    entry,
    missingFields: [],
    language: "en",
  });
  assert(shape === "stub_summary", `case7: stub summary must still classify as stub_summary, got ${shape}`);
}

// -----------------------------------------------------------------------
// Case 8: mid-booking with a price mention is NOT summary_fact_drift.
// The fact-drift check only runs in draft-complete state.
// -----------------------------------------------------------------------
{
  const draft = buildCompleteDraft();
  draft.recipientPhone = null; // draft incomplete
  const entry = buildEntry(draft);
  const reply = "The price from Hawalli to Salmiya is 5.000 KWD. Who's the recipient?";
  const shape = classifyOutboundReplyShape({
    replyText: reply,
    entry,
    missingFields: ["recipient.phone"],
    language: "en",
  });
  // Mid-booking replies must not be classified as summary_fact_drift — the
  // fact-drift concept is only meaningful when the LLM is writing the FINAL
  // summary (draft complete). Here the reply is a mid-flow route-recap
  // with a follow-up ask (recipient?) so it should be "ok" — it has an
  // explicit ask, so looksLikeRoutePriceRecap excludes it.
  assert(shape === "ok", `case8: mid-booking recap-with-ask must be ok, got ${shape}`);
}

// -----------------------------------------------------------------------
// Case 9: phone-candidate extractor tolerance
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  // LLM writes phone with spaces: still should match stored
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: Aziz — +965 9748 5757",
    "Recipient: Ahmed — 6284 4738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const verify = verifySummaryFacts(reply, entry);
  assert(
    verify.consistent,
    `case9: spaced phone format must still match stored, got ${JSON.stringify(verify.mismatches)}`,
  );
}

// -----------------------------------------------------------------------
// Case 10: block/street digits are NOT mistaken for phones
// -----------------------------------------------------------------------
{
  const entry = buildEntry(buildCompleteDraft());
  const reply = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19, floor 8, door 11",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const verify = verifySummaryFacts(reply, entry);
  assert(
    verify.consistent,
    `case10: block/street/apt digits must not false-positive as phones, got ${JSON.stringify(verify.mismatches)}`,
  );
}

console.log("ok: all 10 summary fact-verifier smoke cases passed");
