#!/usr/bin/env node
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
const truth = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/booking-truth-snapshot.ts"),
);
const outboundVerify = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/outbound-verify.ts"),
);
const outboundDecision = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/outbound-decision.ts"),
);
const coherence = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/post-drain-reply-coherence.ts"),
);
const orderGuard = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/order-guard.ts"),
);
const applyBoundary = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/apply-boundary.ts"),
);

const { createEmptyBookingDraft } = policy;
const { seedDialogStateFromDraft } = dialog;
const { buildBookingTruthSnapshot } = truth;
const { buildDeterministicOrderSummaryFromSnapshot } = outboundVerify;
const { decidePostStateOutbound } = outboundDecision;
const { checkPostDrainReplyCoherence } = coherence;
const { looksLikeConfirmation } = orderGuard;
const { applyProposals, llmProposal } = applyBoundary;

const now = Date.now();

function option(delivery_type, label_en, label_ar, price) {
  return {
    delivery_type,
    label_en,
    label_ar,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "available_on_request",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

const route = {
  routeKey: "northwest_sulaibikhat__zahra",
  pickupAreaNameEn: "Northwest Sulaibikhat",
  pickupAreaNameAr: "شمال غرب الصليبخات",
  dropoffAreaNameEn: "Zahra",
  dropoffAreaNameAr: "الزهراء",
  pickupAreaResolution: {
    status: "canonical",
    areaId: 11,
    nameEn: "Northwest Sulaibikhat",
    nameAr: "شمال غرب الصليبخات",
    options: [],
    confirmedByUser: true,
    quoteBuiltFromAreaIds: true,
  },
  dropoffAreaResolution: {
    status: "canonical",
    areaId: 22,
    nameEn: "Zahra",
    nameAr: "الزهراء",
    options: [],
    confirmedByUser: true,
    quoteBuiltFromAreaIds: true,
  },
  pricesByType: {
    sedan_normal: 1.25,
    sedan_fast: 1.75,
  },
  optionCatalog: [
    option("sedan_normal", "Standard sedan", "سيدان عادي", 1.25),
    option("sedan_fast", "Express sedan", "سيدان سريع", 1.75),
  ],
  serviceDiscovery: null,
  quotedAt: now,
  quoteRef: `northwest_sulaibikhat__zahra:${now}`,
};

function completeEnglishDraft(overrides = {}) {
  return {
    ...createEmptyBookingDraft(),
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
  };
}

function completeArabicDraft() {
  return {
    ...completeEnglishDraft(),
    senderName: "عبدالعزيز الملا",
    recipientName: "أحمد باشا",
    deliveryExtra: "شقة 11، الدور 4، باب 2",
  };
}

function entry(overrides = {}) {
  const draft = overrides.bookingDraft || completeEnglishDraft();
  return {
    lastActivityTs: now,
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep: "sender",
    conversationId: "snapshot-authority-smoke",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: route.routeKey,
    quoteTs: now,
    quotePickupAreaNameEn: route.pickupAreaNameEn,
    quotePickupAreaNameAr: route.pickupAreaNameAr,
    quoteDropoffAreaNameEn: route.dropoffAreaNameEn,
    quoteDropoffAreaNameAr: route.dropoffAreaNameAr,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionLabelEn: "Express sedan",
    selectedQuoteOptionLabelAr: "سيدان سريع",
    selectedQuoteOptionPrice: 1.75,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
    bookingDraft: draft,
    pendingReplyText: null,
    quotePresentedToCustomer: true,
    submittedOrderUid: null,
    dialogState: seedDialogStateFromDraft(draft),
    pendingOrderEdits: null,
    ...overrides,
  };
}

function session(overrides = {}) {
  return {
    allValidPrices: new Set(["1.250", "1.750"]),
    lastToolName: "get_price",
    lastCustomerMessage: null,
    lastCustomerMessages: { ar: null, en: null },
    lastToolTs: now,
    lastQuotedRoute: route,
    pendingOrderSummary: null,
    lastCreatedOrderUid: null,
    ...overrides,
  };
}

function snapshotFor(entryOverrides = {}, snapshotOverrides = {}) {
  const e = entry(entryOverrides);
  return buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: e,
    sessionGuard: session(),
    dialogState: e.dialogState,
    missingFields: [],
    now,
    ...snapshotOverrides,
  });
}

// English all-in-one summary must preserve customer values and apartment type.
{
  const snapshot = snapshotFor();
  assert.equal(snapshot.nextAction.type, "show_summary");
  const summary = buildDeterministicOrderSummaryFromSnapshot({ snapshot, language: "en" });
  assert(summary.includes("Abdulaziz Almulla"));
  assert(summary.includes("Ahmad Basha"));
  assert(summary.includes("Apartment 11, Floor 4, Door 2"));
  assert(!summary.includes("House 11"));
  assert(!summary.includes("عبدالعزيز"));
}

// Arabic all-in-one summary preserves Arabic values as values, not translations.
{
  const snapshot = snapshotFor({
    language: "ar",
    bookingDraft: completeArabicDraft(),
    dialogState: seedDialogStateFromDraft(completeArabicDraft()),
  });
  const summary = buildDeterministicOrderSummaryFromSnapshot({ snapshot, language: "ar" });
  assert(summary.includes("عبدالعزيز الملا"));
  assert(summary.includes("أحمد باشا"));
  assert(summary.includes("شقة 11، الدور 4، باب 2"));
}

// Confirmation variants are semantic only after the summary has been shown.
{
  const variants = ["yes", "yes l", "yala", "tamam", "تم", "اي", "يلا اوك"];
  for (const text of variants) {
    assert.equal(looksLikeConfirmation(text), true, text);
    const beforeSummary = snapshotFor({}, { confirmationExplicit: looksLikeConfirmation(text) });
    assert.equal(beforeSummary.nextAction.type, "show_summary", text);
    const afterSummary = snapshotFor(
      { stage: "awaiting_confirmation", bookingStep: "awaiting_summary_confirmation" },
      { confirmationExplicit: looksLikeConfirmation(text) },
    );
    assert.equal(afterSummary.nextAction.type, "submit_order", text);
  }
}

// No third summary: after an already-shown summary and another confirmation,
// snapshot authority emits a transaction-safe submit failure, not a summary.
{
  const snapshot = snapshotFor(
    { stage: "awaiting_confirmation", bookingStep: "awaiting_summary_confirmation" },
    { confirmationExplicit: true },
  );
  const decision = decidePostStateOutbound({
    replyText: "*Order summary*\nShall I confirm this order?",
    preferredLanguage: "en",
    conversationControllerEntry: snapshot.controllerState,
    missingFields: [],
    bookingTruthSnapshot: snapshot,
    hallucinationGuardRejections: [],
    stageAtTurnStart: "awaiting_confirmation",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    activeQuotedPrices: snapshot.quote.validQuotedPrices,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: () => "",
    buildProviderIssueFallbackReply: () => "fallback",
    conversationId: "snapshot-authority-smoke",
  });
  assert.equal(decision.decision, "replace_authoritative");
  assert(!decision.replyText.includes("*Order summary*"));
  assert(decision.replyText.includes("can't safely confirm"));
}

// Snapshot authority blocks legacy summary substitution on conflict.
{
  const e = entry();
  const dialogState = seedDialogStateFromDraft(e.bookingDraft);
  dialogState.slots.sender_name = {
    status: "conflict",
    value: "عبدالعزيز",
    conflictCandidate: "Abdulaziz Almulla",
    updatedAt: now,
    lastSource: "llm_apply",
  };
  const snapshot = snapshotFor({ dialogState }, {});
  assert.equal(snapshot.nextAction.type, "resolve_slot_conflict");
  const decision = decidePostStateOutbound({
    replyText: "All set, send yes and I'll place it.",
    preferredLanguage: "en",
    conversationControllerEntry: snapshot.controllerState,
    missingFields: [],
    bookingTruthSnapshot: snapshot,
    hallucinationGuardRejections: [],
    stageAtTurnStart: "collecting_booking_details",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    activeQuotedPrices: snapshot.quote.validQuotedPrices,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: () => "",
    buildProviderIssueFallbackReply: () => "fallback",
    conversationId: "snapshot-authority-smoke",
  });
  assert.equal(decision.replyText.includes("*Order summary*"), false);
  assert(decision.replyText.includes("sender name"));
}

// Source evidence saying apartment/floor/door cannot become house.
{
  const res = applyProposals([
    llmProposal({
      op: {
        sender_name: null,
        sender_phone: null,
        phone_decision: null,
        recipient_name: null,
        recipient_phone: null,
        address_block: "2",
        address_street: "9",
        address_house: "11",
        address_avenue: null,
        address_extra: "floor 4, door 2",
        address_role: "delivery",
        source_quote: "Delivery address is block 2, street 9, apartment 11, floor 4, door 2.",
        turn_id: "t1",
      },
    }),
  ], {
    draft: createEmptyBookingDraft(),
    dialogState: null,
    whatsappNumber: "96599338566",
    stage: "collecting_booking_details",
  });
  assert.equal(res.draft.deliveryHouse, null);
  assert.equal(res.draft.deliveryExtra, "floor 4, door 2, apartment 11");
  assert(res.normalizations.some((item) => item.kind === "interior_detail_house_to_extra"));
}

// Fresh all-in-one rebind lets new complete values override stale filled slots.
{
  const staleDraft = completeEnglishDraft({
    senderName: "عبدالعزيز",
    recipientName: "أحمد",
    deliveryExtra: "شقة 11",
  });
  const res = applyProposals([
    llmProposal({
      op: {
        sender_name: "Abdulaziz Almulla",
        sender_phone: null,
        phone_decision: "use_whatsapp",
        recipient_name: "Ahmad Basha",
        recipient_phone: "99278765",
        address_block: null,
        address_street: null,
        address_house: null,
        address_avenue: null,
        address_extra: null,
        address_role: null,
        source_quote:
          "Hi, delivery from Northwest Sulaibikhat to Zahra. Sender is Abdulaziz Almulla, use my WhatsApp number. Recipient is Ahmad Basha, 99278765.",
        turn_id: "t1",
      },
    }),
  ], {
    draft: staleDraft,
    dialogState: seedDialogStateFromDraft(staleDraft),
    whatsappNumber: "96599338566",
    stage: "quoted",
    freshAllInOneRebind: true,
  });
  assert.equal(res.conflicts.length, 0);
  assert.equal(res.draft.senderName, "Abdulaziz Almulla");
  assert.equal(res.draft.recipientName, "Ahmad Basha");
}

// Snapshot contradiction checks: wrong service/price, stale route ask,
// missing-field ask, and mutated summary values are rejected.
{
  const snapshot = snapshotFor();
  const wrongFacts = checkPostDrainReplyCoherence({
    replyText: "Standard sedan is 1.250 KWD. Which pickup area did you mean?",
    bookingTruthSnapshot: snapshot,
  });
  assert(wrongFacts.invalidations.some((item) => item.kind === "states_wrong_selected_service"));
  assert(wrongFacts.invalidations.some((item) => item.kind === "states_wrong_selected_price"));
  assert(wrongFacts.invalidations.some((item) => item.kind === "asks_for_route_ambiguity_when_snapshot_locked"));

  const missingAsk = checkPostDrainReplyCoherence({
    replyText: "Please send the recipient phone.",
    bookingTruthSnapshot: snapshot,
  });
  assert(missingAsk.invalidations.some((item) => item.kind === "asks_for_any_missing_field_when_complete"));

  const mutatedSummary = checkPostDrainReplyCoherence({
    replyText:
      "*Order summary*\n" +
      "Pickup: Northwest Sulaibikhat - Block 2, Street 7, House 19\n" +
      "Delivery: Zahra - Block 2, Street 9, House 11\n" +
      "Sender: عبدالعزيز - 96599338566\n" +
      "Recipient: أحمد - 99278765\n" +
      "Service: Express sedan\nPrice: 1.750 KWD",
    bookingTruthSnapshot: snapshot,
  });
  assert(mutatedSummary.invalidations.some((item) => item.kind === "mutates_summary_value"));
}

// Service edit to cheapest stays on selected snapshot service without
// reopening locked route ambiguity.
{
  const cheapest = snapshotFor({
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionLabelAr: "سيدان عادي",
    selectedQuoteOptionPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  });
  assert.equal(cheapest.route.lockStatus, "locked");
  assert.notEqual(cheapest.nextAction.type, "resolve_route_ambiguity");
}

console.log("snapshot authority cleanup smoke passed");
