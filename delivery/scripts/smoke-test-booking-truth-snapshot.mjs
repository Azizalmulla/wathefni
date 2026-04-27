#!/usr/bin/env node
// Smoke test: canonical booking truth snapshot.
//
// The invariant under test: once a route is quoted, downstream layers must
// consume the full active quoted route/catalog while the route authority is
// valid, even after the controller advances into booking collection.

import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const policy = loadTs("plugins/shared/conversation-policy.ts");
const dialog = loadTs("plugins/shared/dialog-state.ts");
const truth = loadTs("plugins/shared/booking-truth-snapshot.ts");
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");
const oneBrainContext = loadTs("plugins/octopus-channel/lib/one-brain-context.ts");
const hallucination = loadTs("plugins/shared/reply-hallucination-guard.ts");
const outboundVerify = loadTs("plugins/shared/outbound-verify.ts");
const lifecycle = loadTs("plugins/shared/booking-lifecycle-gate.ts");
const orderGuard = loadTs("plugins/shared/order-guard.ts");
const postDrainCoherence = loadTs("plugins/octopus-channel/lib/post-drain-reply-coherence.ts");

const { createEmptyBookingDraft } = policy;
const { createEmptyDialogState } = dialog;
const { buildBookingTruthSnapshot } = truth;
const {
  matchQuotedOptionDiscriminated,
  matchLlmOptionInterpretation,
  resolveOptionFromProposals,
} = quotedOptions;
const { formatOneBrainLiveChannelContext } = oneBrainContext;
const { runHallucinationGuard } = hallucination;
const { verifySummaryFacts } = outboundVerify;
const { canAdvanceBookingFlow, buildBookingLifecycleRouteAudit } = lifecycle;
const { guardCreateSimpleOrder } = orderGuard;
const { checkPostDrainReplyCoherence } = postDrainCoherence;

function option(deliveryType, labelEn, price, status = "verified") {
  return {
    delivery_type: deliveryType,
    label_ar: labelEn,
    label_en: labelEn,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "available_on_request",
    direct_chat_booking_status: status,
    direct_chat_booking_note: null,
  };
}

const now = Date.now();
const route = {
  routeKey: "sharq__shuwaikh",
  pickupAreaNameAr: "Sharq",
  pickupAreaNameEn: "Sharq",
  dropoffAreaNameAr: "Shuwaikh",
  dropoffAreaNameEn: "Shuwaikh",
  pickupAreaResolution: {
    status: "canonical",
    areaId: 101,
    nameEn: "Sharq",
    nameAr: "Sharq",
    options: [],
    confirmedByUser: true,
    quoteBuiltFromAreaIds: true,
  },
  dropoffAreaResolution: {
    status: "canonical",
    areaId: 202,
    nameEn: "Shuwaikh",
    nameAr: "Shuwaikh",
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
    option("sedan_normal", "Standard sedan", 1.25),
    option("sedan_fast", "Express sedan", 1.75),
    option("van_normal", "Standard box van", 1.75),
    option("van_fast", "Express box van", 2.25),
    option("helper_standard", "Helper service", 3.25, "manual_confirmation_required"),
  ],
  serviceDiscovery: null,
  quotedAt: now,
  quoteRef: `sharq__shuwaikh:${now}`,
};

function completeDraft() {
  return {
    ...createEmptyBookingDraft(),
    senderName: "Aziz",
    senderPhone: "96550000001",
    recipientName: "Sara",
    recipientPhone: "96550000002",
    pickupBlock: "1",
    pickupStreet: "2",
    pickupHouse: "3",
    deliveryBlock: "4",
    deliveryStreet: "5",
    deliveryHouse: "6",
  };
}

function entry(overrides = {}) {
  return {
    lastActivityTs: now,
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep: "sender",
    conversationId: "truth-smoke",
    replyTarget: "96550000000",
    accountId: "default",
    quoteRouteKey: "sharq__shuwaikh",
    quoteTs: now,
    quotePickupAreaNameEn: "Sharq",
    quotePickupAreaNameAr: "Sharq",
    quoteDropoffAreaNameEn: "Shuwaikh",
    quoteDropoffAreaNameAr: "Shuwaikh",
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
    bookingDraft: completeDraft(),
    pendingReplyText: null,
    quotePresentedToCustomer: true,
    submittedOrderUid: null,
    dialogState: createEmptyDialogState(),
    pendingOrderEdits: null,
    ...overrides,
  };
}

function sessionGuard() {
  return {
    allValidPrices: new Set(["1.250", "1.750", "2.250", "3.250"]),
    lastToolName: "get_price",
    lastCustomerMessage: "Delivery from Sharq to Shuwaikh. Price: 1.250 KWD",
    lastCustomerMessages: {
      ar: null,
      en: "Delivery from Sharq to Shuwaikh. Price: 1.250 KWD",
    },
    lastToolTs: now,
    lastQuotedRoute: route,
    pendingOrderSummary: null,
    lastCreatedOrderUid: null,
  };
}

// Quote truth remains active after the flow moves into booking collection.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "turn_start",
    controllerState: entry(),
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  assert(snapshot.quote.routeAuthorityActive, "quote authority should remain active during collection");
  assert.equal(snapshot.quote.activeQuotedRoute?.routeKey, "sharq__shuwaikh");
  assert(snapshot.quote.validQuotedPrices.includes(1.75), "full valid quoted prices must include Express sedan");
  assert.equal(snapshot.quote.optionCatalog.find((o) => o.delivery_type === "sedan_fast")?.label_en, "Express sedan");
  assert.deepEqual(snapshot.missingFields, []);
  assert.equal(snapshot.nextMissingField, null);
  assert.equal(snapshot.route.lockStatus, "locked");
  assert.equal(snapshot.summary.ready, true);
  assert.equal(snapshot.order.ready, false);
  assert(snapshot.order.blockers.includes("summary_not_shown"));
  assert.equal(snapshot.nextAction.type, "show_summary");
  const context = formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "96550000000",
    preferredReplyLanguage: "en",
    customerScriptMode: "english",
    controllerEntry: entry(),
    bookingTruthSnapshot: snapshot,
    snapshotContextOnly: true,
  });
  assert(context.includes("active_quoted_options:"), "LLM context should expose full active quote catalog");
  assert(context.includes("sedan_fast | Express sedan"), "LLM context should expose Express sedan from snapshot");
  assert(context.includes("missing_fields: []"), "snapshot-only context should render snapshot missing fields");
  assert(context.includes("summary_ready: true"), "snapshot-only context should render snapshot readiness");
  assert(context.includes("next_action: show_summary"), "snapshot-only context should render snapshot next action");
}

// Single lifecycle engine: confirmation only counts for the exact summary the
// customer last saw. Any later operational fact change forces a fresh summary.
{
  const rendered = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "summary_shown",
      bookingStep: "summary_pending",
    }),
    sessionGuard: sessionGuard(),
    missingFields: [],
    requireRenderedSummaryHash: true,
    now,
  });
  assert(rendered.summary.currentHash, "complete summary should have a hash");

  const confirmed = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "awaiting_confirmation",
      bookingStep: "awaiting_summary_confirmation",
      lastRenderedSummaryHash: rendered.summary.currentHash,
      lastRenderedSummaryAt: now,
    }),
    sessionGuard: sessionGuard(),
    missingFields: [],
    confirmationExplicit: true,
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(confirmed.summary.hashMatchesLastRendered, true);
  assert.equal(confirmed.nextAction.type, "submit_order");
  assert.equal(confirmed.lifecycleState, "submitting_order");

  const staleConfirmation = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "awaiting_confirmation",
      bookingStep: "awaiting_summary_confirmation",
      lastRenderedSummaryHash: rendered.summary.currentHash,
      lastRenderedSummaryAt: now,
      bookingDraft: {
        ...completeDraft(),
        senderName: "Aziz Updated",
      },
    }),
    sessionGuard: sessionGuard(),
    missingFields: [],
    confirmationExplicit: true,
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(staleConfirmation.summary.hashMatchesLastRendered, false);
  assert(staleConfirmation.order.blockers.includes("summary_hash_mismatch"));
  assert.equal(staleConfirmation.nextAction.type, "show_summary");
  assert.equal(staleConfirmation.lifecycleState, "ready_to_show_summary");
}

// Single lifecycle engine: awaiting-confirmation turns consume the latest
// semantic disposition instead of blindly re-asking for confirmation.
{
  const rendered = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "summary_shown",
      bookingStep: "summary_pending",
    }),
    sessionGuard: sessionGuard(),
    missingFields: [],
    requireRenderedSummaryHash: true,
    now,
  });
  const awaiting = {
    stage: "awaiting_confirmation",
    bookingStep: "awaiting_summary_confirmation",
    lastRenderedSummaryHash: rendered.summary.currentHash,
    lastRenderedSummaryAt: now,
  };
  const editRequest = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(awaiting),
    sessionGuard: sessionGuard(),
    missingFields: [],
    confirmationExplicit: false,
    currentTurnDisposition: {
      turnKind: "confirmation_or_cancel",
      pricingAction: "none",
      awaitingConfirmationKind: "edit_order",
      turnIntentKind: "clarifying_question",
      turnIntentConfidence: "high",
      getPriceFired: false,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(editRequest.summary.hashMatchesLastRendered, true);
  assert.equal(editRequest.nextAction.type, "ask_edit_target");
  assert.equal(editRequest.lifecycleState, "awaiting_confirmation");

  const question = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(awaiting),
    sessionGuard: sessionGuard(),
    missingFields: [],
    currentTurnDisposition: {
      turnKind: "confirmation_or_cancel",
      pricingAction: "none",
      awaitingConfirmationKind: "informational_question",
      turnIntentKind: "clarifying_question",
      turnIntentConfidence: "high",
      getPriceFired: false,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(question.nextAction.type, "answer_question_then_wait_for_confirmation");

  const semanticConfirm = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(awaiting),
    sessionGuard: sessionGuard(),
    missingFields: [],
    currentTurnDisposition: {
      turnKind: "confirmation_or_cancel",
      pricingAction: "none",
      awaitingConfirmationKind: "confirm_order",
      turnIntentKind: "acknowledgement",
      turnIntentConfidence: "high",
      getPriceFired: false,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(semanticConfirm.nextAction.type, "submit_order");
}

// Stale route-request slots must not reappear once snapshot route truth is
// locked and the final next action is confirmation/submission, not clarification.
{
  const staleRouteDialogState = {
    ...createEmptyDialogState(),
    requestedSlot: {
      name: "pickup_area",
      options: ["Sulaibikhat", "Northwest Sulaibikhat", "Sulaibikhat Cemetery"],
      askedTs: now,
    },
  };
  const lockedEntry = entry({
    stage: "awaiting_confirmation",
    bookingStep: "awaiting_summary_confirmation",
    dialogState: staleRouteDialogState,
  });
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: lockedEntry,
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  assert.equal(snapshot.route.lockStatus, "locked");
  assert.equal(snapshot.nextAction.type, "wait_for_confirmation");
  const context = formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "96550000000",
    preferredReplyLanguage: "en",
    customerScriptMode: "english",
    controllerEntry: lockedEntry,
    bookingTruthSnapshot: snapshot,
    snapshotContextOnly: true,
  });
  assert(!context.includes("requested_slot: pickup_area"), "snapshot-only context must hide stale route requested_slot when nextAction is not route ambiguity");
  const coherence = checkPostDrainReplyCoherence({
    replyText: "الصليبيخات، شمال غرب الصليبيخات، أو مقبرة الصليبيخات؟",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0]?.kind, "asks_for_route_ambiguity_when_snapshot_locked");
  const gateDecision = canAdvanceBookingFlow("summary_shown", {
    controllerState: lockedEntry,
    sessionGuard: sessionGuard(),
    dialogState: staleRouteDialogState,
    routeAudit: buildBookingLifecycleRouteAudit({
      controllerState: lockedEntry,
      sessionGuard: sessionGuard(),
      bookingTruthSnapshot: snapshot,
    }),
    bookingTruthSnapshot: snapshot,
    currentTurnToolResults: { missingFields: [] },
    now,
  });
  assert.equal(gateDecision.decision, "allow", "lifecycle gate should ignore stale route requested_slot when snapshot is locked");
}

// Single lifecycle engine: latest-turn meaning gates stale state. Idle
// chit-chat must not let stale route/reprice state speak.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "idle",
      bookingStep: "none",
      quoteRouteKey: null,
      quoteTs: null,
      quotePickupAreaNameEn: null,
      quoteDropoffAreaNameEn: null,
      selectedDeliveryType: null,
      quotedPrice: null,
      bookingDraft: createEmptyBookingDraft(),
    }),
    sessionGuard: {
      ...sessionGuard(),
      lastQuotedRoute: null,
    },
    missingFields: [],
    currentTurnDisposition: {
      turnKind: "informational",
      pricingAction: "none",
      awaitingConfirmationKind: null,
      turnIntentKind: null,
      turnIntentConfidence: null,
      getPriceFired: false,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(snapshot.nextAction.type, "answer_customer_question");
  assert(snapshot.blockedStateActions.some((item) => item.action === "reprice_route"));
}

// Single lifecycle engine: questions outrank stale missing-field collection.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "collecting_booking_details",
      bookingStep: "sender",
      bookingDraft: {
        ...completeDraft(),
        senderPhone: null,
      },
    }),
    sessionGuard: sessionGuard(),
    missingFields: ["sender.phone"],
    currentTurnDisposition: {
      turnKind: "booking_detail_collection",
      pricingAction: "continue_existing_quote",
      awaitingConfirmationKind: null,
      turnIntentKind: "clarifying_question",
      turnIntentConfidence: "high",
      getPriceFired: false,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(snapshot.nextAction.type, "answer_customer_question");
  assert(snapshot.blockedStateActions.some((item) => item.action === "collect_missing_field"));
}

// Single lifecycle engine: fresh route quote comes before sender collection
// when the latest turn requested a route and did not voluntarily fill details.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({
      stage: "quoted",
      bookingStep: "none",
      bookingDraft: createEmptyBookingDraft(),
    }),
    sessionGuard: sessionGuard(),
    missingFields: ["sender.name", "sender.phone"],
    currentTurnDisposition: {
      turnKind: "initial_route",
      pricingAction: "call_get_price",
      awaitingConfirmationKind: null,
      turnIntentKind: null,
      turnIntentConfidence: null,
      getPriceFired: true,
      hasConcreteMutation: false,
      stateResetApplied: false,
      source: "proposed_turn_decision",
    },
    requireRenderedSummaryHash: true,
    now,
  });
  assert.equal(snapshot.route.lockStatus, "locked");
  assert.equal(snapshot.nextAction.type, "show_quote");
}

// Post-drain coherence detector: combined recipient name+phone commits must not
// be followed by a request for the recipient phone.
{
  const recipientDraft = {
    ...completeDraft(),
    recipientName: "Ahamad basha",
    recipientPhone: "99227462",
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({ bookingDraft: recipientDraft }),
    sessionGuard: sessionGuard(),
    now,
  });
  const coherence = checkPostDrainReplyCoherence({
    replyText: "Got it. Send me the recipient phone too.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0].field, "recipient.phone");
}

// Same invariant for sender name+phone.
{
  const senderDraft = {
    ...completeDraft(),
    senderName: "abdulaziz almulla",
    senderPhone: "99338566",
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({ bookingDraft: senderDraft }),
    sessionGuard: sessionGuard(),
    now,
  });
  const coherence = checkPostDrainReplyCoherence({
    replyText: "Thanks Abdulaziz. Please send the sender phone number.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0].field, "sender.phone");
}

// Apartment/floor/door style address extras satisfy the house/unit requirement.
{
  const addressDraft = {
    ...completeDraft(),
    pickupHouse: null,
    pickupExtra: "apartment 12 door 12 floor 3",
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry({ bookingDraft: addressDraft }),
    sessionGuard: sessionGuard(),
    now,
  });
  assert.equal(snapshot.addressSatisfaction.pickup, true);
  assert(!snapshot.missingFields.includes("pickup.house_or_unit"));
  const coherence = checkPostDrainReplyCoherence({
    replyText: "Got it. Send me the pickup house or building number.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0].field, "pickup.house_or_unit");
}

// Selected service is snapshot truth; do not ask the customer to select again.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: sessionGuard(),
    now,
  });
  const coherence = checkPostDrainReplyCoherence({
    replyText: "Which service do you want, standard or express?",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0].field, "service_type");
}

// Final reply contract: when the final snapshot says the selected service is
// Express sedan, a stale standard-sedan/1.250 recap must be rejected even if it
// looks like a normal route-price reply.
{
  const fastEntry = entry({
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionLabelAr: "Express sedan",
    selectedQuoteOptionLabelEn: "Express sedan",
    selectedQuoteOptionPrice: 1.75,
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
  });
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: fastEntry,
    sessionGuard: sessionGuard(),
    now,
  });
  assert.equal(snapshot.nextAction.type, "show_summary");
  assert.equal(snapshot.quote.selected.deliveryType, "sedan_fast");
  const coherence = checkPostDrainReplyCoherence({
    replyText:
      "تمام، الصليبيخات إلى الزهراء، السيارة العادية + توصيل عادي بسعر 1.250 KWD. إذا تبي أكمل الحجز، قل أكمل.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert(
    coherence.invalidations.some(
      (item) =>
        item.kind === "states_wrong_selected_service" ||
        item.kind === "states_wrong_selected_price",
    ),
    JSON.stringify(coherence.invalidations),
  );
}

// When snapshot.nextAction is submit_order, the final reply cannot ask for a
// route clarification or missing booking fields.
{
  const readyEntry = entry({
    stage: "awaiting_confirmation",
    bookingStep: "awaiting_summary_confirmation",
  });
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: readyEntry,
    sessionGuard: sessionGuard(),
    confirmationExplicit: true,
    now,
  });
  assert.equal(snapshot.nextAction.type, "submit_order");
  const routeAsk = checkPostDrainReplyCoherence({
    replyText: "Which Sulaibikhat area do you mean?",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(routeAsk.coherent, false);
  assert.equal(routeAsk.invalidations[0]?.kind, "asks_for_route_ambiguity_when_submitting");
  const fieldAsk = checkPostDrainReplyCoherence({
    replyText: "Send me the sender phone.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(fieldAsk.coherent, false);
  assert(fieldAsk.invalidations.some((item) => item.field === "sender.phone"));
}

// If snapshot.nextAction requires collecting a specific missing field, a generic
// acknowledgement is not enough after old directive authoring is demoted.
{
  const incompleteEntry = entry({
    bookingDraft: {
      ...completeDraft(),
      senderPhone: null,
    },
  });
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: incompleteEntry,
    sessionGuard: sessionGuard(),
    now,
  });
  assert.equal(snapshot.nextAction.type, "collect_missing_field");
  assert.equal(snapshot.nextAction.field, "sender.phone");
  const coherence = checkPostDrainReplyCoherence({
    replyText: "تمام، سجلت التفاصيل.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0]?.kind, "omits_required_missing_field_ask");
}

// If snapshot.nextAction requires route ambiguity resolution, a generic route
// recap cannot pass just because the old directive renderer is shadow-only.
{
  const ambiguousRoute = {
    ...route,
    pickupAreaResolution: {
      status: "ambiguous",
      areaId: null,
      nameEn: "Sulaibikhat",
      nameAr: "الصليبيخات",
      options: [
        { areaId: 23, nameEn: "Sulaibikhat", nameAr: "الصليبيخات" },
        { areaId: 24, nameEn: "Northwest Sulaibikhat", nameAr: "شمال غرب الصليبيخات" },
      ],
      confirmedByUser: false,
      quoteBuiltFromAreaIds: false,
    },
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: { ...sessionGuard(), lastQuotedRoute: ambiguousRoute },
    now,
  });
  assert.equal(snapshot.nextAction.type, "resolve_route_ambiguity");
  const coherence = checkPostDrainReplyCoherence({
    replyText: "تمام، من الصليبيخات إلى الزهراء.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert.equal(coherence.invalidations[0]?.kind, "omits_required_route_ambiguity");
}

// Route not locked means the final reply cannot proceed as if quoting/booking is
// safe.
{
  const ambiguousRoute = {
    ...route,
    dropoffAreaResolution: {
      status: "ambiguous",
      areaId: null,
      nameEn: "Shuwaikh",
      nameAr: "الشويخ",
      options: [{ areaId: 34, nameEn: "Shuwaikh Industrial-1", nameAr: "الشويخ الصناعية 1" }],
      confirmedByUser: false,
      quoteBuiltFromAreaIds: false,
    },
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: { ...sessionGuard(), lastQuotedRoute: ambiguousRoute },
    now,
  });
  const coherence = checkPostDrainReplyCoherence({
    replyText: "Price is 1.250 KWD. Send me the sender name and phone.",
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(coherence.coherent, false);
  assert(coherence.invalidations.some((item) => item.kind === "proceeds_with_unlocked_route"));
}

// A clear option request resolves against the snapshot option catalog.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "turn_start",
    controllerState: entry(),
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  const raw = matchQuotedOptionDiscriminated({
    normalizedText: policy.normalizeIntentText("express sedan pls"),
    options: snapshot.quote.optionCatalog,
  });
  const llm = matchLlmOptionInterpretation({
    interpretation: {
      class: "sedan",
      tier: "fast",
      source_quote: "express sedan",
      confidence: "high",
    },
    options: snapshot.quote.optionCatalog,
  });
  const resolved = resolveOptionFromProposals({ rawTextOutcome: raw, llmOutcome: llm });
  assert.equal(resolved.kind, "commit");
  assert.equal(resolved.option.delivery_type, "sedan_fast");
}

// Price guard must accept any price in the full active quoted route, not only
// the scalar selected `quotedPrice=1.250`.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  const decision = runHallucinationGuard({
    replyText:
      "Express sedan is 1.750 KWD for Sharq to Shuwaikh. If you want to book it, send the sender name and phone.",
    entry: entry(),
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    activeQuotedPrices: snapshot.quote.validQuotedPrices,
  });
  assert.equal(decision.blocked, false, `price guard should accept catalog price, got ${decision.reason}`);
}

// Summary fact verification may accept catalog option prices when the reply
// explicitly names the catalog option.
{
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  const result = verifySummaryFacts(
    "Sender Aziz, recipient Sara. Other options include Express sedan for 1.750 KWD.",
    entry(),
    snapshot,
  );
  assert.equal(result.consistent, true, `catalog option price should be grounded: ${JSON.stringify(result.mismatches)}`);
}

// Lifecycle gate must reject scalar/catalog divergence from the same snapshot.
{
  const divergentEntry = entry({
    selectedQuoteOptionType: "sedan_fast",
    selectedDeliveryType: "sedan_fast",
    selectedQuoteOptionLabelEn: "Express sedan",
    selectedQuoteOptionPrice: 1.75,
    quotedPrice: 1.25,
    bookingStep: "summary_pending",
  });
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: divergentEntry,
    sessionGuard: sessionGuard(),
    missingFields: [],
    now,
  });
  const decision = canAdvanceBookingFlow("summary_shown", {
    controllerState: divergentEntry,
    sessionGuard: sessionGuard(),
    dialogState: divergentEntry.dialogState,
    currentTurnToolResults: { missingFields: [] },
    bookingTruthSnapshot: snapshot,
    routeAudit: buildBookingLifecycleRouteAudit({
      controllerState: divergentEntry,
      sessionGuard: sessionGuard(),
      bookingTruthSnapshot: snapshot,
    }),
    now,
  });
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "price_mismatch");
}

// Resolver provenance, not area name, owns route canonicality.
{
  const ambiguousRoute = {
    ...route,
    dropoffAreaResolution: {
      status: "ambiguous",
      areaId: null,
      nameEn: "Shuwaikh",
      nameAr: "الشويخ",
      ambiguityGroupId: "shuwaikh",
      options: [
        { areaId: 42, nameEn: "Shuwaikh", nameAr: "الشويخ" },
        { areaId: 34, nameEn: "Shuwaikh Industrial-1", nameAr: "الشويخ الصناعية 1" },
        { areaId: 17, nameEn: "Shuwaikh Industrial-2", nameAr: "الشويخ الصناعية 2" },
        { areaId: 14, nameEn: "Shuwaikh Industrial-3", nameAr: "الشويخ الصناعية 3" },
      ],
      sourceText: "shwuai5",
      normalizedText: "shwuai5",
      resolverSource: "resolver",
      confirmedByUser: false,
      quoteBuiltFromAreaIds: false,
    },
  };
  const ambiguousSession = {
    ...sessionGuard(),
    lastQuotedRoute: ambiguousRoute,
  };
  const snapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entry(),
    sessionGuard: ambiguousSession,
    missingFields: [],
    now,
  });
  assert.equal(snapshot.route.dropoff.status, "ambiguous");
  assert.equal(snapshot.route.lockStatus, "blocked");
  assert(snapshot.missingFields.includes("delivery.area"));
  assert.equal(snapshot.pendingRouteAmbiguity.side, "dropoff");
  assert.equal(snapshot.summary.ready, false);
  assert(snapshot.summary.blockers.includes("route_blocked"));
  assert(snapshot.summary.blockers.includes("missing_fields"));
  const context = formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "96550000000",
    preferredReplyLanguage: "en",
    customerScriptMode: "english",
    controllerEntry: entry(),
    bookingTruthSnapshot: snapshot,
    snapshotContextOnly: true,
  });
  assert(context.includes("route_lock_status: blocked"));
  assert(context.includes("route_pending_options:"));
  assert(context.includes("pending_route_ambiguity: side=dropoff"));
  const decision = canAdvanceBookingFlow("collecting_booking_details", {
    controllerState: entry(),
    sessionGuard: ambiguousSession,
    bookingTruthSnapshot: snapshot,
    routeAudit: buildBookingLifecycleRouteAudit({
      controllerState: entry(),
      sessionGuard: ambiguousSession,
      bookingTruthSnapshot: snapshot,
    }),
    currentTurnToolResults: { missingFields: [] },
    now,
  });
  assert.equal(decision.decision, "block");
  assert.equal(decision.blockingReason, "route_not_canonical");
  const guard = guardCreateSimpleOrder({
    draft: completeDraft(),
    pickupAreaNameEn: "Sharq",
    dropoffAreaNameEn: "Shuwaikh",
    deliveryType: "sedan_normal",
    quotedPrice: 1.25,
    visibleCustomerText: "yes",
    lastQuotedRoute: ambiguousRoute,
    bookingTruthSnapshot: snapshot,
  });
  assert.equal(guard.ok, false);
  assert.equal(guard.code, "route_not_canonical");
}

console.log("booking truth snapshot smoke passed");
