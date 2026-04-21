#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

function buildControllerEntry(shared, overrides = {}) {
  return {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep: "pickup_address",
    conversationId: "test-conversation",
    replyTarget: "96550000000",
    accountId: "test-account",
    quoteRouteKey: null,
    quoteTs: null,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedQuoteOptionType: null,
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: null,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: null,
    quotedPrice: null,
    bookingDraft: shared.createEmptyBookingDraft(),
    pendingReplyText: null,
    ...overrides,
  };
}

async function main() {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const sourcePath = path.join(root, "plugins/octopus-channel/index.ts");
  const ridersToolsPath = path.join(root, "plugins/riders-tools/index.ts");
  // After Waves 2–5 the octopus-channel plugin was surgically split into
  // plugins/octopus-channel/lib/*.ts. Collect source from the entry + every
  // extracted module so legacy string-contract assertions still find their
  // needles wherever they currently live.
  const octopusLibDir = path.join(root, "plugins/octopus-channel/lib");
  const source = [
    fs.readFileSync(sourcePath, "utf-8"),
    ...(fs.existsSync(octopusLibDir)
      ? fs
          .readdirSync(octopusLibDir)
          .filter((f) => f.endsWith(".ts"))
          .map((f) => fs.readFileSync(path.join(octopusLibDir, f), "utf-8"))
      : []),
  ].join("\n");
  // After the Wave 1a surgical split, riders-tools/index.ts is a composition
  // root and the individual tool bodies live in plugins/riders-tools/tools/*.ts.
  // Collect source from the entry + each extracted tool module so legacy
  // string-contract assertions still find their needles wherever they
  // currently live.
  const ridersToolsDir = path.join(root, "plugins/riders-tools");
  const toolsDir = path.join(ridersToolsDir, "tools");
  const ridersToolsSource = [
    fs.readFileSync(ridersToolsPath, "utf-8"),
    ...(fs.existsSync(toolsDir)
      ? fs
          .readdirSync(toolsDir)
          .filter((f) => f.endsWith(".ts"))
          .map((f) => fs.readFileSync(path.join(toolsDir, f), "utf-8"))
      : []),
  ].join("\n");

  const octopus = await loadTsModule("plugins/octopus-channel/index.ts");
  const shared = await loadTsModule("plugins/shared/conversation-policy.ts");
  const t = octopus.__testables;

  assert(t, "__testables export should exist");

  // normalizeInterpretedCustomerTurn was removed along with the legacy
  // interpreter LLM path (one-brain owns every customer turn now).
  // The deterministic helpers below remain the interpretation layer.

  assert(t.getLocationRoleSelection("Pic up") === "pickup", "Pic up should resolve as pickup");
  assert(t.getLocationRoleSelection("for the sender") === "pickup", "sender-side phrasing should resolve as pickup");
  assert(t.getLocationRoleSelection("مكان المستلم") === "delivery", "Arabic recipient-side phrasing should resolve as delivery");

  const pendingLocation = {
    source: "location_pin",
    latitude: 29.3759,
    longitude: 47.9774,
    name: "Qibla",
    address: "Qibla, Kuwait",
    resolvedAreaName: "Qibla",
  };
  const pendingEntry = buildControllerEntry(shared, {
    bookingDraft: {
      ...shared.createEmptyBookingDraft(),
      senderName: "Sender",
      senderPhone: "50000000",
      recipientName: "Recipient",
      recipientPhone: "51111111",
      pendingLocation,
    },
  });
  const pendingResult = t.applyPendingLocationRoleSelection({
    controllerEntry: pendingEntry,
    visibleText: "for the sender",
  });
  assert(pendingResult?.role === "pickup", "pending location should bind to pickup from sender phrasing");
  assert(pendingResult?.entry.bookingDraft.pickupLocation?.name === "Qibla", "pickup location should be saved");
  assert(pendingResult?.entry.bookingDraft.pendingLocation === null, "pending location should be cleared after binding");

  const idleWithPickupOnly = buildControllerEntry(shared, {
    stage: "idle",
    bookingStep: "none",
    bookingDraft: {
      ...shared.createEmptyBookingDraft(),
      pickupLocation: pendingLocation,
    },
  });
  assert(
    t.getStandaloneLocationAutoAssignmentRole(idleWithPickupOnly) === "delivery",
    "when pickup is already saved, the next standalone location should default to delivery",
  );
  const salmiyaLocation = {
    source: "map_link",
    latitude: 29.3336,
    longitude: 48.0761,
    name: "Salmiya",
    address: "Salmiya, Kuwait",
    resolvedAreaName: "Salmiya",
  };
  const autoAssignedDelivery = t.applyStandaloneLocationAssignment({
    controllerEntry: idleWithPickupOnly,
    location: salmiyaLocation,
    role: "delivery",
  });
  assert(
    autoAssignedDelivery.bookingDraft.pickupLocation?.name === "Qibla",
    "auto-assignment should preserve the original pickup location",
  );
  assert(
    autoAssignedDelivery.bookingDraft.deliveryLocation?.name === "Salmiya",
    "auto-assignment should save the second standalone location as delivery",
  );

  const idleWithDeliveryOnly = buildControllerEntry(shared, {
    stage: "idle",
    bookingStep: "none",
    bookingDraft: {
      ...shared.createEmptyBookingDraft(),
      deliveryLocation: salmiyaLocation,
    },
  });
  assert(
    t.getStandaloneLocationAutoAssignmentRole(idleWithDeliveryOnly) === "pickup",
    "when delivery is already saved, the next standalone location should default to pickup",
  );

  const quotedEntry = buildControllerEntry(shared, {
    stage: "quoted",
    bookingStep: "none",
    quoteRouteKey: "hawalli::salmiya",
    quoteTs: Date.now(),
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionLabelAr: "سيارة عادية",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  });
  const clearedQuoted = t.clearQuotedRouteContext(quotedEntry);
  assert(clearedQuoted.stage === "idle", "clearing quoted route context should return to idle");
  assert(clearedQuoted.quoteRouteKey === null, "clearing quoted route context should drop route authority");
  assert(clearedQuoted.selectedDeliveryType === null, "clearing quoted route context should drop selected delivery type");

  const quotedRoute = {
    routeKey: "hawalli::salmiya",
    pickupAreaNameEn: "Hawalli",
    pickupAreaNameAr: "حولي",
    dropoffAreaNameEn: "Salmiya",
    dropoffAreaNameAr: "السالمية",
    optionCatalog: [
      {
        delivery_type: "sedan_normal",
        label_en: "Standard sedan",
        label_ar: "سيارة عادية",
        quoted_price: 1.25,
        formatted_price: "1.250 KWD",
        visibility: "recommended_customer_quote",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
      {
        delivery_type: "sedan_fast",
        label_en: "Express sedan",
        label_ar: "سيارة سريعة",
        quoted_price: 1.75,
        formatted_price: "1.750 KWD",
        visibility: "other_options_if_customer_asks",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
    ],
  };
  const quotedContextLines = t.buildQuotedRouteContextLines(quotedRoute, quotedEntry);
  assert(
    quotedContextLines.some((line) => line.includes("bookable=verified")) &&
      quotedContextLines.some((line) => line.includes("label_ar=سيارة سريعة")),
    "quoted route context should expose per-option bookability and Arabic labels",
  );
  assert(
    t.shouldIncludeQuotedRouteContext({
      currentIntent: "pricing_request",
      interpretedTurn: {
        action: "same_route_show_other_options",
        selected_delivery_type: null,
        should_use_active_quote: true,
        route_changed: false,
        order_id: null,
        requested_language: null,
        confidence: "high",
        reason: "customer is comparing active quote options",
        booking_fields: null,
        location_role_hint: null,
      },
      conversationStage: "collecting_booking_details",
    }) === true,
    "quote context should stay available during booking for same-route comparisons",
  );
  assert(
    t.shouldIncludeQuotedRouteContext({
      currentIntent: "pricing_request",
      interpretedTurn: {
        action: "clarify",
        selected_delivery_type: null,
        should_use_active_quote: true,
        route_changed: false,
        order_id: null,
        requested_language: null,
        confidence: "medium",
        reason: "clarifying active quote",
        booking_fields: null,
        location_role_hint: null,
      },
      conversationStage: "collecting_booking_details",
    }) === true,
    "active-quote clarifications during booking should keep quoted route context",
  );

  // Note: `applyBookingFieldCorrection` was deleted in the step-2 dead-code
  // sweep (it was only reachable via the unreachable legacy `applyResponderStateOps`
  // branch). The summary-stage correction behavior that used to be validated
  // here is now covered by the live-drain path: the LLM's `apply_booking_field`
  // tool call is applied by `applyBookingFieldPatch` + `applyBookingDraftProgress`,
  // exercised end-to-end by `smoke-test-carry-over-live-drain.mjs` and the
  // main octopus-channel integration.

  const senderEntry = buildControllerEntry(shared, {
    stage: "collecting_booking_details",
    bookingStep: "sender",
    bookingDraft: {
      ...shared.createEmptyBookingDraft(),
    },
  });
  const volunteeredFutureFields = t.applyVolunteeredFutureBookingFields({
    controllerEntry: senderEntry,
    bookingFields: {
      sender_name: "Ahmed",
      sender_phone: "50000000",
      phone_decision: "none",
      recipient_name: "Sara",
      recipient_phone: "51111111",
      address_block: null,
      address_street: null,
      address_house: null,
    },
  });
  assert(
    volunteeredFutureFields.bookingDraft.recipientName === "Sara" &&
      volunteeredFutureFields.bookingDraft.recipientPhone === "51111111",
    "sender step should preserve safe volunteered recipient details for the next step",
  );
  assert(
    t.shouldFallbackToDeterministicBookingReply({
      replyText: "Please share the sender full name, and should we use this same WhatsApp number?",
      controllerEntry: senderEntry,
    }) === false,
    "natural single-step sender prompts should not be replaced by the deterministic fallback",
  );
  assert(
    t.shouldFallbackToDeterministicBookingReply({
      replyText: "Please share the sender name, recipient details, and both addresses.",
      controllerEntry: senderEntry,
    }) === true,
    "booking output guard should catch replies that skip ahead to multiple booking steps",
  );
  assert(
    t.shouldFallbackToDeterministicSummaryReply({
      replyText: "Order summary: Sender: Ahmed. Recipient: Sara. Pickup: Hawalli. Delivery: Salmiya. Service: Standard sedan. Price: 1.250 KWD. Shall I proceed?",
      preferredLanguage: "en",
    }) === false,
    "summary output guard should allow complete natural summaries that include the key fields and confirmation ask",
  );
  assert(
    t.shouldFallbackToDeterministicSummaryReply({
      replyText: "Everything looks good.",
      preferredLanguage: "en",
    }) === true,
    "summary output guard should reject incomplete summaries",
  );

  const freshEntry = buildControllerEntry(shared, {
    lastActivityTs: Date.now() - 10 * 60_000,
  });
  const graceEntry = buildControllerEntry(shared, {
    lastActivityTs: Date.now() - (shared.CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS + 5 * 60_000),
  });
  const expiredEntry = buildControllerEntry(shared, {
    lastActivityTs: Date.now() - (shared.CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS + 20 * 60_000),
  });
  assert(t.shouldPreserveGreetingDuringActiveFlow(freshEntry) === true, "fresh active flow should preserve greeting");
  assert(t.isGreetingInGraceWindow(freshEntry) === false, "fresh active flow should not be in grace window");
  assert(t.shouldPreserveGreetingDuringActiveFlow(graceEntry) === false, "grace-window flow should not count as fresh");
  assert(t.isGreetingInGraceWindow(graceEntry) === true, "stale-but-recent flow should enter grace window");
  assert(t.isGreetingInGraceWindow(expiredEntry) === false, "expired flow should fall outside grace window");
  assert(
    shared.resolveCustomerReplyLanguage({
      visibleText: "وين الطلب",
      explicitLanguage: null,
      fallbackLanguage: "en",
      preferFallbackForAudioTranscript: true,
    }) === "ar",
    "Arabic audio transcript text should stay Arabic instead of being forced back to English",
  );

  // Stage 4 interpreter collapse: the `llmSaysBookingData` predicate and the
  // LLM-driven handoff trigger were deleted along with the dormant turn
  // interpreter. The route-reset logic now runs unconditionally on inbound
  // customer text (no `!llmSaysBookingData` guard), and handoff escalation is
  // driven by (a) a `request_handoff` responder op from the one-brain tool and
  // (b) the `shouldMoveToHumanAgent(outboundText)` string match applied by
  // `sendOctopusTextReply`.
  assert(
    source.includes("shouldResetControllerForNewRouteMessage") &&
      !source.includes("llmSaysBookingData"),
    "route reset should run unconditionally (llmSaysBookingData predicate removed)",
  );
  assert(
    source.includes("shouldMoveToHumanAgent(outboundText)") &&
      !source.includes("LLM-driven handoff triggered"),
    "source should rely on shouldMoveToHumanAgent for handoff (LLM-driven handoff trigger removed)",
  );
  assert(
    source.includes("const effectiveLanguageSwitch: \"ar\" | \"en\" | null = explicitLanguageRequest") &&
      !source.includes('interpretedCustomerTurn?.action === "language_switch"'),
    "effectiveLanguageSwitch should collapse to explicitLanguageRequest (interpreter fallback removed)",
  );
  assert(
    source.includes("Location pin saved during") &&
      source.includes('conversationControllerEntry.bookingStep === "sender" || conversationControllerEntry.bookingStep === "recipient"'),
    "source should preserve pins during sender/recipient steps",
  );
  assert(
    source.includes("pending location replaced with newer shared location") &&
      source.includes("getDeclaredLocationRole"),
    "source should handle same-turn role binding and newer locations while another pending location exists",
  );
  assert(
    source.includes("applyVolunteeredFutureBookingFields") &&
      source.includes("recipientName") &&
      source.includes("recipientPhone"),
    "local smoke should cover volunteered next-step recipient details",
  );
  assert(
    source.includes("clearQuotedRouteContext") &&
      source.includes("standalone location auto-assigned") &&
      source.includes("location_saved:"),
    "source should clear stale quote context and route saved-location acknowledgments through the agent",
  );
  assert(
    source.includes("pre-dispatch quoted conversation transitioned to booking-details stage") &&
      source.includes("blocked booking transition for non-direct-bookable option"),
    "source should start booking before agent reply while still blocking non-direct-bookable options",
  );
  assert(
    source.includes("cleared automated state after handoff"),
    "source should clear automated controller state after human handoff",
  );
  assert(
    ridersToolsSource.includes("getDirectChatBookingBlockReason") &&
      ridersToolsSource.includes("requires manual confirmation before booking"),
    "riders-tools should block create_simple_order for non-direct-bookable options",
  );
  assert(
    source.includes("shouldIncludeQuotedRouteContext") &&
      source.includes("current_controller_transition_hint") &&
      !source.includes("deterministic quoted-stage greeting reply sent") &&
      !source.includes("deterministic service overview reply sent"),
    "source should expose richer quote/controller context and remove the canned greeting/service interceptions",
  );
  assert(
    source.includes('"RIDERS_INBOUND_DEBOUNCE_MS"') &&
      source.includes('"RIDERS_INBOUND_MEDIA_DEBOUNCE_MS"') &&
      source.includes("resolveInboundDebounceMs") &&
      source.includes("windowMs="),
    "source should debounce media turns so they can merge with nearby follow-up text (env-overridable)",
  );
  assert(
    source.includes("isSummaryEditRequest") &&
      source.includes("summary edit clarification routed through agent") &&
      source.includes('controllerTransitionHint === "summary_edit_request" && !reply'),
    "source should route summary edits through the agent while avoiding unchanged-summary loops",
  );
  assert(
    source.includes("Quote follow-up hint: The customer is comparing or asking for alternatives") &&
      !source.includes("Replaced same-route other-options reply with deterministic fallback"),
    "source should let GPT handle same-route option comparisons instead of replacing them with a canned list",
  );
  assert(
    source.includes("const sameRouteQuoteSkip = Boolean(") &&
      source.includes("input.activeQuotedRoute && input.sameRouteQuoteAction"),
    "source should skip the canonical price guard for all same-route quote interactions",
  );
  assert(
    source.includes("booking_step_advanced:") &&
      source.includes("booking_started:"),
    "source should use transition hints to guide the LLM through booking steps",
  );
  assert(
    source.includes("grace_window_offer") &&
      source.includes("language_switch_reissue_summary") &&
      source.includes("shouldFallbackToDeterministicSummaryReply"),
    "source should route grace-window and language-switch reissue through the agent with fallback summaries",
  );
  assert(
    source.includes("cancel_booking") &&
      source.includes("booking_cancelled") &&
      source.includes("location_pending_role_clarification") &&
      source.includes("greeting_during_active_booking"),
    "source should support cancel_booking, location clarification, and greeting-during-booking via agent hints",
  );
  assert(
    source.includes("reply send failed on closed conversation; cleared automated state") &&
      source.includes('sessionGuard.lastToolName === "track_order"'),
    "source should clear stale automated state on track-order transitions and closed-thread send failures",
  );
  assert(
    source.includes("octopus-ingress-ledger.json") &&
      source.includes("webhook_received") &&
      source.includes("webhook_accepted") &&
      source.includes("webhook_enqueued") &&
      source.includes("webhook_replayed") &&
      source.includes("outbound_result"),
    "source should persist ingress ledger state and emit ingress/outbound observability markers",
  );
  assert(
    source.includes("buildProviderIssueFallbackReply") &&
      source.includes('cause: "provider_error_suppressed"') &&
      source.includes('cause: "outbound_send_failed"') &&
      source.includes('cause: "webhook_auth_failed"'),
    "source should map provider failures to a safe customer fallback and emit operator-action alerts for auth and outbound failures",
  );
  assert(
    !source.includes('routes.push({ accountId: account.accountId, path: "/" });'),
    "source should only register the explicit webhook path and not expose the root path as a fallback webhook route",
  );

  console.log("PASS smoke-test-octopus-channel-local");
}

main().catch((error) => {
  console.error("FAIL smoke-test-octopus-channel-local");
  console.error(error?.stack || String(error));
  process.exit(1);
});
