#!/usr/bin/env node
// Smoke test: central booking lifecycle gate invariants.
//
// This pins the server-side lifecycle contract. The gate is pure:
// it returns structured allow/block decisions only and never customer wording.

import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

const policy = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/conversation-policy.ts"),
);
const dialog = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/dialog-state.ts"),
);
const lifecycle = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/booking-lifecycle-gate.ts"),
);
const oneBrain = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/one-brain-context.ts"),
);

const { createEmptyBookingDraft } = policy;
const { seedDialogStateFromDraft, setRequestedSlot } = dialog;
const {
  buildBookingLifecycleRouteAudit,
  canAdvanceBookingFlow,
  shouldPreserveDraftOnQuotePromotion,
} = lifecycle;
const { computeOneBrainMissingFields } = oneBrain;

function option(delivery_type, price) {
  return {
    delivery_type,
    label_en: delivery_type,
    label_ar: delivery_type,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "public",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

const route = {
  routeKey: "sharq:shuwaikh_industrial_3",
  pickupAreaNameEn: "Sharq",
  pickupAreaNameAr: "الشرق",
  dropoffAreaNameEn: "Shuwaikh Industrial-3",
  dropoffAreaNameAr: "الشويخ الصناعية 3",
  pricesByType: {
    sedan_normal: 1.25,
    sedan_fast: 1.75,
  },
  optionCatalog: [option("sedan_normal", 1.25), option("sedan_fast", 1.75)],
  serviceDiscovery: null,
  quotedAt: Date.now(),
  quoteRef: "quote-smoke",
};

function buildCompleteDraft(overrides = {}) {
  const draft = createEmptyBookingDraft();
  Object.assign(draft, {
    senderName: "Abdulaziz Almulla",
    senderPhone: "96599338566",
    recipientName: "Ahmad Basha",
    recipientPhone: "99278765",
    pickupBlock: "2",
    pickupStreet: "7",
    pickupHouse: "19",
    deliveryBlock: "2",
    deliveryStreet: "9",
    deliveryHouse: null,
    deliveryExtra: "apartment 11, floor 4, door 2",
    ...overrides,
  });
  return draft;
}

function buildEntry(draft = buildCompleteDraft(), overrides = {}) {
  return {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "summary_shown",
    bookingStep: "summary_pending",
    conversationId: "lifecycle-smoke",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: route.routeKey,
    quoteTs: Date.now(),
    quotePickupAreaNameEn: route.pickupAreaNameEn,
    quotePickupAreaNameAr: route.pickupAreaNameAr,
    quoteDropoffAreaNameEn: route.dropoffAreaNameEn,
    quoteDropoffAreaNameAr: route.dropoffAreaNameAr,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: "Standard sedan",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    bookingDraft: draft,
    pendingReplyText: null,
    quotePresentedToCustomer: true,
    submittedOrderUid: null,
    dialogState: seedDialogStateFromDraft(draft),
    pendingOrderEdits: null,
    ...overrides,
  };
}

function buildSession(overrides = {}) {
  return {
    allValidPrices: new Set(["1.250", "1.750"]),
    lastToolName: "get_price",
    lastCustomerMessage: null,
    lastCustomerMessages: { ar: null, en: null },
    lastToolTs: Date.now(),
    lastQuotedRoute: route,
    pendingOrderSummary: null,
    lastCreatedOrderUid: null,
    ...overrides,
  };
}

function summaryDecision(entry, overrides = {}) {
  return canAdvanceBookingFlow("summary_shown", {
    controllerState: entry,
    sessionGuard: buildSession(),
    dialogState: entry.dialogState,
    currentCustomerText: "details",
    currentTurnToolResults: {
      missingFields: computeOneBrainMissingFields(entry.bookingDraft, entry),
    },
    now: Date.now(),
    ...overrides,
  });
}

function collectingDecision(entry, overrides = {}) {
  return canAdvanceBookingFlow("collecting_booking_details", {
    controllerState: entry,
    sessionGuard: buildSession(),
    dialogState: entry.dialogState,
    currentCustomerText: "book it",
    now: Date.now(),
    ...overrides,
  });
}

{
  const entry = buildEntry();
  const decision = canAdvanceBookingFlow("quoted", {
    controllerState: entry,
    sessionGuard: buildSession(),
    dialogState: entry.dialogState,
    currentCustomerText: "quote it",
    routeAudit: {
      pickup: { status: "canonical", areaId: 19, nameEn: "Sharq" },
      dropoff: { status: "ambiguous", nameEn: "Shuwaikh" },
    },
  });
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_not_canonical");
  assert.equal(decision.requiredNextAction.type, "resolve_dropoff_area");
  console.log("ok - quote promotion blocked if route ambiguity exists");
}

{
  const entry = buildEntry(buildCompleteDraft({ senderName: "Rawan Al Ajmi" }));
  assert.equal(
    shouldPreserveDraftOnQuotePromotion({
      controllerState: entry,
      turnAppliedBookingProgress: true,
    }),
    true,
  );
  assert.equal(entry.bookingDraft.senderName, "Rawan Al Ajmi");
  console.log("ok - quote promotion preserves same-turn draft fields");
}

{
  const entry = buildEntry(buildCompleteDraft(), {
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionPrice: 1.75,
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
  });
  const session = buildSession();
  const audit = buildBookingLifecycleRouteAudit({
    controllerState: entry,
    sessionGuard: session,
  });
  assert.equal(audit.selectedServiceInQuote, true);
  assert.equal(audit.priceMatchesQuote, true);
  const decision = canAdvanceBookingFlow("quoted", {
    controllerState: entry,
    sessionGuard: session,
    dialogState: entry.dialogState,
    currentCustomerText: "express sedan",
    routeAudit: audit,
  });
  assert.equal(decision.decision, "allow");
  console.log("ok - quote promotion preserves same-turn selected service");
}

{
  const entry = buildEntry();
  const decision = summaryDecision(entry, {
    routeAudit: {
      pickup: { status: "canonical", areaId: 19, nameEn: "Sharq" },
      dropoff: { status: "ambiguous", nameEn: "Shuwaikh" },
    },
  });
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_not_canonical");
  assert.equal(decision.requiredNextAction.type, "resolve_dropoff_area");
  assert.equal(decision.preserveDraft, true);
  console.log("ok - ambiguous area cannot enter summary");
}

{
  const draft = buildCompleteDraft();
  let state = seedDialogStateFromDraft(draft);
  state = setRequestedSlot(state, {
    name: "dropoff_area",
    options: ["Shuwaikh", "Shuwaikh Industrial-1", "Shuwaikh Industrial-2"],
    askedTs: Date.now(),
  });
  const entry = buildEntry(draft, { dialogState: state });
  const decision = summaryDecision(entry);
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_clarification_pending");
  assert.equal(decision.requiredNextAction.type, "resolve_dropoff_area");
  console.log("ok - requested_slot_options cannot survive into summary");
}

{
  const draft = buildCompleteDraft();
  let state = seedDialogStateFromDraft(draft);
  state = setRequestedSlot(state, {
    name: "dropoff_area",
    options: ["Shuwaikh", "Shuwaikh Industrial-3"],
    askedTs: Date.now(),
  });
  const entry = buildEntry(draft, {
    stage: "collecting_booking_details",
    bookingStep: "delivery_address",
    dialogState: state,
  });
  const decision = summaryDecision(entry);
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_clarification_pending");
  console.log("ok - applyBookingDraftProgress cannot enter summary with requested_slot_options open");
}

{
  const entry = buildEntry(buildCompleteDraft(), {
    pendingOrderEdits: {
      fields: ["sender_name", "service"],
      askedTs: Date.now(),
      sourceQuote: "change sender name and service",
    },
  });
  const decision = summaryDecision(entry);
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "pending_order_edits");
  assert.equal(decision.requiredNextAction.type, "resolve_pending_edit");
  console.log("ok - pending edit blocks summary");
}

{
  const draft = buildCompleteDraft();
  const state = seedDialogStateFromDraft(draft);
  state.slots.sender_name = {
    value: "Abdulaziz Almulla",
    status: "conflict",
    lastSetTs: Date.now(),
    lastSource: "llm_apply",
    conflictCandidate: "Rawan Al Ajmi",
  };
  const entry = buildEntry(draft, { dialogState: state });
  const decision = summaryDecision(entry);
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "slot_conflict");
  assert.equal(decision.requiredNextAction.type, "resolve_slot_conflict");
  console.log("ok - DST conflict blocks summary");
}

{
  const draft = buildCompleteDraft();
  const ambiguousEntry = buildEntry(draft, {
    quoteDropoffAreaNameEn: "Shuwaikh",
    quoteDropoffAreaNameAr: "الشويخ",
  });
  const blocked = summaryDecision(ambiguousEntry, {
    routeAudit: {
      pickup: { status: "canonical", areaId: 19, nameEn: "Sharq" },
      dropoff: { status: "ambiguous", nameEn: "Shuwaikh" },
    },
  });
  assert.equal(blocked.decision, "block");
  assert.equal(blocked.preserveDraft, true);

  const correctedEntry = buildEntry(draft, {
    quoteDropoffAreaNameEn: "Shuwaikh Industrial-3",
    quoteDropoffAreaNameAr: "الشويخ الصناعية 3",
  });
  const allowed = summaryDecision(correctedEntry, {
    routeAudit: {
      pickup: { status: "canonical", areaId: 19, nameEn: "Sharq" },
      dropoff: { status: "canonical", areaId: 14, nameEn: "Shuwaikh Industrial-3" },
      quoteMatchesCanonicalRoute: true,
      selectedServiceInQuote: true,
      priceMatchesQuote: true,
    },
  });
  assert.equal(allowed.decision, "allow");
  assert.equal(correctedEntry.bookingDraft, draft, "late ambiguity recovery must preserve collected draft");
  console.log("ok - late ambiguity preserves draft and allows updated summary after reprice");
}

{
  const draft = buildCompleteDraft();
  const entry = buildEntry(draft, {
    stage: "collecting_booking_details",
    bookingStep: "delivery_address",
  });
  const decision = summaryDecision(entry);
  assert.equal(computeOneBrainMissingFields(draft, entry).length, 0);
  assert.equal(decision.decision, "allow");
  console.log("ok - all-in-one booking reaches summary");
}

{
  const draft = buildCompleteDraft();
  let state = seedDialogStateFromDraft(draft);
  state = setRequestedSlot(state, {
    name: "dropoff_area",
    options: ["Shuwaikh", "Shuwaikh Industrial-3"],
    askedTs: Date.now(),
  });
  const entry = buildEntry(draft, {
    stage: "quoted",
    bookingStep: "none",
    dialogState: state,
  });
  const decision = collectingDecision(entry);
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_clarification_pending");
  console.log("ok - ambiguous route cannot move into sender/address collection");
}

{
  const entry = buildEntry();
  const missingConfirmation = canAdvanceBookingFlow("order_submitted", {
    controllerState: entry,
    sessionGuard: buildSession({ lastToolName: "create_simple_order", lastCreatedOrderUid: "ORDER-123" }),
    dialogState: entry.dialogState,
    currentCustomerText: "maybe",
    currentTurnToolResults: { orderCreatedUid: "ORDER-123", confirmationExplicit: false },
    orderGuardResult: { ok: true },
  });
  assert.equal(missingConfirmation.decision, "block");
  assert.equal(missingConfirmation.blockingReason, "confirmation_missing");

  const failedGuard = canAdvanceBookingFlow("order_submitted", {
    controllerState: entry,
    sessionGuard: buildSession({ lastToolName: "create_simple_order", lastCreatedOrderUid: "ORDER-123" }),
    dialogState: entry.dialogState,
    currentCustomerText: "yes",
    currentTurnToolResults: { orderCreatedUid: "ORDER-123" },
    orderGuardResult: {
      ok: false,
      code: "confirmation_missing",
      message: "missing",
    },
  });
  assert.equal(failedGuard.decision, "block");
  assert.equal(failedGuard.blockingReason, "order_guard_failed");

  const allowed = canAdvanceBookingFlow("order_submitted", {
    controllerState: entry,
    sessionGuard: buildSession({ lastToolName: "create_simple_order", lastCreatedOrderUid: "ORDER-123" }),
    dialogState: entry.dialogState,
    currentCustomerText: "yes",
    currentTurnToolResults: { orderCreatedUid: "ORDER-123", confirmationExplicit: true },
    orderGuardResult: { ok: true },
  });
  assert.equal(allowed.decision, "allow");
  console.log("ok - order_submitted requires confirmation plus order guard");
}

{
  const draft = buildCompleteDraft({
    pickupBlock: null,
    pickupStreet: null,
    pickupHouse: null,
    pickupLocation: {
      source: "location_pin",
      latitude: 29.379,
      longitude: 47.973,
      name: null,
      address: null,
      resolvedAreaName: "Sharq",
    },
    deliveryBlock: null,
    deliveryStreet: null,
    deliveryHouse: null,
    deliveryExtra: null,
    deliveryLocation: {
      source: "location_pin",
      latitude: 29.339,
      longitude: 47.921,
      name: null,
      address: null,
      resolvedAreaName: "Shuwaikh Industrial-3",
    },
  });
  const entry = buildEntry(draft);
  const missing = computeOneBrainMissingFields(draft, entry);
  assert.deepEqual(missing, []);
  const decision = summaryDecision(entry);
  assert.equal(decision.decision, "allow");
  console.log("ok - native pins satisfy address completeness for summary");
}

console.log("ok - booking lifecycle gate smoke tests passed");
