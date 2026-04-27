#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {
  deliveryRoot,
  loadDeliveryTsModule,
} from "./_helpers/riders-plugin-loader.mjs";

const truth = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/booking-truth-snapshot.ts"),
);
const policy = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/conversation-policy.ts"),
);
const dialog = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/shared/dialog-state.ts"),
);
const finalReplyMod = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/final-snapshot-reply.ts"),
);
const outboundDecision = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/outbound-decision.ts"),
);
const coherenceMod = await loadDeliveryTsModule(
  import.meta.url,
  path.join(deliveryRoot, "plugins/octopus-channel/lib/post-drain-reply-coherence.ts"),
);

const { buildBookingTruthSnapshot } = truth;
const { createEmptyBookingDraft } = policy;
const { createEmptyDialogState } = dialog;
const {
  generateFinalSnapshotReply,
  buildFinalSnapshotReplyMessages,
  compactSnapshotForFinalReply,
} = finalReplyMod;
const { decidePostStateOutbound } = outboundDecision;
const { checkPostDrainReplyCoherence } = coherenceMod;

const now = Date.now();

function option(deliveryType, labelEn, labelAr, price) {
  return {
    delivery_type: deliveryType,
    label_en: labelEn,
    label_ar: labelAr,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "available_on_request",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

function route(overrides = {}) {
  return {
    routeKey: "sulaibikhat__zahra",
    pickupAreaNameEn: "Sulaibikhat",
    pickupAreaNameAr: "الصليبيخات",
    dropoffAreaNameEn: "Zahra",
    dropoffAreaNameAr: "الزهراء",
    pickupAreaResolution: {
      status: "canonical",
      areaId: 1001,
      nameEn: "Sulaibikhat",
      nameAr: "الصليبيخات",
      options: [],
      confirmedByUser: true,
      quoteBuiltFromAreaIds: true,
    },
    dropoffAreaResolution: {
      status: "canonical",
      areaId: 1002,
      nameEn: "Zahra",
      nameAr: "الزهراء",
      options: [],
      confirmedByUser: true,
      quoteBuiltFromAreaIds: true,
    },
    pricesByType: {
      sedan_normal: 1.25,
      sedan_fast: 1.75,
      van_normal: 1.75,
      van_fast: 2.25,
    },
    optionCatalog: [
      option("sedan_normal", "Standard sedan", "سيارة عادية", 1.25),
      option("sedan_fast", "Express sedan", "سيارة اكسبرس", 1.75),
      option("van_normal", "Standard box van", "بوكس عادي", 1.75),
      option("van_fast", "Express box van", "بوكس اكسبرس", 2.25),
    ],
    quotedAt: now,
    quoteRef: `sulaibikhat__zahra:${now}`,
    serviceDiscovery: null,
    ...overrides,
  };
}

function completeDraft(overrides = {}) {
  return {
    ...createEmptyBookingDraft(),
    senderName: "Abdulaziz",
    senderPhone: "96599338566",
    recipientName: "Ahmad",
    recipientPhone: "96599227462",
    pickupBlock: "2",
    pickupStreet: "7",
    pickupHouse: "19",
    deliveryBlock: "3",
    deliveryStreet: "9",
    deliveryExtra: "Apartment 11, floor 4, door 2",
    ...overrides,
  };
}

function entry(overrides = {}) {
  return {
    lastActivityTs: now,
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep: "sender",
    conversationId: "plan-b-smoke",
    replyTarget: "96550000000",
    accountId: "default",
    quoteRouteKey: "sulaibikhat__zahra",
    quoteTs: now,
    quotePickupAreaNameEn: "Sulaibikhat",
    quotePickupAreaNameAr: "الصليبيخات",
    quoteDropoffAreaNameEn: "Zahra",
    quoteDropoffAreaNameAr: "الزهراء",
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionLabelEn: "Express sedan",
    selectedQuoteOptionLabelAr: "سيارة اكسبرس",
    selectedQuoteOptionPrice: 1.75,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
    bookingDraft: completeDraft(),
    pendingReplyText: null,
    quotePresentedToCustomer: true,
    submittedOrderUid: null,
    dialogState: createEmptyDialogState(),
    pendingOrderEdits: null,
    ...overrides,
  };
}

function sessionGuard(overrides = {}) {
  return {
    allValidPrices: new Set(["1.250", "1.750", "2.250"]),
    lastToolName: "get_price",
    lastToolTs: now,
    lastCustomerMessage: "Express sedan from Sulaibikhat to Zahra: 1.750 KWD",
    lastCustomerMessages: {
      en: "Express sedan from Sulaibikhat to Zahra: 1.750 KWD",
      ar: "سيارة اكسبرس من الصليبيخات إلى الزهراء: 1.750 د.ك",
    },
    lastQuotedRoute: route(),
    pendingOrderSummary: null,
    lastCreatedOrderUid: null,
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(overrides.entry || {}),
    sessionGuard: sessionGuard(overrides.sessionGuard || {}),
    dialogState: overrides.dialogState || undefined,
    missingFields: overrides.missingFields || [],
    confirmationExplicit: overrides.confirmationExplicit || false,
    now,
  });
}

function goodEnglishSummary() {
  return [
    "Order summary:",
    "Pickup: Sulaibikhat, block 2, street 7, house 19",
    "Delivery: Zahra, block 3, street 9, Apartment 11, floor 4, door 2",
    "Sender: Abdulaziz, 96599338566",
    "Recipient: Ahmad, 96599227462",
    "Service: Express sedan",
    "Price: 1.750 KWD",
    "Please confirm.",
  ].join("\n");
}

function noopBuilders() {
  return {
    buildDeterministicGraceWindowReply: () => "Grace window",
    buildProviderIssueFallbackReply: () => "Provider issue",
  };
}

// Model/profile config: customer riders uses full GPT-5.4; riders-mini remains mini.
{
  const config = JSON.parse(
    fs.readFileSync(path.join(deliveryRoot, "openclaw.template.json"), "utf8"),
  );
  const providerIds = config.models.providers.openai.models.map((model) => model.id);
  assert(providerIds.includes("gpt-5.4"), "provider catalog must include full GPT-5.4");
  assert.equal(config.agents.defaults.model.primary, "openai/gpt-5.4");
  const riders = config.agents.list.find((agent) => agent.id === "riders");
  const ridersMini = config.agents.list.find((agent) => agent.id === "riders-mini");
  assert.equal(riders?.model?.primary, "openai/gpt-5.4");
  assert.equal(ridersMini?.model?.primary, "openai/gpt-5.4-mini");
  assert.equal(config.env?.RIDERS_SINGLE_LIFECYCLE_ENGINE, "1");
}

// English all-in-one: no missing delivery address; final pass owns full summary.
{
  const s = snapshot();
  assert.deepEqual(s.missingFields, []);
  assert.equal(s.addressSatisfaction.delivery, true);
  assert.equal(s.nextAction.type, "show_summary");
  let capturedMessages = null;
  const outcome = await generateFinalSnapshotReply({
    originalCustomerMessage:
      "Need express sedan from Sulaibikhat to Zahra. Sender Abdulaziz 99338566, recipient Ahmad 99227462. Pickup block 2 street 7 house 19, delivery block 3 street 9 apartment 11 floor 4 door 2.",
    appliedOpsSummary: ["apply_booking_field:sender.name", "apply_booking_field:delivery.extra"],
    rejectedOpsSummary: ["delivery.address:duplicate_satisfied"],
    bookingTruthSnapshot: s,
    preferredLanguage: "en",
    generateReply: async (messages) => {
      capturedMessages = messages;
      return goodEnglishSummary();
    },
  });
  assert.equal(outcome.status, "generated");
  assert.equal(outcome.markedSummaryShown, true);
  assert.equal(outcome.coherence.coherent, true, JSON.stringify(outcome.coherence.invalidations));
  assert(!/send.*delivery address/i.test(outcome.replyText), "must not ask for delivery address");
  assert(outcome.replyText.includes("Abdulaziz"), "English name must be preserved");
  assert(outcome.replyText.includes("Apartment 11, floor 4, door 2"), "apartment/floor/door must be preserved");
  assert(capturedMessages.user.includes('"type": "show_summary"'), "prompt must carry snapshot nextAction");
  assert(capturedMessages.user.includes("rejectedOpsSummary"), "prompt must carry rejected op summary");
  assert.equal(compactSnapshotForFinalReply(s).nextAction.type, "show_summary");
}

// Arabic Sulaibikhat clarification/service continuity: locked route and express service survive to final prompt.
{
  const s = snapshot({
    entry: {
      language: "ar",
      bookingDraft: completeDraft({
        senderName: "عبدالعزيز",
        recipientName: "أحمد",
        deliveryExtra: "شقة ١١، دور ٤، باب ٢",
      }),
    },
  });
  assert.equal(s.route.lockStatus, "locked");
  assert.equal(s.pendingRouteAmbiguity, null);
  assert.equal(s.quote.selected.deliveryType, "sedan_fast");
  const messages = buildFinalSnapshotReplyMessages({
    originalCustomerMessage: "يلا اكسبرس",
    appliedOpsSummary: ["get_price:locked_route"],
    bookingTruthSnapshot: s,
    preferredLanguage: "ar",
  });
  assert(messages.user.includes("sedan_fast"), "final pass payload must preserve express selection");
  assert(messages.system.includes("If route.lockStatus is locked, do not reopen route ambiguity."));
}

// Summary edit + confirmation: cheapest service update keeps route locked and moves to submit-order safety.
{
  const edited = snapshot({
    entry: {
      stage: "summary_shown",
      bookingStep: "summary_pending",
      selectedQuoteOptionType: "sedan_normal",
      selectedQuoteOptionLabelEn: "Standard sedan",
      selectedQuoteOptionLabelAr: "سيارة عادية",
      selectedQuoteOptionPrice: 1.25,
      selectedDeliveryType: "sedan_normal",
      quotedPrice: 1.25,
    },
    confirmationExplicit: true,
  });
  assert.equal(edited.route.lockStatus, "locked");
  assert.equal(edited.pendingRouteAmbiguity, null);
  assert.equal(edited.nextAction.type, "submit_order");
  const outcome = await generateFinalSnapshotReply({
    originalCustomerMessage: "يلا اوك",
    appliedOpsSummary: ["confirm_summary:confirmed"],
    bookingTruthSnapshot: edited,
    preferredLanguage: "ar",
    generateReply: async () => {
      throw new Error("submit_order must not call GPT wording");
    },
  });
  assert.equal(outcome.status, "server_transaction_result");
  assert.equal(outcome.reason, "submit_order_without_artifact");
}

// Recipient name + phone are satisfied together: a phone ask is rejected and retried.
{
  const s = snapshot();
  let attempts = 0;
  const outcome = await generateFinalSnapshotReply({
    originalCustomerMessage: "recipient Ahmad 99227462",
    appliedOpsSummary: ["apply_booking_field:recipient.name", "apply_booking_field:recipient.phone"],
    bookingTruthSnapshot: s,
    preferredLanguage: "en",
    generateReply: async () => {
      attempts += 1;
      return attempts === 1
        ? "I still need the recipient phone before I can confirm."
        : goodEnglishSummary();
    },
  });
  assert.equal(attempts, 2, "bad recipient-phone ask should trigger retry");
  assert.equal(outcome.status, "generated");
  assert.equal(outcome.coherence.coherent, true);
}

// Contradictions: satisfied delivery address asks, wrong service, English-name mutation, and house/apartment mutation fail validation.
{
  const s = snapshot();
  const badReplies = [
    "Express sedan from Sulaibikhat to Zahra is 1.750 KWD. If you want us to proceed with this order using the details you sent, reply confirm.",
    "Please send the delivery address.",
    goodEnglishSummary().replace("Express sedan", "Standard sedan"),
    goodEnglishSummary().replace("Abdulaziz", "عبدالعزيز"),
    goodEnglishSummary().replace("Apartment 11, floor 4, door 2", "House 11"),
  ];
  for (const reply of badReplies) {
    const result = checkPostDrainReplyCoherence({
      replyText: reply,
      bookingTruthSnapshot: s,
    });
    assert.equal(result.coherent, false, `expected contradiction to fail: ${reply}`);
  }
}

// Rollback: Plan B disables deterministic snapshot-authority substitution; flag off preserves old path.
{
  const s = snapshot();
  const base = {
    replyText: "GPT final summary text",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    bookingTruthSnapshot: s,
    hallucinationGuardRejections: [],
    stageAtTurnStart: "collecting_booking_details",
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    activeQuotedPrices: [1.25, 1.75],
    cancelContradicted: null,
    controllerTransitionHint: null,
    transactionResultRequired: false,
    canonicalTransactionText: null,
    classFifteenBypass: false,
    classFifteenCoverageInformationalOnly: false,
    conversationId: "plan-b-rollback-smoke",
    ...noopBuilders(),
  };
  const rollbackOff = decidePostStateOutbound({
    ...base,
    planBSnapshotFinalReply: true,
  });
  assert.equal(rollbackOff.decision, "allow");
  assert.equal(rollbackOff.replyText, "GPT final summary text");
  const rollbackOn = decidePostStateOutbound({
    ...base,
    planBSnapshotFinalReply: false,
  });
  assert.equal(rollbackOn.decision, "replace_authoritative");
  assert.notEqual(rollbackOn.replyText, "GPT final summary text");
}

console.log("ok - Plan B final snapshot reply flow");
