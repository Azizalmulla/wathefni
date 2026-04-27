#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Step-5 compact factual drift detector (log-only).
//
// Step 5 adds `verifyCompactFactualClaims` in
// `plugins/shared/outbound-verify.ts` and wires it into
// `decidePostStateOutbound` as a log-only observation. No substitution,
// no new reason code, no decision-kind change. The whole point of this
// smoke is to lock in both halves of that contract:
//
//   (a) The DETECTOR catches compact wrong-claim cases AND leaves
//       compact no-claim / correct-claim cases alone. False-positive
//       resistance is the critical property.
//
//   (b) The DECISION MODULE emits a `[one-brain/compact-fact-drift]`
//       warn entry on detection but does NOT substitute `replyText`
//       and does NOT change `decision` / `reason`.
//
// If a later step promotes the detector to substitution, the decision
// enum grows and this smoke needs to be updated alongside it. Until
// then, Step 5 stays behavioral-noop for the customer.
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

const { verifyCompactFactualClaims } = await loadTsModule(
  "plugins/shared/outbound-verify.ts",
);
const { decidePostStateOutbound } = await loadTsModule(
  "plugins/octopus-channel/lib/outbound-decision.ts",
);
const { createEmptyBookingDraft } = await loadTsModule(
  "plugins/shared/conversation-policy.ts",
);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function buildCompleteDraft() {
  const d = createEmptyBookingDraft();
  d.senderName = "Aziz";
  d.senderPhone = "96597485757";
  d.recipientName = "Ahmad";
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

const noopBuilders = {
  buildDeterministicGraceWindowReply: (l) => (l === "ar" ? "نافذة سماح" : "Grace window reply"),
  buildProviderIssueFallbackReply: (l) =>
    l === "ar" ? "يوجد خلل فني، جربوا بعد شوي." : "There's a technical issue, please try again in a moment.",
};

// ---------------------------------------------------------------------------
// (1) Detector unit behavior — drift must be caught
// ---------------------------------------------------------------------------

// D1: compact stub reply with a wrong recipient phone tail. Stored
// recipient tail is "4738"; reply mentions "99991111". Drift.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Got it, sending to +96599991111. All set?",
    entry,
  );
  assert.equal(res.consistent, false, "D1: wrong phone tail must be inconsistent");
  assert.ok(
    res.mismatches.some((m) => m.kind === "phone"),
    "D1: mismatch must be tagged kind=phone",
  );
}

// D2: compact ack-like reply that attributes to the wrong name. Stored
// recipient is "Ahmad"; reply says "sending to Sara". Drift.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Got it, sending to Sara. Confirm?",
    entry,
  );
  assert.equal(res.consistent, false, "D2: wrong attribution name must be inconsistent");
  assert.ok(
    res.mismatches.some((m) => m.kind === "name"),
    "D2: mismatch must be tagged kind=name",
  );
}

// D3: wrong sender name with explicit attribution. Stored sender is
// "Aziz"; reply says "sender Jamal". Drift.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "All set — sender Jamal, confirming now.",
    entry,
  );
  assert.equal(res.consistent, false, "D3: wrong sender name must be inconsistent");
  assert.ok(res.mismatches.some((m) => m.kind === "name"));
}

// D4: wrong sender phone tail. Stored sender tail "5757" vs reply
// "11112222".
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Quick one, sender 96511112222 confirmed.",
    entry,
  );
  assert.equal(res.consistent, false, "D4: wrong sender phone tail must be inconsistent");
  assert.ok(res.mismatches.some((m) => m.kind === "phone"));
}

// ---------------------------------------------------------------------------
// (2) Detector unit behavior — false-positive resistance
// ---------------------------------------------------------------------------

// N1: compact stub with no phone / name claim at all.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims("All set, ready to confirm?", entry);
  assert.equal(res.consistent, true, "N1: no claims must be consistent");
  assert.equal(res.mismatches.length, 0);
}

// N2: compact reply with a correct phone tail.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Got it, sending to 96562844738. Confirm?",
    entry,
  );
  assert.equal(res.consistent, true, "N2: correct phone tail must be consistent");
}

// N3: compact reply with a correct recipient name.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Got it, sending to Ahmad. Confirm?",
    entry,
  );
  assert.equal(res.consistent, true, "N3: correct name must be consistent");
}

// N4: generic verb with capitalised first word ("Sending your order
// now.") — no attribution preposition so no claim, must not be flagged.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims("Sending your order now.", entry);
  assert.equal(res.consistent, true, "N4: bare capitalised verb is not a name claim");
}

// N5: reply greets the customer by their own stored sender name. "Hi
// Aziz" uses a preposition-less greeting — even though "Aziz" is a
// stored name, there's no false drift because Aziz is matched.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims("Hi Aziz — processing now.", entry);
  assert.equal(res.consistent, true, "N5: greeting of stored sender must not flag");
}

// N6: Arabic-script attribution + correct recipient token.
{
  const entry = buildCompleteEntry();
  entry.bookingDraft.recipientName = "أحمد";
  const res = verifyCompactFactualClaims("تمام، نرسل إلى أحمد. أأكد؟", entry);
  assert.equal(res.consistent, true, "N6: correct Arabic name attribution must be consistent");
}

// N7: reply contains a short digit run (< 7 digits) that happens not to
// match. Should not be flagged as a phone claim — our rule requires
// ≥ 7 digits to count as a candidate.
{
  const entry = buildCompleteEntry();
  const res = verifyCompactFactualClaims(
    "Pickup at block 6, street 9, house 17. Confirm?",
    entry,
  );
  assert.equal(res.consistent, true, "N7: short digit runs must not be treated as phone claims");
}

// ---------------------------------------------------------------------------
// (3) Integration — detector must LOG but NOT substitute in the decision
// module.
// ---------------------------------------------------------------------------

// I1: wrong phone tail in a stub_summary shape → warn log emitted,
// replyText unchanged, decision=allow, reason=allow.
{
  const entry = buildCompleteEntry();
  const reply = "Got it, sending to +96599991111. All set?";
  const res = decidePostStateOutbound({
    replyText: reply,
    preferredLanguage: "en",
    conversationControllerEntry: entry,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "i1",
  });
  assert.equal(res.decision, "allow", "I1: Step-5 must not change decision kind");
  assert.equal(res.reason, "allow", "I1: Step-5 must not change reason code");
  assert.equal(res.replyText, reply, "I1: Step-5 must not mutate replyText");
  assert.equal(res.markedSummaryShown, false);
  const driftLog = res.logEntries.find((e) =>
    /\[one-brain\/compact-fact-drift\]/.test(e.message),
  );
  assert.ok(driftLog, "I1: compact-fact-drift warn log must be emitted");
  assert.equal(driftLog.level, "warn", "I1: drift log must be at warn level");
  assert.equal(driftLog.detail?.kind, "phone", "I1: detail.kind must be phone");
  assert.equal(driftLog.detail?.substituted, false, "I1: detail.substituted must be false");
}

// I2: wrong name attribution in a compact reply — same contract as I1.
{
  const entry = buildCompleteEntry();
  const reply = "Got it, sending to Sara. Confirm?";
  const res = decidePostStateOutbound({
    replyText: reply,
    preferredLanguage: "en",
    conversationControllerEntry: entry,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "i2",
  });
  assert.equal(res.decision, "allow");
  assert.equal(res.reason, "allow");
  assert.equal(res.replyText, reply);
  const driftLog = res.logEntries.find((e) =>
    /\[one-brain\/compact-fact-drift\]/.test(e.message),
  );
  assert.ok(driftLog, "I2: compact-fact-drift warn log must be emitted for name drift");
  assert.equal(driftLog.detail?.kind, "name");
}

// I3: healthy compact reply (no claims) must NOT emit the drift log.
{
  const entry = buildCompleteEntry();
  const res = decidePostStateOutbound({
    replyText: "All set, ready to confirm?",
    preferredLanguage: "en",
    conversationControllerEntry: entry,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "i3",
  });
  const driftLog = res.logEntries.find((e) =>
    /\[one-brain\/compact-fact-drift\]/.test(e.message),
  );
  assert.ok(!driftLog, "I3: no drift log for compact reply without claims");
}

// I4: clarifying question must skip the detector (already repair work).
{
  const entry = buildCompleteEntry();
  const res = decidePostStateOutbound({
    replyText: "Could you confirm the recipient phone number?",
    preferredLanguage: "en",
    conversationControllerEntry: entry,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "i4",
  });
  assert.equal(res.decision, "allow");
  assert.equal(res.reason, "preserve_clarification");
  const driftLog = res.logEntries.find((e) =>
    /\[one-brain\/compact-fact-drift\]/.test(e.message),
  );
  assert.ok(!driftLog, "I4: clarifying question must skip compact-fact-drift detector");
}

// ---------------------------------------------------------------------------
// (4) Source-shape anchors — Step-5 behavioral-noop contract
// ---------------------------------------------------------------------------

const moduleSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/lib/outbound-decision.ts"),
  "utf8",
);

// The decision kind union must STILL be the 5-way Step-4 contract —
// Step 5 does not widen it.
{
  const kindMatch = moduleSrc.match(
    /export type OutboundDecisionKind =\s*([\s\S]*?);/,
  );
  assert.ok(kindMatch, "Decision kind union must exist");
  const kinds = [...kindMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(
    kinds,
    ["allow", "allow_sanitized", "block_retry", "replace_authoritative", "replace_fallback"],
    "Step 5 must NOT add a new decision kind (log-only round)",
  );
}

// The reason code union must be the tight fixed enum. Each new guard keeps
// its own reason code rather than overloading an existing one.
{
  const reasonMatch = moduleSrc.match(
    /export type OutboundDecisionReason =\s*([\s\S]*?);/,
  );
  assert.ok(reasonMatch, "Reason code union must exist");
  const reasons = [...reasonMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(
    reasons,
    [
      "allow",
      "allow_sanitized",
      "block_provider_error",
      "fallback_empty_reply",
      "preserve_clarification",
      "replace_clarify_option_before_proceed",
      "replace_directive_ask",
      "replace_field_rejection_hallucination",
      "replace_get_price_bypass",
      "replace_manual_confirm_address_ask",
      "replace_manual_confirm_handoff",
      "replace_order_placed_hallucination",
      "replace_price_mismatch",
      "replace_stale_missing_field_ask",
      "replace_state_write_hallucination",
      "replace_summary_completion_checkpoint",
      "replace_summary_fact_drift",
      "replace_transaction_artifact_missing",
      "replace_untracked_multi_edit_ask",
    ],
    "Reason codes must be exactly the fixed enum (19 entries after multi-edit ask guard)",
  );
}

// The detector must be wired in (search for the log marker) AND must
// not mutate reply. The presence of both the import and the log marker
// in the source is our structural guarantee.
const verifySrc = fs.readFileSync(
  path.join(root, "plugins/shared/outbound-verify.ts"),
  "utf8",
);
assert.ok(
  /export function verifyCompactFactualClaims\s*\(/.test(verifySrc),
  "verifyCompactFactualClaims must exist in outbound-verify.ts",
);
assert.ok(
  /verifyCompactFactualClaims/.test(moduleSrc),
  "outbound-decision.ts must reference verifyCompactFactualClaims",
);
assert.ok(
  /\[one-brain\/compact-fact-drift\]/.test(moduleSrc),
  "outbound-decision.ts must emit the [one-brain/compact-fact-drift] log marker",
);

console.log("ALL PASS smoke-test-compact-factual-drift.mjs");
