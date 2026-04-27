import type {
  ConversationFlowStage,
  PersistedConversationControllerEntry,
} from "./conversation-policy.js";
import type { DialogState } from "./dialog-state.js";
import type { PersistedGuardSessionState } from "./guard-state.js";
import { looksLikeConfirmation, type OrderGuardResult } from "./order-guard.js";
import type { BookingTruthSnapshot } from "./booking-truth-snapshot.js";

const PENDING_ORDER_EDIT_TTL_MS = 15 * 60 * 1000;

export type BookingLifecycleTargetStage =
  | "quoted"
  | "collecting_booking_details"
  | "summary_shown"
  | "awaiting_confirmation"
  | "order_submitted";

export type BookingLifecycleBlockingReason =
  | "route_not_canonical"
  | "quote_missing"
  | "quote_route_mismatch"
  | "selected_service_missing"
  | "selected_service_not_quoted"
  | "price_missing"
  | "price_mismatch"
  | "route_clarification_pending"
  | "coverage_clarification_pending"
  | "missing_fields"
  | "pending_order_edits"
  | "slot_conflict"
  | "summary_not_ready"
  | "confirmation_missing"
  | "order_guard_failed"
  | "transaction_artifact_missing";

export type BookingLifecycleRequiredNextAction =
  | { type: "resolve_pickup_area"; field: "pickup_area"; details?: Record<string, unknown> }
  | { type: "resolve_dropoff_area"; field: "dropoff_area"; details?: Record<string, unknown> }
  | { type: "resolve_route_clarification"; field?: "pickup_area" | "dropoff_area"; details?: Record<string, unknown> }
  | { type: "resolve_coverage_clarification"; details?: Record<string, unknown> }
  | { type: "reprice_route"; details?: Record<string, unknown> }
  | { type: "collect_missing_fields"; details?: Record<string, unknown> }
  | { type: "resolve_slot_conflict"; field?: string; details?: Record<string, unknown> }
  | { type: "resolve_pending_edit"; details?: Record<string, unknown> }
  | { type: "show_summary"; details?: Record<string, unknown> }
  | { type: "wait_for_confirmation"; details?: Record<string, unknown> }
  | { type: "retry_order_with_guard"; details?: Record<string, unknown> }
  | { type: "prepare_transaction_artifact"; details?: Record<string, unknown> };

export type BookingLifecycleDecision =
  | {
      decision: "allow";
      targetStage: BookingLifecycleTargetStage;
      preserveDraft: true;
    }
  | {
      decision: "block";
      targetStage: BookingLifecycleTargetStage;
      blockingReason: BookingLifecycleBlockingReason;
      requiredNextAction: BookingLifecycleRequiredNextAction;
      preserveDraft: true;
    };

export type BookingLifecycleAreaAudit = {
  status:
    | "canonical"
    | "exact_confirmed"
    | "suggested_unconfirmed"
    | "ambiguous"
    | "unresolved"
    | "missing"
    | "unknown";
  areaId?: number | string | null;
  nameEn?: string | null;
};

export type BookingLifecycleRouteAudit = {
  pickup?: BookingLifecycleAreaAudit | null;
  dropoff?: BookingLifecycleAreaAudit | null;
  quoteMatchesCanonicalRoute?: boolean | null;
  selectedServiceInQuote?: boolean | null;
  priceMatchesQuote?: boolean | null;
};

export type BookingLifecycleCurrentTurnToolResults = {
  missingFields?: string[] | null;
  orderCreatedUid?: string | null;
  confirmationExplicit?: boolean | null;
};

export type CanAdvanceBookingFlowInput = {
  controllerState: PersistedConversationControllerEntry | null;
  sessionGuard?: PersistedGuardSessionState | null;
  dialogState?: DialogState | null;
  currentCustomerText?: string | null;
  currentTurnToolResults?: BookingLifecycleCurrentTurnToolResults | null;
  routeAudit?: BookingLifecycleRouteAudit | null;
  bookingTruthSnapshot?: BookingTruthSnapshot | null;
  orderGuardResult?: OrderGuardResult | null;
  now?: number;
};

export type BookingLifecycleLogPayload = {
  event: "booking_lifecycle_gate";
  enabled: boolean;
  targetStage: BookingLifecycleTargetStage;
  decision: BookingLifecycleDecision["decision"];
  blockingReason: BookingLifecycleBlockingReason | null;
  requiredNextAction: string | null;
  requiredNextActionField: string | null;
  preserveDraft: boolean;
  routeAudit: {
    pickupStatus: BookingLifecycleAreaAudit["status"] | null;
    dropoffStatus: BookingLifecycleAreaAudit["status"] | null;
    selectedServiceInQuote: boolean | null;
    priceMatchesQuote: boolean | null;
    quoteMatchesCanonicalRoute: boolean | null;
  };
  requestedSlot: string | null;
  requestedSlotOptionsCount: number;
  pendingOrderEditsActive: boolean;
  missingFieldsCount: number | null;
  orderGuardResult: { ok: true } | { ok: false; code: string } | null;
};

export function shouldPreserveDraftOnQuotePromotion(input: {
  controllerState: PersistedConversationControllerEntry | null;
  turnAppliedBookingProgress?: boolean;
}): boolean {
  const entry = input.controllerState;
  return Boolean(
    input.turnAppliedBookingProgress ||
      entry?.stage === "summary_shown" ||
      entry?.stage === "awaiting_confirmation" ||
      entry?.bookingStep === "summary_pending" ||
      entry?.bookingStep === "awaiting_summary_confirmation",
  );
}

export function buildBookingLifecycleLogPayload(input: {
  decision: BookingLifecycleDecision;
  gateInput: CanAdvanceBookingFlowInput;
  enabled?: boolean;
}): BookingLifecycleLogPayload {
  const dialogState = activeDialogState(input.gateInput);
  const requestedSlot = dialogState?.requestedSlot ?? null;
  const requestedSlotOptionsCount = Array.isArray(requestedSlot?.options)
    ? requestedSlot.options.length
    : 0;
  const now = input.gateInput.now ?? Date.now();
  const orderGuardResult = input.gateInput.orderGuardResult
    ? input.gateInput.orderGuardResult.ok
      ? { ok: true as const }
      : { ok: false as const, code: input.gateInput.orderGuardResult.code }
    : null;
  return {
    event: "booking_lifecycle_gate",
    enabled: input.enabled !== false,
    targetStage: input.decision.targetStage,
    decision: input.decision.decision,
    blockingReason:
      input.decision.decision === "block" ? input.decision.blockingReason : null,
    requiredNextAction:
      input.decision.decision === "block"
        ? input.decision.requiredNextAction.type
        : null,
    requiredNextActionField:
      input.decision.decision === "block" &&
      "field" in input.decision.requiredNextAction
        ? input.decision.requiredNextAction.field ?? null
        : null,
    preserveDraft: input.decision.preserveDraft,
    routeAudit: {
      pickupStatus: input.gateInput.routeAudit?.pickup?.status ?? null,
      dropoffStatus: input.gateInput.routeAudit?.dropoff?.status ?? null,
      selectedServiceInQuote:
        input.gateInput.routeAudit?.selectedServiceInQuote ?? null,
      priceMatchesQuote: input.gateInput.routeAudit?.priceMatchesQuote ?? null,
      quoteMatchesCanonicalRoute:
        input.gateInput.routeAudit?.quoteMatchesCanonicalRoute ?? null,
    },
    requestedSlot: requestedSlot?.name ?? null,
    requestedSlotOptionsCount,
    pendingOrderEditsActive: hasActivePendingOrderEdits(
      input.gateInput.controllerState,
      now,
    ),
    missingFieldsCount: Array.isArray(
      input.gateInput.currentTurnToolResults?.missingFields ??
        input.gateInput.bookingTruthSnapshot?.missingFields,
    )
      ? (
          input.gateInput.currentTurnToolResults?.missingFields ??
          input.gateInput.bookingTruthSnapshot?.missingFields ??
          []
        ).length
      : null,
    orderGuardResult,
  };
}

function allow(targetStage: BookingLifecycleTargetStage): BookingLifecycleDecision {
  return {
    decision: "allow",
    targetStage,
    preserveDraft: true,
  };
}

function block(
  targetStage: BookingLifecycleTargetStage,
  blockingReason: BookingLifecycleBlockingReason,
  requiredNextAction: BookingLifecycleRequiredNextAction,
): BookingLifecycleDecision {
  return {
    decision: "block",
    targetStage,
    blockingReason,
    requiredNextAction,
    preserveDraft: true,
  };
}

function activeDialogState(input: CanAdvanceBookingFlowInput): DialogState | null {
  return input.bookingTruthSnapshot?.dialogState ?? input.dialogState ?? input.controllerState?.dialogState ?? null;
}

function routeSideFromSlot(
  slot: string | null | undefined,
): "pickup_area" | "dropoff_area" | null {
  if (slot === "pickup_area") return "pickup_area";
  if (slot === "dropoff_area") return "dropoff_area";
  return null;
}

function hasOpenRouteSideRequestedSlot(input: CanAdvanceBookingFlowInput): {
  open: boolean;
  side: "pickup_area" | "dropoff_area" | null;
  options: string[];
} {
  const requestedSlot = activeDialogState(input)?.requestedSlot ?? null;
  const side = routeSideFromSlot(requestedSlot?.name);
  const options = Array.isArray(requestedSlot?.options)
    ? requestedSlot.options.filter((option) => String(option || "").trim())
    : [];
  return {
    open: Boolean(side),
    side,
    options,
  };
}

function findOpenConflict(input: CanAdvanceBookingFlowInput): string | null {
  const slots = activeDialogState(input)?.slots ?? {};
  for (const [name, record] of Object.entries(slots)) {
    if (record && record.status === "conflict") {
      return name;
    }
  }
  return null;
}

function hasActivePendingOrderEdits(
  entry: PersistedConversationControllerEntry | null,
  now: number,
): boolean {
  const pending = entry?.pendingOrderEdits ?? null;
  if (!pending || !Array.isArray(pending.fields) || pending.fields.length === 0) {
    return false;
  }
  return now - Number(pending.askedTs || 0) <= PENDING_ORDER_EDIT_TTL_MS;
}

function pricesMatch(left: number | null | undefined, right: number | null | undefined): boolean {
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  return Math.abs(Number(left) - Number(right)) < 0.001;
}

function quoteRouteMatchesEntry(
  entry: PersistedConversationControllerEntry,
  session: PersistedGuardSessionState | null | undefined,
): boolean {
  const quote = session?.lastQuotedRoute ?? null;
  if (!quote) return false;
  return (
    String(entry.quoteRouteKey || "") === String(quote.routeKey || "") &&
    String(entry.quotePickupAreaNameEn || "").trim().toLowerCase() ===
      String(quote.pickupAreaNameEn || "").trim().toLowerCase() &&
    String(entry.quoteDropoffAreaNameEn || "").trim().toLowerCase() ===
      String(quote.dropoffAreaNameEn || "").trim().toLowerCase()
  );
}

function selectedServiceIsQuoted(
  entry: PersistedConversationControllerEntry,
  session: PersistedGuardSessionState | null | undefined,
): boolean {
  const service = String(entry.selectedDeliveryType || "").trim();
  if (!service) return false;
  const quote = session?.lastQuotedRoute ?? null;
  if (!quote) return false;
  return quote.pricesByType?.[service] != null;
}

function selectedPriceMatchesQuote(
  entry: PersistedConversationControllerEntry,
  session: PersistedGuardSessionState | null | undefined,
): boolean {
  const service = String(entry.selectedDeliveryType || "").trim();
  const quotePrice = service ? session?.lastQuotedRoute?.pricesByType?.[service] : null;
  return pricesMatch(entry.quotedPrice, quotePrice);
}

export function buildBookingLifecycleRouteAudit(input: {
  controllerState: PersistedConversationControllerEntry | null;
  sessionGuard?: PersistedGuardSessionState | null;
  bookingTruthSnapshot?: BookingTruthSnapshot | null;
}): BookingLifecycleRouteAudit {
  if (input.bookingTruthSnapshot) {
    const truth = input.bookingTruthSnapshot;
    return {
      pickup: truth.route.pickup,
      dropoff: truth.route.dropoff,
      quoteMatchesCanonicalRoute: truth.route.quoteMatchesCanonicalRoute,
      selectedServiceInQuote: truth.quote.selectedServiceInQuote,
      priceMatchesQuote: truth.quote.selectedPriceMatchesQuote,
    };
  }
  const entry = input.controllerState;
  const quote = input.sessionGuard?.lastQuotedRoute ?? null;
  const pickupName =
    entry?.quotePickupAreaNameEn ||
    entry?.pendingPickupAreaNameEn ||
    quote?.pickupAreaNameEn ||
    null;
  const dropoffName =
    entry?.quoteDropoffAreaNameEn ||
    entry?.pendingDropoffAreaNameEn ||
    quote?.dropoffAreaNameEn ||
    null;
  const pickupResolution =
    quote?.pickupAreaResolution ||
    entry?.quotePickupAreaResolution ||
    entry?.pendingPickupAreaResolution ||
    null;
  const dropoffResolution =
    quote?.dropoffAreaResolution ||
    entry?.quoteDropoffAreaResolution ||
    entry?.pendingDropoffAreaResolution ||
    null;
  const selectedService = String(entry?.selectedDeliveryType || "").trim();
  const quotedPriceForService =
    selectedService && quote?.pricesByType
      ? quote.pricesByType[selectedService]
      : null;
  return {
    pickup: pickupResolution
      ? {
          status: pickupResolution.status as BookingLifecycleAreaAudit["status"],
          areaId: pickupResolution.areaId ?? null,
          nameEn: pickupResolution.nameEn ?? pickupName,
        }
      : pickupName
        ? { status: "canonical", nameEn: pickupName }
        : { status: "missing" },
    dropoff: dropoffResolution
      ? {
          status: dropoffResolution.status as BookingLifecycleAreaAudit["status"],
          areaId: dropoffResolution.areaId ?? null,
          nameEn: dropoffResolution.nameEn ?? dropoffName,
        }
      : dropoffName
        ? { status: "canonical", nameEn: dropoffName }
        : { status: "missing" },
    quoteMatchesCanonicalRoute:
      entry && quote
        ? quoteRouteMatchesEntry(entry, input.sessionGuard)
        : null,
    selectedServiceInQuote:
      entry && quote && selectedService
        ? selectedServiceIsQuoted(entry, input.sessionGuard)
        : null,
    priceMatchesQuote:
      entry && quote && selectedService && quotedPriceForService != null
        ? selectedPriceMatchesQuote(entry, input.sessionGuard)
        : null,
  };
}

function routeAuditBlocks(
  targetStage: BookingLifecycleTargetStage,
  routeAudit: BookingLifecycleRouteAudit | null | undefined,
): BookingLifecycleDecision | null {
  if (!routeAudit) return null;
  const pickupStatus = routeAudit?.pickup?.status ?? "unknown";
  if (
    pickupStatus === "ambiguous" ||
    pickupStatus === "suggested_unconfirmed" ||
    pickupStatus === "unresolved" ||
    pickupStatus === "missing" ||
    pickupStatus === "unknown"
  ) {
    return block(targetStage, "route_not_canonical", {
      type: "resolve_pickup_area",
      field: "pickup_area",
      details: { status: pickupStatus },
    });
  }
  const dropoffStatus = routeAudit?.dropoff?.status ?? "unknown";
  if (
    dropoffStatus === "ambiguous" ||
    dropoffStatus === "suggested_unconfirmed" ||
    dropoffStatus === "unresolved" ||
    dropoffStatus === "missing" ||
    dropoffStatus === "unknown"
  ) {
    return block(targetStage, "route_not_canonical", {
      type: "resolve_dropoff_area",
      field: "dropoff_area",
      details: { status: dropoffStatus },
    });
  }
  if (routeAudit?.quoteMatchesCanonicalRoute === false) {
    return block(targetStage, "quote_route_mismatch", {
      type: "reprice_route",
    });
  }
  if (routeAudit?.selectedServiceInQuote === false) {
    return block(targetStage, "selected_service_not_quoted", {
      type: "reprice_route",
    });
  }
  if (routeAudit?.priceMatchesQuote === false) {
    return block(targetStage, "price_mismatch", {
      type: "reprice_route",
    });
  }
  return null;
}

function blockIfRouteSideClarificationOpen(
  targetStage: BookingLifecycleTargetStage,
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision | null {
  const truth = input.bookingTruthSnapshot ?? null;
  if (truth) {
    if (truth.nextAction.type === "resolve_route_ambiguity") {
      return block(targetStage, "route_clarification_pending", {
        type:
          truth.nextAction.field === "pickup_area"
            ? "resolve_pickup_area"
            : "resolve_dropoff_area",
        field: truth.nextAction.field,
        details: {
          status: truth.nextAction.status,
          options: truth.nextAction.options
            .map((option) => option.nameEn || option.nameAr)
            .filter(Boolean),
        },
      });
    }
    if (truth.route.lockStatus === "locked" && !truth.pendingRouteAmbiguity) {
      return null;
    }
  }
  const openRequested = hasOpenRouteSideRequestedSlot(input);
  if (!openRequested.open) return null;
  return block(targetStage, "route_clarification_pending", {
    type:
      openRequested.side === "pickup_area"
        ? "resolve_pickup_area"
        : "resolve_dropoff_area",
    field: openRequested.side ?? "dropoff_area",
    details: { options: openRequested.options },
  });
}

function blockIfSummaryInvariantFails(
  targetStage: "summary_shown" | "awaiting_confirmation",
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision | null {
  const entry = input.controllerState;
  const now = input.now ?? Date.now();
  const routeBlock = routeAuditBlocks(targetStage, input.routeAudit);
  if (routeBlock) return routeBlock;

  const routeClarificationBlock = blockIfRouteSideClarificationOpen(targetStage, input);
  if (routeClarificationBlock) return routeClarificationBlock;

  const conflictSlot = findOpenConflict(input);
  if (conflictSlot) {
    return block(targetStage, "slot_conflict", {
      type: "resolve_slot_conflict",
      field: conflictSlot,
    });
  }

  if (hasActivePendingOrderEdits(entry, now)) {
    return block(targetStage, "pending_order_edits", {
      type: "resolve_pending_edit",
      details: { fields: entry?.pendingOrderEdits?.fields ?? [] },
    });
  }

  const missing =
    input.currentTurnToolResults?.missingFields ??
    input.bookingTruthSnapshot?.missingFields ??
    null;
  if (Array.isArray(missing) && missing.length > 0) {
    return block(targetStage, "missing_fields", {
      type: "collect_missing_fields",
      details: { missingFields: missing },
    });
  }

  if (!entry?.selectedDeliveryType) {
    return block(targetStage, "selected_service_missing", {
      type: "reprice_route",
    });
  }
  if (entry.quotedPrice == null) {
    return block(targetStage, "price_missing", {
      type: "reprice_route",
    });
  }
  if (!entry.quoteRouteKey || !input.sessionGuard?.lastQuotedRoute) {
    return block(targetStage, "quote_missing", {
      type: "reprice_route",
    });
  }
  if (!quoteRouteMatchesEntry(entry, input.sessionGuard)) {
    return block(targetStage, "quote_route_mismatch", {
      type: "reprice_route",
    });
  }
  if (!selectedServiceIsQuoted(entry, input.sessionGuard)) {
    return block(targetStage, "selected_service_not_quoted", {
      type: "reprice_route",
    });
  }
  if (!selectedPriceMatchesQuote(entry, input.sessionGuard)) {
    return block(targetStage, "price_mismatch", {
      type: "reprice_route",
    });
  }

  return null;
}

function blockIfCollectingInvariantFails(
  targetStage: "collecting_booking_details",
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision | null {
  const entry = input.controllerState;
  const routeBlock = routeAuditBlocks(targetStage, input.routeAudit);
  if (routeBlock) return routeBlock;
  const routeClarificationBlock = blockIfRouteSideClarificationOpen(targetStage, input);
  if (routeClarificationBlock) return routeClarificationBlock;
  if (!entry?.quoteRouteKey || !input.sessionGuard?.lastQuotedRoute) {
    return block(targetStage, "quote_missing", {
      type: "reprice_route",
    });
  }
  if (!quoteRouteMatchesEntry(entry, input.sessionGuard)) {
    return block(targetStage, "quote_route_mismatch", {
      type: "reprice_route",
    });
  }
  if (!entry.selectedDeliveryType) {
    return block(targetStage, "selected_service_missing", {
      type: "reprice_route",
    });
  }
  if (entry.quotedPrice == null) {
    return block(targetStage, "price_missing", {
      type: "reprice_route",
    });
  }
  return null;
}

function blockIfQuotedInvariantFails(
  targetStage: "quoted",
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision | null {
  const routeBlock = routeAuditBlocks(targetStage, input.routeAudit);
  if (routeBlock) return routeBlock;
  const routeClarificationBlock = blockIfRouteSideClarificationOpen(targetStage, input);
  if (routeClarificationBlock) return routeClarificationBlock;
  if (!input.sessionGuard?.lastQuotedRoute) {
    return block(targetStage, "quote_missing", {
      type: "reprice_route",
    });
  }
  return null;
}

function blockIfOrderSubmittedInvariantFails(
  targetStage: "order_submitted",
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision | null {
  const routeBlock = routeAuditBlocks(targetStage, input.routeAudit);
  if (routeBlock) return routeBlock;
  const guard = input.orderGuardResult;
  if (!guard || !guard.ok) {
    return block(targetStage, "order_guard_failed", {
      type: "retry_order_with_guard",
    });
  }
  if (
    input.currentTurnToolResults?.confirmationExplicit === false ||
    (input.currentTurnToolResults?.confirmationExplicit == null &&
      !input.orderGuardResult &&
      !looksLikeConfirmation(input.currentCustomerText))
  ) {
    return block(targetStage, "confirmation_missing", {
      type: "wait_for_confirmation",
    });
  }
  if (!input.currentTurnToolResults?.orderCreatedUid) {
    return block(targetStage, "transaction_artifact_missing", {
      type: "prepare_transaction_artifact",
    });
  }
  return null;
}

export function canAdvanceBookingFlow(
  targetStage: BookingLifecycleTargetStage,
  input: CanAdvanceBookingFlowInput,
): BookingLifecycleDecision {
  const effectiveInput =
    !input.routeAudit && input.bookingTruthSnapshot
      ? {
          ...input,
          routeAudit: buildBookingLifecycleRouteAudit({
            controllerState: input.controllerState,
            sessionGuard: input.sessionGuard,
            bookingTruthSnapshot: input.bookingTruthSnapshot,
          }),
        }
      : input;
  let decision: BookingLifecycleDecision | null = null;
  if (targetStage === "quoted") {
    decision = blockIfQuotedInvariantFails(targetStage, effectiveInput);
  } else if (targetStage === "collecting_booking_details") {
    decision = blockIfCollectingInvariantFails(targetStage, effectiveInput);
  } else if (targetStage === "summary_shown" || targetStage === "awaiting_confirmation") {
    decision = blockIfSummaryInvariantFails(targetStage, effectiveInput);
  } else if (targetStage === "order_submitted") {
    decision = blockIfOrderSubmittedInvariantFails(targetStage, effectiveInput);
  }
  return decision ?? allow(targetStage);
}

export function bookingLifecycleDecisionSummary(decision: BookingLifecycleDecision): string {
  if (decision.decision === "allow") {
    return `allow:${decision.targetStage}`;
  }
  const field =
    "field" in decision.requiredNextAction && decision.requiredNextAction.field
      ? `:${decision.requiredNextAction.field}`
      : "";
  return `block:${decision.targetStage}:${decision.blockingReason}:${decision.requiredNextAction.type}${field}`;
}
