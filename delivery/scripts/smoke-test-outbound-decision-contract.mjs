#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Step-4 outbound-decision contract.
//
// Locks in the Step-4 consolidation: every outbound-reply decision now
// flows through `decidePreStateOutbound` + `decidePostStateOutbound` in
// `plugins/octopus-channel/lib/outbound-decision.ts`, and every outcome
// lands on ONE of the tight fixed reason codes in the module's
// `OutboundDecisionReason` union.
//
// We verify:
//   1. The 5-decision vocabulary (`allow`, `allow_sanitized`,
//      `replace_authoritative`, `replace_fallback`, `block_retry`) is the
//      complete set of top-level outcomes.
//   2. The 14 reason codes are the complete set of reason codes exported.
//      (10 before Bug 1; + `replace_clarify_option_before_proceed` (Bug 1);
//       + `replace_manual_confirm_address_ask` +
//       `replace_manual_confirm_handoff` (Bug 4);
//       + `replace_directive_ask` (Phase 2 directive-to-reply registry).)
//   3. Representative callsites for each customer-outcome produce the
//      expected (decision, reason) pair:
//        - price whitelist → replace_fallback / replace_price_mismatch
//        - empty LLM reply → replace_fallback / fallback_empty_reply
//        - summary_fact_drift → replace_authoritative / replace_summary_fact_drift
//        - canonical tx-artifact loss → replace_authoritative /
//          replace_transaction_artifact_missing
//        - clarifying question → allow / preserve_clarification
//        - healthy natural reply → allow / allow
//   4. Source-shape anchors for the Step-4 refactor:
//        - `decidePreStateOutbound` and `decidePostStateOutbound` exist,
//        - `index.ts` no longer imports `verifyAndRepairOutbound` /
//          `runHallucinationGuard` directly,
//        - `shouldPreferCanonicalToolReply` is gone from `index.ts`.
//
// Any change that adds a new decision kind or reason code MUST update
// this smoke — that's the point: one fixed enum, one fixed contract.
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

const { decidePreStateOutbound, decidePostStateOutbound } = await loadTsModule(
  "plugins/octopus-channel/lib/outbound-decision.ts",
);
const { createEmptyBookingDraft } = await loadTsModule(
  "plugins/shared/conversation-policy.ts",
);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function priceExtractor(text) {
  const out = [];
  const re = /\b(\d+\.\d{3})\b/g;
  let m;
  while ((m = re.exec(text)) !== null) out.push(m[1]);
  return out;
}

function fakeSessionGuard(overrides = {}) {
  return {
    allValidPrices: new Set(["1.250"]),
    lastToolTs: Date.now(),
    lastToolName: "get_price",
    ...overrides,
  };
}

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

const noopBuilders = {
  buildDeterministicSelectedQuotedOptionReply: ({ language }) =>
    language === "ar" ? "خيار موثق" : "Verified option reply",
  buildDeterministicGraceWindowReply: (l) => (l === "ar" ? "نافذة سماح" : "Grace window reply"),
  buildProviderIssueFallbackReply: (l) =>
    l === "ar" ? "يوجد خلل فني، جربوا بعد شوي." : "There's a technical issue, please try again in a moment.",
};

// ---------------------------------------------------------------------------
// (1) Decision + reason code vocabulary anchors
// ---------------------------------------------------------------------------
// We can't introspect a TS union at runtime, but we can anchor the module
// source. If someone adds a new kind or reason without updating this smoke,
// the assertion fails.

const moduleSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/lib/outbound-decision.ts"),
  "utf8",
);

{
  const kindMatch = moduleSrc.match(
    /export type OutboundDecisionKind =\s*([\s\S]*?);/,
  );
  assert.ok(kindMatch, "Decision kind union must exist");
  const kinds = [...kindMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(
    kinds,
    ["allow", "allow_sanitized", "block_retry", "replace_authoritative", "replace_fallback"],
    "Decision kinds must be exactly the 5-way contract",
  );
}

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
      "replace_summary_fact_drift",
      "replace_transaction_artifact_missing",
    ],
    "Reason codes must be exactly the fixed enum (15 entries after Class-15 bypass repair)",
  );
}

// ---------------------------------------------------------------------------
// (2) Behavioral anchors — pre-state (Region A)
// ---------------------------------------------------------------------------

// A-clean: healthy LLM reply with a valid price → allow / allow
{
  const res = decidePreStateOutbound({
    replyText: "Sure, 1.250 KWD for this trip.",
    preferredLanguage: "en",
    sessionGuard: fakeSessionGuard(),
    sessionIsRecent: true,
    preferredCanonicalText: "Canonical price message",
    guardToolAgeMs: 1000,
    canonicalOverwriteAllowed: false, // stage=quoted post-price → no overwrite
    canonicalOverwriteSkipReason: "post_quote_stage:quoted",
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "quoted",
  });
  assert.equal(res.decision, "allow", "A-clean: healthy reply allowed");
  assert.equal(res.reason, "allow", "A-clean: reason=allow");
  assert.equal(res.replyText, "Sure, 1.250 KWD for this trip.");
}

// A-price: hallucinated KWD token → replace_fallback / replace_price_mismatch
{
  const res = decidePreStateOutbound({
    replyText: "Great news — only 0.750 KWD.",
    preferredLanguage: "en",
    sessionGuard: fakeSessionGuard(),
    sessionIsRecent: true,
    preferredCanonicalText: null,
    guardToolAgeMs: 1000,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "quoted",
  });
  assert.equal(res.decision, "replace_fallback", "A-price: price whitelist blocks without canonical");
  assert.equal(res.reason, "replace_price_mismatch");
  assert.ok(/pricing error/i.test(res.replyText), "A-price: pricing-error fallback used");
  assert.ok(
    res.logEntries.some((e) => e.level === "warn" && /BLOCKED hallucinated prices/.test(e.message)),
    "A-price: must emit whitelist warn log",
  );
}

// A-price-canonical: hallucinated KWD token + canonical available →
// replace_authoritative / replace_price_mismatch
{
  const res = decidePreStateOutbound({
    replyText: "Great news — only 0.750 KWD.",
    preferredLanguage: "en",
    sessionGuard: fakeSessionGuard(),
    sessionIsRecent: true,
    preferredCanonicalText: "The correct price is 1.250 KWD.",
    guardToolAgeMs: 1000,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "quoted",
  });
  assert.equal(res.decision, "replace_authoritative", "A-price-canonical: canonical substituted");
  assert.equal(res.reason, "replace_price_mismatch");
  assert.equal(res.replyText, "The correct price is 1.250 KWD.");
}

// A-txartifact: create_simple_order reply lost the tracking URL within 15s
// → replace_authoritative / replace_transaction_artifact_missing
{
  const res = decidePreStateOutbound({
    replyText: "Order created. We'll deliver it soon.",
    preferredLanguage: "en",
    sessionGuard: fakeSessionGuard({ lastToolName: "create_simple_order", allValidPrices: new Set() }),
    sessionIsRecent: true,
    preferredCanonicalText:
      "Order ORDER-abc-123 created. Track: https://riders.example/track/abc",
    guardToolAgeMs: 2000,
    canonicalOverwriteAllowed: true,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "idle",
  });
  assert.equal(res.decision, "replace_authoritative");
  assert.equal(res.reason, "replace_transaction_artifact_missing");
  assert.ok(/https:\/\//.test(res.replyText), "canonical with URL restored");
}

// A-empty-fill: empty LLM reply + recent canonical → replace_authoritative
// / replace_transaction_artifact_missing
{
  const res = decidePreStateOutbound({
    replyText: "",
    preferredLanguage: "en",
    sessionGuard: fakeSessionGuard({ lastToolName: "get_price" }),
    sessionIsRecent: true,
    preferredCanonicalText: "Price: 1.250 KWD.",
    guardToolAgeMs: 1000,
    canonicalOverwriteAllowed: true,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "idle",
  });
  assert.equal(res.decision, "replace_authoritative", "A-empty-fill: empty reply filled from canonical");
  assert.equal(res.reason, "replace_transaction_artifact_missing");
  assert.equal(res.replyText, "Price: 1.250 KWD.");
}

// ---------------------------------------------------------------------------
// (3) Behavioral anchors — post-state (Regions B + C)
// ---------------------------------------------------------------------------

// B-empty: no controller entry, empty reply → replace_fallback /
// fallback_empty_reply (generic provider-issue fallback)
{
  const res = decidePostStateOutbound({
    replyText: "",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "c1",
  });
  assert.equal(res.decision, "replace_fallback");
  assert.equal(res.reason, "fallback_empty_reply");
  assert.ok(/technical issue/.test(res.replyText), "provider-issue fallback used");
  assert.ok(
    res.logEntries.some((e) => e.level === "warn" && /LLM produced empty reply/.test(e.message)),
    "empty-reply warn log emitted",
  );
}

// B-transition-edit: summary_edit_request hint + empty reply → fallback
{
  const res = decidePostStateOutbound({
    replyText: "",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: "summary_edit_request",
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "c1",
  });
  assert.equal(res.decision, "replace_fallback");
  assert.equal(res.reason, "fallback_empty_reply");
  assert.ok(/change/.test(res.replyText), "summary-edit-request template used");
}

// C-drift: summary_fact_drift on complete draft → replace_authoritative /
// replace_summary_fact_drift + markedSummaryShown
{
  const entry = buildCompleteEntry();
  entry.quotedPrice = 1.25;
  const driftyFullSummary = [
    "Sender: Aziz (7485)",
    "Recipient: Ahmed (4738)",
    "Pickup: Hawalli block 6, street 9, house 17",
    "Delivery: Salmiya block 2, street 9, apartment 19",
    "Service: sedan",
    "Total: 3.500 KWD",
    "Confirm?",
  ].join("\n");
  const res = decidePostStateOutbound({
    replyText: driftyFullSummary,
    preferredLanguage: "en",
    conversationControllerEntry: entry,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "summary_shown",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "c1",
  });
  assert.equal(res.decision, "replace_authoritative", "C-drift: fact drift triggers substitute");
  assert.equal(res.reason, "replace_summary_fact_drift");
  assert.equal(res.markedSummaryShown, true, "C-drift: marks summary shown for persistence");
  assert.ok(/1\.250|1\.25/.test(res.replyText), "C-drift: authoritative price used");
}

// C-clarify: clarifying question → allow / preserve_clarification
{
  const entry = buildCompleteEntry();
  const clarifyReply = "Could you confirm the recipient phone number?";
  const res = decidePostStateOutbound({
    replyText: clarifyReply,
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
    conversationId: "c1",
  });
  assert.equal(res.decision, "allow", "C-clarify: clarifying question passes through");
  assert.equal(res.reason, "preserve_clarification", "C-clarify: tagged preserve_clarification");
  assert.equal(res.markedSummaryShown, false);
  assert.equal(res.replyText, clarifyReply, "C-clarify: replyText unchanged");
  assert.equal(res.detectedShape, "clarifying_question");
}

// C-stub-log-only: stub_summary on complete draft → allow / allow (log-only)
// This is the Step-3 relaxation — anchored here to prove Step-4 did NOT
// accidentally re-introduce the substitute.
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
    conversationId: "c1",
  });
  assert.equal(res.decision, "allow", "C-stub-log-only: stub_summary still log-only post-Step-4");
  assert.equal(res.markedSummaryShown, false);
  assert.equal(res.replyText, "All set, ready to confirm?");
  assert.equal(res.detectedShape, "stub_summary");
}

// ---------------------------------------------------------------------------
// (3.5) Class-15 bypass repair (2026-04-21)
//
// Invariant under test: on a route-intent turn where no active quoted
// route exists AND `get_price` was NOT called this turn, if the LLM
// free-composed an area clarification the post-state decision MUST
// substitute it with the deterministic repair reply and tag the
// attribution as `server` via `replace_get_price_bypass`.
// ---------------------------------------------------------------------------

// C15-trigger-en: classic forward-path bypass. LLM replies "What's the
// delivery area?" on a `stage=idle` turn with route evidence in the
// inbound and no tool call → substitute + attribute as server.
{
  const res = decidePostStateOutbound({
    replyText: "Pickup from Salmiya. What's the delivery area?",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: true,
    conversationId: "c1",
  });
  assert.equal(
    res.decision,
    "replace_authoritative",
    "C15-trigger-en: free-composed area ask without get_price must be substituted",
  );
  assert.equal(res.reason, "replace_get_price_bypass");
  assert.equal(res.replyAuthor, "server");
  assert.ok(
    /pickup area and the delivery area together/i.test(res.replyText),
    `C15-trigger-en: repair reply should ask for both areas together, got ${JSON.stringify(res.replyText)}`,
  );
  assert.ok(
    res.logEntries.some(
      (e) =>
        e.level === "warn" &&
        /class-15\/bypass/.test(e.message) &&
        /free_composed_area_clarification/.test(e.message),
    ),
    "C15-trigger-en: must emit class-15 warn log line",
  );
}

// C15-trigger-ar: Arabic variant of the same bypass.
{
  const res = decidePostStateOutbound({
    replyText: "استلام من السالمية. شنو منطقة التوصيل بالضبط؟",
    preferredLanguage: "ar",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: true,
    conversationId: "c1",
  });
  assert.equal(res.decision, "replace_authoritative", "C15-trigger-ar: Arabic area ask substituted");
  assert.equal(res.reason, "replace_get_price_bypass");
  assert.ok(
    /منطقة التوصيل/.test(res.replyText),
    "C15-trigger-ar: repair reply must be Arabic and reference both areas",
  );
}

// C15-bypass-off: same LLM reply, but the caller says get_price fired
// this turn (`classFifteenBypass: false`). Must pass through unchanged.
{
  const res = decidePostStateOutbound({
    replyText: "Pickup from Salmiya. What's the delivery area?",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: false,
    conversationId: "c1",
  });
  assert.equal(
    res.decision,
    "allow",
    "C15-bypass-off: healthy tool-owned turn must not substitute",
  );
  assert.equal(res.replyText, "Pickup from Salmiya. What's the delivery area?");
}

// C15-nonmatching-shape: bypass asserted but reply isn't a free-composed
// area question (e.g. a grounded price recap). Detector must stay
// narrow — no substitution.
{
  const res = decidePostStateOutbound({
    replyText: "Thanks for your message, I'll check that in a moment.",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: true,
    conversationId: "c1",
  });
  assert.equal(
    res.decision,
    "allow",
    "C15-nonmatching-shape: non-area-question reply must pass through even under bypass flag",
  );
}

// C15-whichpart: "Which part of Kuwait City?" shape also caught.
{
  const res = decidePostStateOutbound({
    replyText: "Which part of Kuwait City?",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: true,
    conversationId: "c1",
  });
  assert.equal(res.decision, "replace_authoritative");
  assert.equal(res.reason, "replace_get_price_bypass");
}

// C15-price-reply-ignored: a price-bearing reply ("1.250 KWD ...") must
// NEVER be treated as a free-composed area clarification, because the
// `route_price_recap` / price-whitelist paths own that class.
{
  const res = decidePostStateOutbound({
    replyText: "Salmiya → Kuwait City, 1.250 KWD. What's the delivery area?",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: "idle",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    classFifteenBypass: true,
    conversationId: "c1",
  });
  assert.equal(
    res.decision,
    "allow",
    "C15-price-reply-ignored: price-bearing replies stay out of class-15 scope",
  );
}

// ---------------------------------------------------------------------------
// (4) Callsite source-shape anchors
// ---------------------------------------------------------------------------

const indexSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// `index.ts` must use the new decision entry points.
assert.ok(
  /decidePreStateOutbound\(/.test(indexSrc),
  "index.ts must call decidePreStateOutbound",
);
assert.ok(
  /decidePostStateOutbound\(/.test(indexSrc),
  "index.ts must call decidePostStateOutbound",
);

// `index.ts` must NOT import the lower-level guards directly anymore —
// they're encapsulated in the decision module.
assert.ok(
  !/from "\.\.\/shared\/outbound-verify"/.test(indexSrc),
  "index.ts must not import verifyAndRepairOutbound directly",
);
assert.ok(
  !/^\s*runHallucinationGuard,?\s*$/m.test(indexSrc),
  "index.ts must not import runHallucinationGuard directly",
);

// The Step-3 inlined `shouldPreferCanonicalToolReply` must be gone from
// `index.ts` — the factual-only policy now lives as
// `needsCanonicalOverwriteForTxArtifacts` inside the decision module.
assert.ok(
  !/function shouldPreferCanonicalToolReply\s*\(/.test(indexSrc),
  "shouldPreferCanonicalToolReply must be gone from index.ts",
);
assert.ok(
  /function needsCanonicalOverwriteForTxArtifacts\s*\(/.test(moduleSrc),
  "needsCanonicalOverwriteForTxArtifacts must live in outbound-decision.ts",
);

// The central emitter helper must exist so logs still surface.
assert.ok(
  /function emitOutboundDecisionLogs\s*\(/.test(indexSrc),
  "emitOutboundDecisionLogs helper must exist in index.ts",
);

// Class-15 wiring anchors (2026-04-21): the callsite must snapshot the
// dispatcher-entry wall-clock and pass `classFifteenBypass` through to
// the post-state decision.
assert.ok(
  /const\s+turnStartMs\s*=\s*Date\.now\(\)\s*;/.test(indexSrc),
  "index.ts must snapshot turnStartMs at dispatcher entry for class-15 detection",
);
assert.ok(
  /classFifteenBypass\s*,/.test(indexSrc),
  "index.ts must forward classFifteenBypass into decidePostStateOutbound",
);
assert.ok(
  /getPriceFiredThisTurn\s*=\s*[\s\S]*?sessionGuard\.lastToolTs\s*>=\s*turnStartMs/.test(
    indexSrc,
  ),
  "index.ts must compute getPriceFiredThisTurn using the turnStartMs snapshot",
);

console.log("ALL PASS smoke-test-outbound-decision-contract.mjs");
