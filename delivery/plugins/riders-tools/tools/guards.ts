// Guard hooks, session state, and intent gates.
//
// Extracted from plugins/riders-tools/index.ts as part of Wave 1a of the
// surgical plugin split. All bodies are unchanged from their original
// register()-scope position; they now live inside a `createGuardModule()`
// factory so the helpers (intentGates, recordGuardState) and runtime
// wiring (before/after_tool_call, globalThis.__ridersGuardState, GC
// timer) have explicit ownership.
//
// Contract:
//   const guards = createGuardModule({ buildRouteKey, buildBookableQuoteMapFromGetPricePayload });
//   // pass guards.helpers into deps (intentGates, booking, recordGuardState)
//   // ... register tools ...
//   guards.registerHooks(api);

import { createHash } from "node:crypto";
import {
  buildConversationControllerKey,
  CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS,
  extractTrackingOrderId,
  hasRouteEvidence,
  isExplicitOrderConfirmation,
  isBookingStartIntent,
  isGeneralServiceInquiry,
  isPassengerTransportRequest,
  isSimpleGreeting,
  normalizeIntentText,
  resolveSessionIdentityKey,
} from "../../shared/conversation-policy";
import {
  persistGuardSessionAliases,
  PersistedGuardSessionState,
} from "../../shared/guard-state";

type BookableDeliveryType = "sedan_normal" | "sedan_fast" | "van_normal" | "van_fast";

export interface GuardModuleDeps {
  buildRouteKey: (pickupArea: string | null | undefined, dropoffArea: string | null | undefined) => string | null;
  buildBookableQuoteMapFromGetPricePayload: (payload: any) => Partial<Record<BookableDeliveryType, number>>;
}

export interface GuardHelpers {
  // intent gates
  isCustomerOctopusContext: (ctx: any) => boolean;
  getVisibleCustomerText: (ctx: any) => string;
  getCustomerTurnActionHint: (ctx: any) => string;
  getNormalizedBookingAuthority: (ctx: any) => {
    stage: string;
    bookingStep: string;
    controller: any;
  };
  isActiveBookingFlow: (stage: string, bookingStep: string) => boolean;
  customerExplicitlyRequestsHuman: (text: string) => boolean;
  assignAgentReasonLooksLegitimate: (reason: string) => boolean;
  hasStrictTrackingOrderId: (text: string) => boolean;
  hasFreshLastQuotedRoute: (route: any) => boolean;
  getSessionFromCtx: (ctx: any) => { key: string; aliases: string[]; session: any };

  // booking-scope helpers (also used inside guard hooks)
  getDirectChatBookingBlockReason: (controller: any) => string | null;
  buildCanonicalCreateOrderParamsFromController: (
    controller: any,
    params: Record<string, unknown>,
  ) => Record<string, unknown> | null;
  buildPendingOrderFingerprint: (params: Record<string, unknown>) => string;
  isExplicitSummaryConfirmation: (text: string) => boolean;

  // guard-state recorder
  recordGuardState: (toolName: string, result: any, ctx: any) => Promise<void>;

  // price extraction (used by the global guard-state bridge)
  extractPricesFromText: (text: string) => string[];

  // raw session map (same reference passed into globalThis.__ridersGuardState)
  sessionState: Map<string, any>;
}

export interface GuardModule {
  helpers: GuardHelpers;
  registerHooks: (api: any) => void;
}

export function createGuardModule(moduleDeps: GuardModuleDeps): GuardModule {
  const { buildRouteKey, buildBookableQuoteMapFromGetPricePayload } = moduleDeps;

  // =========================================================================
  // HOOKS: Session state tracker + structured rendering enforcement
  //
  // Architecture:
  //   1. after_tool_call → records valid prices AND _customer_message from
  //      critical tools (get_price, create_simple_order, track_order)
  //   2. message_sending → enforces two rules:
  //      a) Prices in outbound messages must match a get_price result
  //      b) If a _customer_message was returned by the last tool, verify
  //         the outbound message contains the critical facts from it
  // =========================================================================

  interface QuotedRouteState {
    routeKey: string;
    pickupAreaNameAr: string;
    pickupAreaNameEn: string;
    dropoffAreaNameAr: string;
    dropoffAreaNameEn: string;
    pricesByType: Partial<Record<BookableDeliveryType, number>>;
    optionCatalog: Array<{
      delivery_type: string;
      label_ar: string;
      label_en: string;
      quoted_price: number | null;
      formatted_price: string | null;
      visibility: string | null;
      direct_chat_booking_status: string | null;
      direct_chat_booking_note: string | null;
    }>;
    serviceDiscovery: {
      default_prompt_ar: string | null;
      default_prompt_en: string | null;
    };
    quotedAt: number;
    quoteRef: string;
  }

  /** Per-session state for tool results and price validation. */
  interface SessionGuardState extends PersistedGuardSessionState {
    allValidPrices: Set<string>;         // every price (formatted "X.XXX") from get_price
    lastToolName: string | null;         // name of last critical tool call
    lastCustomerMessage: string | null;  // _customer_message from last tool result
    lastCustomerMessages: { ar: string | null; en: string | null };
    lastToolTs: number;                  // timestamp of last critical tool call
    lastQuotedRoute: QuotedRouteState | null;
    pendingOrderSummary: {
      fingerprint: string;
      createdAt: number;
    } | null;
  }

  const sessionState = new Map<string, SessionGuardState>();
  const FORBIDDEN_CUSTOMER_OCTOPUS_TOOLS = new Set(["message"]);

  const CRITICAL_TOOLS = new Set(["get_price", "create_simple_order", "track_order"]);

  function getVisibleCustomerText(ctx: any): string {
    return String(ctx?.BodyForAgent || ctx?.Body || ctx?.RawBody || "").trim();
  }

  function getCustomerIntentHint(ctx: any): string {
    return normalizeIntentText(ctx?.CustomerIntentHint || ctx?.customerIntentHint || "");
  }

  function getCustomerTurnActionHint(ctx: any): string {
    return normalizeIntentText(ctx?.CustomerTurnActionHint || ctx?.customerTurnActionHint || "");
  }

  function getConversationStageHint(ctx: any): string {
    return normalizeIntentText(ctx?.ConversationStageHint || ctx?.conversationStageHint || "");
  }

  function getBookingStepHint(ctx: any): string {
    const normalized = normalizeIntentText(ctx?.BookingStepHint || ctx?.bookingStepHint || "");
    return normalized === "none" ? "" : normalized;
  }

  function normalizeBookingStepValue(value: unknown): string {
    const normalized = normalizeIntentText(typeof value === "string" ? value : String(value || ""));
    return normalized === "none" ? "" : normalized;
  }

  function normalizeConversationStageValue(value: unknown): string {
    const normalized = normalizeIntentText(typeof value === "string" ? value : String(value || ""));
    return normalized === "none" ? "" : normalized;
  }

  function normalizeAddressPart(value: unknown): string {
    return String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/^(block|street|house|building)\s+/i, "")
      .trim();
  }

  // NOTE: This helper returns the mirrored conversation-controller entry
  // created by the octopus-channel plugin. Its real shape has many more
  // fields (selectedQuoteOptionDirectChatBookingStatus, bookingDraft sub-
  // objects, etc.) than we want to name statically here, so we widen the
  // return to `any` and rely on call-sites to guard access. That matches
  // how index.ts originally used the entry before the wave-1a extraction.
  function getMirroredConversationControllerEntry(ctx: any): any {
    const root = (globalThis as any).__ridersConversationControllerState;
    const entries = root?.entries;
    if (!(entries instanceof Map)) {
      return null;
    }
    const candidates = [
      ctx?.ControllerStateKey,
      ctx?.controllerStateKey,
      ctx?.SessionKey,
      ctx?.sessionKey,
      sessionKey(ctx),
      ctx?.ConversationId,
      ctx?.conversationId,
      ctx?.SenderId,
      ctx?.senderId,
      ctx?.replyTarget,
    ]
      .map((value) => String(value || "").trim())
      .filter(Boolean);
    for (const candidate of candidates) {
      const entry = entries.get(candidate);
      if (entry) {
        return entry;
      }
    }
    return null;
  }

  function getNormalizedBookingAuthority(ctx: any): {
    stage: string;
    bookingStep: string;
    controller: ReturnType<typeof getMirroredConversationControllerEntry>;
  } {
    const controller = getMirroredConversationControllerEntry(ctx);
    return {
      stage: getConversationStageHint(ctx) || normalizeConversationStageValue(controller?.stage || ""),
      bookingStep: getBookingStepHint(ctx) || normalizeBookingStepValue(controller?.bookingStep || ""),
      controller,
    };
  }

  function isActiveBookingFlow(stage: string, bookingStep: string): boolean {
    return (
      stage === "collecting_booking_details" ||
      stage === "summary_shown" ||
      stage === "awaiting_confirmation" ||
      bookingStep === "sender" ||
      bookingStep === "recipient" ||
      bookingStep === "pickup_address" ||
      bookingStep === "delivery_address" ||
      bookingStep === "summary_pending" ||
      bookingStep === "awaiting_summary_confirmation"
    );
  }

  function getDirectChatBookingBlockReason(
    controller: ReturnType<typeof getMirroredConversationControllerEntry> | null | undefined,
  ): string | null {
    const status = String(controller?.selectedQuoteOptionDirectChatBookingStatus || "").trim().toLowerCase();
    if (!status || status === "verified") {
      return null;
    }
    if (status === "manual_confirmation_required") {
      return "This selected delivery option requires manual confirmation before booking. Do not call create_simple_order for it in chat.";
    }
    if (status === "not_available") {
      return "This selected delivery option is not currently available for direct chat booking. Do not call create_simple_order for it in chat.";
    }
    return "This selected delivery option is not verified for direct chat booking right now. Do not call create_simple_order until the customer chooses a directly bookable option.";
  }

  function buildCanonicalCreateOrderParamsFromController(
    controller: ReturnType<typeof getMirroredConversationControllerEntry>,
    fallbackParams: Record<string, unknown>,
  ): Record<string, unknown> | null {
    const draft = controller?.bookingDraft || null;
    if (!controller || !draft) {
      return null;
    }
    const quotedPrice = Number(controller.quotedPrice ?? Number.NaN);
    const requiredValues = [
      controller.quotePickupAreaNameEn,
      controller.quoteDropoffAreaNameEn,
      controller.selectedDeliveryType,
      draft.senderName,
      draft.senderPhone,
      draft.recipientName,
      draft.recipientPhone,
    ];
    const pickupHasLocation =
      typeof draft.pickupLocation?.latitude === "number" &&
      Number.isFinite(draft.pickupLocation.latitude) &&
      typeof draft.pickupLocation?.longitude === "number" &&
      Number.isFinite(draft.pickupLocation.longitude);
    const deliveryHasLocation =
      typeof draft.deliveryLocation?.latitude === "number" &&
      Number.isFinite(draft.deliveryLocation.latitude) &&
      typeof draft.deliveryLocation?.longitude === "number" &&
      Number.isFinite(draft.deliveryLocation.longitude);
    const pickupHasTextAddress =
      String(draft.pickupBlock ?? "").trim() &&
      String(draft.pickupStreet ?? "").trim() &&
      String(draft.pickupHouse ?? "").trim();
    const deliveryHasTextAddress =
      String(draft.deliveryBlock ?? "").trim() &&
      String(draft.deliveryStreet ?? "").trim() &&
      String(draft.deliveryHouse ?? "").trim();
    if (
      requiredValues.some((value) => !String(value ?? "").trim()) ||
      !Number.isFinite(quotedPrice) ||
      (!pickupHasLocation && !pickupHasTextAddress) ||
      (!deliveryHasLocation && !deliveryHasTextAddress)
    ) {
      return null;
    }
    const pickupLocationLabel =
      [
        String(draft.pickupLocation?.name ?? "").trim(),
        String(draft.pickupLocation?.address ?? "").trim(),
      ].filter(Boolean).join(" — ") ||
      String(draft.pickupLocation?.resolvedAreaName ?? "").trim() ||
      (pickupHasLocation
        ? `${Number(draft.pickupLocation.latitude).toFixed(6)}, ${Number(draft.pickupLocation.longitude).toFixed(6)}`
        : "");
    const deliveryLocationLabel =
      [
        String(draft.deliveryLocation?.name ?? "").trim(),
        String(draft.deliveryLocation?.address ?? "").trim(),
      ].filter(Boolean).join(" — ") ||
      String(draft.deliveryLocation?.resolvedAreaName ?? "").trim() ||
      (deliveryHasLocation
        ? `${Number(draft.deliveryLocation.latitude).toFixed(6)}, ${Number(draft.deliveryLocation.longitude).toFixed(6)}`
        : "");
    return {
      ...fallbackParams,
      sender_name: String(draft.senderName),
      sender_phone: String(draft.senderPhone),
      recipient_name: String(draft.recipientName),
      recipient_phone: String(draft.recipientPhone),
      pickup_area: String(controller.quotePickupAreaNameEn),
      delivery_area: String(controller.quoteDropoffAreaNameEn),
      delivery_type: String(controller.selectedDeliveryType),
      quoted_price: quotedPrice,
      pickup_block: pickupHasLocation ? null : String(draft.pickupBlock),
      pickup_street: pickupHasLocation ? null : String(draft.pickupStreet),
      pickup_house: pickupHasLocation ? null : String(draft.pickupHouse),
      pickup_avenue: pickupHasLocation ? null : (draft.pickupAvenue ? String(draft.pickupAvenue) : null),
      pickup_extra: pickupHasLocation ? null : (draft.pickupExtra ? String(draft.pickupExtra) : null),
      pickup_notes: pickupHasLocation ? `Location pin shared by customer: ${pickupLocationLabel}` : fallbackParams.pickup_notes ?? null,
      pickup_latitude: pickupHasLocation ? Number(draft.pickupLocation.latitude) : null,
      pickup_longitude: pickupHasLocation ? Number(draft.pickupLocation.longitude) : null,
      delivery_block: deliveryHasLocation ? null : String(draft.deliveryBlock),
      delivery_street: deliveryHasLocation ? null : String(draft.deliveryStreet),
      delivery_house: deliveryHasLocation ? null : String(draft.deliveryHouse),
      delivery_avenue: deliveryHasLocation ? null : (draft.deliveryAvenue ? String(draft.deliveryAvenue) : null),
      delivery_extra: deliveryHasLocation ? null : (draft.deliveryExtra ? String(draft.deliveryExtra) : null),
      delivery_notes: deliveryHasLocation ? `Location pin shared by customer: ${deliveryLocationLabel}` : fallbackParams.delivery_notes ?? null,
      delivery_latitude: deliveryHasLocation ? Number(draft.deliveryLocation.latitude) : null,
      delivery_longitude: deliveryHasLocation ? Number(draft.deliveryLocation.longitude) : null,
    };
  }

  function getToolParams(event: any): Record<string, unknown> {
    const params = event?.params || event?.arguments || event?.args || {};
    return params && typeof params === "object" ? params : {};
  }

  function hasStrictTrackingOrderId(text: string): boolean {
    const normalized = String(text || "").trim().toUpperCase();
    return /\bORDER-[A-Z0-9]+(?:-[A-Z0-9]+)*\b/.test(normalized);
  }

  function customerExplicitlyRequestsHuman(text: string): boolean {
    const normalized = normalizeIntentText(text);
    if (!normalized) {
      return false;
    }
    return [
      "agent",
      "human",
      "support",
      "customer service",
      "representative",
      "someone call me",
      "refund",
      "complaint",
      "problem",
      "issue",
      "help me",
      "talk to support",
      "talk to agent",
      "handoff",
      "escalate",
      "موظف",
      "موظف الدعم",
      "الدعم",
      "خدمة العملاء",
      "ابي موظف",
      "أبي موظف",
      "ابي اكلم موظف",
      "أبي أكلم موظف",
      "شكوى",
      "مشكلة",
      "مساعدة",
    ].some((phrase) => normalized.includes(phrase));
  }

  function assignAgentReasonLooksLegitimate(reason: string): boolean {
    const normalized = normalizeIntentText(reason);
    if (!normalized) {
      return false;
    }
    return [
      "refund",
      "complaint",
      "human",
      "support",
      "agent",
      "manual",
      "confirmation",
      "system error",
      "payment",
      "modify",
      "change",
      "edit",
      "special request",
      "unsupported",
      "not available",
      "schedule",
      "reschedule",
      "tracking",
      "order id",
      "order number",
      "job application",
      "handoff",
      "escalat",
      "مشكلة",
      "شكوى",
      "موظف",
      "الدعم",
      "تأكيد يدوي",
      "تعديل",
      "استرجاع",
    ].some((phrase) => normalized.includes(phrase));
  }

  function blockTool(reason: string): never {
    throw new Error(reason);
  }

  function buildPendingOrderFingerprint(params: Record<string, unknown>): string {
    const normalized = {
      sender_name: String(params.sender_name ?? "").trim().toLowerCase(),
      sender_phone: String(params.sender_phone ?? "").replace(/\D/g, ""),
      recipient_name: String(params.recipient_name ?? "").trim().toLowerCase(),
      recipient_phone: String(params.recipient_phone ?? "").replace(/\D/g, ""),
      delivery_type: String(params.delivery_type ?? "").trim().toLowerCase(),
      quoted_price: Number(params.quoted_price ?? 0).toFixed(3),
      pickup_block: normalizeAddressPart(params.pickup_block),
      pickup_street: normalizeAddressPart(params.pickup_street),
      pickup_house: normalizeAddressPart(params.pickup_house),
      pickup_latitude: typeof params.pickup_latitude === "number" ? Number(params.pickup_latitude).toFixed(6) : "",
      pickup_longitude: typeof params.pickup_longitude === "number" ? Number(params.pickup_longitude).toFixed(6) : "",
      delivery_block: normalizeAddressPart(params.delivery_block),
      delivery_street: normalizeAddressPart(params.delivery_street),
      delivery_house: normalizeAddressPart(params.delivery_house),
      delivery_latitude: typeof params.delivery_latitude === "number" ? Number(params.delivery_latitude).toFixed(6) : "",
      delivery_longitude: typeof params.delivery_longitude === "number" ? Number(params.delivery_longitude).toFixed(6) : "",
    };
    return createHash("sha256").update(JSON.stringify(normalized)).digest("hex");
  }

  function isExplicitSummaryConfirmation(text: string): boolean {
    return isBookingStartIntent(text) || isExplicitOrderConfirmation(text);
  }

  function sessionKey(ctx: any): string {
    return resolveSessionIdentityKey(ctx);
  }

  function extractConversationIdFromCtx(ctx: any): string {
    const direct = String(ctx?.ConversationId || ctx?.conversationId || "").trim();
    if (direct) {
      return direct;
    }
    const to = String(ctx?.To || ctx?.to || "").trim();
    if (to.startsWith("octopus:")) {
      return to.slice("octopus:".length).trim();
    }
    return "";
  }

  function buildControllerStateKeyFromCtx(ctx: any): string {
    const explicit = String(ctx?.ControllerStateKey || ctx?.controllerStateKey || "").trim();
    if (explicit) {
      return explicit;
    }
    const sessionKeyValue = String(ctx?.SessionKey || ctx?.sessionKey || "").trim();
    const sessionConversationIdMatch = sessionKeyValue.match(/:octopus:direct:(.+?)(?:::prompt=|$)/);
    const accountId = String(ctx?.AccountId || ctx?.accountId || "default").trim();
    const conversationId = extractConversationIdFromCtx(ctx) || String(sessionConversationIdMatch?.[1] || "").trim();
    if (accountId && conversationId) {
      return buildConversationControllerKey(accountId, conversationId);
    }
    return "";
  }

  function getSessionAliases(ctx: any): string[] {
    const aliases = new Set<string>();
    const primary = sessionKey(ctx);
    const canonical = buildControllerStateKeyFromCtx(ctx);
    const sessionKeyValue = String(ctx?.SessionKey || ctx?.sessionKey || "").trim();
    const conversationId = extractConversationIdFromCtx(ctx);
    const replyTarget = String(ctx?.replyTarget || ctx?.ReplyTarget || ctx?.SenderId || ctx?.senderId || "").trim();
    for (const value of [canonical, primary, sessionKeyValue, conversationId, replyTarget]) {
      const normalized = String(value || "").trim();
      if (normalized) {
        aliases.add(normalized);
      }
    }
    return [...aliases];
  }

  function isCustomerOctopusContext(ctx: any): boolean {
    const surface = String(ctx?.Surface || ctx?.surface || ctx?.Provider || ctx?.provider || "").toLowerCase();
    const originatingChannel = String(ctx?.OriginatingChannel || ctx?.originatingChannel || "").toLowerCase();
    const from = String(ctx?.From || ctx?.from || "");
    const label = String(ctx?.ConversationLabel || ctx?.conversationLabel || "");
    if (ctx?.requesterSenderId) {
      return false;
    }
    return (
      (surface === "octopus" || originatingChannel === "octopus" || from.startsWith("octopus:")) &&
      label.startsWith("customer:")
    );
  }

  function getSession(key: string): SessionGuardState {
    let s = sessionState.get(key);
    if (!s) {
      s = {
        allValidPrices: new Set(),
        lastToolName: null,
        lastCustomerMessage: null,
        lastCustomerMessages: { ar: null, en: null },
        lastToolTs: 0,
        lastQuotedRoute: null,
        pendingOrderSummary: null,
      };
      sessionState.set(key, s);
    }
    return s;
  }

  function getSessionFromCtx(ctx: any): { key: string; aliases: string[]; session: SessionGuardState } {
    const aliases = getSessionAliases(ctx);
    for (const alias of aliases) {
      const existing = sessionState.get(alias);
      if (existing) {
        for (const nextAlias of aliases) {
          sessionState.set(nextAlias, existing);
        }
        return { key: aliases[0] || alias, aliases, session: existing };
      }
    }
    const key = aliases[0] || sessionKey(ctx);
    const session = getSession(key);
    for (const alias of aliases) {
      sessionState.set(alias, session);
    }
    return { key, aliases, session };
  }

  function hasFreshLastQuotedRoute(route: QuotedRouteState | null | undefined): boolean {
    return !!route?.quotedAt && (Date.now() - route.quotedAt) <= CONVERSATION_CONTROLLER_QUOTE_WINDOW_MS;
  }

  /** Parse tool result to extract _customer_message and prices. */
  function parseToolResult(rawResult: unknown): {
    customerMessage: string | null;
    customerMessages: { ar: string | null; en: string | null };
    prices: string[];
    quotedRoute: Omit<QuotedRouteState, "quotedAt" | "quoteRef"> | null;
    createdOrderUid: string | null;
  } {
    let data: any = rawResult;
    try {
      // Unwrap OpenClaw tool result wrapper: { content: [{ type: "text", text: "..." }] }
      if (data?.content && Array.isArray(data.content)) {
        for (const item of data.content) {
          if (item?.type === "text" && typeof item.text === "string") {
            try { data = JSON.parse(item.text); } catch { /* not JSON */ }
          }
        }
      }
      if (data?.details) data = data.details;
    } catch { /* ignore */ }

    const customerMessage: string | null =
      (typeof data?._customer_message === "string" && data._customer_message) || null;
    const customerMessages = {
      ar: (typeof data?._customer_message_ar === "string" && data._customer_message_ar) || null,
      en: (typeof data?._customer_message_en === "string" && data._customer_message_en) || null,
    };

    const routeKey = buildRouteKey(data?.route?.pickup?.name_en, data?.route?.dropoff?.name_en);
    const quoteMap = buildBookableQuoteMapFromGetPricePayload(data);
    const optionCatalog = [
      data?.recommended_customer_quote && {
        delivery_type: data.recommended_customer_quote.delivery_type,
        label_ar: data.recommended_customer_quote.label_ar,
        label_en: data.recommended_customer_quote.label_en,
        quoted_price:
          typeof data.recommended_customer_quote.quoted_price === "number"
            ? data.recommended_customer_quote.quoted_price
            : null,
        formatted_price:
          typeof data.recommended_customer_quote.formatted_price === "string"
            ? data.recommended_customer_quote.formatted_price
            : null,
        visibility: "default",
        direct_chat_booking_status:
          typeof data.recommended_direct_chat_booking_option?.delivery_type === "string" &&
          data.recommended_direct_chat_booking_option.delivery_type === data.recommended_customer_quote.delivery_type
            ? "verified"
            : typeof data.recommended_customer_quote.available_for_direct_chat_booking === "boolean"
              ? (data.recommended_customer_quote.available_for_direct_chat_booking ? "verified" : "unknown")
              : null,
        direct_chat_booking_note:
          typeof data.recommended_customer_quote.note === "string" ? data.recommended_customer_quote.note : null,
      },
      ...(Array.isArray(data?.other_options_if_customer_asks)
        ? data.other_options_if_customer_asks.map((option: any) => ({
            delivery_type: String(option?.delivery_type || ""),
            label_ar: String(option?.label_ar || ""),
            label_en: String(option?.label_en || ""),
            quoted_price: typeof option?.quoted_price === "number" ? option.quoted_price : null,
            formatted_price: typeof option?.formatted_price === "string" ? option.formatted_price : null,
            visibility: typeof option?.visibility === "string" ? option.visibility : null,
            direct_chat_booking_status:
              typeof option?.direct_chat_booking_status === "string" ? option.direct_chat_booking_status : null,
            direct_chat_booking_note:
              typeof option?.direct_chat_booking_note === "string" ? option.direct_chat_booking_note : null,
          }))
        : []),
    ].filter(
      (option): option is NonNullable<typeof option> =>
        Boolean(option && option.delivery_type && option.label_ar && option.label_en),
    );
    const serviceDiscovery = {
      default_prompt_ar:
        typeof data?.service_discovery?.default_prompt_ar === "string"
          ? data.service_discovery.default_prompt_ar
          : null,
      default_prompt_en:
        typeof data?.service_discovery?.default_prompt_en === "string"
          ? data.service_discovery.default_prompt_en
          : null,
    };
    const quotedRoute =
      routeKey &&
      data?.route?.pickup?.name_en &&
      data?.route?.dropoff?.name_en &&
      Object.keys(quoteMap).length > 0
        ? {
            routeKey,
            pickupAreaNameAr: data.route.pickup.name_ar,
            pickupAreaNameEn: data.route.pickup.name_en,
            dropoffAreaNameAr: data.route.dropoff.name_ar,
            dropoffAreaNameEn: data.route.dropoff.name_en,
            pricesByType: quoteMap,
            optionCatalog,
            serviceDiscovery,
          }
        : null;

    const prices: string[] = [];
    try {
      if (data?.default_quote?.price != null) {
        prices.push(Number(data.default_quote.price).toFixed(3));
      }
      if (data?.recommended_customer_quote?.quoted_price != null) {
        prices.push(Number(data.recommended_customer_quote.quoted_price).toFixed(3));
      }
      if (data?.validated_quoted_price != null) {
        prices.push(Number(data.validated_quoted_price).toFixed(3));
      }
      if (Array.isArray(data?.other_options_if_customer_asks)) {
        for (const opt of data.other_options_if_customer_asks) {
          if (opt?.quoted_price != null) prices.push(Number(opt.quoted_price).toFixed(3));
        }
      }
    } catch { /* ignore */ }

    // create_simple_order puts the placed order under `order` (and also under
    // details.raw_create.data.order when the full server payload survives).
    // Grab the uid defensively from both spots so downstream code can key off
    // it when the stage transitions to "order_submitted".
    let createdOrderUid: string | null = null;
    try {
      const candidate =
        (typeof data?.order?.uid === "string" && data.order.uid) ||
        (typeof data?.raw_create?.data?.order?.uid === "string" && data.raw_create.data.order.uid) ||
        (typeof data?.order_uid === "string" && data.order_uid) ||
        null;
      if (candidate) createdOrderUid = String(candidate).trim() || null;
    } catch { /* ignore */ }

    return { customerMessage, customerMessages, prices, quotedRoute, createdOrderUid };
  }

  /** Extract KWD prices from message text. Returns "X.XXX" strings. */
  function extractPricesFromText(text: string): string[] {
    const out: string[] = [];
    const re = /(\d{1,3}(?:\.\d{1,3})?)\s*(?:د\.ك|KWD|KD)/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      out.push(Number(m[1]).toFixed(3));
    }
    return out;
  }

  // --- before_tool_call: hard-block generic outbound tools for customer Octopus chats ---
  function beforeToolCall(event: any, ctx: any) {
    const toolName = String(event?.toolName || "");
    if (isCustomerOctopusContext(ctx)) {
      const visibleText = getVisibleCustomerText(ctx);
      const intentHint = getCustomerIntentHint(ctx);
      const actionHint = getCustomerTurnActionHint(ctx);
      const bookingAuthority = getNormalizedBookingAuthority(ctx);
      const stageHint = bookingAuthority.stage;
      const bookingStepHint = bookingAuthority.bookingStep;
      const toolParams = getToolParams(event);
      if (toolName === "get_price") {
        const currentSession = getSessionFromCtx(ctx).session;
        const explicitLanguageHint = Boolean(ctx?.ExplicitLanguageHint || ctx?.explicitLanguageHint);
        const looksLikeGreeting = isSimpleGreeting(visibleText);
        const looksLikePassengerTransport = isPassengerTransportRequest(visibleText);
        const looksLikeBookingStartFromQuotedState =
          stageHint === "quoted" &&
          hasFreshLastQuotedRoute(currentSession.lastQuotedRoute) &&
          (actionHint === "start booking" || isBookingStartIntent(visibleText));
        const sameQuotedRouteWithoutNewRoute =
          stageHint === "quoted" &&
          hasFreshLastQuotedRoute(currentSession.lastQuotedRoute) &&
          !hasRouteEvidence(visibleText) &&
          !extractTrackingOrderId(visibleText) &&
          !looksLikeGreeting &&
          !looksLikePassengerTransport &&
          !explicitLanguageHint &&
          !looksLikeBookingStartFromQuotedState &&
          actionHint !== "pricing request";
        if (sameQuotedRouteWithoutNewRoute) {
          console.log(
            `[intent-gate] blocked get_price same_quoted_route_followup session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            "Do not call get_price again when there is already an active quoted route and the customer did not provide a new route in this turn. Answer from the stored quote and service options for that same route instead. Only call get_price again if the customer clearly changes pickup or dropoff.",
          );
        }
        const broadServiceQuestion =
          isGeneralServiceInquiry(visibleText) && !hasRouteEvidence(visibleText);
        if (broadServiceQuestion) {
          console.log(
            `[intent-gate] blocked get_price broad_service intent=${intentHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            "Do not call get_price for a broad service overview question. Answer with the available Riders service categories first, and only quote a route if the customer clearly asks for pricing on a specific route.",
          );
        }
        if (
          looksLikeGreeting ||
          explicitLanguageHint ||
          looksLikePassengerTransport ||
          actionHint === "tracking missing id" ||
          actionHint === "passenger transport request" ||
          actionHint === "service overview" ||
          actionHint === "same route quote option" ||
          actionHint === "same route show other options" ||
          actionHint === "booking step input" ||
          looksLikeBookingStartFromQuotedState ||
          isActiveBookingFlow(stageHint, bookingStepHint)
        ) {
          console.log(
            `[intent-gate] blocked get_price intent=${intentHint} stage=${stageHint || "unknown"} bookingStep=${bookingStepHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            "Do not call get_price during the booking collection or summary-confirmation flow. Continue the current booking step instead.",
          );
        }
        console.log(
          `[intent-gate] allow get_price intent=${intentHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
        );
      }

      if (toolName === "track_order") {
        const providedOrderId = String(toolParams.order_id || "");
        const visibleOrderId = extractTrackingOrderId(visibleText);
        const hasValidOrderId =
          hasStrictTrackingOrderId(providedOrderId) ||
          hasStrictTrackingOrderId(visibleOrderId || "");
        if (!hasValidOrderId || actionHint === "tracking missing id") {
          console.log(
            `[intent-gate] blocked track_order intent=${intentHint || "unknown"} stage=${stageHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            "Do not call track_order until the customer has provided a valid order number starting with ORDER-. If they are asking about tracking without an order number, ask for it first.",
          );
        }
      }

      if (toolName === "create_simple_order") {
        const awaitingConfirmation =
          stageHint === "awaiting_confirmation" ||
          bookingStepHint === "awaiting_summary_confirmation";
        if (!awaitingConfirmation) {
          console.log(
            `[intent-gate] blocked create_simple_order booking_step=${bookingStepHint || "unknown"} stage=${stageHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            `Do not call create_simple_order during the ${(bookingStepHint || stageHint || "current").replace(/_/g, " ")} booking step. Continue collecting the missing booking details first.`,
          );
        }
        if (actionHint !== "confirm summary" && !isExplicitSummaryConfirmation(visibleText)) {
          console.log(
            `[intent-gate] blocked create_simple_order awaiting_confirmation intent=${intentHint || "unknown"} stage=${stageHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} text=${JSON.stringify(visibleText.slice(0, 120))}`,
          );
          blockTool(
            "Do not call create_simple_order until the customer explicitly confirms the final order summary you already showed. Ask for confirmation instead.",
          );
        }
        const directChatBlockReason = getDirectChatBookingBlockReason(bookingAuthority.controller);
        if (directChatBlockReason) {
          console.log(
            `[intent-gate] blocked create_simple_order direct_chat_unavailable status=${String(bookingAuthority.controller?.selectedQuoteOptionDirectChatBookingStatus || "unknown")} session=${sessionKey(ctx).slice(0, 32)}`,
          );
          blockTool(directChatBlockReason);
        }
        const canonicalParams = buildCanonicalCreateOrderParamsFromController(
          bookingAuthority.controller,
          toolParams,
        );
        if (!canonicalParams) {
          console.log(
            `[intent-gate] blocked create_simple_order incomplete_controller intent=${intentHint || "unknown"} stage=${stageHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)}`,
          );
          blockTool(
            "Do not call create_simple_order until the canonical booking controller has the confirmed sender, recipient, address, service, and price fields ready.",
          );
        }
      }

      if (toolName === "assign_agent") {
        const reason = String(toolParams.reason || "");
        const explicitHumanRequest = customerExplicitlyRequestsHuman(visibleText);
        const legitimateReason = assignAgentReasonLooksLegitimate(reason);
        const interpreterWantsHandoff = actionHint === "handoff";
        const quotedBookingFollowup =
          stageHint === "quoted" && (actionHint === "start booking" || isBookingStartIntent(visibleText));
        const activeBookingCollection =
          isActiveBookingFlow(stageHint, bookingStepHint);
        const trackingFallbackReason =
          normalizeIntentText(reason).includes("tracking") ||
          normalizeIntentText(reason).includes("order id") ||
          normalizeIntentText(reason).includes("order number");
        const hasVisibleTrackingId = hasStrictTrackingOrderId(extractTrackingOrderId(visibleText) || "");
        if (
          (activeBookingCollection && !explicitHumanRequest && !interpreterWantsHandoff) ||
          (quotedBookingFollowup && !explicitHumanRequest && !legitimateReason && !interpreterWantsHandoff) ||
          (actionHint === "tracking missing id" && !explicitHumanRequest) ||
          (actionHint === "booking step input" && !explicitHumanRequest) ||
          (trackingFallbackReason && !hasVisibleTrackingId && !explicitHumanRequest)
        ) {
          console.log(
            `[intent-gate] blocked assign_agent intent=${intentHint || "unknown"} stage=${stageHint || "unknown"} bookingStep=${bookingStepHint || "unknown"} session=${sessionKey(ctx).slice(0, 32)} reason=${JSON.stringify(reason.slice(0, 160))}`,
          );
          blockTool(
            "Do not escalate to a human here. Continue the current booking flow unless the customer explicitly asked for human support or there is a real unsupported/manual-confirmation/system-error case.",
          );
        }
      }
    }
    if (!FORBIDDEN_CUSTOMER_OCTOPUS_TOOLS.has(toolName)) {
      return;
    }
    if (!isCustomerOctopusContext(ctx)) {
      return;
    }
    blockTool(
      `Tool ${toolName} is disabled for customer Octopus conversations. Reply with normal assistant text and let the Octopus channel deliver it.`,
    );
  }

  async function recordGuardState(toolName: string, result: any, ctx: any): Promise<void> {
    if (!CRITICAL_TOOLS.has(toolName)) return;
    const { key, aliases, session } = getSessionFromCtx(ctx);
    const { customerMessage, customerMessages, prices, quotedRoute, createdOrderUid } = parseToolResult(result);

    session.lastToolName = toolName;
    session.lastToolTs = Date.now();
    session.lastCustomerMessage = customerMessage;
    session.lastCustomerMessages = customerMessages;

    for (const p of prices) session.allValidPrices.add(p);

    if (toolName === "get_price" && quotedRoute) {
      session.lastQuotedRoute = {
        ...quotedRoute,
        quotedAt: session.lastToolTs,
        quoteRef: `${quotedRoute.routeKey}:${session.lastToolTs}`,
      };
      session.pendingOrderSummary = null;
    }

    if (toolName === "create_simple_order") {
      session.pendingOrderSummary = null;
      if (createdOrderUid) {
        (session as any).lastCreatedOrderUid = createdOrderUid;
        try {
          console.log(
            `[post-order] captured order_uid=${createdOrderUid} session=${key.slice(0, 16)}...`,
          );
        } catch {}
      }
    }

    const bareConversationId = extractConversationIdFromCtx(ctx);
    if (bareConversationId && bareConversationId !== key) {
      sessionState.set(bareConversationId, session);
    }
    const controllerKey = buildControllerStateKeyFromCtx(ctx);
    if (controllerKey && controllerKey !== key && controllerKey !== bareConversationId) {
      sessionState.set(controllerKey, session);
    }
    const persistAliases = new Set<string>(aliases);
    if (key) persistAliases.add(key);
    if (bareConversationId) persistAliases.add(bareConversationId);
    if (controllerKey) persistAliases.add(controllerKey);
    await persistGuardSessionAliases([...persistAliases], session);

    if (customerMessage) {
      console.log(`[guard] Recorded _customer_message from ${toolName} for session ${key.slice(0, 12)}... aliases=[${bareConversationId || ""}, ${controllerKey || ""}]`);
    }
  }



  (globalThis as any).__ridersGuardState = {
    sessionState,
    extractPricesFromText,
  };

  function registerHooks(api: any): void {
    api.on("before_tool_call", beforeToolCall);
    api.on("after_tool_call", (event: any, ctx: any) => {
      void recordGuardState(event.toolName as string, event.result, ctx);
    });
    setInterval(() => {
      const cutoff = Date.now() - 3_600_000;
      for (const [key, s] of sessionState) {
        if (s.lastToolTs < cutoff) sessionState.delete(key);
      }
    }, 600_000);
  }

  return {
    helpers: {
      isCustomerOctopusContext,
      getVisibleCustomerText,
      getCustomerTurnActionHint,
      getNormalizedBookingAuthority,
      isActiveBookingFlow,
      customerExplicitlyRequestsHuman,
      assignAgentReasonLooksLegitimate,
      hasStrictTrackingOrderId,
      hasFreshLastQuotedRoute,
      getSessionFromCtx,
      getDirectChatBookingBlockReason,
      buildCanonicalCreateOrderParamsFromController,
      buildPendingOrderFingerprint,
      isExplicitSummaryConfirmation,
      recordGuardState,
      extractPricesFromText,
      sessionState,
    },
    registerHooks,
  };
}
