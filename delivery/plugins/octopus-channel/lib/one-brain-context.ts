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
import type { TurnDisposition } from "../../shared/turn-disposition";
import {
  getEffectiveDeliveryAreaName,
  getEffectivePickupAreaName,
} from "../../shared/conversation-policy";
import { formatCustomerMemoryValue } from "./customer-profile";
import type { StoredQuotedRoute } from "./quoted-options";
import { buildQuotedRouteContextLines } from "./quoted-options";
import {
  hasSatisfiedBookingAddress,
  formatPersistedBookingLocationLabel,
  diagnoseBookingAddressMissing,
} from "./booking-flow";
import type { DirectiveAction } from "../../shared/directive-reply-registry";

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

// Re-export the registry action union as the authoritative type for
// `OneBrainNextRequiredAction.action`. Any new action string added here
// requires a matching entry in `DIRECTIVE_REPLY_RENDERERS`; the
// `satisfies Record<DirectiveAction, …>` check in
// `directive-reply-registry.ts` fails the build otherwise. This is the
// Phase 2 exhaustiveness tripwire.
export type OneBrainNextRequiredAction = {
  action: import("../../shared/directive-reply-registry").DirectiveAction;
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
  // Accepted for compatibility with legacy callers that still pass
  // these from the Region-A block; no longer consumed. The
  // clarify-before-proceed branch that used them was deleted in the
  // authority-cutover.
  currentCustomerText?: string | null;
  activeQuotedRoute?: StoredQuotedRoute | null;
}): OneBrainNextRequiredAction | null {
  const { draft, entry, missing } = params;

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

  // Authority-cutover: the clarify-before-proceed branch (Bug 1,
  // 2026-04-20 manual-confirm incident) lived here pre-cutover. It
  // emitted `CLARIFY_OPTION_BEFORE_PROCEED` off a substring match
  // (`detectVagueProceedSignal`) and a mixed-bookability catalog, which
  // caused the "so i cant order rn if its manual confirmation" failure
  // — the detector matched "confirm" inside "confirmation" and the A0
  // Region-A substitution stamped the options menu over the LLM's
  // contextual answer. The LLM now handles this end-to-end: it reads
  // the option catalog + manual-confirm caveat + customer message and
  // answers naturally. No pre-LLM authority shortcut.

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
    let action: DirectiveAction = "ASK_MISSING_AREAS";
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
        // Zero-distance rebinds (2026-04-21 clarification regression).
        // Forbid symmetric `get_price(pickup=X, dropoff=X)` shapes AND
        // the "Delivery from X to X" recap. Typical trigger: a
        // single-word clarification answer ("mirqab") for a dropoff
        // ambiguity echoed on both legs. The server already has the
        // pinned side in `pendingPickupAreaNameEn` /
        // `pendingDropoffAreaNameEn`; the LLM must not overwrite it.
        "route_price_recap_with_symmetric_areas",
        "get_price_with_symmetric_areas",
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

  // Authority-cutover Phase 6 (2026-04-23): the manual-confirmation
  // selection gate (`isManualConfirmSelection → ASK_*_FOR_MANUAL_CONFIRM
  // / REQUEST_HANDOFF_FOR_MANUAL_CONFIRM`) lived here pre-cutover. It
  // was the upstream companion to the A0a / A0b Region-A substitutions
  // that authored the manual-confirm address asks and handoff reply
  // from `outbound-decision.ts`. Those substitutions were deleted in
  // cutover phases 2 and 3, which left this gate emitting three
  // directive actions that had no render path:
  //
  //   - ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM
  //   - ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM
  //   - REQUEST_HANDOFF_FOR_MANUAL_CONFIRM
  //
  // The LLM now handles manual-confirm end-to-end using hard rule 8 in
  // the system-context block + the `manual_confirmation_required` flag
  // surfaced on the active route's option catalog. The tool-level
  // guard (`getDirectChatBookingBlockReason`) still blocks any rogue
  // `create_simple_order` attempt in this state, so safety is
  // preserved; only the server-side authoring shortcut is gone.

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
    let action: DirectiveAction = "COLLECT_NEXT_MISSING_FIELD";

    // Sequential sender-then-recipient sequencing. When sender is still
    // unresolved, any recipient ask in the same message is forbidden —
    // bundling sender + recipient into one prompt creates ambiguous
    // replies where a single name+phone pair can be silently attributed
    // to the wrong party (see 2026-04-19 19:14 incident and
    // `shared/ambiguous-pair-guard.ts`).
    const senderAskFirst =
      field === "sender.name" || field === "sender.phone";
    if (senderAskFirst) {
      // 2026-04-22 sender-step incident (conv 19399): when the sender
      // phone is already resolved (either via a `use_whatsapp` decision
      // or an explicit write, either path populates draft.senderPhone)
      // but the name is still missing, fall through to the narrow
      // `ASK_SENDER_NAME`. Before this branch, the selector only had
      // "name missing → combined ask" or "name present, phone missing
      // → phone-only ask", so the (phone resolved, name missing) state
      // kept re-emitting the combined ask — leaving the customer with
      // the impression the server had ignored their phone answer. See
      // `directive-reply-registry.ts::renderAskSenderName`.
      if (!draft.senderName && draft.senderPhone) {
        field = "sender.name";
        action = "ASK_SENDER_NAME";
      } else if (!draft.senderName) {
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
//
// Authority-cutover (2026-04-23): this formatter is now the ONLY place the
// turn's prompt is shaped. State FACTS (booking_draft, missing_fields,
// requested_slot, pending_*_area, slot_conflicts, selected_service,
// selected_price, current_conversation_stage) are surfaced verbatim; the
// LLM reads them and decides how to reply. The former state-authoring
// imperatives (`next_required_action`, `forbidden_reply_shapes`,
// `requested_slot_rule`, `pending_area_rule`, `slot_conflicts_rule`, and
// hard rule 10 "your draft is discarded") are gone — there is no longer
// any server-side author that can overwrite the LLM's reply for routine
// collection flow turns, so those imperatives were lying.
export function formatOneBrainLiveChannelContext(params: {
  normalizedReplyTarget: string | null;
  preferredReplyLanguage?: "ar" | "en" | null;
  customerScriptMode?: CustomerScriptMode | null;
  controllerEntry?: PersistedConversationControllerEntry | null;
  quotedRoute?: StoredQuotedRoute | null;
  // Accepted for compatibility with legacy callers; no longer consumed.
  // The clarify-before-proceed gate was deleted from
  // `computeOneBrainNextRequiredAction` and the pre-LLM shaping
  // disposition was removed along with the dropped state-authoring
  // imperatives.
  currentCustomerText?: string | null;
  promptShapingDisposition?: TurnDisposition | null;
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
    // Effective-area resolver (quote → pending → pin-resolved) so the
    // context block agrees with `missing_fields`.
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

    // Dialog State Tracking: surface the requested_slot FACT so the LLM
    // knows which slot the customer is currently answering. This closes
    // the "misroute" class of bug (customer's disambiguation answer
    // written to the wrong slot). The deterministic `apply_booking_field`
    // boundary guards still enforce correct routing; the fact is here so
    // the LLM's baseline accuracy is higher and the guards fire less.
    const requestedSlot = entry?.dialogState?.requestedSlot ?? null;
    if (requestedSlot) {
      lines.push(`requested_slot: ${requestedSlot.name}`);
      if (requestedSlot.options && requestedSlot.options.length > 0) {
        lines.push(
          `requested_slot_options: [${requestedSlot.options.map(formatOneBrainValue).join(", ")}]`,
        );
      }
    }

    // Area-clarification pinning FACTS. The pricing tool persisted one
    // resolved leg as `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn`
    // while asking about the other. The symmetric-rebind guard on
    // `get_price` still catches any attempt to echo the other side;
    // surfacing the pinned value here keeps tool calls clean.
    const pinnedPickup = entry?.pendingPickupAreaNameEn || null;
    const pinnedDropoff = entry?.pendingDropoffAreaNameEn || null;
    if (pinnedPickup) lines.push(`pending_pickup_area: ${pinnedPickup}`);
    if (pinnedDropoff) lines.push(`pending_dropoff_area: ${pinnedDropoff}`);

    // Slot-conflict FACTS. A prior turn's write tried to overwrite a
    // confirmed value with something different; the CONFIRM_SLOT_CONFLICT
    // path in the registry will still deterministically ask the customer
    // to disambiguate when a directive dispatch runs for this case. The
    // facts here give the LLM the context to answer naturally if the
    // customer asks about the conflict first.
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
    }
  }

  lines.push("hard_rules:");
  lines.push("  1. Every price you state must come from a get_price result for the active route this turn or an already-active quoted route above. Never invent, cache, or reuse prices from earlier in the conversation if the route changed.");
  lines.push("  2. The only way to place an order is calling create_simple_order. The server validates the draft, route, service, and price; if it rejects, fix what it asks and try again. Never claim an order was placed without a successful tool result.");
  lines.push("  3. Reply language rule — only two valid reply scripts: (a) if `customer_script_mode` is `arabic`, reply in Arabic script (Kuwaiti White Dialect); (b) if `customer_script_mode` is `english`, reply in English. NEVER reply in Arabizi (Latin letters with digit-for-letter substitutions like 7/9/5/6/3/2) — this is NOT a valid reply style, even if the customer wrote to you in Arabizi. When a customer writes in Arabizi (e.g. `slam 3laikm`, `bkm il tws6eel`, `shlonkm`), understand it and reply in English. If the customer switches between Arabic script and English between turns, switch with them immediately.");
  lines.push("  4. Respond to what the customer means on this turn. Use the facts above as ground truth — prices come only from `get_price` results for the active route, draft values are already written, and the fields still needed appear in `missing_fields`. When the customer advances the booking, call the relevant tools (`apply_booking_field`, `get_price`, `create_simple_order`, `cancel_booking`, `request_handoff`) and ask naturally for whatever's still needed. When they ask a question, answer it. When they correct a prior value, apply the correction via `apply_booking_field` and confirm. When they change the route, call `get_price` with the new route. When they acknowledge, acknowledge back briefly. Keep replies concise and natural. Never state a price that doesn't come from a tool result; never claim an order was placed without a successful `create_simple_order` response.");
  lines.push("  5. Informational option/price questions (e.g. 'what is the cheapest?', 'most expensive option?', 'do you have a van?', 'is there a faster one?', 'how much for express?', 'شنو أرخص خيار؟', 'عندكم باص؟') are ANSWER-ONLY turns. Reply with the direct answer (option name + price, or a short factual yes/no) and stop. Do NOT append the next slot ask (sender name, phone, recipient, address, etc.), do NOT invite the customer to proceed, do NOT attach a 'if you want to book it, send me…' suffix. The customer is evaluating options, not proceeding. Only advance to the next slot ask when the customer's NEXT message contains an explicit proceed signal: 'yes', 'go', 'let's do it', 'book it', 'proceed', 'continue', 'confirm', 'اطلب', 'اكمل', 'نعم', 'تمام خلّيها', 'خذ', 'سكّر', etc.");
  lines.push("  6. Edit turns — when the customer explicitly edits already-filled fields (e.g. 'block 3 to block 4', 'change the street to 10', 'no, make it sedan_fast', 'بدّل الشقة إلى 25') after the summary or during confirmation, treat the new values as the sole source of truth. Acknowledge the update briefly and either re-show the updated summary or ask only for the specific field that is still genuinely ambiguous. Do NOT re-offer the old value as an alternative. Do NOT say 'is it A or B?' listing the pre-edit and post-edit values. The server applies the edit; your job is to confirm it, not to re-litigate it.");
  lines.push("  7. Cancel vs option-switch — NEVER call `cancel_booking` when the same customer utterance also names one of the currently quoted options (e.g. 'nvm pls standard sedan', 'cancel, actually fast box van', 'skip the helper, do sedan instead', 'لا بس مبرد', 'مو مساعد، عادي'). 'nvm', 'never mind', 'forget it', 'skip', 'cancel', 'actually', 'no' paired with a vehicle/option name is an OPTION SWITCH, not a cancellation. In that case, emit an `apply_booking_field` or option-selection update for the named option if applicable, answer the customer by naming the switched-to option + its quoted price, and continue the flow. Only call `cancel_booking` when the customer clearly wants to abandon the booking entirely, with no option-switch wording in the same message ('cancel the booking', 'never mind the whole thing', 'ألغي الطلب').");
  lines.push("  8. Manual-confirmation options — some options in the active route's option catalog require manual confirmation by our team and CANNOT be placed via `create_simple_order` (typically flagged in `optionCatalog` with a direct-chat-booking status like 'manual_confirmation_required'; Helper service and refrigerated-van variants are canonical cases). When the customer selects one of these options: do NOT call `create_simple_order`, do NOT collect sender/recipient identity. Apply address ops normally for pickup + delivery, then call `request_handoff` with a short manual-confirm reason so the Octopus layer transfers the conversation to a human agent. The customer is not booking an instant order; they are handing off to a human for manual scheduling.");
  lines.push("  9. Structured option interpretation — whenever the customer's message in THIS turn names or implies a choice among the currently quoted options (switching, confirming, or asking about a specific one: 'express ref van', 'the cool one', 'helper please', 'خذ المبرد', 'standard sedan بس'), you MUST call the `propose_option_interpretation` tool alongside your reply. Emit the structured reading: `class` ∈ {sedan, van, cooled_van, helper} (null if the customer didn't signal a class), `tier` ∈ {normal, fast} (null if the customer didn't signal a tier), `source_quote` = substring of the customer's inbound text this turn, `confidence` = 'high' when you are confident, 'low' when genuinely ambiguous. This is PROPOSE-ONLY — the server reconciles your structured reading with its own deterministic parse and decides whether to commit or clarify. Do NOT call it on generic booking questions, price asks, or messages that don't name an option. Do NOT mention the tool to the customer.");
  lines.push("  10. structured_output_v1 — every customer turn, call `propose_turn_decision` exactly ONCE, BEFORE you emit your final reply. Fields: `schema_version=\"1.2\"`; `turn_kind` ∈ {initial_route, post_clarify_continuation, informational, address_collection, booking_detail_collection, confirmation_or_cancel, post_order_chat, other}; `pricing_decision.action` ∈ {call_get_price, continue_existing_quote, informational_only, awaiting_state, none} with a one-line `reason`; `planned_tool_calls` is the names of tools you intend to call THIS turn, in order (names only, e.g. [\"get_price\", \"set_pending_area\"]); `customer_reply_draft` is the text you intend to say. Rules: (a) if this turn carries a route intent AND there is no active quoted route, `action` MUST be `call_get_price` AND `\"get_price\"` MUST appear in `planned_tool_calls` AND you MUST actually call `get_price` this turn; (b) on a post_clarify_continuation turn (when `requested_slot` is `pickup_area` or `dropoff_area`, or `pending_pickup_area`/`pending_dropoff_area` is set), `action` MUST be `call_get_price` and `\"get_price\"` MUST appear in `planned_tool_calls`; (c) never call `propose_turn_decision` more than once per turn; (d) the tool is observability-only — it does NOT replace calling `get_price` or any other state tool, and its output is NOT shown to the customer.");
  lines.push("  11. turn_intent classification (v1.2) — when `current_conversation_stage` is `collecting_booking_details`, `summary_shown`, or `awaiting_confirmation`, OR when `requested_slot` is non-null, you MUST include `turn_intent` in your `propose_turn_decision` call. Fields: `turn_intent.kind` ∈ {answered_full, answered_partial, answered_unasked, corrected_prior, clarifying_question, acknowledgement, refused_or_stuck, unclear}, chosen by MEANING not surface words. `turn_intent.addressed_fields` is a CLOSED SET from {sender_name, sender_phone, recipient_name, recipient_phone, pickup_area, dropoff_area, pickup_address, delivery_address, route, option}. Empty array is valid for acknowledgements, pure questions, and refused/unclear turns. `turn_intent.confidence` ∈ {high, medium, low}. `turn_intent.reason` is a ≤200 char rationale. Outside of these stages, OMIT `turn_intent` (or set it to null).");
  lines.push("[/SYSTEM CONTEXT - LIVE CHANNEL]");
  return lines.join("\n");
}
