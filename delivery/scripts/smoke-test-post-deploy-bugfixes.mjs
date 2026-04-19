#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: regression anchors for the 2026-04-20 post-deploy bug bundle.
//
// Four bugs were reported after the prior deploy + session clear. Each was
// fixed with a layered server-side guard (deterministic, in code) and — for
// three of them — a complementary LLM prompt rule. This file pins the
// server-side half: if these anchors ever break, the original user-visible
// regression is one deploy away.
//
// Bug 1 — "Helper service" / manual-confirmation flow.
//   Symptom: after quote, customer said "go ahead with helper service".
//   Bot started collecting sender name/phone — a `create_simple_order`
//   attempt, which `getDirectChatBookingBlockReason` would later reject.
//   The collection never should have started.
//   Fix anchor (this file): `computeOneBrainNextRequiredAction` returns
//   a `*_FOR_MANUAL_CONFIRM` action (ASK pickup → ASK delivery →
//   REQUEST handoff) when the selected option has
//   `direct_chat_booking_status === "manual_confirmation_required"`.
//   Sender / recipient asks and `create_simple_order` shapes are in
//   `forbiddenShapes`.
//
// Bug 2 — "nvm pls standard sedan" cancel misclassification.
//   Symptom: customer said "nvm pls standard sedan" after a quote; the
//   LLM emitted `cancel_booking`; the bot confirmed cancellation. Real
//   intent was an option switch, not a cancel.
//   Fix anchors (this file):
//     a. `detectCancelContradictsOptionMention` returns
//        `contradicted: true` with the option label when the cancel's
//        `source_quote` also mentions a quoted option alias.
//     b. The hallucination guard blocks cancel-claim replies whenever
//        `cancelContradicted` is set, and substitutes the
//        `cancel_repair` disambiguation template.
//
// Bug 3a — address-extra duplicate-write conflicts.
//   Symptom: fast-path wrote "Apartment 19, floor 8, door 11" and the
//   LLM independently wrote "apartment 19 floor 8 door 11"; `updateSlot`
//   treated them as different values and raised a `slot_conflict`, two
//   turns later the bot asked to confirm. With the normalization + strict
//   superset upgrade logic in place, these two writes must be
//   indistinguishable (`unchanged`) and a strict information upgrade
//   (door number added on top) must overwrite without a conflict
//   (action: `upgraded_by_superset`).
//
// Bug 3b — unresolved DST conflicts block advancement.
//   Symptom: with a real `slot_conflict` on `pickup_extra`, the next
//   turn happily advanced to the delivery address ask; by the time the
//   confirm came the customer was confused.
//   Fix anchor (this file): `computeOneBrainNextRequiredAction` returns
//   `CONFIRM_SLOT_CONFLICT` with the conflicting slot in `field` before
//   any downstream `ASK_*`, and forbids `ask_next_slot_before_conflict_resolved`.
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

const dst = await loadTsModule("plugins/shared/dialog-state.ts");
const { createEmptyBookingDraft } = await loadTsModule(
  "plugins/shared/conversation-policy.ts",
);
const { computeOneBrainNextRequiredAction } = await loadTsModule(
  "plugins/octopus-channel/lib/one-brain-context.ts",
);
const { detectCancelContradictsOptionMention } = await loadTsModule(
  "plugins/octopus-channel/lib/quoted-options.ts",
);
const { runHallucinationGuard, looksLikeCancellationClaim } = await loadTsModule(
  "plugins/shared/reply-hallucination-guard.ts",
);

const { createEmptyDialogState, updateSlot } = dst;

// ---------------------------------------------------------------------------
// Fixtures.
// ---------------------------------------------------------------------------

function helperOptionCatalog() {
  return [
    {
      delivery_type: "sedan_normal",
      label_ar: "عادي",
      label_en: "Standard",
      quoted_price: 1.25,
      formatted_price: "1.250 KWD",
      visibility: "public",
      direct_chat_booking_status: "bookable",
      direct_chat_booking_note: null,
    },
    {
      delivery_type: "sedan_fast",
      label_ar: "سريع",
      label_en: "Express",
      quoted_price: 1.75,
      formatted_price: "1.750 KWD",
      visibility: "public",
      direct_chat_booking_status: "bookable",
      direct_chat_booking_note: null,
    },
    {
      delivery_type: "helper_standard",
      label_ar: "مع مساعد",
      label_en: "Helper service",
      quoted_price: 3.25,
      formatted_price: "3.250 KWD",
      visibility: "public",
      direct_chat_booking_status: "manual_confirmation_required",
      direct_chat_booking_note: "Manual team follow-up",
    },
  ];
}

function quotedRoute() {
  return {
    routeKey: "hawalli->salmiya",
    pickupAreaNameEn: "Hawalli",
    pickupAreaNameAr: "حولي",
    dropoffAreaNameEn: "Salmiya",
    dropoffAreaNameAr: "السالمية",
    pricesByType: { sedan_normal: 1.25, sedan_fast: 1.75 },
    optionCatalog: helperOptionCatalog(),
  };
}

function emptyEntry(overrides = {}) {
  return {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: "en",
    stage: "collecting_booking_details",
    bookingStep: "pickup_address",
    conversationId: "conv-1",
    replyTarget: "wa:999",
    accountId: "acct",
    quoteRouteKey: "hawalli->salmiya",
    quoteTs: Date.now(),
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedQuoteOptionType: null,
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: null,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    bookingDraft: createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Bug 3a — address-extra normalization + strict-superset upgrade.
// ---------------------------------------------------------------------------

// 3a.1: trivial case / whitespace / ordering drift within the same set of
// comma-separated parts is collapsed to `unchanged`. This is the exact
// shape the fast-path vs LLM produced in the 2026-04-20 incident — same
// parts, formatting drift — and it must not raise a conflict.
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "pickup_extra", "Apartment 19, floor 8, door 11", "customer_fast_path").state;
  const res = updateSlot(
    s,
    "pickup_extra",
    "apartment 19 ,  FLOOR 8, Door 11",
    "llm_apply",
  );
  assert(
    res.decision.action === "unchanged",
    `3a.1: whitespace/case drift within same parts must collapse to unchanged, got ${res.decision.action}`,
  );
  assert(
    res.state.slots.pickup_extra.status === "filled",
    "3a.1: slot must stay filled",
  );
  assert(
    res.state.slots.pickup_extra.value === "Apartment 19, floor 8, door 11",
    "3a.1: filled value preserved (first writer wins)",
  );
}

// 3a.1b: part order within the comma-separated list does not matter —
// the canonicalization sorts parts before comparing.
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "pickup_extra", "floor 8, apartment 19, door 11", "customer_fast_path").state;
  const res = updateSlot(
    s,
    "pickup_extra",
    "Apartment 19, Door 11, Floor 8",
    "llm_apply",
  );
  assert(
    res.decision.action === "unchanged",
    `3a.1b: reordered parts must collapse to unchanged, got ${res.decision.action}`,
  );
}

// 3a.2: incoming value adds a new part on top → strict-superset upgrade.
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "pickup_extra", "apartment 19, floor 8", "customer_fast_path").state;
  const res = updateSlot(
    s,
    "pickup_extra",
    "Apartment 19, floor 8, door 11",
    "llm_apply",
  );
  assert(
    res.decision.action === "upgraded_by_superset",
    `3a.2: superset write must upgrade, got ${res.decision.action}`,
  );
  assert(
    res.state.slots.pickup_extra.value === "Apartment 19, floor 8, door 11",
    "3a.2: new value stored",
  );
  assert(
    res.state.slots.pickup_extra.status === "filled",
    "3a.2: status stays filled (no conflict surfaced)",
  );
}

// 3a.3: unrelated value is still a real conflict (we did not over-relax).
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "pickup_extra", "apartment 19, floor 8, door 11", "customer_fast_path").state;
  const res = updateSlot(
    s,
    "pickup_extra",
    "villa 3, near mosque",
    "llm_apply",
  );
  assert(
    res.decision.action === "conflict",
    `3a.3: genuinely different values must still conflict, got ${res.decision.action}`,
  );
  assert(
    res.state.slots.pickup_extra.status === "conflict",
    "3a.3: status conflict raised",
  );
}

// 3a.4: upgrade works on delivery_extra too (both address-extra slots).
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "delivery_extra", "floor 8, apt 19", "customer_fast_path").state;
  const res = updateSlot(
    s,
    "delivery_extra",
    "Floor 8, Apt 19, door 11",
    "llm_apply",
  );
  assert(
    res.decision.action === "upgraded_by_superset",
    `3a.4: delivery_extra must also upgrade, got ${res.decision.action}`,
  );
}

// 3a.5: non-address-extra slots (e.g., sender_name) are unaffected by the
// superset logic — a differing value must still be a conflict.
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_name", "Aziz", "llm_apply").state;
  const res = updateSlot(s, "sender_name", "Aziz Almulla", "llm_apply");
  assert(
    res.decision.action === "conflict",
    `3a.5: non-extra slots must NOT pick up superset behavior, got ${res.decision.action}`,
  );
}

console.log("PASS: Bug 3a — address-extra normalization + strict-superset upgrade");

// ---------------------------------------------------------------------------
// Bug 3b — unresolved DST conflicts block advancement.
// ---------------------------------------------------------------------------

// 3b.1: with a conflict on pickup_extra, next_required_action must be
// CONFIRM_SLOT_CONFLICT with the conflicting slot in `field`, and must
// forbid advancing to the next ask.
{
  let ds = createEmptyDialogState();
  ds = updateSlot(ds, "pickup_extra", "villa 3", "customer_fast_path").state;
  ds = updateSlot(ds, "pickup_extra", "apartment 19", "llm_apply").state; // conflict

  const entry = emptyEntry({ dialogState: ds });
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    // Delivery address is missing — this would normally route to ASK_DELIVERY_ADDRESS.
    missing: [
      "pickup.address", // already have pickup extra conflict
      "delivery.address",
      "sender.name",
      "sender.phone",
      "recipient.name",
      "recipient.phone",
    ],
  });
  assert(next, "3b.1: next action must not be null");
  assert(
    next.action === "CONFIRM_SLOT_CONFLICT",
    `3b.1: must return CONFIRM_SLOT_CONFLICT, got ${next.action}`,
  );
  assert(
    next.field === "pickup_extra",
    `3b.1: must pin the conflicting slot, got ${next.field}`,
  );
  const forbidden = next.forbiddenShapes || [];
  assert(
    forbidden.includes("ask_next_slot_before_conflict_resolved"),
    "3b.1: must forbid ask_next_slot_before_conflict_resolved",
  );
  assert(
    forbidden.includes("summary_before_conflict_resolved"),
    "3b.1: must forbid summary_before_conflict_resolved",
  );
}

// 3b.2: with no conflicts, the gate is a no-op — the normal missing-field
// logic runs.
{
  const entry = emptyEntry();
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing: ["pickup.address", "delivery.address"],
  });
  assert(next, "3b.2: next action must not be null");
  assert(
    next.action !== "CONFIRM_SLOT_CONFLICT",
    "3b.2: no conflicts → not a CONFIRM_SLOT_CONFLICT step",
  );
}

console.log("PASS: Bug 3b — unresolved conflicts block advancement");

// ---------------------------------------------------------------------------
// Bug 1 — manual-confirmation flow gating on next_required_action.
// ---------------------------------------------------------------------------

// 1.1: Helper selected, pickup address missing → ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM.
{
  const entry = emptyEntry({
    selectedDeliveryType: "helper_standard",
    selectedQuoteOptionType: "helper_standard",
    selectedQuoteOptionLabelEn: "Helper service",
    selectedQuoteOptionPrice: 3.25,
    selectedQuoteOptionDirectChatBookingStatus: "manual_confirmation_required",
    quotedPrice: 3.25,
  });
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing: [
      "pickup.address",
      "delivery.address",
      "sender.name",
      "sender.phone",
      "recipient.name",
      "recipient.phone",
    ],
  });
  assert(next, "1.1: next action must not be null");
  assert(
    next.action === "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM",
    `1.1: must ask for pickup address under manual-confirm, got ${next.action}`,
  );
  const forbidden = next.forbiddenShapes || [];
  assert(
    forbidden.includes("ask_sender_for_manual_confirm"),
    "1.1: must forbid sender ask",
  );
  assert(
    forbidden.includes("ask_recipient_for_manual_confirm"),
    "1.1: must forbid recipient ask",
  );
  assert(
    forbidden.includes("call_create_simple_order_for_manual_confirm"),
    "1.1: must forbid create_simple_order call",
  );
}

// 1.2: Helper + pickup has resolved, delivery missing → ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM.
{
  const entry = emptyEntry({
    selectedDeliveryType: "helper_standard",
    selectedQuoteOptionDirectChatBookingStatus: "manual_confirmation_required",
    quotedPrice: 3.25,
  });
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing: [
      "delivery.address",
      "sender.name",
      "sender.phone",
      "recipient.name",
      "recipient.phone",
    ],
  });
  assert(next, "1.2: next action must not be null");
  assert(
    next.action === "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM",
    `1.2: expected delivery-address ask for manual-confirm, got ${next.action}`,
  );
}

// 1.3: Helper + both addresses in → REQUEST_HANDOFF_FOR_MANUAL_CONFIRM.
// Sender / recipient collection is explicitly skipped under manual confirm.
{
  const entry = emptyEntry({
    selectedDeliveryType: "helper_standard",
    selectedQuoteOptionDirectChatBookingStatus: "manual_confirmation_required",
    quotedPrice: 3.25,
  });
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    // Addresses resolved; sender + recipient still missing but irrelevant here.
    missing: ["sender.name", "sender.phone", "recipient.name", "recipient.phone"],
  });
  assert(next, "1.3: next action must not be null");
  assert(
    next.action === "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM",
    `1.3: expected manual-confirm handoff, got ${next.action}`,
  );
  const forbidden = next.forbiddenShapes || [];
  assert(
    forbidden.includes("write_full_order_summary_for_manual_confirm"),
    "1.3: must forbid order-summary write under manual-confirm",
  );
  assert(
    forbidden.includes("call_create_simple_order_for_manual_confirm"),
    "1.3: must forbid create_simple_order call at handoff step",
  );
}

// 1.4: bookable sedan_normal under the same shape is UNTOUCHED by the
// manual-confirm gate — regression guard against the gate leaking.
{
  const entry = emptyEntry({
    selectedDeliveryType: "sedan_normal",
    selectedQuoteOptionDirectChatBookingStatus: "bookable",
    quotedPrice: 1.25,
  });
  const next = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing: [
      "pickup.address",
      "delivery.address",
      "sender.name",
      "sender.phone",
      "recipient.name",
      "recipient.phone",
    ],
  });
  assert(next, "1.4: next action must not be null");
  assert(
    next.action !== "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM" &&
      next.action !== "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM" &&
      next.action !== "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM",
    `1.4: bookable options must not pick up manual-confirm branch, got ${next.action}`,
  );
}

console.log("PASS: Bug 1 — manual-confirm next_required_action gating");

// ---------------------------------------------------------------------------
// Bug 2 — cancel vs option-switch.
// ---------------------------------------------------------------------------

// 2.1: sourceQuote names a quoted option → contradiction detected, label echoed.
{
  const result = detectCancelContradictsOptionMention({
    sourceQuote: "nvm pls standard sedan",
    route: quotedRoute(),
  });
  assert(
    result.contradicted === true,
    "2.1: cancel + quoted-option alias must be flagged as contradicted",
  );
  assert(
    result.optionType === "sedan_normal",
    `2.1: must pin sedan_normal, got ${result.optionType}`,
  );
  assert(
    typeof result.optionLabel === "string" && result.optionLabel.length > 0,
    "2.1: optionLabel must be populated for the repair template",
  );
}

// 2.2: Arabic alias — "عادي" maps to sedan_normal alias list.
{
  const result = detectCancelContradictsOptionMention({
    sourceQuote: "لا خلاص خليها عادي",
    route: quotedRoute(),
  });
  assert(
    result.contradicted === true,
    "2.2: Arabic 'عادي' must flag contradiction",
  );
  assert(
    result.optionType === "sedan_normal",
    `2.2: Arabic alias must resolve to sedan_normal, got ${result.optionType}`,
  );
}

// 2.3: plain cancel without option mention → not contradicted.
{
  const result = detectCancelContradictsOptionMention({
    sourceQuote: "cancel the booking please",
    route: quotedRoute(),
  });
  assert(
    result.contradicted === false,
    "2.3: plain cancel must not trigger contradiction",
  );
  assert(result.optionType === null, "2.3: no option pinned");
}

// 2.4: no route → not contradicted (defensive).
{
  const result = detectCancelContradictsOptionMention({
    sourceQuote: "nvm pls standard sedan",
    route: null,
  });
  assert(
    result.contradicted === false,
    "2.4: without a route, cannot contradict",
  );
}

// 2.5: looksLikeCancellationClaim recognises affirmative cancel text only.
{
  assert(
    looksLikeCancellationClaim("Your booking has been cancelled.") === true,
    "2.5: affirmative cancel claim must be recognised",
  );
  assert(
    looksLikeCancellationClaim("تم إلغاء الطلب") === true,
    "2.5: Arabic affirmative cancel claim must be recognised",
  );
  assert(
    looksLikeCancellationClaim("Do you want to cancel the booking?") === false,
    "2.5: offer / question must NOT look like a cancel claim",
  );
  assert(
    looksLikeCancellationClaim("Would you like me to cancel?") === false,
    "2.5: 'would you like me to cancel' is an offer, not a claim",
  );
}

// 2.6: end-to-end — hallucination guard substitutes a cancel-claim reply
// with the `cancel_repair` template when `cancelContradicted` is set.
{
  const draft = createEmptyBookingDraft();
  const entry = {
    stage: "quoted",
    bookingStep: "quote_presented",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  };
  const decision = runHallucinationGuard({
    replyText: "Your booking has been cancelled.",
    entry,
    missingFields: ["pickup.address"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: "ASK_PICKUP_ADDRESS",
    cancelContradicted: { optionLabel: "Standard" },
  });
  assert(
    decision.blocked,
    `2.6: cancel-claim with cancelContradicted must block, got blocked=${decision.blocked}`,
  );
  assert(
    decision.claims.includes("cancel_misclassification"),
    `2.6: claims must include cancel_misclassification, got ${decision.claims.join(",")}`,
  );
  assert(
    decision.substitutedFrom === "cancel_repair",
    `2.6: substitutedFrom must be cancel_repair, got ${decision.substitutedFrom}`,
  );
  assert(
    decision.replyText !== "Your booking has been cancelled.",
    "2.6: reply must be rewritten",
  );
  assert(
    /Standard/.test(decision.replyText),
    `2.6: repair must surface the contradicted option label, got: ${decision.replyText}`,
  );
}

// 2.7: without the `cancelContradicted` signal, a cancel-claim reply is
// NOT blocked by this new branch (guard stays scoped to server-signalled
// contradictions only).
{
  const draft = createEmptyBookingDraft();
  const entry = {
    stage: "quoted",
    bookingStep: "quote_presented",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  };
  const decision = runHallucinationGuard({
    replyText: "Your booking has been cancelled.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "quoted",
    language: "en",
    nextRequiredAction: null,
    // cancelContradicted omitted
  });
  assert(
    !decision.claims.includes("cancel_misclassification"),
    "2.7: without cancelContradicted signal, do not flag cancel_misclassification",
  );
}

console.log("PASS: Bug 2 — cancel vs option-switch");

console.log("ALL PASS smoke-test-post-deploy-bugfixes.mjs");
