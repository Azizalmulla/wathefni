#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Step-3 outbound-guards narrowing — "factual-only" policy.
//
// Locks in the Step-3 contract for outbound reply guards:
//
//   STRICT (factual / transactional — substitute on mismatch):
//     - Price drift in a complete-draft summary (summary_fact_drift)
//     - Missing payment/tracking URL or ORDER-id after create_simple_order /
//       track_order (shouldPreferCanonicalToolReply)
//
//   FREE (stylistic — log-only, trust the LLM's phrasing):
//     - stub_summary: short/sparse summary phrasing
//     - route_price_recap: mid-booking recap shape
//     - standalone_ack: bare "Sure" / "تمام" style acks
//     - Wrong-script swaps for get_price replies (feature retired)
//     - "Lossy" / price-only get_price replies (feature retired)
//     - Clarifying questions (explicitly preserved — detector still active)
//
// Any change that re-enables stylistic substitution, or that accidentally
// disables factual substitution, must break this smoke. New stylistic-only
// shapes should be added to the log-only assertions; new factual shapes
// should be added to the substitute-on-drift assertions.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

async function loadTsModule(relativePath) {
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const { verifyAndRepairOutbound } = await loadTsModule("plugins/shared/outbound-verify.ts");
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
  d.deliveryExtra = "Apartment 19";
  return d;
}

function buildCompleteEntry() {
  return {
    stage: "summary_shown",
    bookingStep: "summary_pending",
    bookingDraft: buildCompleteDraft(),
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  };
}

// =========================================================================
// FREE (log-only) — stylistic shapes must NOT be substituted
// =========================================================================

// Case F1: stub_summary on a complete draft → log-only
{
  const entry = buildCompleteEntry();
  const res = verifyAndRepairOutbound({
    replyText: "All set, ready to confirm?",
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(res.shape, "stub_summary");
  assert.equal(res.replaced, false, "F1: stub_summary must be log-only");
  assert.equal(res.reason, "detected_stub_summary_log_only");
  assert.equal(res.replyText, "All set, ready to confirm?");
}

// Case F2: route_price_recap mid-booking → log-only
{
  const draft = buildCompleteDraft();
  draft.recipientPhone = null;
  const entry = { ...buildCompleteEntry(), bookingDraft: draft };
  const res = verifyAndRepairOutbound({
    replyText: "Delivery from Hawalli to Salmiya. 1.250 KWD.",
    entry,
    missingFields: ["recipient.phone"],
    language: "en",
  });
  assert.equal(res.shape, "route_price_recap");
  assert.equal(res.replaced, false, "F2: route_price_recap must be log-only");
  assert.equal(res.reason, "detected_route_price_recap_log_only");
}

// Case F3: standalone_ack on complete draft → log-only (used to substitute)
{
  const entry = buildCompleteEntry();
  const res = verifyAndRepairOutbound({
    replyText: "Sure",
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(res.shape, "standalone_ack");
  assert.equal(res.replaced, false, "F3: standalone_ack must be log-only under Step-3");
  assert.equal(res.reason, "detected_standalone_ack_log_only");
}

// Case F4: Arabic standalone_ack (تمام) on complete draft → log-only
{
  const entry = buildCompleteEntry();
  const res = verifyAndRepairOutbound({
    replyText: "تمام",
    entry,
    missingFields: [],
    language: "ar",
  });
  assert.equal(res.shape, "standalone_ack");
  assert.equal(res.replaced, false, "F4: Arabic ack must be log-only");
}

// Case F5: route_price_recap on complete draft → log-only
// (used to be substituted with the canonical summary)
{
  const entry = buildCompleteEntry();
  const res = verifyAndRepairOutbound({
    replyText: "Delivery from Hawalli to Salmiya, 1.250 KWD.",
    entry,
    missingFields: [],
    language: "en",
  });
  // Without identity mentions and without an ask, this is a route_price_recap
  // even at draft-complete stage. Under the new policy: log-only.
  assert.equal(res.shape, "route_price_recap");
  assert.equal(res.replaced, false, "F5: route_price_recap on complete draft is log-only");
}

// =========================================================================
// STRICT (factual) — drift must still be substituted
// =========================================================================

// Case S1: summary_fact_drift (wrong price) → substitute with canonical
{
  const entry = buildCompleteEntry();
  const drifty = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96562844738",
    "Service: Standard sedan",
    "Price: 5.000 KWD",
    "Confirm?",
  ].join("\n");
  const res = verifyAndRepairOutbound({
    replyText: drifty,
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(res.shape, "summary_fact_drift");
  assert.equal(res.replaced, true, "S1: fact drift must still substitute");
  assert.match(res.replyText, /1\.250 KWD/);
  assert.ok(!/5\.000 KWD/.test(res.replyText), "S1: drifted price must be gone");
}

// Case S2: summary_fact_drift (wrong phone) → substitute
{
  const entry = buildCompleteEntry();
  const drifty = [
    "*Order summary*",
    "Pickup: Hawalli — Block 6, Street 9, House 17",
    "Delivery: Salmiya — Block 2, Street 9, Apartment 19",
    "Sender: Aziz — 96597485757",
    "Recipient: Ahmed — 96512345678", // wrong tail
    "Service: Standard sedan",
    "Price: 1.250 KWD",
    "Confirm?",
  ].join("\n");
  const res = verifyAndRepairOutbound({
    replyText: drifty,
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(res.shape, "summary_fact_drift");
  assert.equal(res.replaced, true, "S2: wrong phone in summary must substitute");
  assert.match(res.replyText, /96562844738/);
}

// =========================================================================
// PRESERVED — clarifying questions must always pass through
// =========================================================================

// Case C1: clarifying question mid-repair → pass through
{
  const entry = buildCompleteEntry();
  // Simulate a poisoned stored name to force the LLM into a repair.
  entry.bookingDraft.senderName = "Is this the cheapest option";
  const clarify = `Please confirm the sender name. Is it "Aziz" or "Is this the cheapest option"?`;
  const res = verifyAndRepairOutbound({
    replyText: clarify,
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(res.shape, "clarifying_question");
  assert.equal(res.replaced, false, "C1: clarifying questions never substituted");
  assert.equal(res.reason, "preserved_clarifying_question");
  assert.equal(res.replyText, clarify);
}

// =========================================================================
// SOURCE-SHAPE ANCHORS — lock in the deletion of stylistic branches
// =========================================================================

const indexSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// The wrong-script blanket swap was deleted.
assert.ok(
  !/wrongLanguageForConversation/.test(indexSrc),
  "SA1: wrongLanguageForConversation branch must stay removed",
);

// The get_price "lossy" branch was deleted.
assert.ok(
  !/replyLooksLossy/.test(indexSrc) && !/sharesKnownPrice/.test(indexSrc),
  "SA2: get_price lossy/sharesKnownPrice branches must stay removed",
);

// shouldReplaceGreetingForLanguage was deleted.
assert.ok(
  !/function shouldReplaceGreetingForLanguage\s*\(/.test(indexSrc),
  "SA3: shouldReplaceGreetingForLanguage must stay deleted",
);

// shouldPreferCanonicalToolReply was inlined into the outbound-decision
// module in the Step-4 consolidation. The underlying factual-only policy
// is now encoded by `needsCanonicalOverwriteForTxArtifacts` in
// `plugins/octopus-channel/lib/outbound-decision.ts`. We anchor:
//   - the original function name no longer exists as a definition anywhere,
//   - the replacement helper has the right factual-only signature,
//   - the stylistic params (preferredLanguage / scriptMode /
//     extractPricesFromText) are NOT on the replacement.
{
  const outboundDecisionSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/lib/outbound-decision.ts"),
    "utf8",
  );
  assert.ok(
    !/function shouldPreferCanonicalToolReply\s*\(/.test(indexSrc),
    "SA4: shouldPreferCanonicalToolReply must not live in index.ts anymore (moved to outbound-decision module)",
  );
  assert.ok(
    !/function shouldPreferCanonicalToolReply\s*\(/.test(outboundDecisionSrc),
    "SA4a: shouldPreferCanonicalToolReply must not be re-introduced in outbound-decision (policy lives in needsCanonicalOverwriteForTxArtifacts)",
  );
  const sig = outboundDecisionSrc.match(
    /function needsCanonicalOverwriteForTxArtifacts\(args: \{[\s\S]*?\}\): boolean \{/,
  );
  assert.ok(sig, "SA4b: needsCanonicalOverwriteForTxArtifacts signature must exist");
  const signature = sig[0];
  assert.ok(!/preferredLanguage/.test(signature), "SA4c: preferredLanguage param removed");
  assert.ok(!/scriptMode/.test(signature), "SA4d: scriptMode param removed");
  assert.ok(!/extractPricesFromText/.test(signature), "SA4e: extractPricesFromText param removed");
  assert.ok(/toolName/.test(signature), "SA4f: toolName param kept");
  assert.ok(/canonical/.test(signature), "SA4g: canonical param kept");
  assert.ok(/lastToolAgeMs/.test(signature), "SA4h: lastToolAgeMs param kept");
}

// Factual guards stay present (defense-in-depth). Post-Step-4 the price
// whitelist and same-route quote correction log messages are emitted via
// the outbound-decision module; anchor both locations.
{
  const outboundDecisionSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/lib/outbound-decision.ts"),
    "utf8",
  );
  assert.ok(
    /\[guard\] BLOCKED hallucinated prices/.test(outboundDecisionSrc),
    "SA5: outbound price whitelist log marker must stay (in outbound-decision)",
  );
  assert.ok(
    /Replaced semantically wrong same-route quote reply/.test(outboundDecisionSrc),
    "SA6: same-route quote correction log marker must stay (in outbound-decision)",
  );
}
assert.ok(
  /blocked booking transition for non-direct-bookable option/.test(indexSrc),
  "SA7: non-direct-bookable block log marker must stay (in index.ts booking-transition block)",
);

console.log("ALL PASS smoke-test-outbound-guards-factual-only.mjs");
