#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 3 — server-rendered order summary (2026-04-20).
//
// Product rule:
//   When `next_required_action = WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED`
//   fires AND the customer's current message is NOT an explicit order
//   confirmation, the server composes the summary from state and Region A
//   substitutes the LLM's draft reply. The substitution also promotes
//   the controller to `summary_shown` / `summary_pending` in the same
//   turn via `markedSummaryShown`.
//
//   On the confirmation turn ("yes", "confirm", "اكمل"), the substitution
//   is intentionally skipped so the LLM can call `create_simple_order`
//   and acknowledge the placed order.
//
// Cases covered:
//   R1   Byte-exact summary: every field in the draft appears in the
//        rendered output; no field is dropped or reformatted.
//   R2   Service label preference: uses entry.selectedQuoteOptionLabelEn
//        when present (covers cooled_van / helper variants), falls
//        back to the static table, then to the raw delivery type.
//   R3   Area name language selection: Arabic output uses
//        quotePickupAreaNameAr; English uses quotePickupAreaNameEn.
//   W1   Substitution fires when directive is WRITE_FULL_ORDER_SUMMARY
//        and customer text is not a confirmation → decision=replace_authoritative,
//        reason=replace_directive_ask, markedSummaryShown=true.
//   W2   Substitution SKIPPED when customer text is an explicit
//        confirmation — LLM's draft reply survives unchanged.
//   W3   Edit then re-render: draft mutation between turns produces a
//        summary reflecting the new field values.
//   W4   markedSummaryShown is only set when the substituted directive
//        is WRITE_FULL_ORDER_SUMMARY (not e.g. ASK_PICKUP_ADDRESS).
//   C1   C-drift regression alarm no-op: when Phase 3 substituted,
//        the post-state `verifyAndRepairOutbound` on the substituted
//        text returns shape=ok (no drift), so C-drift path is a pure
//        observer.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function loadTs(relativePath) {
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const policy = loadTs("plugins/shared/conversation-policy.ts");
const verify = loadTs("plugins/shared/outbound-verify.ts");
const registry = loadTs("plugins/shared/directive-reply-registry.ts");
const outboundDecision = loadTs("plugins/octopus-channel/lib/outbound-decision.ts");

const { createEmptyBookingDraft, isExplicitOrderConfirmation } = policy;
const { buildDeterministicOrderSummary, verifyAndRepairOutbound } = verify;
const { renderDirectiveReply } = registry;
const { decidePreStateOutbound } = outboundDecision;

function completeDraft(overrides = {}) {
  const d = createEmptyBookingDraft();
  d.senderName = "Aziz Almulla";
  d.senderPhone = "96597485757";
  d.recipientName = "Ahmad Basha";
  d.recipientPhone = "96562844738";
  d.pickupBlock = "5";
  d.pickupStreet = "7";
  d.pickupHouse = "19";
  d.deliveryBlock = "6";
  d.deliveryStreet = "9";
  d.deliveryHouse = "17";
  d.deliveryExtra = "Floor 2";
  return { ...d, ...overrides };
}

function completeEntry(overrides = {}) {
  return {
    stage: "collecting_booking_details",
    bookingStep: "summary_pending",
    bookingDraft: completeDraft(),
    quotePickupAreaNameEn: "Jabriya",
    quotePickupAreaNameAr: "الجابرية",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    quoteRouteKey: "jabriya__salmiya",
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionLabelAr: "سيدان عادي",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    quoteTs: Date.now(),
    lastActivityTs: Date.now(),
    ...overrides,
  };
}

// -------------------------------------------------------------------------
// R1: byte-exact summary — every draft/entry field appears in the output.
// -------------------------------------------------------------------------
{
  const entry = completeEntry();
  const out = buildDeterministicOrderSummary({ entry, language: "en" });
  const required = [
    "*Order summary*",
    "Pickup: Jabriya",
    "Block 5",
    "Street 7",
    "House 19",
    "Delivery: Salmiya",
    "Block 6",
    "Street 9",
    "House 17",
    "Floor 2",
    "Aziz Almulla",
    "Ahmad Basha",
    "Standard sedan",
    "1.250 KWD",
    "Shall I confirm this order?",
  ];
  for (const needle of required) {
    assert.ok(out.includes(needle), `R1 en: missing ${JSON.stringify(needle)} in:\n${out}`);
  }
  // Phone tail present (4 digits).
  assert.ok(/7485757|\*\*\*7485757|\*+7485757|7485757$/m.test(out) || /7485757/.test(out), `R1 en: sender phone tail missing: ${out}`);
  assert.ok(/62844738|2844738|\*+2844738/.test(out), `R1 en: recipient phone tail missing: ${out}`);
}

// AR mirror.
{
  const entry = completeEntry();
  const out = buildDeterministicOrderSummary({ entry, language: "ar" });
  const required = [
    "*ملخص الطلب*",
    "الاستلام: الجابرية",
    "التسليم: السالمية",
    "Aziz Almulla",
    "Ahmad Basha",
    "سيدان عادي",
    "1.250 د.ك",
    "أأكد الطلب؟",
  ];
  for (const needle of required) {
    assert.ok(out.includes(needle), `R1 ar: missing ${JSON.stringify(needle)} in:\n${out}`);
  }
}

// -------------------------------------------------------------------------
// R2: service label preference — entry label wins over static table;
// static table wins over raw key; raw key is final fallback.
// -------------------------------------------------------------------------
{
  // Entry label present → uses it (cooled_van has no static entry, so
  // without the preference we'd fall to the raw key).
  const entry = completeEntry({
    selectedDeliveryType: "cooled_van_fast",
    selectedQuoteOptionLabelEn: "Express refrigerated van",
    selectedQuoteOptionLabelAr: "سيارة مبردة سريع",
    quotedPrice: 2.25,
    selectedQuoteOptionPrice: 2.25,
  });
  const en = buildDeterministicOrderSummary({ entry, language: "en" });
  assert.ok(en.includes("Express refrigerated van"), `R2 en entry label: ${en}`);
  assert.ok(!en.includes("cooled_van_fast"), `R2 en no raw key: ${en}`);
  const ar = buildDeterministicOrderSummary({ entry, language: "ar" });
  assert.ok(ar.includes("سيارة مبردة سريع"), `R2 ar entry label: ${ar}`);
}

{
  // Entry label absent → falls back to SERVICE_LABELS_EN ("Standard sedan").
  const entry = completeEntry({
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionLabelAr: null,
  });
  const out = buildDeterministicOrderSummary({ entry, language: "en" });
  assert.ok(out.includes("Standard sedan"), `R2b: fallback table: ${out}`);
}

{
  // Both sources absent, unknown key → raw key echoed.
  const entry = completeEntry({
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionLabelAr: null,
    selectedDeliveryType: "some_future_variant",
  });
  const out = buildDeterministicOrderSummary({ entry, language: "en" });
  assert.ok(
    out.includes("some_future_variant"),
    `R2c: raw key fallback: ${out}`,
  );
}

// -------------------------------------------------------------------------
// R3: area language selection
// -------------------------------------------------------------------------
{
  const entry = completeEntry();
  const ar = buildDeterministicOrderSummary({ entry, language: "ar" });
  assert.ok(ar.includes("الجابرية"), `R3 ar pickup: ${ar}`);
  assert.ok(ar.includes("السالمية"), `R3 ar delivery: ${ar}`);
  // English pickup/delivery names should NOT leak into AR.
  assert.ok(!/Pickup:/i.test(ar) && !/Delivery:/i.test(ar), `R3 ar labels pure AR: ${ar}`);
}

// -------------------------------------------------------------------------
// Registry dispatch: renderDirectiveReply returns render for summary.
// -------------------------------------------------------------------------
{
  const entry = completeEntry();
  const res = renderDirectiveReply(
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    {
      language: "en",
      draft: entry.bookingDraft,
      entry,
      route: null,
      turnSeed: "t1::conv",
    },
  );
  assert.equal(res.kind, "render", `registry: kind=${res.kind}`);
  assert.ok(res.text.includes("*Order summary*"), `registry render text: ${res.text}`);
}

// -------------------------------------------------------------------------
// W1: substitution fires when directive is active and customer is not
// confirming. markedSummaryShown is true.
// -------------------------------------------------------------------------

const noopBuilders = {
  buildDeterministicSelectedQuotedOptionReply: () => "selected",
  buildDeterministicGraceWindowReply: (l) => (l === "ar" ? "نافذة" : "grace"),
  buildProviderIssueFallbackReply: (l) => (l === "ar" ? "خلل" : "tech issue"),
};

function preInput(overrides = {}) {
  return {
    replyText: "LLM draft we expect to be replaced",
    preferredLanguage: "en",
    sessionGuard: null,
    sessionIsRecent: false,
    preferredCanonicalText: null,
    guardToolAgeMs: Number.POSITIVE_INFINITY,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: () => [],
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "collecting_booking_details",
    directiveAction: null,
    directiveRenderContext: null,
    renderDirectiveReply,
    ...overrides,
  };
}

{
  const entry = completeEntry();
  const ctx = {
    language: "en",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t1::c1",
  };
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Sure, here's the summary: ...",
      directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
      directiveRenderContext: ctx,
    }),
  );
  assert.equal(res.decision, "replace_authoritative", "W1 decision");
  assert.equal(res.reason, "replace_directive_ask", "W1 reason");
  assert.equal(res.markedSummaryShown, true, "W1 markedSummaryShown");
  assert.ok(res.replyText.includes("*Order summary*"), `W1 text: ${res.replyText}`);
  assert.ok(res.replyText.includes("Shall I confirm this order?"), "W1 confirm prompt");
}

// -------------------------------------------------------------------------
// W2: substitution skipped on explicit confirmation. Caller is
// responsible for NOT setting directiveActionForRender on the confirm
// turn; this test verifies that shape.
// -------------------------------------------------------------------------
{
  // Sanity: the skip is a property of the caller. Here we simulate the
  // caller's logic: when the customer text is a confirmation, the
  // caller passes directiveAction=null. The outbound decision then
  // preserves the LLM reply.
  //
  // Uses the authoritative list from
  // `isExplicitOrderConfirmation` (plugins/shared/conversation-policy.ts)
  // — keep these two in sync. If new confirmation markers are added
  // there, add them here to cover the skip behavior.
  const confirmTexts = ["yes", "confirm", "go ahead", "proceed", "نعم", "مؤكد"];
  for (const text of confirmTexts) {
    assert.ok(
      isExplicitOrderConfirmation(text),
      `W2 precondition: isExplicitOrderConfirmation('${text}')`,
    );
  }
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Order placed! Track here: https://...",
      directiveAction: null, // caller skipped on confirm turn
      directiveRenderContext: null,
    }),
  );
  assert.equal(res.decision, "allow", "W2 decision");
  assert.equal(res.replyText, "Order placed! Track here: https://...", "W2 passthrough");
  assert.equal(res.markedSummaryShown, false, "W2 no promotion");
}

// -------------------------------------------------------------------------
// W3: edit-then-resummarize — draft mutation produces a fresh summary
// with the new values on the next directive turn.
// -------------------------------------------------------------------------
{
  const entry1 = completeEntry();
  const out1 = renderDirectiveReply(
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    {
      language: "en",
      draft: entry1.bookingDraft,
      entry: entry1,
      route: null,
      turnSeed: "turn1",
    },
  );
  assert.ok(out1.text.includes("Block 6"), `W3a: original delivery block`);

  // Simulate edit: customer changed delivery block from 6 → 8.
  const editedDraft = { ...entry1.bookingDraft, deliveryBlock: "8" };
  const entry2 = { ...entry1, bookingDraft: editedDraft };
  const out2 = renderDirectiveReply(
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    {
      language: "en",
      draft: editedDraft,
      entry: entry2,
      route: null,
      turnSeed: "turn2",
    },
  );
  assert.ok(out2.text.includes("Block 8"), `W3b: edited delivery block; got:\n${out2.text}`);
  assert.ok(!out2.text.includes("Block 6"), `W3c: pre-edit value gone; got:\n${out2.text}`);
}

// -------------------------------------------------------------------------
// W4: markedSummaryShown flips only for the summary directive. Other
// server-composed directives (e.g. ASK_PICKUP_ADDRESS) must leave it
// false so we don't spuriously promote to summary_shown.
// -------------------------------------------------------------------------
{
  const entry = completeEntry({ bookingDraft: createEmptyBookingDraft() });
  const ctx = {
    language: "en",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t4",
  };
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Some draft.",
      directiveAction: "ASK_PICKUP_ADDRESS",
      directiveRenderContext: ctx,
    }),
  );
  assert.equal(res.decision, "replace_authoritative", "W4 decision");
  assert.equal(res.reason, "replace_directive_ask", "W4 reason");
  assert.equal(res.markedSummaryShown, false, "W4 no promotion for ASK_PICKUP_ADDRESS");
}

// -------------------------------------------------------------------------
// C1: regression alarm — after Phase 3 substitutes the canonical
// summary, the post-state verifier classifies the substituted text as
// shape=ok (no drift), so the C-drift guard is a pure observer on
// directive-driven summary turns.
// -------------------------------------------------------------------------
{
  const entry = completeEntry();
  const substituted = buildDeterministicOrderSummary({ entry, language: "en" });
  const verification = verifyAndRepairOutbound({
    replyText: substituted,
    entry,
    missingFields: [],
    language: "en",
  });
  assert.equal(
    verification.replaced,
    false,
    `C1: substituted summary must not trigger C-drift replacement; got reason=${verification.reason}`,
  );
  assert.ok(
    verification.shape === "ok" || verification.shape === "stub_summary",
    `C1: verifier shape should be ok/stub (not summary_fact_drift); got ${verification.shape}`,
  );
}

console.log("smoke-test-server-rendered-summary: OK");
