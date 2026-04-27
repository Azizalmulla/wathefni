import type {
  ConversationFlowStage,
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
  PendingOrderEdits,
} from "./conversation-policy.js";
import {
  CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS,
  getEffectiveDeliveryAreaName,
  getEffectivePickupAreaName,
} from "./conversation-policy.js";
import type { DialogState, SlotName } from "./dialog-state.js";
import { findFirstConflictSlot } from "./dialog-state.js";
import type {
  PersistedGuardSessionState,
  PersistedQuotedRouteState,
} from "./guard-state.js";
import type { AreaResolutionProvenance } from "./area-resolution-provenance.js";
import {
  cloneAreaResolutionProvenance,
  isCanonicalAreaResolutionStatus,
  normalizeAreaResolutionStatus,
} from "./area-resolution-provenance.js";

const PENDING_ORDER_EDIT_TTL_MS = 15 * 60 * 1000;

export type BookingTruthSnapshotTiming = "turn_start" | "post_drain";

export type BookingTruthRouteSide = {
  status:
    | "canonical"
    | "exact_confirmed"
    | "suggested_unconfirmed"
    | "ambiguous"
    | "unresolved"
    | "missing"
    | "unknown";
  areaId: number | string | null;
  nameEn: string | null;
  nameAr: string | null;
  provenance: AreaResolutionProvenance | null;
  ambiguityGroupId: string | null;
  options: NonNullable<AreaResolutionProvenance["options"]>;
  sourceText: string | null;
  normalizedText: string | null;
  confirmedByUser: boolean;
  quoteBuiltFromAreaIds: boolean;
};

export type BookingTruthAddressSatisfaction = {
  pickup: boolean;
  delivery: boolean;
};

export type BookingTruthPendingRouteAmbiguity = {
  side: "pickup" | "dropoff";
  status: BookingTruthRouteSide["status"];
  field: "pickup_area" | "dropoff_area";
  ambiguityGroupId: string | null;
  options: BookingTruthRouteSide["options"];
  sourceText: string | null;
} | null;

export type BookingTruthSlotConflict = {
  field: SlotName;
  value: string | null;
  conflictCandidate: string | null;
};

export type BookingTruthReadiness = {
  ready: boolean;
  blockers: string[];
};

export type BookingTruthSelectedOption = {
  deliveryType: string | null;
  labelEn: string | null;
  labelAr: string | null;
  price: number | null;
  formattedPrice: string | null;
  directChatBookingStatus: string | null;
};

export type BookingTruthAwaitingConfirmationDisposition =
  | "confirm_order"
  | "cancel_order"
  | "edit_order"
  | "informational_question"
  | "coherence_pleasantry"
  | "unclear";

export type BookingTruthTurnIntentDisposition =
  | "answered_full"
  | "answered_partial"
  | "answered_unasked"
  | "corrected_prior"
  | "clarifying_question"
  | "acknowledgement"
  | "refused_or_stuck"
  | "unclear";

export type BookingTruthTurnKind =
  | "initial_route"
  | "post_clarify_continuation"
  | "informational"
  | "address_collection"
  | "booking_detail_collection"
  | "confirmation_or_cancel"
  | "post_order_chat"
  | "other";

export type BookingTruthPricingAction =
  | "call_get_price"
  | "continue_existing_quote"
  | "informational_only"
  | "awaiting_state"
  | "none";

export type BookingTruthStateActionBlock = {
  action: string;
  reason: string;
};

export type BookingTruthCurrentTurnDisposition = {
  turnKind: BookingTruthTurnKind | null;
  pricingAction: BookingTruthPricingAction | null;
  awaitingConfirmationKind: BookingTruthAwaitingConfirmationDisposition | null;
  turnIntentKind: BookingTruthTurnIntentDisposition | null;
  turnIntentConfidence: "high" | "medium" | "low" | null;
  getPriceFired: boolean;
  hasConcreteMutation: boolean;
  stateResetApplied: boolean;
  source: "proposed_turn_decision" | null;
};

export type BookingTruthNextAction =
  | { type: "none_idle"; reason: string }
  | { type: "answer_customer_question"; reason: string }
  | { type: "show_quote"; reason: string }
  | { type: "ask_edit_target"; reason: string }
  | { type: "answer_question_then_wait_for_confirmation"; reason: string }
  | { type: "pause_confirmation"; reason: string }
  | { type: "cancel_or_confirm_cancel"; reason: string }
  | { type: "ask_clarification_about_confirmation"; reason: string }
  | {
      type: "resolve_route_ambiguity";
      reason: string;
      field: "pickup_area" | "dropoff_area";
      side: "pickup" | "dropoff";
      status: BookingTruthRouteSide["status"];
      options: BookingTruthRouteSide["options"];
    }
  | { type: "resolve_coverage_ambiguity"; reason: string }
  | { type: "resolve_slot_conflict"; reason: string; field: SlotName | null }
  | { type: "resolve_pending_edit"; reason: string; fields: PendingOrderEdits["fields"] }
  | { type: "collect_missing_field"; reason: string; field: string; missingFields: string[] }
  | { type: "reprice_route"; reason: string }
  | { type: "show_summary"; reason: string }
  | { type: "wait_for_confirmation"; reason: string }
  | { type: "submit_order"; reason: string }
  | { type: "show_order_result"; reason: string; orderUid: string | null }
  | { type: "handoff_or_transaction_failure"; reason: string };

export type BookingLifecycleState =
  | "collecting_details"
  | "resolving_route"
  | "quoting"
  | "ready_to_show_summary"
  | "awaiting_confirmation"
  | "submitting_order"
  | "order_submitted"
  | "transaction_failed"
  | "handoff_required";

export type BookingTruthSnapshot = {
  timing: BookingTruthSnapshotTiming;
  now: number;
  controllerState: PersistedConversationControllerEntry | null;
  dialogState: DialogState | null;
  stage: ConversationFlowStage | null;
  bookingStep: string | null;
  draft: PersistedBookingDraft | null;
  route: {
    pickup: BookingTruthRouteSide;
    dropoff: BookingTruthRouteSide;
    quoteMatchesCanonicalRoute: boolean | null;
    locked: boolean;
    lockStatus: "locked" | "blocked" | "incomplete" | "unknown";
    quoteBuiltFromAreaIds: boolean;
  };
  lifecycleState: BookingLifecycleState;
  quote: {
    activeQuotedRoute: PersistedQuotedRouteState | null;
    routeAuthorityActive: boolean;
    optionCatalog: PersistedQuotedRouteState["optionCatalog"];
    validQuotedPrices: number[];
    selected: BookingTruthSelectedOption;
    selectedService: string | null;
    selectedServiceInQuote: boolean | null;
    selectedPriceMatchesQuote: boolean | null;
  };
  missingFields: string[];
  nextMissingField: string | null;
  addressSatisfaction: BookingTruthAddressSatisfaction;
  requestedSlot: DialogState["requestedSlot"];
  requestedSlotOptions: string[];
  pendingOrderEdits: PendingOrderEdits | null;
  conflictSlot: SlotName | null;
  slotConflicts: BookingTruthSlotConflict[];
  pendingRouteAmbiguity: BookingTruthPendingRouteAmbiguity;
  coveragePending: unknown | null;
  currentTurnDisposition: BookingTruthCurrentTurnDisposition | null;
  blockedStateActions: BookingTruthStateActionBlock[];
  summary: {
    shown: boolean;
    awaitingConfirmation: boolean;
    ready: boolean;
    blockers: string[];
    currentHash: string | null;
    lastRenderedHash: string | null;
    hashMatchesLastRendered: boolean;
    hashRequiredForConfirmation: boolean;
  };
  order: {
    submitted: boolean;
    submittedOrderUid: string | null;
    createdOrderUid: string | null;
    ready: boolean;
    blockers: string[];
  };
  readiness: {
    summary: BookingTruthReadiness;
    order: BookingTruthReadiness;
  };
  nextAction: BookingTruthNextAction;
};

export type BookingTruthSnapshotInput = {
  timing: BookingTruthSnapshotTiming;
  controllerState: PersistedConversationControllerEntry | null;
  sessionGuard?: PersistedGuardSessionState | null;
  dialogState?: DialogState | null;
  missingFields?: string[] | null;
  coveragePending?: unknown | null;
  orderCreatedUid?: string | null;
  confirmationExplicit?: boolean | null;
  currentTurnDisposition?: BookingTruthCurrentTurnDisposition | null;
  requireRenderedSummaryHash?: boolean | null;
  now?: number;
};

function hasStructuredLocation(location: PersistedBookingDraft["pickupLocation"]): boolean {
  return Boolean(
    location && Number.isFinite(location.latitude) && Number.isFinite(location.longitude),
  );
}

function hasSubstantiveExtra(extra: string | null | undefined): boolean {
  const trimmed = String(extra || "").trim();
  if (trimmed.length < 3) return false;
  if (/\d/.test(trimmed) || /[\u0660-\u0669]/.test(trimmed)) return true;
  const lower = trimmed.toLowerCase();
  return [
    "building",
    "tower",
    "villa",
    "compound",
    "apt",
    "apartment",
    "flat",
    "floor",
    "unit",
    "office",
    "shop",
    "gate",
    "suite",
    "شقة",
    "شقه",
    "دور",
    "طابق",
    "عمارة",
    "عماره",
    "برج",
    "فيلا",
    "مجمع",
    "وحدة",
    "وحده",
    "مكتب",
    "محل",
    "بوابة",
    "بوابه",
  ].some((marker) => lower.includes(marker) || trimmed.includes(marker));
}

function hasBlockEvidence(extra: string | null | undefined): boolean {
  const text = String(extra || "").toLowerCase();
  return /\bblock\s*[\d\u0660-\u0669]+/i.test(text) || /(?:قطعة|قطعه)\s*[\d\u0660-\u0669]+/.test(text);
}

function hasStreetOrAvenueEvidence(extra: string | null | undefined): boolean {
  const text = String(extra || "").toLowerCase();
  return (
    /\b(?:street|st|avenue|ave|road|rd)\b\s*[\w\d\u0660-\u0669-]*/i.test(text) ||
    /(?:شارع|جادة|جاده)\s*[\w\d\u0660-\u0669-]*/.test(text)
  );
}

function hasSatisfiedAddress(
  draft: PersistedBookingDraft | null,
  side: "pickup" | "delivery",
): boolean {
  if (!draft) return false;
  const location = side === "pickup" ? draft.pickupLocation : draft.deliveryLocation;
  if (hasStructuredLocation(location)) return true;
  const block = side === "pickup" ? draft.pickupBlock : draft.deliveryBlock;
  const street = side === "pickup" ? draft.pickupStreet : draft.deliveryStreet;
  const avenue = side === "pickup" ? draft.pickupAvenue : draft.deliveryAvenue;
  const house = side === "pickup" ? draft.pickupHouse : draft.deliveryHouse;
  const extra = side === "pickup" ? draft.pickupExtra : draft.deliveryExtra;
  const blockSatisfied = Boolean(block || hasBlockEvidence(extra));
  const streetSatisfied = Boolean(street || avenue || hasStreetOrAvenueEvidence(extra));
  const unitSatisfied = Boolean(house || hasSubstantiveExtra(extra));
  return blockSatisfied && streetSatisfied && unitSatisfied;
}

function diagnoseAddressMissing(
  draft: PersistedBookingDraft | null,
  side: "pickup" | "delivery",
): string[] {
  if (!draft || hasSatisfiedAddress(draft, side)) return [];
  const location = side === "pickup" ? draft?.pickupLocation : draft?.deliveryLocation;
  if (hasStructuredLocation(location)) return [];
  const block = side === "pickup" ? draft.pickupBlock : draft.deliveryBlock;
  const street = side === "pickup" ? draft.pickupStreet : draft.deliveryStreet;
  const avenue = side === "pickup" ? draft.pickupAvenue : draft.deliveryAvenue;
  const house = side === "pickup" ? draft.pickupHouse : draft.deliveryHouse;
  const extra = side === "pickup" ? draft.pickupExtra : draft.deliveryExtra;
  const missing: string[] = [];
  if (!block && !hasBlockEvidence(extra)) missing.push("block");
  if (!street && !avenue && !hasStreetOrAvenueEvidence(extra)) missing.push("street_or_avenue");
  if (!house && !hasSubstantiveExtra(extra)) missing.push("house_or_unit");
  return missing;
}

function isQuoteFresh(route: PersistedQuotedRouteState | null | undefined, now: number): boolean {
  return Boolean(
    route?.quotedAt &&
      now - Number(route.quotedAt || 0) <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS,
  );
}

function normalize(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

function normalizeSummaryValue(value: unknown): string | number | boolean | null {
  if (value == null) return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? Number(value.toFixed(6)) : null;
  }
  if (typeof value === "boolean") return value;
  return String(value).trim().replace(/\s+/g, " ");
}

function stableSummaryHash(value: unknown): string {
  const json = JSON.stringify(value);
  let hash = 0x811c9dc5;
  for (let i = 0; i < json.length; i += 1) {
    hash ^= json.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

export function buildBookingSummaryHash(params: {
  draft: PersistedBookingDraft | null;
  pickup: BookingTruthRouteSide;
  dropoff: BookingTruthRouteSide;
  selected: BookingTruthSelectedOption;
  selectedService: string | null;
}): string | null {
  const { draft, pickup, dropoff, selected, selectedService } = params;
  if (!draft) return null;
  const price =
    selected.price != null && Number.isFinite(Number(selected.price))
      ? Number(Number(selected.price).toFixed(3))
      : normalizeSummaryValue(selected.formattedPrice);
  const operationalSummary = {
    schema: 1,
    service: normalizeSummaryValue(selectedService || selected.deliveryType),
    serviceLabelEn: normalizeSummaryValue(selected.labelEn),
    serviceLabelAr: normalizeSummaryValue(selected.labelAr),
    price,
    pickup: {
      areaId: normalizeSummaryValue(pickup.areaId),
      areaEn: normalizeSummaryValue(pickup.nameEn),
      areaAr: normalizeSummaryValue(pickup.nameAr),
      address: {
        block: normalizeSummaryValue(draft.pickupBlock),
        street: normalizeSummaryValue(draft.pickupStreet),
        avenue: normalizeSummaryValue(draft.pickupAvenue),
        house: normalizeSummaryValue(draft.pickupHouse),
        extra: normalizeSummaryValue(draft.pickupExtra),
        location: draft.pickupLocation
          ? {
              source: normalizeSummaryValue(draft.pickupLocation.source),
              latitude: normalizeSummaryValue(draft.pickupLocation.latitude),
              longitude: normalizeSummaryValue(draft.pickupLocation.longitude),
              name: normalizeSummaryValue(draft.pickupLocation.name),
              address: normalizeSummaryValue(draft.pickupLocation.address),
              resolvedAreaName: normalizeSummaryValue(
                draft.pickupLocation.resolvedAreaName,
              ),
            }
          : null,
      },
    },
    sender: {
      name: normalizeSummaryValue(draft.senderName),
      phone: normalizeSummaryValue(draft.senderPhone),
    },
    delivery: {
      areaId: normalizeSummaryValue(dropoff.areaId),
      areaEn: normalizeSummaryValue(dropoff.nameEn),
      areaAr: normalizeSummaryValue(dropoff.nameAr),
      address: {
        block: normalizeSummaryValue(draft.deliveryBlock),
        street: normalizeSummaryValue(draft.deliveryStreet),
        avenue: normalizeSummaryValue(draft.deliveryAvenue),
        house: normalizeSummaryValue(draft.deliveryHouse),
        extra: normalizeSummaryValue(draft.deliveryExtra),
        location: draft.deliveryLocation
          ? {
              source: normalizeSummaryValue(draft.deliveryLocation.source),
              latitude: normalizeSummaryValue(draft.deliveryLocation.latitude),
              longitude: normalizeSummaryValue(draft.deliveryLocation.longitude),
              name: normalizeSummaryValue(draft.deliveryLocation.name),
              address: normalizeSummaryValue(draft.deliveryLocation.address),
              resolvedAreaName: normalizeSummaryValue(
                draft.deliveryLocation.resolvedAreaName,
              ),
            }
          : null,
      },
    },
    recipient: {
      name: normalizeSummaryValue(draft.recipientName),
      phone: normalizeSummaryValue(draft.recipientPhone),
    },
  };
  return stableSummaryHash(operationalSummary);
}

function routeMatchesEntry(
  route: PersistedQuotedRouteState | null,
  entry: PersistedConversationControllerEntry | null,
): boolean | null {
  if (!route || !entry) return null;
  if (entry.quoteRouteKey && route.routeKey) {
    return entry.quoteRouteKey === route.routeKey;
  }
  const pickup =
    normalize(entry.quotePickupAreaNameEn || entry.pendingPickupAreaNameEn) ||
    normalize(getEffectivePickupAreaName(entry.bookingDraft, entry));
  const dropoff =
    normalize(entry.quoteDropoffAreaNameEn || entry.pendingDropoffAreaNameEn) ||
    normalize(getEffectiveDeliveryAreaName(entry.bookingDraft, entry));
  if (!pickup || !dropoff) return null;
  return (
    pickup === normalize(route.pickupAreaNameEn) &&
    dropoff === normalize(route.dropoffAreaNameEn)
  );
}

function hasQuoteAuthority(
  entry: PersistedConversationControllerEntry | null,
  route: PersistedQuotedRouteState | null,
  now: number,
): boolean {
  if (!entry || !route || !isQuoteFresh(route, now)) return false;
  if (
    ![
      "quoted",
      "collecting_booking_details",
      "summary_shown",
      "awaiting_confirmation",
    ].includes(entry.stage)
  ) {
    return false;
  }
  return routeMatchesEntry(route, entry) !== false;
}

function collectValidQuotedPrices(route: PersistedQuotedRouteState | null): number[] {
  const out: number[] = [];
  if (!route) return out;
  for (const price of Object.values(route.pricesByType || {})) {
    if (typeof price === "number" && Number.isFinite(price) && price > 0) {
      out.push(price);
    }
  }
  for (const option of route.optionCatalog || []) {
    const price = option.quoted_price;
    if (typeof price === "number" && Number.isFinite(price) && price > 0) {
      out.push(price);
    }
  }
  return out;
}

function selectOption(
  entry: PersistedConversationControllerEntry | null,
  route: PersistedQuotedRouteState | null,
): BookingTruthSelectedOption {
  const selectedType =
    String(entry?.selectedQuoteOptionType || entry?.selectedDeliveryType || "").trim() || null;
  const option =
    route?.optionCatalog?.find((candidate) => candidate.delivery_type === selectedType) ||
    route?.optionCatalog?.find((candidate) => candidate.delivery_type === "sedan_normal") ||
    null;
  const price =
    typeof option?.quoted_price === "number" && Number.isFinite(option.quoted_price)
      ? option.quoted_price
      : entry?.quotedPrice ?? null;
  return {
    deliveryType: selectedType || option?.delivery_type || entry?.selectedDeliveryType || null,
    labelEn: option?.label_en || entry?.selectedQuoteOptionLabelEn || null,
    labelAr: option?.label_ar || entry?.selectedQuoteOptionLabelAr || null,
    price,
    formattedPrice:
      option?.formatted_price ||
      (typeof price === "number" && Number.isFinite(price) ? `${price.toFixed(3)} KWD` : null),
    directChatBookingStatus:
      option?.direct_chat_booking_status ||
      entry?.selectedQuoteOptionDirectChatBookingStatus ||
      null,
  };
}

function routeSideStatus(
  requestedSlot: DialogState["requestedSlot"],
  side: "pickup" | "dropoff",
  nameEn: string | null,
  nameAr: string | null,
  provenance: AreaResolutionProvenance | null,
): BookingTruthRouteSide {
  const slotName = side === "pickup" ? "pickup_area" : "dropoff_area";
  const cloned = cloneAreaResolutionProvenance(provenance);
  if (cloned) {
    const status = normalizeAreaResolutionStatus(cloned.status);
    const options = Array.isArray(cloned.options)
      ? cloned.options.map((option) => ({ ...option }))
      : [];
    return {
      status,
      areaId: cloned.areaId ?? null,
      nameEn: cloned.nameEn ?? nameEn,
      nameAr: cloned.nameAr ?? nameAr,
      provenance: cloned,
      ambiguityGroupId: cloned.ambiguityGroupId ?? null,
      options,
      sourceText: cloned.sourceText ?? null,
      normalizedText: cloned.normalizedText ?? null,
      confirmedByUser: Boolean(cloned.confirmedByUser),
      quoteBuiltFromAreaIds: Boolean(cloned.quoteBuiltFromAreaIds),
    };
  }
  if (requestedSlot?.name === slotName && (requestedSlot.options?.length || 0) > 0) {
    return {
      status: "ambiguous",
      areaId: null,
      nameEn,
      nameAr,
      provenance: null,
      ambiguityGroupId: null,
      options: (requestedSlot.options || []).map((option) => ({
        areaId: null,
        nameEn: option,
        nameAr: null,
      })),
      sourceText: null,
      normalizedText: null,
      confirmedByUser: false,
      quoteBuiltFromAreaIds: false,
    };
  }
  if (nameEn) {
    return {
      status: "canonical",
      areaId: null,
      nameEn,
      nameAr,
      provenance: null,
      ambiguityGroupId: null,
      options: [],
      sourceText: null,
      normalizedText: null,
      confirmedByUser: false,
      quoteBuiltFromAreaIds: false,
    };
  }
  return {
    status: "missing",
    areaId: null,
    nameEn: null,
    nameAr: null,
    provenance: null,
    ambiguityGroupId: null,
    options: [],
    sourceText: null,
    normalizedText: null,
    confirmedByUser: false,
    quoteBuiltFromAreaIds: false,
  };
}

function activePendingOrderEdits(
  entry: PersistedConversationControllerEntry | null,
  now: number,
): PendingOrderEdits | null {
  const pending = entry?.pendingOrderEdits ?? null;
  if (!pending || !Array.isArray(pending.fields) || pending.fields.length === 0) return null;
  if (now - Number(pending.askedTs || 0) > PENDING_ORDER_EDIT_TTL_MS) return null;
  return pending;
}

function areaProvenanceForSide(params: {
  side: "pickup" | "dropoff";
  entry: PersistedConversationControllerEntry | null;
  activeQuotedRoute: PersistedQuotedRouteState | null;
}): AreaResolutionProvenance | null {
  if (params.side === "pickup") {
    return (
      cloneAreaResolutionProvenance(params.activeQuotedRoute?.pickupAreaResolution) ||
      cloneAreaResolutionProvenance(params.entry?.quotePickupAreaResolution) ||
      cloneAreaResolutionProvenance(params.entry?.pendingPickupAreaResolution) ||
      null
    );
  }
  return (
    cloneAreaResolutionProvenance(params.activeQuotedRoute?.dropoffAreaResolution) ||
    cloneAreaResolutionProvenance(params.entry?.quoteDropoffAreaResolution) ||
    cloneAreaResolutionProvenance(params.entry?.pendingDropoffAreaResolution) ||
    null
  );
}

function routeLockStatus(
  routeAuthorityActive: boolean,
  pickup: BookingTruthRouteSide,
  dropoff: BookingTruthRouteSide,
): "locked" | "blocked" | "incomplete" | "unknown" {
  if (!routeAuthorityActive) return "unknown";
  if (pickup.status === "missing" || dropoff.status === "missing") return "incomplete";
  if (
    !isCanonicalAreaResolutionStatus(pickup.status) ||
    !isCanonicalAreaResolutionStatus(dropoff.status)
  ) {
    return "blocked";
  }
  return "locked";
}

function mergeRouteMissingFields(
  baseMissingFields: string[],
  pickup: BookingTruthRouteSide,
  dropoff: BookingTruthRouteSide,
): string[] {
  const merged = new Set(baseMissingFields);
  if (!isCanonicalAreaResolutionStatus(pickup.status)) merged.add("pickup.area");
  if (!isCanonicalAreaResolutionStatus(dropoff.status)) merged.add("delivery.area");
  return [...merged];
}

function computeSnapshotMissingFields(params: {
  draft: PersistedBookingDraft | null;
  entry: PersistedConversationControllerEntry | null;
  pickup: BookingTruthRouteSide;
  dropoff: BookingTruthRouteSide;
}): string[] {
  const missing: string[] = [];
  const { draft, entry } = params;
  if (!draft?.senderName) missing.push("sender.name");
  if (!draft?.senderPhone) missing.push("sender.phone");
  if (!draft?.recipientName) missing.push("recipient.name");
  if (!draft?.recipientPhone) missing.push("recipient.phone");
  if (!hasSatisfiedAddress(draft, "pickup")) {
    missing.push("pickup.address");
    for (const sub of diagnoseAddressMissing(draft, "pickup")) {
      missing.push(`pickup.${sub}`);
    }
  }
  if (!hasSatisfiedAddress(draft, "delivery")) {
    missing.push("delivery.address");
    for (const sub of diagnoseAddressMissing(draft, "delivery")) {
      missing.push(`delivery.${sub}`);
    }
  }
  if (!entry?.selectedDeliveryType) missing.push("service_type");
  if (entry?.quotedPrice == null) missing.push("quoted_price");
  return mergeRouteMissingFields(missing, params.pickup, params.dropoff);
}

function collectSlotConflicts(dialogState: DialogState | null): BookingTruthSlotConflict[] {
  const out: BookingTruthSlotConflict[] = [];
  for (const [field, record] of Object.entries(dialogState?.slots ?? {})) {
    if (record?.status === "conflict") {
      out.push({
        field: field as SlotName,
        value: record.value ?? null,
        conflictCandidate: record.conflictCandidate ?? null,
      });
    }
  }
  return out;
}

function pendingRouteAmbiguity(
  pickup: BookingTruthRouteSide,
  dropoff: BookingTruthRouteSide,
): BookingTruthPendingRouteAmbiguity {
  const blockingStatuses = new Set<BookingTruthRouteSide["status"]>([
    "suggested_unconfirmed",
    "ambiguous",
    "unresolved",
    "unknown",
  ]);
  if (blockingStatuses.has(pickup.status)) {
    return {
      side: "pickup",
      field: "pickup_area",
      status: pickup.status,
      ambiguityGroupId: pickup.ambiguityGroupId,
      options: pickup.options,
      sourceText: pickup.sourceText,
    };
  }
  if (blockingStatuses.has(dropoff.status)) {
    return {
      side: "dropoff",
      field: "dropoff_area",
      status: dropoff.status,
      ambiguityGroupId: dropoff.ambiguityGroupId,
      options: dropoff.options,
      sourceText: dropoff.sourceText,
    };
  }
  return null;
}

function buildReadiness(params: {
  missingFields: string[];
  routeLock: ReturnType<typeof routeLockStatus>;
  pendingOrderEdits: PendingOrderEdits | null;
  slotConflicts: BookingTruthSlotConflict[];
  selectedService: string | null;
  selectedPrice: number | null;
  selectedServiceInQuote: boolean | null;
  selectedPriceMatchesQuote: boolean | null;
  summaryShown: boolean;
  summaryHashConfirmed: boolean;
  requireRenderedSummaryHash: boolean;
}): { summary: BookingTruthReadiness; order: BookingTruthReadiness } {
  const summaryBlockers: string[] = [];
  if (params.routeLock !== "locked") summaryBlockers.push(`route_${params.routeLock}`);
  if (params.missingFields.length > 0) summaryBlockers.push("missing_fields");
  if (params.pendingOrderEdits) summaryBlockers.push("pending_order_edits");
  if (params.slotConflicts.length > 0) summaryBlockers.push("slot_conflict");
  if (!params.selectedService) summaryBlockers.push("selected_service_missing");
  if (params.selectedPrice == null) summaryBlockers.push("price_missing");
  if (params.selectedServiceInQuote === false) summaryBlockers.push("selected_service_not_quoted");
  if (params.selectedPriceMatchesQuote === false) summaryBlockers.push("price_mismatch");

  const orderBlockers = [...summaryBlockers];
  if (!params.summaryShown) orderBlockers.push("summary_not_shown");
  if (
    params.requireRenderedSummaryHash &&
    params.summaryShown &&
    !params.summaryHashConfirmed
  ) {
    orderBlockers.push("summary_hash_mismatch");
  }

  return {
    summary: {
      ready: summaryBlockers.length === 0,
      blockers: summaryBlockers,
    },
    order: {
      ready: orderBlockers.length === 0,
      blockers: orderBlockers,
    },
  };
}

function buildNextAction(params: {
  stage: ConversationFlowStage | null;
  routeLock: ReturnType<typeof routeLockStatus>;
  pendingRouteAmbiguity: BookingTruthPendingRouteAmbiguity;
  coveragePending: unknown | null;
  conflictSlot: SlotName | null;
  pendingOrderEdits: PendingOrderEdits | null;
  missingFields: string[];
  readiness: { summary: BookingTruthReadiness; order: BookingTruthReadiness };
  summaryShown: boolean;
  summaryAwaitingConfirmation: boolean;
  summaryHashConfirmed: boolean;
  requireRenderedSummaryHash: boolean;
  submittedOrderUid: string | null;
  createdOrderUid: string | null;
  selectedServiceInQuote: boolean | null;
  selectedPriceMatchesQuote: boolean | null;
  confirmationExplicit: boolean;
  currentTurnDisposition: BookingTruthCurrentTurnDisposition | null;
}): {
  action: BookingTruthNextAction;
  blockedStateActions: BookingTruthStateActionBlock[];
} {
  const blockedStateActions: BookingTruthStateActionBlock[] = [];
  const block = (action: string, reason: string) => {
    if (
      blockedStateActions.some(
        (item) => item.action === action && item.reason === reason,
      )
    ) {
      return;
    }
    blockedStateActions.push({ action, reason });
  };
  const decision = (action: BookingTruthNextAction) => ({
    action,
    blockedStateActions,
  });
  const disposition = params.currentTurnDisposition;
  const turnKind = disposition?.turnKind ?? null;
  const pricingAction = disposition?.pricingAction ?? null;
  const awaitingConfirmationKind = disposition?.awaitingConfirmationKind ?? null;
  const turnIntentKind = disposition?.turnIntentKind ?? null;
  const semanticConfirmation = awaitingConfirmationKind === "confirm_order";
  const semanticEdit =
    awaitingConfirmationKind === "edit_order" ||
    (!awaitingConfirmationKind && turnIntentKind === "corrected_prior");
  const semanticQuestion =
    awaitingConfirmationKind === "informational_question" ||
    turnIntentKind === "clarifying_question" ||
    (turnKind === "informational" && pricingAction !== "call_get_price");
  const semanticPause =
    turnIntentKind === "refused_or_stuck" ||
    awaitingConfirmationKind === "coherence_pleasantry";
  const semanticUnclear =
    awaitingConfirmationKind === "unclear" || turnIntentKind === "unclear";
  const semanticResetOrCancel = awaitingConfirmationKind === "cancel_order";
  const routeCompatible =
    turnKind === "initial_route" ||
    turnKind === "post_clarify_continuation" ||
    pricingAction === "call_get_price" ||
    disposition?.getPriceFired === true;
  const collectionCompatible =
    !semanticQuestion &&
    !semanticPause &&
    !semanticUnclear &&
    !semanticResetOrCancel &&
    (!disposition ||
      disposition.hasConcreteMutation ||
      turnKind === "booking_detail_collection" ||
      turnKind === "address_collection" ||
      turnIntentKind === "answered_full" ||
      turnIntentKind === "answered_partial");
  const stateCanSpeak =
    collectionCompatible ||
    routeCompatible ||
    semanticConfirmation ||
    turnKind === "confirmation_or_cancel";
  const recordIncompatibleStateBlocks = () => {
    if (params.pendingRouteAmbiguity && !routeCompatible && !stateCanSpeak) {
      block("resolve_route_ambiguity", "latest_turn_not_route_compatible");
    }
    if (params.routeLock !== "locked" && !routeCompatible) {
      block("reprice_route", "latest_turn_not_route_compatible");
    }
    if (
      (params.selectedServiceInQuote === false ||
        params.selectedPriceMatchesQuote === false) &&
      !routeCompatible &&
      !collectionCompatible
    ) {
      block("reprice_route", "latest_turn_not_price_compatible");
    }
    if (params.missingFields.length > 0 && !collectionCompatible) {
      block("collect_missing_field", "latest_turn_not_collection_compatible");
    }
    if (
      params.readiness.order.ready &&
      params.summaryAwaitingConfirmation &&
      disposition &&
      !semanticConfirmation &&
      turnKind !== "confirmation_or_cancel"
    ) {
      block("wait_for_confirmation", "latest_turn_not_confirmation_compatible");
    }
  };

  if (params.stage === "order_submitted" || params.submittedOrderUid || params.createdOrderUid) {
    return decision({
      type: "show_order_result",
      reason: "order_submitted",
      orderUid: params.submittedOrderUid || params.createdOrderUid,
    });
  }
  if (semanticResetOrCancel) {
    recordIncompatibleStateBlocks();
    return decision({
      type: disposition?.stateResetApplied ? "none_idle" : "cancel_or_confirm_cancel",
      reason: disposition?.stateResetApplied
        ? "current_turn_reset_cleared_state"
        : "current_turn_cancel_request",
    });
  }
  if (semanticEdit) {
    recordIncompatibleStateBlocks();
    if (disposition?.hasConcreteMutation && params.readiness.summary.ready && !params.summaryHashConfirmed) {
      return decision({
        type: "show_summary",
        reason: "edit_applied_summary_changed",
      });
    }
    return decision({
      type: "ask_edit_target",
      reason: "current_turn_edit_request",
    });
  }
  if (semanticQuestion) {
    recordIncompatibleStateBlocks();
    return decision({
      type:
        params.summaryAwaitingConfirmation && params.readiness.order.ready
          ? "answer_question_then_wait_for_confirmation"
          : "answer_customer_question",
      reason: "current_turn_question",
    });
  }
  if (semanticPause) {
    recordIncompatibleStateBlocks();
    return decision({
      type:
        params.summaryAwaitingConfirmation && params.readiness.order.ready
          ? "pause_confirmation"
          : "answer_customer_question",
      reason: "current_turn_pause_or_chitchat",
    });
  }
  if (semanticUnclear) {
    recordIncompatibleStateBlocks();
    return decision({
      type:
        params.summaryAwaitingConfirmation && params.readiness.order.ready
          ? "ask_clarification_about_confirmation"
          : "answer_customer_question",
      reason: "current_turn_unclear",
    });
  }
  if (params.pendingRouteAmbiguity) {
    if (!routeCompatible && !stateCanSpeak) {
      block("resolve_route_ambiguity", "latest_turn_not_route_compatible");
      return decision({
        type: "answer_customer_question",
        reason: "state_route_ambiguity_blocked_by_current_turn",
      });
    }
    return decision({
      type: "resolve_route_ambiguity",
      reason: `route_${params.pendingRouteAmbiguity.status}`,
      field: params.pendingRouteAmbiguity.field,
      side: params.pendingRouteAmbiguity.side,
      status: params.pendingRouteAmbiguity.status,
      options: params.pendingRouteAmbiguity.options,
    });
  }
  if (params.routeLock !== "locked") {
    if (!routeCompatible) {
      block("reprice_route", "latest_turn_not_route_compatible");
      return decision({
        type: !params.stage || params.stage === "idle" ? "none_idle" : "answer_customer_question",
        reason: "state_reprice_blocked_by_current_turn",
      });
    }
    return decision({
      type: "reprice_route",
      reason: `route_${params.routeLock}`,
    });
  }
  if (params.coveragePending) {
    return decision({
      type: "resolve_coverage_ambiguity",
      reason: "coverage_pending",
    });
  }
  if (params.conflictSlot) {
    return decision({
      type: "resolve_slot_conflict",
      reason: "slot_conflict",
      field: params.conflictSlot,
    });
  }
  if (params.pendingOrderEdits) {
    return decision({
      type: "resolve_pending_edit",
      reason: "pending_order_edits",
      fields: [...params.pendingOrderEdits.fields],
    });
  }
  if (params.selectedServiceInQuote === false || params.selectedPriceMatchesQuote === false) {
    if (!routeCompatible && !collectionCompatible) {
      block("reprice_route", "latest_turn_not_price_compatible");
      return decision({
        type: "answer_customer_question",
        reason: "state_price_readiness_blocked_by_current_turn",
      });
    }
    return decision({
      type: "reprice_route",
      reason:
        params.selectedServiceInQuote === false
          ? "selected_service_not_quoted"
          : "price_mismatch",
    });
  }
  if (routeCompatible && params.missingFields.length > 0) {
    return decision({
      type: "show_quote",
      reason: "current_turn_route_quoted_before_missing_fields",
    });
  }
  if (params.missingFields.length > 0) {
    if (!collectionCompatible) {
      block("collect_missing_field", "latest_turn_not_collection_compatible");
      return decision({
        type: !params.stage || params.stage === "idle" ? "none_idle" : "answer_customer_question",
        reason: "state_missing_field_blocked_by_current_turn",
      });
    }
    return decision({
      type: "collect_missing_field",
      reason: "missing_fields",
      field: params.missingFields[0],
      missingFields: [...params.missingFields],
    });
  }
  if ((params.confirmationExplicit || semanticConfirmation) && params.readiness.order.ready) {
    return decision({
      type: "submit_order",
      reason: semanticConfirmation
        ? "semantic_confirmation_and_order_ready"
        : "explicit_confirmation_and_order_ready",
    });
  }
  if (
    params.confirmationExplicit &&
    params.requireRenderedSummaryHash &&
    params.readiness.summary.ready &&
    !params.summaryHashConfirmed
  ) {
    return decision({
      type: "show_summary",
      reason: "confirmation_rejected_summary_hash_mismatch",
    });
  }
  if (
    params.readiness.summary.ready &&
    (!params.summaryShown ||
      (params.requireRenderedSummaryHash && !params.summaryHashConfirmed))
  ) {
    if (!collectionCompatible && !semanticConfirmation) {
      block("show_summary", "latest_turn_not_summary_compatible");
      return decision({
        type: "answer_customer_question",
        reason: "state_show_summary_blocked_by_current_turn",
      });
    }
    return decision({
      type: "show_summary",
      reason:
        params.summaryShown && params.requireRenderedSummaryHash
          ? "summary_changed_after_render"
          : "summary_ready",
    });
  }
  if (params.readiness.order.ready && params.summaryAwaitingConfirmation) {
    if (disposition && !semanticConfirmation && turnKind !== "confirmation_or_cancel") {
      block("wait_for_confirmation", "latest_turn_not_confirmation_compatible");
      return decision({
        type: "answer_customer_question",
        reason: "state_wait_confirmation_blocked_by_current_turn",
      });
    }
    return decision({
      type: "wait_for_confirmation",
      reason: "summary_shown_order_ready",
    });
  }
  if (!params.stage || params.stage === "idle") {
    return decision({
      type: "none_idle",
      reason: "idle",
    });
  }
  return decision({
    type: "answer_customer_question",
    reason: "no_booking_action_required",
  });
}

function lifecycleStateFromNextAction(
  action: BookingTruthNextAction,
): BookingLifecycleState {
  switch (action.type) {
    case "resolve_route_ambiguity":
    case "resolve_coverage_ambiguity":
      return "resolving_route";
    case "show_quote":
    case "reprice_route":
      return "quoting";
    case "collect_missing_field":
    case "resolve_slot_conflict":
    case "resolve_pending_edit":
      return "collecting_details";
    case "show_summary":
      return "ready_to_show_summary";
    case "ask_edit_target":
    case "answer_question_then_wait_for_confirmation":
    case "pause_confirmation":
    case "cancel_or_confirm_cancel":
    case "ask_clarification_about_confirmation":
    case "wait_for_confirmation":
      return "awaiting_confirmation";
    case "submit_order":
      return "submitting_order";
    case "show_order_result":
      return "order_submitted";
    case "handoff_or_transaction_failure":
      return action.reason.toLowerCase().includes("transaction")
        ? "transaction_failed"
        : "handoff_required";
    case "answer_customer_question":
    case "none_idle":
      return "collecting_details";
    default: {
      const _exhaustive: never = action;
      void _exhaustive;
      return "collecting_details";
    }
  }
}

export function buildBookingTruthSnapshot(
  input: BookingTruthSnapshotInput,
): BookingTruthSnapshot {
  const now = input.now ?? Date.now();
  const entry = input.controllerState;
  const draft = entry?.bookingDraft ?? null;
  const dialogState = input.dialogState ?? entry?.dialogState ?? null;
  const sessionRoute = input.sessionGuard?.lastQuotedRoute ?? null;
  const routeAuthorityActive = hasQuoteAuthority(entry, sessionRoute, now);
  const activeQuotedRoute = routeAuthorityActive ? sessionRoute : null;
  const requestedSlot = dialogState?.requestedSlot ?? null;
  const pickupName =
    activeQuotedRoute?.pickupAreaNameEn ||
    getEffectivePickupAreaName(draft, entry) ||
    null;
  const dropoffName =
    activeQuotedRoute?.dropoffAreaNameEn ||
    getEffectiveDeliveryAreaName(draft, entry) ||
    null;
  const pickupNameAr =
    activeQuotedRoute?.pickupAreaNameAr ||
    entry?.quotePickupAreaNameAr ||
    entry?.pendingPickupAreaNameAr ||
    null;
  const dropoffNameAr =
    activeQuotedRoute?.dropoffAreaNameAr ||
    entry?.quoteDropoffAreaNameAr ||
    entry?.pendingDropoffAreaNameAr ||
    null;
  const pickupProvenance = areaProvenanceForSide({
    side: "pickup",
    entry,
    activeQuotedRoute,
  });
  const dropoffProvenance = areaProvenanceForSide({
    side: "dropoff",
    entry,
    activeQuotedRoute,
  });
  const pickupRouteSide = routeSideStatus(
    requestedSlot,
    "pickup",
    pickupName,
    pickupNameAr,
    pickupProvenance,
  );
  const dropoffRouteSide = routeSideStatus(
    requestedSlot,
    "dropoff",
    dropoffName,
    dropoffNameAr,
    dropoffProvenance,
  );
  const selected = selectOption(entry, activeQuotedRoute);
  const selectedService = String(entry?.selectedDeliveryType || selected.deliveryType || "").trim();
  const quotedPriceForSelected =
    selectedService && activeQuotedRoute?.pricesByType
      ? activeQuotedRoute.pricesByType[selectedService]
      : null;
  const selectedPrice = entry?.quotedPrice ?? selected.price;
  const selectedServiceInQuote =
    activeQuotedRoute && selectedService
      ? activeQuotedRoute.pricesByType?.[selectedService] != null
      : null;
  const selectedPriceMatchesQuote =
    activeQuotedRoute && selectedService && quotedPriceForSelected != null && selectedPrice != null
      ? Math.abs(Number(selectedPrice) - Number(quotedPriceForSelected)) <= 0.05
      : null;
  const routeLock = routeLockStatus(routeAuthorityActive, pickupRouteSide, dropoffRouteSide);
  const missingFields = computeSnapshotMissingFields({
    draft,
    entry,
    pickup: pickupRouteSide,
    dropoff: dropoffRouteSide,
  });
  const pendingEdits = activePendingOrderEdits(entry, now);
  const slotConflicts = collectSlotConflicts(dialogState);
  const conflictSlot = findFirstConflictSlot(dialogState);
  const routeAmbiguity = pendingRouteAmbiguity(pickupRouteSide, dropoffRouteSide);
  const coveragePending = input.coveragePending ?? null;
  const summaryShown = entry?.stage === "summary_shown" || entry?.stage === "awaiting_confirmation";
  const summaryAwaitingConfirmation =
    entry?.stage === "awaiting_confirmation" ||
    entry?.bookingStep === "awaiting_summary_confirmation";
  const currentSummaryHash = buildBookingSummaryHash({
    draft,
    pickup: pickupRouteSide,
    dropoff: dropoffRouteSide,
    selected,
    selectedService: selectedService || null,
  });
  const lastRenderedSummaryHash =
    String(entry?.lastRenderedSummaryHash || "").trim() || null;
  const summaryHashMatchesLastRendered = Boolean(
    currentSummaryHash &&
      lastRenderedSummaryHash &&
      currentSummaryHash === lastRenderedSummaryHash,
  );
  const requireRenderedSummaryHash = input.requireRenderedSummaryHash === true;
  const currentTurnDisposition = input.currentTurnDisposition ?? null;
  const submittedOrderUid = entry?.submittedOrderUid || null;
  const createdOrderUid = input.orderCreatedUid || input.sessionGuard?.lastCreatedOrderUid || null;
  const readiness = buildReadiness({
    missingFields,
    routeLock,
    pendingOrderEdits: pendingEdits,
    slotConflicts,
    selectedService: selectedService || null,
    selectedPrice,
    selectedServiceInQuote,
    selectedPriceMatchesQuote,
    summaryShown,
    summaryHashConfirmed: summaryHashMatchesLastRendered,
    requireRenderedSummaryHash,
  });
  const nextActionDecision = buildNextAction({
    stage: entry?.stage ?? null,
    routeLock,
    pendingRouteAmbiguity: routeAmbiguity,
    coveragePending,
    conflictSlot,
    pendingOrderEdits: pendingEdits,
    missingFields,
    readiness,
    summaryShown,
    summaryAwaitingConfirmation,
    summaryHashConfirmed: summaryHashMatchesLastRendered,
    requireRenderedSummaryHash,
    submittedOrderUid,
    createdOrderUid,
    selectedServiceInQuote,
    selectedPriceMatchesQuote,
    confirmationExplicit: input.confirmationExplicit === true,
    currentTurnDisposition,
  });
  const nextAction = nextActionDecision.action;
  const lifecycleState = lifecycleStateFromNextAction(nextAction);

  return {
    timing: input.timing,
    now,
    controllerState: entry,
    dialogState,
    stage: entry?.stage ?? null,
    bookingStep: entry?.bookingStep ?? null,
    draft,
    route: {
      pickup: pickupRouteSide,
      dropoff: dropoffRouteSide,
      quoteMatchesCanonicalRoute: routeMatchesEntry(activeQuotedRoute, entry),
      locked: routeAuthorityActive,
      lockStatus: routeLock,
      quoteBuiltFromAreaIds:
        Boolean(pickupRouteSide.quoteBuiltFromAreaIds) &&
        Boolean(dropoffRouteSide.quoteBuiltFromAreaIds),
    },
    lifecycleState,
    quote: {
      activeQuotedRoute,
      routeAuthorityActive,
      optionCatalog: activeQuotedRoute?.optionCatalog ?? [],
      validQuotedPrices: collectValidQuotedPrices(activeQuotedRoute),
      selected,
      selectedService: selectedService || null,
      selectedServiceInQuote,
      selectedPriceMatchesQuote,
    },
    missingFields,
    nextMissingField: missingFields[0] ?? null,
    addressSatisfaction: {
      pickup: hasSatisfiedAddress(draft, "pickup"),
      delivery: hasSatisfiedAddress(draft, "delivery"),
    },
    requestedSlot,
    requestedSlotOptions: requestedSlot?.options ? [...requestedSlot.options] : [],
    pendingOrderEdits: pendingEdits,
    conflictSlot,
    slotConflicts,
    pendingRouteAmbiguity: routeAmbiguity,
    coveragePending,
    currentTurnDisposition,
    blockedStateActions: nextActionDecision.blockedStateActions,
    summary: {
      shown: summaryShown,
      awaitingConfirmation: summaryAwaitingConfirmation,
      ready: readiness.summary.ready,
      blockers: readiness.summary.blockers,
      currentHash: currentSummaryHash,
      lastRenderedHash: lastRenderedSummaryHash,
      hashMatchesLastRendered: summaryHashMatchesLastRendered,
      hashRequiredForConfirmation: requireRenderedSummaryHash,
    },
    order: {
      submitted: entry?.stage === "order_submitted",
      submittedOrderUid,
      createdOrderUid,
      ready: readiness.order.ready,
      blockers: readiness.order.blockers,
    },
    readiness,
    nextAction,
  };
}
