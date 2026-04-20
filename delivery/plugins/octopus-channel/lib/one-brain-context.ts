// ---------------------------------------------------------------------------
// Wave 5 extraction: ONE-BRAIN live-channel context formatter and its pure
// siblings (`formatOneBrainValue`, `computeOneBrainMissingFields`,
// `computeOneBrainNextRequiredAction`, `shouldIncludeQuotedRouteContext`, plus
// the `OneBrainNextRequiredAction` type).
//
// These functions are invoked on every inbound turn to assemble the hidden
// system-context block the LLM sees. They are entirely pure — every input is
// passed in; no module-scope state, no I/O. Extracted from
// `plugins/octopus-channel/index.ts`.
// ---------------------------------------------------------------------------

import type {
  ConversationFlowStage,
  CustomerIntent,
  CustomerScriptMode,
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
} from "../../shared/conversation-policy";
import {
  getEffectiveDeliveryAreaName,
  getEffectivePickupAreaName,
} from "../../shared/conversation-policy";
import { formatCustomerMemoryValue } from "./customer-profile";
import type { StoredQuotedRoute } from "./quoted-options";
import {
  buildQuotedRouteContextLines,
  detectExplicitOptionMention,
  detectVagueProceedSignal,
  routeHasManualConfirmOption,
} from "./quoted-options";
import {
  hasSatisfiedBookingAddress,
  formatPersistedBookingLocationLabel,
  diagnoseBookingAddressMissing,
} from "./booking-flow";

type InterpretedCustomerTurnLike = {
  action?: string | null;
  should_use_active_quote?: boolean | null;
};

export function shouldIncludeQuotedRouteContext(options?: {
  currentIntent?: CustomerIntent | null;
  interpretedTurn?: InterpretedCustomerTurnLike | null;
  conversationStage?: ConversationFlowStage | null;
}): boolean {
  const stage = options?.conversationStage || null;
  const action = options?.interpretedTurn?.action || "";
  const isQuoteFollowupClarification =
    action === "clarify" && options?.interpretedTurn?.should_use_active_quote;
  const shouldKeepQuoteContextDuringBooking =
    [
      "collecting_booking_details",
      "summary_shown",
      "awaiting_confirmation",
    ].includes(String(stage || "")) &&
    (action === "same_route_quote_option" ||
      action === "same_route_show_other_options" ||
      isQuoteFollowupClarification);
  if (stage !== "quoted" && !shouldKeepQuoteContextDuringBooking) {
    return false;
  }
  if (
    [
      "greeting",
      "language_switch",
      "service_overview",
      "tracking_request",
      "tracking_missing_id",
      "passenger_transport_request",
      "handoff",
      "general_support",
    ].includes(action) &&
    !isQuoteFollowupClarification
  ) {
    return false;
  }
  if (
    options?.interpretedTurn &&
    !options.interpretedTurn.should_use_active_quote &&
    stage !== "quoted"
  ) {
    return false;
  }
  const currentIntent = options?.currentIntent || null;
  if (
    currentIntent === "greeting" ||
    currentIntent === "service_inquiry" ||
    currentIntent === "tracking" ||
    currentIntent === "language_switch" ||
    currentIntent === "passenger_transport_request" ||
    currentIntent === "general_support"
  ) {
    return false;
  }
  return true;
}

export function formatOneBrainValue(value: string | null | undefined): string {
  if (value == null || value === "") return "null";
  return JSON.stringify(value);
}

export function computeOneBrainMissingFields(
  draft: PersistedBookingDraft,
  entry: PersistedConversationControllerEntry | null,
): string[] {
  const missing: string[] = [];
  if (!draft.senderName) missing.push("sender.name");
  if (!draft.senderPhone) missing.push("sender.phone");
  if (!draft.recipientName) missing.push("recipient.name");
  if (!draft.recipientPhone) missing.push("recipient.phone");
  // For each side, emit the aggregate marker (`pickup.address` /
  // `delivery.address`) that downstream next-required-action logic already
  // keys on, PLUS granular sub-field markers so the LLM can ask a targeted
  // question ("block?", "building number or apartment?", etc.) instead of
  // the previously vague "I still need the delivery address." Hallucination
  // incident 2026-04-17 was driven in large part by the LLM being unable to
  // tell *which* sub-field the server considered missing.
  if (!hasSatisfiedBookingAddress(draft, "pickup")) {
    missing.push("pickup.address");
    for (const sub of diagnoseBookingAddressMissing(draft, "pickup")) {
      missing.push(`pickup.${sub}`);
    }
  }
  if (!hasSatisfiedBookingAddress(draft, "delivery")) {
    missing.push("delivery.address");
    for (const sub of diagnoseBookingAddressMissing(draft, "delivery")) {
      missing.push(`delivery.${sub}`);
    }
  }
  // Area is satisfied by the effective area (quote → pending → pin)
  // so a pin-resolved area that hasn't yet been priced still counts
  // as "area known". Without this, a location pin that resolves to
  // "Mirqab" leaves `pickup.area` in `missing_fields`, which makes
  // the LLM ask "which pickup area is it from?" even though the
  // resolver already produced the answer and it's sitting in
  // `pickupLocation.resolvedAreaName` / `pendingPickupAreaNameEn`.
  if (!getEffectivePickupAreaName(draft, entry)) missing.push("pickup.area");
  if (!getEffectiveDeliveryAreaName(draft, entry)) missing.push("delivery.area");
  if (!entry?.selectedDeliveryType) missing.push("service_type");
  if (entry?.quotedPrice == null) missing.push("quoted_price");
  return missing;
}

export type OneBrainNextRequiredAction = {
  action: string;
  field: string | null;
  forbiddenShapes: string[];
};

/**
 * Turn the current booking-draft state into a single imperative directive the
 * LLM receives every turn. This is a deterministic backstop for prompt drift:
 * LLMs follow a short state-derived directive (`next_required_action: X`) much
 * more reliably than prose rules buried in SKILL.md, especially under
 * ambiguity or after clarification detours.
 *
 * Returns null when no booking has started (pre-quote / chit-chat); SKILL.md
 * governs those turns.
 */
export function computeOneBrainNextRequiredAction(params: {
  draft: PersistedBookingDraft;
  entry: PersistedConversationControllerEntry | null;
  missing: string[];
  /**
   * Current customer utterance for this turn. Used by the
   * clarify-before-proceed gate (Bug 1, 2026-04-20): a vague "proceed"
   * signal on a route that has a manual-confirm option is ambiguous and
   * must not silently advance into sender collection. Optional — callers
   * that don't have the text available (e.g. post-drain recomputation)
   * skip the gate.
   */
  currentCustomerText?: string | null;
  /**
   * Active quoted route for this turn. Needed by the clarify-before-
   * proceed gate to inspect the option catalog. Optional for the same
   * reason as `currentCustomerText`.
   */
  activeQuotedRoute?: StoredQuotedRoute | null;
}): OneBrainNextRequiredAction | null {
  const { draft, entry, missing, currentCustomerText, activeQuotedRoute } = params;

  if (entry?.stage === "order_submitted") {
    return {
      action: "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
      field: null,
      forbiddenShapes: [
        "standalone_ack",
        "route_price_recap",
        "fake_handoff_claim",
        "field_update_without_recreate",
      ],
    };
  }

  // Clarify-before-proceed gate (Bug 1, 2026-04-20 manual-confirm incident).
  //
  // Background: on `stage=quoted` with a mixed-bookability catalog (at
  // least one `manual_confirmation_required` option alongside others),
  // a vague proceed signal ("can we go ahead with it or?", "let's do
  // it", "اكمل", "نعم") is AMBIGUOUS. The customer could mean the
  // currently-selected option, the option the bot last mentioned, or
  // any other priced option in the catalog — and at least one of them
  // can't be booked via `create_simple_order`. Advancing silently into
  // sender collection here is the category failure we're fixing: the
  // LLM implicitly commits to the default `sedan_normal` (verified +
  // bookable) and kicks off sender collection, even though the bot was
  // just quoting Helper service (manual-confirm).
  //
  // Gate invariants:
  //  * stage === "quoted" (pre-collection, post-pricing)
  //  * route has at least one manual-confirm option AND >= 2 priced options
  //  * the customer's text this turn contains a vague proceed signal
  //  * the customer did NOT name any specific option in this same turn
  //  * `currentCustomerText` and `activeQuotedRoute` were both supplied
  //
  // When the gate fires, the directive is `CLARIFY_OPTION_BEFORE_PROCEED`
  // and `forbidden_reply_shapes` hard-blocks the LLM from the known drift
  // patterns: starting sender collection, calling `start_booking`, or
  // silently defaulting to the verified option. The reply itself is
  // server-composed by `buildDeterministicClarifyOptionBeforeProceedReply`
  // at the outbound-decision Region-A substitution point; the directive
  // here is the upstream steer that also keeps the LLM's tool calls
  // constrained.
  const inQuotedPreCollection = entry?.stage === "quoted";
  if (
    inQuotedPreCollection &&
    activeQuotedRoute &&
    currentCustomerText &&
    routeHasManualConfirmOption(activeQuotedRoute) &&
    detectVagueProceedSignal(currentCustomerText) &&
    !detectExplicitOptionMention({ text: currentCustomerText, route: activeQuotedRoute })
  ) {
    return {
      action: "CLARIFY_OPTION_BEFORE_PROCEED",
      field: "selected_option",
      forbiddenShapes: [
        "standalone_ack",
        "route_price_recap",
        "ask_sender_before_option_confirmed",
        "ask_recipient_before_option_confirmed",
        "start_booking_with_default_option",
        "call_create_simple_order_before_option_confirmed",
      ],
    };
  }

  // Pre-pricing gate: when a route-side area is still missing, the LLM
  // must ask for the area(s) before any sender/recipient collection.
  //
  // Why this exists as a deterministic directive instead of a prompt rule:
  // the 2026-04-19 transcript showed the LLM asking for sender name after
  // only pickup.area had resolved (via a pin), even though delivery.area
  // was still null. That left the customer halfway through a booking with
  // no priced route — the flow's most confusing failure mode. Area must
  // be resolved first so `get_price` can run and the draft has a
  // committed, priced route.
  //
  // The gate fires only when there's visible forward motion (stage is
  // `collecting_booking_details`, i.e. something has happened on this
  // conversation). That keeps pure chit-chat in SKILL.md's domain.
  const pickupAreaMissing = missing.includes("pickup.area");
  const deliveryAreaMissing = missing.includes("delivery.area");
  const inBookingCollection =
    entry?.stage === "collecting_booking_details" ||
    entry?.stage === "quoted";
  if (inBookingCollection && (pickupAreaMissing || deliveryAreaMissing)) {
    let action = "ASK_MISSING_AREAS";
    let field: string = "areas";
    if (pickupAreaMissing && !deliveryAreaMissing) {
      action = "ASK_PICKUP_AREA";
      field = "pickup.area";
    } else if (deliveryAreaMissing && !pickupAreaMissing) {
      action = "ASK_DELIVERY_AREA";
      field = "delivery.area";
    }
    return {
      action,
      field,
      forbiddenShapes: [
        "standalone_ack",
        "route_price_recap",
        // Explicitly forbid sender/recipient asks at this step. The LLM
        // has a standing instruction to collect all missing fields, so
        // without this the model happily asks for names while the route
        // is still unresolved. This line is the anchor that keeps the
        // sequencing correct.
        "ask_sender_before_area",
        "ask_recipient_before_area",
      ],
    };
  }

  if (!entry || entry.quotedPrice == null || !entry.selectedDeliveryType) {
    return null;
  }

  // Manual-confirmation selection gate. Some option types (typically
  // Helper service) are flagged as `manual_confirmation_required` on
  // the route's `optionCatalog`. They cannot be placed via
  // `create_simple_order`; our team schedules them manually. When the
  // customer has selected such an option, the collection flow is
  // truncated: pickup address, delivery address, then `request_handoff`
  // with a `manual_confirm_<type>` reason. Sender/recipient identity is
  // NOT collected (the team collects that directly). See Bug 1 in the
  // 2026-04-20 retro and hard rule 8 in the live channel context.
  //
  // The tool-level guard (`getDirectChatBookingBlockReason`) already
  // blocks any `create_simple_order` attempt for this status. This
  // directive is the upstream steer — it keeps the LLM from even
  // starting sender collection, which was the visible failure mode.
  const selectedDirectChatStatus = String(
    entry.selectedQuoteOptionDirectChatBookingStatus || "",
  )
    .trim()
    .toLowerCase();
  const isManualConfirmSelection =
    selectedDirectChatStatus === "manual_confirmation_required";
  if (isManualConfirmSelection) {
    const pickupMissing = missing.includes("pickup.address");
    const deliveryMissing = missing.includes("delivery.address");
    // Bug 4 (2026-04-20 manual-confirm signal drop incident): the LLM
    // previously produced address-ask replies that looked identical to
    // the direct-booking flow (e.g. "Express refrigerated van is 2.250
    // KWD. Send the pickup address first."). The outbound decision now
    // substitutes a deterministic, server-composed reply via
    // `buildDeterministicManualConfirmAddressAskReply`, but we keep the
    // forbidden-shape signal here so the LLM upstream is also steered
    // and the guard is defensible in both layers. Key new shapes:
    //   - `ask_pickup_address_without_manual_confirm_signal`
    //   - `ask_delivery_address_without_manual_confirm_signal`
    //   - `request_handoff_without_manual_confirm_signal`
    // These are enforced by the outbound substitution; listing them
    // makes the intent visible in logs and smoke tests.
    if (pickupMissing) {
      return {
        action: "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM",
        field: "pickup.address",
        forbiddenShapes: [
          "standalone_ack",
          "ask_sender_for_manual_confirm",
          "ask_recipient_for_manual_confirm",
          "call_create_simple_order_for_manual_confirm",
          "ask_pickup_address_without_manual_confirm_signal",
        ],
      };
    }
    if (deliveryMissing) {
      return {
        action: "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM",
        field: "delivery.address",
        forbiddenShapes: [
          "standalone_ack",
          "ask_sender_for_manual_confirm",
          "ask_recipient_for_manual_confirm",
          "call_create_simple_order_for_manual_confirm",
          "ask_delivery_address_without_manual_confirm_signal",
        ],
      };
    }
    return {
      action: "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM",
      field: null,
      forbiddenShapes: [
        "standalone_ack",
        "route_price_recap",
        "ask_sender_for_manual_confirm",
        "ask_recipient_for_manual_confirm",
        "call_create_simple_order_for_manual_confirm",
        "write_full_order_summary_for_manual_confirm",
        "request_handoff_without_manual_confirm_signal",
      ],
    };
  }

  // Conflict gate: once pricing has happened and we're collecting fields,
  // any unresolved DST conflict must be disambiguated BEFORE we advance
  // to the next ASK step. Background: in the 2026-04-20 pickup-extra
  // incident the fast-path and the LLM both wrote different whitespace
  // forms of the same apartment description in the same turn, raising a
  // `slot_conflict`. The next-action logic below does not look at
  // conflicts — it only looks at missing fields — so the flow happily
  // asked for the DELIVERY address next. Two turns later, when the LLM
  // finally asked "please confirm the pickup extra exactly as you want
  // it written", the customer had already moved on and the confirm felt
  // out of nowhere. Unresolved conflicts advancing past their own slot
  // is exactly the "late confirmation" failure mode the user flagged.
  //
  // Rule: CONFIRM_<slot> comes before ASK_<next>. The directive below
  // overrides any downstream ASK so the LLM's reply this turn must be
  // the disambiguation ask, nothing else. The 3a normalization work
  // should have eliminated the fast-path-vs-LLM whitespace-drift source
  // of this, but we keep the gate as the deterministic backstop for
  // genuine conflicts (two materially different values).
  const dstSlots = entry.dialogState?.slots ?? {};
  const conflictingSlotNames: string[] = [];
  for (const [name, record] of Object.entries(dstSlots)) {
    if (record && record.status === "conflict") {
      conflictingSlotNames.push(name);
    }
  }
  if (conflictingSlotNames.length > 0) {
    return {
      action: "CONFIRM_SLOT_CONFLICT",
      field: conflictingSlotNames[0],
      forbiddenShapes: [
        // The conflict ask is the ONLY move this turn. No ASKs for
        // later slots, no summaries, no "and then we'll need…" tails.
        "standalone_ack",
        "route_price_recap",
        "ask_next_slot_before_conflict_resolved",
        "summary_before_conflict_resolved",
      ],
    };
  }

  const collectionMissing = missing.filter(
    (f) =>
      f === "sender.name" ||
      f === "sender.phone" ||
      f === "recipient.name" ||
      f === "recipient.phone" ||
      f === "pickup.address" ||
      f === "delivery.address",
  );

  if (collectionMissing.length > 0) {
    let field: string = collectionMissing[0];
    let action = "COLLECT_NEXT_MISSING_FIELD";

    // Sequential sender-then-recipient sequencing. When sender is still
    // unresolved, any recipient ask in the same message is forbidden —
    // bundling sender + recipient into one prompt creates ambiguous
    // replies where a single name+phone pair can be silently attributed
    // to the wrong party (see 2026-04-19 19:14 incident and
    // `shared/ambiguous-pair-guard.ts`).
    const senderAskFirst =
      field === "sender.name" || field === "sender.phone";
    if (senderAskFirst) {
      if (!draft.senderName) {
        field = "sender";
        action = "ASK_SENDER_NAME_AND_PHONE_DECISION";
      } else {
        field = "sender.phone";
        action = "ASK_SENDER_PHONE";
      }
    } else if (field === "recipient.name" || field === "recipient.phone") {
      field = "recipient";
      action = "ASK_RECIPIENT_NAME_AND_PHONE";
    } else if (field === "pickup.address") {
      action = "ASK_PICKUP_ADDRESS";
    } else if (field === "delivery.address") {
      action = "ASK_DELIVERY_ADDRESS";
    }

    const forbiddenShapes = ["standalone_ack", "route_price_recap"];
    if (senderAskFirst) {
      // Hard rule for the sender step: ask ONLY for the sender here.
      // The LLM has a strong tendency to pack both sender + recipient
      // asks into one message, which makes the customer's single-pair
      // answer ambiguous on the server side.
      forbiddenShapes.push("ask_recipient_with_sender");
    }

    // Bug 2 (address-drift, 2026-04-20): when a side's address is already
    // satisfied under `hasSatisfiedBookingAddress` (block + street|avenue +
    // either house OR a substantive extra), the LLM must not ask for any
    // more sub-fields of that side. Without this hard shape, SKILL.md's
    // documentation of the house/extra fields consistently steered the
    // LLM to append "send the building number" even after the customer
    // provided apartment/floor/door. Rendering the forbidden shapes per-
    // side tells the LLM which side is frozen this turn, keeping the
    // forbidden-list self-explanatory in logs.
    addAddressSatisfiedForbiddenShapes(forbiddenShapes, draft);

    return {
      action,
      field,
      forbiddenShapes,
    };
  }

  const summaryForbiddenShapes = [
    "standalone_ack",
    "route_price_recap",
    "one_line_confirmation_without_summary",
  ];
  addAddressSatisfiedForbiddenShapes(summaryForbiddenShapes, draft);
  return {
    action: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    field: null,
    forbiddenShapes: summaryForbiddenShapes,
  };
}

/**
 * Bug 2 helper (2026-04-20 address-drift incident).
 *
 * Pushes the per-side "don't ask for address sub-fields that are already
 * satisfied" shape names onto the forbidden list for whichever sides
 * (pickup / delivery) have an address that passes
 * `hasSatisfiedBookingAddress`. The pair of shape names is intentional:
 *
 *   * `ask_for_satisfied_<side>_address_field` — the generic guard for
 *     any sub-field ask (block / street / avenue / house / extra) when
 *     the side is already locatable.
 *   * `ask_for_<side>_house_when_extra_satisfies_completeness` — the
 *     specific sub-shape we saw drift into: `address_extra` holds
 *     apartment/floor/door, which the server accepts as satisfying
 *     completeness (per `hasSubstantiveAddressExtra`), but the LLM
 *     still asks for the house / building number because SKILL.md told
 *     it to do that whenever `address_house` is null. Listing the
 *     specific shape too makes the drift visible in logs and keeps the
 *     prompt-side rewrite in SKILL.md anchored to a named server shape.
 */
function addAddressSatisfiedForbiddenShapes(
  forbiddenShapes: string[],
  draft: PersistedBookingDraft,
): void {
  const pushIfAbsent = (value: string) => {
    if (!forbiddenShapes.includes(value)) forbiddenShapes.push(value);
  };
  if (hasSatisfiedBookingAddress(draft, "pickup")) {
    pushIfAbsent("ask_for_satisfied_pickup_address_field");
    if (!draft.pickupHouse && draft.pickupExtra) {
      pushIfAbsent("ask_for_pickup_house_when_extra_satisfies_completeness");
    }
  }
  if (hasSatisfiedBookingAddress(draft, "delivery")) {
    pushIfAbsent("ask_for_satisfied_delivery_address_field");
    if (!draft.deliveryHouse && draft.deliveryExtra) {
      pushIfAbsent("ask_for_delivery_house_when_extra_satisfies_completeness");
    }
  }
}

// ONE-BRAIN: produces a short, descriptive state snapshot for the agent.
// Intentionally minimal — no step hints, no "ask ONLY for X" imperatives, no
// intent enum, no transition hints. The agent reads the facts and decides what
// to do. Hard rules are a tight, boundary-aligned 4-item list — nothing else.
export function formatOneBrainLiveChannelContext(params: {
  normalizedReplyTarget: string | null;
  preferredReplyLanguage?: "ar" | "en" | null;
  customerScriptMode?: CustomerScriptMode | null;
  controllerEntry?: PersistedConversationControllerEntry | null;
  quotedRoute?: StoredQuotedRoute | null;
  /**
   * Current customer utterance for this turn. Forwarded to
   * `computeOneBrainNextRequiredAction` so the clarify-before-proceed
   * gate (Bug 1) can fire on vague proceed signals.
   */
  currentCustomerText?: string | null;
}): string {
  const entry = params.controllerEntry || null;
  const draft = entry?.bookingDraft || null;
  const lines: string[] = [
    "[SYSTEM CONTEXT - LIVE CHANNEL]",
    "Hidden runtime facts. Do not quote, mention, or explain this block to the customer.",
    "current_sender_role: customer",
    `current_customer_whatsapp: ${formatCustomerMemoryValue(params.normalizedReplyTarget)}`,
  ];
  if (params.preferredReplyLanguage) {
    lines.push(`preferred_reply_language: ${params.preferredReplyLanguage}`);
  }
  if (params.customerScriptMode) {
    lines.push(`customer_script_mode: ${params.customerScriptMode}`);
  }

  if (params.quotedRoute) {
    lines.push(...buildQuotedRouteContextLines(params.quotedRoute, entry));
  }

  if (entry?.stage) {
    lines.push(`current_conversation_stage: ${entry.stage}`);
  }
  if (entry?.stage === "order_submitted" && entry.submittedOrderUid) {
    lines.push(`submitted_order_uid: ${formatOneBrainValue(entry.submittedOrderUid)}`);
  }

  if (draft) {
    const sender = `sender: { name: ${formatOneBrainValue(draft.senderName)}, phone: ${formatOneBrainValue(draft.senderPhone)} }`;
    const recipient = `recipient: { name: ${formatOneBrainValue(draft.recipientName)}, phone: ${formatOneBrainValue(draft.recipientPhone)} }`;
    const pickupPin = formatPersistedBookingLocationLabel(draft.pickupLocation);
    const deliveryPin = formatPersistedBookingLocationLabel(draft.deliveryLocation);
    // Use the effective-area resolver (quote → pending → pin-resolved)
    // so the context block agrees with `missing_fields`. Previously
    // this line only read the quote slot, so a pin that resolved to
    // "Mirqab" but hadn't been priced yet showed as `area: null` here
    // even though `pickupLocation.resolvedAreaName = "Mirqab"`, and
    // the LLM would read that and ask for the area again.
    const effectivePickupArea = getEffectivePickupAreaName(draft, entry);
    const effectiveDeliveryArea = getEffectiveDeliveryAreaName(draft, entry);
    const pickup = `pickup: { area: ${formatOneBrainValue(effectivePickupArea)}, block: ${formatOneBrainValue(draft.pickupBlock)}, street: ${formatOneBrainValue(draft.pickupStreet)}, avenue: ${formatOneBrainValue(draft.pickupAvenue)}, house: ${formatOneBrainValue(draft.pickupHouse)}, extra: ${formatOneBrainValue(draft.pickupExtra)}, pin: ${formatOneBrainValue(pickupPin)} }`;
    const delivery = `delivery: { area: ${formatOneBrainValue(effectiveDeliveryArea)}, block: ${formatOneBrainValue(draft.deliveryBlock)}, street: ${formatOneBrainValue(draft.deliveryStreet)}, avenue: ${formatOneBrainValue(draft.deliveryAvenue)}, house: ${formatOneBrainValue(draft.deliveryHouse)}, extra: ${formatOneBrainValue(draft.deliveryExtra)}, pin: ${formatOneBrainValue(deliveryPin)} }`;
    lines.push("booking_draft:");
    lines.push(`  ${sender}`);
    lines.push(`  ${recipient}`);
    lines.push(`  ${pickup}`);
    lines.push(`  ${delivery}`);
    const pendingPin = formatPersistedBookingLocationLabel(draft.pendingLocation);
    if (pendingPin) {
      lines.push(`pending_shared_location: ${pendingPin}`);
    }
    const selectedType = entry?.selectedDeliveryType || null;
    const selectedPrice = entry?.quotedPrice != null ? `${entry.quotedPrice.toFixed(3)} KWD` : null;
    if (selectedType || selectedPrice) {
      lines.push(`selected_service: ${formatOneBrainValue(selectedType)}`);
      lines.push(`selected_price: ${formatOneBrainValue(selectedPrice)}`);
    }
    const missing = computeOneBrainMissingFields(draft, entry);
    lines.push(`missing_fields: [${missing.join(", ")}]`);

    const directive = computeOneBrainNextRequiredAction({
      draft,
      entry,
      missing,
      currentCustomerText: params.currentCustomerText ?? null,
      activeQuotedRoute: params.quotedRoute ?? null,
    });
    if (directive) {
      lines.push(`next_required_action: ${directive.action}`);
      if (directive.field) lines.push(`next_field: ${directive.field}`);
      if (directive.forbiddenShapes.length > 0) {
        lines.push(`forbidden_reply_shapes: [${directive.forbiddenShapes.join(", ")}]`);
      }
    }

    // Dialog State Tracking: surface the requested_slot register so the LLM
    // sees exactly which slot the customer is currently answering. This
    // closes the "misroute" class of bug where the LLM writes a
    // disambiguation answer to the wrong slot (e.g. answered dropoff
    // disambiguation, LLM calls apply_booking_field with the area in
    // pickup_area). Deterministic guards still enforce the correct routing,
    // but this raises the LLM's baseline accuracy so the guard fires less
    // often.
    const requestedSlot = entry?.dialogState?.requestedSlot ?? null;
    if (requestedSlot) {
      lines.push(`requested_slot: ${requestedSlot.name}`);
      if (requestedSlot.options && requestedSlot.options.length > 0) {
        lines.push(
          `requested_slot_options: [${requestedSlot.options.map(formatOneBrainValue).join(", ")}]`,
        );
      }
      lines.push(
        `requested_slot_rule: The customer's next reply is answering "${requestedSlot.name}". Apply their value to that slot only. Do NOT route it to any other field, even if the value could plausibly belong elsewhere.`,
      );
    }

    // Surface conflicts for slots that the customer has filled but a later
    // write tried to overwrite with a different value. The LLM should ask
    // the customer to disambiguate instead of silently keeping either.
    const slots = entry?.dialogState?.slots ?? {};
    const conflicts: string[] = [];
    for (const [name, record] of Object.entries(slots)) {
      if (record && record.status === "conflict") {
        conflicts.push(
          `${name}: kept="${record.value}" proposed="${record.conflictCandidate ?? ""}"`,
        );
      }
    }
    if (conflicts.length > 0) {
      lines.push(`slot_conflicts: [${conflicts.join("; ")}]`);
      lines.push(
        `slot_conflicts_rule: One or more slots have conflicting values. Ask the customer to confirm which is correct before continuing. Do NOT silently overwrite.`,
      );
    }
  }

  lines.push("hard_rules:");
  lines.push("  1. Every price you state must come from a get_price result for the active route this turn or an already-active quoted route above. Never invent, cache, or reuse prices from earlier in the conversation if the route changed.");
  lines.push("  2. The only way to place an order is calling create_simple_order. The server validates the draft, route, service, and price; if it rejects, fix what it asks and try again. Never claim an order was placed without a successful tool result.");
  lines.push("  3. Reply language rule — only two valid reply scripts: (a) if `customer_script_mode` is `arabic`, reply in Arabic script (Kuwaiti White Dialect); (b) if `customer_script_mode` is `english`, reply in English. NEVER reply in Arabizi (Latin letters with digit-for-letter substitutions like 7/9/5/6/3/2) — this is NOT a valid reply style, even if the customer wrote to you in Arabizi. When a customer writes in Arabizi (e.g. `slam 3laikm`, `bkm il tws6eel`, `shlonkm`), understand it and reply in English. If the customer switches between Arabic script and English between turns, switch with them immediately.");
  lines.push("  4. Every reply must move the conversation forward. Never emit a standalone acknowledgement like 'Sure', 'Noted', 'Understood', or 'We'll proceed' without also taking the next concrete action in the same message (ask for the next missing field, show the summary, confirm, etc.). Rule 5 defines what 'next concrete action' means for informational questions — for those, answering the question IS the concrete action and you must not append the next ASK step.");
  lines.push("  5. Informational option/price questions (e.g. 'what is the cheapest?', 'most expensive option?', 'do you have a van?', 'is there a faster one?', 'how much for express?', 'شنو أرخص خيار؟', 'عندكم باص؟') are ANSWER-ONLY turns. Reply with the direct answer (option name + price, or a short factual yes/no) and stop. Do NOT append the next slot ask (sender name, phone, recipient, address, etc.), do NOT invite the customer to proceed, do NOT attach a 'if you want to book it, send me…' suffix — even when `next_required_action` is a slot ask. The customer is evaluating options, not proceeding. Only advance to the next slot ask when the customer's NEXT message contains an explicit proceed signal: 'yes', 'go', 'let's do it', 'book it', 'proceed', 'continue', 'confirm', 'اطلب', 'اكمل', 'نعم', 'تمام خلّيها', 'خذ', 'سكّر', etc.");
  lines.push("  6. Edit turns — when the customer explicitly edits already-filled fields (e.g. 'block 3 to block 4', 'change the street to 10', 'no, make it sedan_fast', 'بدّل الشقة إلى 25') after the summary or during confirmation, treat the new values as the sole source of truth. Acknowledge the update briefly and either re-show the updated summary or ask only for the specific field that is still genuinely ambiguous. Do NOT re-offer the old value as an alternative. Do NOT say 'is it A or B?' listing the pre-edit and post-edit values. The server applies the edit; your job is to confirm it, not to re-litigate it.");
  lines.push("  7. Cancel vs option-switch — NEVER call `cancel_booking` when the same customer utterance also names one of the currently quoted options (e.g. 'nvm pls standard sedan', 'cancel, actually fast box van', 'skip the helper, do sedan instead', 'لا بس مبرد', 'مو مساعد، عادي'). 'nvm', 'never mind', 'forget it', 'skip', 'cancel', 'actually', 'no' paired with a vehicle/option name is an OPTION SWITCH, not a cancellation. In that case, emit an `apply_booking_field` or option-selection update for the named option if applicable, answer the customer by naming the switched-to option + its quoted price, and continue the flow. Only call `cancel_booking` when the customer clearly wants to abandon the booking entirely, with no option-switch wording in the same message ('cancel the booking', 'never mind the whole thing', 'ألغي الطلب').");
  lines.push("  8. Manual-confirmation options — some options in the active route's option catalog require manual confirmation by our team and CANNOT be placed via `create_simple_order` directly (typically flagged in `optionCatalog` with a direct-chat-booking status like 'manual_confirmation_required'; Helper service and refrigerated-van variants are canonical cases). The SERVER composes the customer-facing reply on these turns — it always names the option, its price, the 'needs manual confirmation by our team' signal, and the next address ask (or the handoff message once both addresses are collected). Your reply text will be substituted; what matters on your side is the OP layer: do NOT call `create_simple_order`, do NOT collect sender/recipient identity, apply address ops normally for pickup + delivery, and when both addresses are present call `request_handoff` with a short reason tag like 'manual_confirm_<option_type>' so the team picks up. The customer is not booking an instant order; they are handing off to a human for manual scheduling.");
  lines.push("  9. Structured option interpretation — whenever the customer's message in THIS turn names or implies a choice among the currently quoted options (switching, confirming, or asking about a specific one: 'express ref van', 'the cool one', 'helper please', 'خذ المبرد', 'standard sedan بس'), you MUST call the `propose_option_interpretation` tool alongside your reply. Emit the structured reading: `class` ∈ {sedan, van, cooled_van, helper} (null if the customer didn't signal a class), `tier` ∈ {normal, fast} (null if the customer didn't signal a tier), `source_quote` = substring of the customer's inbound text this turn, `confidence` = 'high' when you are confident, 'low' when genuinely ambiguous. This is PROPOSE-ONLY — the server reconciles your structured reading with its own deterministic parse and decides whether to commit or clarify. Do NOT call it on generic booking questions, price asks, or messages that don't name an option. Do NOT mention the tool to the customer.");
  lines.push("[/SYSTEM CONTEXT - LIVE CHANNEL]");
  return lines.join("\n");
}
