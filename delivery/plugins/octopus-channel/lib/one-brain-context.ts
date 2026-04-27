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
import type { BookingTruthSnapshot } from "../../shared/booking-truth-snapshot";

const PENDING_ORDER_EDIT_TTL_MS = 15 * 60 * 1000;

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

function addressSatisfiedBy(
  draft: PersistedBookingDraft,
  kind: "pickup" | "delivery",
): "pin" | "house" | "extra" | null {
  const pin = kind === "pickup" ? draft.pickupLocation : draft.deliveryLocation;
  if (formatPersistedBookingLocationLabel(pin)) return "pin";
  if (!hasSatisfiedBookingAddress(draft, kind)) return null;
  const house = kind === "pickup" ? draft.pickupHouse : draft.deliveryHouse;
  if (house) return "house";
  const extra = kind === "pickup" ? draft.pickupExtra : draft.deliveryExtra;
  if (extra) return "extra";
  return null;
}

function formatAddressSatisfactionLine(
  draft: PersistedBookingDraft,
  kind: "pickup" | "delivery",
): string {
  const satisfied = hasSatisfiedBookingAddress(draft, kind);
  const satisfiedBy = addressSatisfiedBy(draft, kind);
  const missing = diagnoseBookingAddressMissing(draft, kind);
  return `${kind}_address_satisfied=${satisfied ? "true" : "false"} ${kind}_address_satisfied_by=${satisfiedBy ?? "null"} ${kind}_missing_subfields=[${missing.join(", ")}]`;
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
  bookingTruthSnapshot?: BookingTruthSnapshot | null;
  coveragePending?: any | null;
  snapshotContextOnly?: boolean;
  // Accepted for compatibility with legacy callers; no longer consumed.
  // The clarify-before-proceed gate was deleted from
  // `computeOneBrainNextRequiredAction` and the pre-LLM shaping
  // disposition was removed along with the dropped state-authoring
  // imperatives.
  currentCustomerText?: string | null;
  promptShapingDisposition?: TurnDisposition | null;
}): string {
  const truth = params.bookingTruthSnapshot ?? null;
  const snapshotOnly = Boolean(params.snapshotContextOnly && truth);
  const entry = snapshotOnly ? truth?.controllerState ?? null : params.controllerEntry || null;
  const draft = snapshotOnly ? truth?.draft ?? null : entry?.bookingDraft || null;
  const quotedRoute = snapshotOnly
    ? ((truth?.quote.activeQuotedRoute as StoredQuotedRoute | null) ?? null)
    : ((truth?.quote.activeQuotedRoute as StoredQuotedRoute | null) ?? params.quotedRoute ?? null);
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

  if (quotedRoute) {
    lines.push(...buildQuotedRouteContextLines(quotedRoute, entry));
  }

  const coveragePending = snapshotOnly
    ? truth?.coveragePending ?? null
    : truth?.coveragePending ?? params.coveragePending ?? null;
  if (coveragePending && typeof coveragePending === "object") {
    const pending = coveragePending as any;
    const pendingKind = String(pending.kind || "").trim();
    if (pendingKind) {
      lines.push(`coverage_pending_kind: ${pendingKind}`);
      if (pendingKind === "covered_area_candidate") {
        const candidateArea =
          pending.area?.canonical_en ||
          pending.area?.canonical_ar ||
          pending.original_query ||
          null;
        lines.push(`coverage_pending_area_candidate: ${formatOneBrainValue(candidateArea)}`);
        lines.push(`coverage_pending_original_query: ${formatOneBrainValue(pending.original_query || null)}`);
        lines.push(
          "Coverage pending fact: the previous coverage check resolved this area. If the customer confirms it as pickup/delivery or gives the other route leg, treat this as the local route candidate and call `get_price` with the two distinct areas instead of asking broadly or doing a global search.",
        );
      } else if (pendingKind === "needs_area_for_place") {
        lines.push(`coverage_pending_place: ${formatOneBrainValue(pending.place_canonical_en || pending.place_query || null)}`);
        lines.push(
          "Coverage pending fact: the previous coverage result needed the area for this place/landmark. If this customer message is an area answer, call `check_area_coverage` with the customer's current message so the tool can resolve the pending place context.",
        );
      } else if (pendingKind === "ambiguous_area") {
        const options = Array.isArray(pending.options)
          ? pending.options
              .map((option: any) => option?.canonical_en)
              .filter(Boolean)
              .map(formatOneBrainValue)
              .join(", ")
          : "";
        lines.push(`coverage_pending_original_query: ${formatOneBrainValue(pending.original_query || null)}`);
        if (options) lines.push(`coverage_pending_options: [${options}]`);
        lines.push(
          "Coverage pending fact: the previous coverage result was ambiguous. If this customer message is a short option answer, call `check_area_coverage` with the customer's current message so the tool can resolve it against those options.",
        );
      } else if (pendingKind === "unsupported_area") {
        const nearby = Array.isArray(pending.nearby_covered)
          ? pending.nearby_covered
              .map((option: any) => option?.canonical_en)
              .filter(Boolean)
              .map(formatOneBrainValue)
              .join(", ")
          : "";
        lines.push(`coverage_pending_unsupported_query: ${formatOneBrainValue(pending.original_query || null)}`);
        lines.push(`coverage_pending_nearby_covered: [${nearby}]`);
        lines.push(
          "Coverage pending fact: the previous area was not covered. Only offer nearby covered areas if `coverage_pending_nearby_covered` is non-empty. If it is empty, say you do not have a nearby covered suggestion instead of inventing one.",
        );
      }
    }
  }

  const currentStage = snapshotOnly ? truth?.stage ?? null : entry?.stage ?? truth?.stage ?? null;
  if (currentStage) {
    lines.push(`current_conversation_stage: ${currentStage}`);
  }
  if (truth) {
    lines.push(`route_lock_status: ${truth.route.lockStatus}`);
    lines.push(
      `route_pickup_resolution: status=${truth.route.pickup.status} area=${formatOneBrainValue(truth.route.pickup.nameEn)} area_id=${formatOneBrainValue(truth.route.pickup.areaId == null ? null : String(truth.route.pickup.areaId))}`,
    );
    lines.push(
      `route_dropoff_resolution: status=${truth.route.dropoff.status} area=${formatOneBrainValue(truth.route.dropoff.nameEn)} area_id=${formatOneBrainValue(truth.route.dropoff.areaId == null ? null : String(truth.route.dropoff.areaId))}`,
    );
    const pendingRouteOptions = [
      ...truth.route.pickup.options.map((option) => option.nameEn || option.nameAr).filter(Boolean),
      ...truth.route.dropoff.options.map((option) => option.nameEn || option.nameAr).filter(Boolean),
    ];
    if (pendingRouteOptions.length > 0) {
      lines.push(
        `route_pending_options: [${pendingRouteOptions.map(formatOneBrainValue).join(", ")}]`,
      );
    }
    if (truth.pendingRouteAmbiguity) {
      const pending = truth.pendingRouteAmbiguity;
      lines.push(
        `pending_route_ambiguity: side=${pending.side} status=${pending.status} field=${pending.field}`,
      );
    }
    lines.push(`summary_ready: ${truth.summary.ready ? "true" : "false"}`);
    lines.push(`order_ready: ${truth.order.ready ? "true" : "false"}`);
    lines.push(`next_action: ${truth.nextAction.type}`);
    lines.push(`next_action_reason: ${truth.nextAction.reason}`);
    if (truth.nextAction.type === "collect_missing_field") {
      lines.push(`next_action_field: ${truth.nextAction.field}`);
    } else if (truth.nextAction.type === "resolve_route_ambiguity") {
      lines.push(`next_action_field: ${truth.nextAction.field}`);
      lines.push(
        `next_action_options: [${truth.nextAction.options
          .map((option) => option.nameEn || option.nameAr)
          .filter(Boolean)
          .map(formatOneBrainValue)
          .join(", ")}]`,
      );
    }
  }
  if (truth?.order.submitted && truth.order.submittedOrderUid) {
    lines.push(`submitted_order_uid: ${formatOneBrainValue(truth.order.submittedOrderUid)}`);
  } else if (!snapshotOnly && entry?.stage === "order_submitted" && entry.submittedOrderUid) {
    lines.push(`submitted_order_uid: ${formatOneBrainValue(entry.submittedOrderUid)}`);
  }

  if (draft) {
    const sender = `sender: { name: ${formatOneBrainValue(draft.senderName)}, phone: ${formatOneBrainValue(draft.senderPhone)} }`;
    const recipient = `recipient: { name: ${formatOneBrainValue(draft.recipientName)}, phone: ${formatOneBrainValue(draft.recipientPhone)} }`;
    const pickupPin = formatPersistedBookingLocationLabel(draft.pickupLocation);
    const deliveryPin = formatPersistedBookingLocationLabel(draft.deliveryLocation);
    // Effective-area resolver (quote → pending → pin-resolved) so the
    // context block agrees with `missing_fields`.
    const effectivePickupArea = snapshotOnly
      ? truth?.route.pickup.nameEn ?? null
      : getEffectivePickupAreaName(draft, entry);
    const effectiveDeliveryArea = snapshotOnly
      ? truth?.route.dropoff.nameEn ?? null
      : getEffectiveDeliveryAreaName(draft, entry);
    const pickup = `pickup: { area: ${formatOneBrainValue(effectivePickupArea)}, block: ${formatOneBrainValue(draft.pickupBlock)}, street: ${formatOneBrainValue(draft.pickupStreet)}, avenue: ${formatOneBrainValue(draft.pickupAvenue)}, house: ${formatOneBrainValue(draft.pickupHouse)}, extra: ${formatOneBrainValue(draft.pickupExtra)}, pin: ${formatOneBrainValue(pickupPin)} }`;
    const delivery = `delivery: { area: ${formatOneBrainValue(effectiveDeliveryArea)}, block: ${formatOneBrainValue(draft.deliveryBlock)}, street: ${formatOneBrainValue(draft.deliveryStreet)}, avenue: ${formatOneBrainValue(draft.deliveryAvenue)}, house: ${formatOneBrainValue(draft.deliveryHouse)}, extra: ${formatOneBrainValue(draft.deliveryExtra)}, pin: ${formatOneBrainValue(deliveryPin)} }`;
    lines.push("booking_draft:");
    lines.push(`  ${sender}`);
    lines.push(`  ${recipient}`);
    lines.push(`  ${pickup}`);
    lines.push(`  ${delivery}`);
    lines.push("address_satisfaction:");
    if (snapshotOnly && truth) {
      lines.push(`  pickup_address_satisfied=${truth.addressSatisfaction.pickup ? "true" : "false"}`);
      lines.push(`  delivery_address_satisfied=${truth.addressSatisfaction.delivery ? "true" : "false"}`);
    } else {
      lines.push(`  ${formatAddressSatisfactionLine(draft, "pickup")}`);
      lines.push(`  ${formatAddressSatisfactionLine(draft, "delivery")}`);
    }
    const pendingPin = formatPersistedBookingLocationLabel(draft.pendingLocation);
    if (pendingPin) {
      lines.push(`pending_shared_location: ${pendingPin}`);
    }
    const selectedType =
      truth?.quote.selected.deliveryType ||
      (snapshotOnly ? null : entry?.selectedDeliveryType) ||
      null;
    const selectedPrice =
      truth?.quote.selected.formattedPrice ||
      (!snapshotOnly && entry?.quotedPrice != null ? `${entry.quotedPrice.toFixed(3)} KWD` : null);
    if (selectedType || selectedPrice) {
      lines.push(`selected_service: ${formatOneBrainValue(selectedType)}`);
      lines.push(`selected_price: ${formatOneBrainValue(selectedPrice)}`);
    }
    const missing = snapshotOnly
      ? truth?.missingFields ?? []
      : computeOneBrainMissingFields(draft, entry);
    lines.push(`missing_fields: [${missing.join(", ")}]`);
    if (truth?.nextMissingField) {
      lines.push(`next_missing_field: ${truth.nextMissingField}`);
    }

    // Dialog State Tracking: surface the requested_slot FACT so the LLM
    // knows which slot the customer is currently answering. This closes
    // the "misroute" class of bug (customer's disambiguation answer
    // written to the wrong slot). The deterministic `apply_booking_field`
    // boundary guards still enforce correct routing; the fact is here so
    // the LLM's baseline accuracy is higher and the guards fire less.
    const requestedSlot = snapshotOnly
      ? truth?.nextAction.type === "resolve_route_ambiguity" ||
        truth?.nextAction.type === "resolve_slot_conflict"
        ? truth?.requestedSlot ?? null
        : null
      : truth?.requestedSlot ?? entry?.dialogState?.requestedSlot ?? null;
    if (requestedSlot) {
      lines.push(`requested_slot: ${requestedSlot.name}`);
      if (requestedSlot.options && requestedSlot.options.length > 0) {
        lines.push(
          `requested_slot_options: [${requestedSlot.options.map(formatOneBrainValue).join(", ")}]`,
        );
      }
    }
    const rawPendingOrderEdits = snapshotOnly ? null : entry?.pendingOrderEdits ?? null;
    const pendingOrderEdits = snapshotOnly
      ? truth?.pendingOrderEdits ?? null
      : rawPendingOrderEdits &&
          Date.now() - Number(rawPendingOrderEdits.askedTs || 0) <= PENDING_ORDER_EDIT_TTL_MS
        ? rawPendingOrderEdits
        : null;
    if (
      pendingOrderEdits &&
      Array.isArray(pendingOrderEdits.fields) &&
      pendingOrderEdits.fields.length > 0
    ) {
      lines.push(`pending_order_edits: [${pendingOrderEdits.fields.join(", ")}]`);
      if (pendingOrderEdits.sourceQuote) {
        lines.push(
          `pending_order_edits_source: ${formatOneBrainValue(pendingOrderEdits.sourceQuote)}`,
        );
      }
    }

    // Area-clarification pinning FACTS. The pricing tool persisted one
    // resolved leg as `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn`
    // while asking about the other. The symmetric-rebind guard on
    // `get_price` still catches any attempt to echo the other side;
    // surfacing the pinned value here keeps tool calls clean.
    if (!snapshotOnly) {
      const pinnedPickup = entry?.pendingPickupAreaNameEn || null;
      const pinnedDropoff = entry?.pendingDropoffAreaNameEn || null;
      if (pinnedPickup) lines.push(`pending_pickup_area: ${pinnedPickup}`);
      if (pinnedDropoff) lines.push(`pending_dropoff_area: ${pinnedDropoff}`);
    }

    // Slot-conflict FACTS. A prior turn's write tried to overwrite a
    // confirmed value with something different; the CONFIRM_SLOT_CONFLICT
    // path in the registry will still deterministically ask the customer
    // to disambiguate when a directive dispatch runs for this case. The
    // facts here give the LLM the context to answer naturally if the
    // customer asks about the conflict first.
    const conflicts = snapshotOnly
      ? (truth?.slotConflicts ?? []).map(
          (record) =>
            `${record.field}: kept="${record.value ?? ""}" proposed="${record.conflictCandidate ?? ""}"`,
        )
      : (() => {
          const slots = entry?.dialogState?.slots ?? {};
          const out: string[] = [];
          for (const [name, record] of Object.entries(slots)) {
            if (record && record.status === "conflict") {
              out.push(
                `${name}: kept="${record.value}" proposed="${record.conflictCandidate ?? ""}"`,
              );
            }
          }
          return out;
        })();
    if (conflicts.length > 0) {
      lines.push(`slot_conflicts: [${conflicts.join("; ")}]`);
    }
  }

  // 2026-04-23 rule-budget audit: hard_rules block was ~6.4K chars (~1.8K
  // tokens) per turn, dominated by duplication with tool schemas and
  // long example lists. Trimmed to ~3.8K chars (~1.1K tokens). Safety-
  // critical rules (price integrity, order placement, cancel-vs-switch,
  // manual-confirm) are preserved; tool-protocol rules (9/10/11) delegate
  // to the tool `description` / schema which the LLM already sees. Canary
  // anchors `structured_output_v1` and `propose_turn_decision` preserved.
  lines.push("hard_rules:");
  lines.push("  1. Every price you state must come from a `get_price` tool result for the active route this turn, or from an already-active quoted route shown above. Every specific coverage answer ('do you deliver to X?' / 'توصلون لي X؟'), including landmarks/malls like The Avenues / افنيوز / 360 and short coverage follow-ups to a pending coverage clarification, must come from `check_area_coverage` before you answer. Never invent, cache, or reuse prices or coverage from memory.");
  lines.push("  2. Only `create_simple_order` can place an order. Never claim an order was placed without a successful tool result. If the server rejects, fix what it asks and retry.");
  lines.push("  3. Language: reply in Arabic script (Kuwaiti White Dialect) when `customer_script_mode` is `arabic`, and in English when it is `english`. NEVER reply in Arabizi (Latin + digits like 7/9/6/3) — if the customer writes Arabizi (e.g. `shlonkm`), understand it but reply in English. Switch scripts when the customer switches.");
  lines.push("  4. Respond to what the customer means this turn. The facts above are ground truth — prices come only from `get_price`, draft values are already written, and `missing_fields` is authoritative for what's left. Address satisfaction facts override raw null fields: if `pickup_address_satisfied=true` or `delivery_address_satisfied=true`, do not ask for any more sub-fields on that side even if `house` is null. Call tools when action is needed; otherwise answer, acknowledge, or ask naturally. Keep replies concise.");
  lines.push("  5. Short customer questions are MEANING questions — answer the likely intent, not the literal surface. 'only standard?' on a multi-option quote = 'is standard my only choice?' → name the real other options + prices, don't just repeat the standard price. 'do u deliver to zoor?' with no active route = 'do you cover Zoor, what's the cost?' → direct yes/no tied to that specific place (not a generic 'we cover Kuwait' blurb), then one helpful next step (e.g. 'what's the pickup area so I can quote?'). Shape: direct yes/no or the specific fact, one short useful detail, and ONE helpful next-step offer ONLY when it advances the customer's goal. Don't robotically advance the slot ladder mid-flow — if the customer asks a side question while a booking is being collected, answer the question and stop; don't append the next missing-field ask just because the field is missing. Advance booking slots only when the customer's NEXT message proceeds explicitly ('yes', 'book it', 'اطلب', 'اكمل').");
  lines.push("  6. Edits after the summary or during confirmation ('block 3 to block 4', 'make it sedan_fast', 'بدّل الشقة إلى 25') are the new source of truth. Acknowledge the update and re-show the updated summary or ask only for a field that is still genuinely ambiguous. If you ask the customer to send updated values for more than one field, first call `set_pending_order_edits` with exactly those fields. Do NOT create an expectation the controller cannot track.");
  lines.push("  7. Cancel vs option-switch: 'nvm' / 'cancel' / 'actually' / 'no' paired with a named option ('nvm standard sedan', 'cancel, actually fast van', 'لا بس مبرد') is an OPTION SWITCH, not a cancellation. Switch the option and continue — do NOT call `cancel_booking`. Only call `cancel_booking` when the customer clearly wants to abandon the whole booking ('cancel the booking', 'ألغي الطلب').");
  lines.push("  8. Manual-confirmation options in the route's `optionCatalog` (Helper, refrigerated-van variants, anything flagged `manual_confirmation_required`) cannot be placed via `create_simple_order`. When the customer selects one: apply the pickup/delivery addresses normally, skip sender/recipient identity collection, and call `request_handoff` with a short manual-confirm reason so Octopus transfers to a human.");
  lines.push("  9. When the customer's message names or implies one of the currently quoted options, call `propose_option_interpretation` alongside your reply (the tool description defines its fields). Don't call it on generic booking/price questions, and don't mention it to the customer.");
  lines.push("  10. structured_output_v1 — call `propose_turn_decision` exactly ONCE per customer turn, BEFORE your reply (the tool schema defines the fields). Additional prompt-level obligation: if this turn carries a route intent with no active quoted route, OR it is a post-clarify continuation (`requested_slot` is `pickup_area`/`dropoff_area`, or `pending_pickup_area`/`pending_dropoff_area` is set), then `planned_tool_calls` MUST include `get_price` AND you MUST actually call `get_price` this turn. The tool is observability-only — its output is not shown to the customer.");
  lines.push("  11. Include `turn_intent` in your `propose_turn_decision` call whenever `current_conversation_stage` is `collecting_booking_details` / `summary_shown` / `awaiting_confirmation`, or `requested_slot` is non-null. The tool schema defines its fields; classify by MEANING, not surface words. Otherwise omit it.");
  lines.push("  12. Riders-scope boundary: you are NOT a general chatbot. If the customer asks an unrelated public-world/general-knowledge question (politics, celebrities, sports, news, weather, medical/legal advice, homework, trivia, or web/current-events facts), do not answer the factual question and do not cite sources or external links. Briefly say you can help with Riders deliveries, prices, coverage, tracking, complaints, and order support, then ask what delivery help they need. External links are allowed only when they are official Riders links or tool-confirmed order/payment/tracking links.");
  lines.push("[/SYSTEM CONTEXT - LIVE CHANNEL]");
  return lines.join("\n");
}
