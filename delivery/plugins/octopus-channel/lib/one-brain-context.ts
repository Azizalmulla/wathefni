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
import { formatCustomerMemoryValue } from "./customer-profile";
import type { StoredQuotedRoute } from "./quoted-options";
import { buildQuotedRouteContextLines } from "./quoted-options";
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
  if (!entry?.quotePickupAreaNameEn) missing.push("pickup.area");
  if (!entry?.quoteDropoffAreaNameEn) missing.push("delivery.area");
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

  if (!entry || entry.quotedPrice == null || !entry.selectedDeliveryType) {
    return null;
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

    if (field === "sender.name" || field === "sender.phone") {
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

    return {
      action,
      field,
      forbiddenShapes: ["standalone_ack", "route_price_recap"],
    };
  }

  return {
    action: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    field: null,
    forbiddenShapes: ["standalone_ack", "route_price_recap", "one_line_confirmation_without_summary"],
  };
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
    const pickup = `pickup: { area: ${formatOneBrainValue(entry?.quotePickupAreaNameEn || null)}, block: ${formatOneBrainValue(draft.pickupBlock)}, street: ${formatOneBrainValue(draft.pickupStreet)}, avenue: ${formatOneBrainValue(draft.pickupAvenue)}, house: ${formatOneBrainValue(draft.pickupHouse)}, extra: ${formatOneBrainValue(draft.pickupExtra)}, pin: ${formatOneBrainValue(pickupPin)} }`;
    const delivery = `delivery: { area: ${formatOneBrainValue(entry?.quoteDropoffAreaNameEn || null)}, block: ${formatOneBrainValue(draft.deliveryBlock)}, street: ${formatOneBrainValue(draft.deliveryStreet)}, avenue: ${formatOneBrainValue(draft.deliveryAvenue)}, house: ${formatOneBrainValue(draft.deliveryHouse)}, extra: ${formatOneBrainValue(draft.deliveryExtra)}, pin: ${formatOneBrainValue(deliveryPin)} }`;
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

    const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
    if (directive) {
      lines.push(`next_required_action: ${directive.action}`);
      if (directive.field) lines.push(`next_field: ${directive.field}`);
      if (directive.forbiddenShapes.length > 0) {
        lines.push(`forbidden_reply_shapes: [${directive.forbiddenShapes.join(", ")}]`);
      }
    }
  }

  lines.push("hard_rules:");
  lines.push("  1. Every price you state must come from a get_price result for the active route this turn or an already-active quoted route above. Never invent, cache, or reuse prices from earlier in the conversation if the route changed.");
  lines.push("  2. The only way to place an order is calling create_simple_order. The server validates the draft, route, service, and price; if it rejects, fix what it asks and try again. Never claim an order was placed without a successful tool result.");
  lines.push("  3. Reply in the customer's current language AND script. If `customer_script_mode` is `arabizi`, reply in Kuwaiti Arabizi (Latin letters + digit-for-letter substitutions like 7/9/5/6/3/2) — NOT Arabic script. If `arabic`, reply in Arabic script (Kuwaiti White Dialect). If `english`, reply in English. If the customer switches mode between turns, switch with them immediately.");
  lines.push("  4. Every reply must move the conversation forward. Never emit a standalone acknowledgement like 'Sure', 'Noted', 'Understood', or 'We'll proceed' without also taking the next concrete action in the same message (ask for the next missing field, show the summary, confirm, etc.).");

  lines.push("[/SYSTEM CONTEXT - LIVE CHANNEL]");
  return lines.join("\n");
}
