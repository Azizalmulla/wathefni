// Booking / order tools.
//
// Extracted from plugins/riders-tools/index.ts as part of Wave 1a of the
// surgical plugin split. Tool bodies are unchanged; they pull shared
// state and helpers from the `deps` bundle instead of relying on
// register()-scope closures in index.ts.
//
// Tools registered:
//   - track_order
//   - create_simple_order
//   - create_order
//   - pay_order
//   - cancel_order
//   - shadow_extract_booking_fields
//   - apply_booking_field
//   - start_booking
//   - confirm_summary
//   - cancel_booking
//   - request_handoff
//   - offers

import {
  extractTrackingOrderId,
  isExplicitOrderConfirmation,
} from "../../shared/conversation-policy";
import {
  pushResponderStateOp,
  ResponderStateOp,
  ResponderBookingFieldOp,
  validateApplyBookingFieldOp,
  sanityCheckBookingDraft,
} from "../../shared/responder-state-ops";
import {
  guardCreateSimpleOrder,
  describeRejection,
} from "../../shared/order-guard";
import { looksLikeInteriorDetail } from "../../shared/booking-draft";

import type { ToolDeps } from "./deps";

type BookableDeliveryType = "sedan_normal" | "sedan_fast" | "van_normal" | "van_fast";
type RidersGridLiveSettingsSummary = any;

export function registerBookingTools(api: any, deps: ToolDeps): void {
  const { intentGates, quoting, recordGuardState } = deps;
  const {
    isCustomerOctopusContext,
    getVisibleCustomerText,
    getCustomerTurnActionHint,
    getNormalizedBookingAuthority,
    getSessionFromCtx,
    hasStrictTrackingOrderId,
    customerExplicitlyRequestsHuman,
  } = intentGates;
  const {
    resolvePricingAreaQuery,
    resolveAreaForOrdering,
    getCommonShippingMethods,
    selectShippingMethod,
    createAreaSuggestionResult,
    createAreaNotFoundResult,
    createAreaClarificationResult,
    formatPrice,
  } = quoting;
  const { loadPricing } = deps.pricing;
  const {
    resolveToolConversationId,
    resolveToolTurnId,
    asOptionalTrimmedString,
    splitFullName,
    buildAddressPayload,
    pricesMatch,
    getRouteSheetPrice,
    isOrderCreationBlockedByLiveMaintenance,
    buildCreateOrderMaintenanceResult,
    loadRidersGridLiveSettingsSummary,
    assertWriteActionsEnabled,
    assertValidFleetrunnrOrderId,
    fleetrunnrRequest,
    normalizeFleetrunnrTracking,
    ridersRequest,
    ridersFormDataRequest,
    normalizeOrder,
    validateCreateSimpleOrderPreflight,
    getDirectChatBookingBlockReason,
    buildCanonicalCreateOrderParamsFromController,
    buildPendingOrderFingerprint,
    isExplicitSummaryConfirmation,
    getTrackingProvider,
    getActiveOffers,
    isRidersOneBrainEnabled,
    RidersApiError,
  } = deps.booking;
  const { createTextResult, errorPayload, isRecord } = deps;

  // Local aliases so the re-pasted block sees the register()-scope names it
  // used originally. These are live getters/values (not copies) so ONE_BRAIN
  // / tracking-provider / offers updates stay in sync with the parent module.
  const trackingProvider = getTrackingProvider();
  const RIDERS_ONE_BRAIN_ENABLED = isRidersOneBrainEnabled();
  const activeOffers = getActiveOffers();

  // =========================================================================
  // TOOL: track_order — STUB (read-only API call, safe but not wired yet)
  // =========================================================================
  api.registerTool({
    name: "track_order",
    label: "Track Order",
    description:
      "Retrieve the current status of a customer's delivery order using the order ID. Returns order status, driver info, and estimated delivery time. The order ID will be sanitized automatically (e.g. trailing # or spaces are stripped).",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        order_id: {
          type: "string",
          description: "The order ID or tracking number provided by the customer",
        },
      },
      required: ["order_id"],
    },

    async execute(_toolCallId: string, params: { order_id: string }, ctx?: any) {
      try {
        if (ctx && isCustomerOctopusContext(ctx)) {
          const visibleText = getVisibleCustomerText(ctx);
          const actionHint = getCustomerTurnActionHint(ctx);
          const providedOrderId = String(params.order_id || "");
          const visibleOrderId = extractTrackingOrderId(visibleText);
          const hasValidOrderId =
            hasStrictTrackingOrderId(providedOrderId) ||
            hasStrictTrackingOrderId(visibleOrderId || "");
          if (!hasValidOrderId || actionHint === "tracking missing id") {
            console.log(`[intent-gate-exec] blocked track_order no_valid_order_id`);
            throw new Error(
              "Do not call track_order until the customer has provided a valid order number starting with ORDER-. If they are asking about tracking without an order number, ask for it first.",
            );
          }
        }

        const rawOrderId = asOptionalTrimmedString(params.order_id);
        if (!rawOrderId) {
          throw new Error("order_id is required");
        }

        const normalizedMatch = rawOrderId.toUpperCase().match(/\bORDER-[A-Z0-9]+(?:-[A-Z0-9]+)*\b/);
        if (!normalizedMatch) {
          throw new Error("A valid ORDER-... ID is required.");
        }
        const orderId = normalizedMatch[0];

        const shouldUseFleetrunnr =
          trackingProvider === "fleetrunnr" || /^order-[a-z0-9-]+$/i.test(orderId);

        if (shouldUseFleetrunnr) {
          const normalizedOrderId = orderId.toUpperCase();
          assertValidFleetrunnrOrderId(normalizedOrderId);
          const payload = await fleetrunnrRequest(
            "GET",
            `/orders?external_id=${encodeURIComponent(normalizedOrderId)}`,
          );
          const tracking = normalizeFleetrunnrTracking(payload, normalizedOrderId);

          const trackMsgAr =
            `رقم الطلب: ${tracking.order_id}\n` +
            `الحالة: ${tracking.status || "غير معروفة"}\n` +
            (tracking.tracking_url ? `رابط التتبع: ${tracking.tracking_url}\n` : "") +
            (tracking.agent_phone_number ? `رقم السائق: ${tracking.agent_phone_number}\n` : "");
          const trackMsgEn =
            `Order status: ${tracking.order_id}\n` +
            `Status: ${tracking.status || "Unknown"}\n` +
            (tracking.tracking_url ? `Tracking: ${tracking.tracking_url}\n` : "") +
            (tracking.agent_phone_number ? `Driver: ${tracking.agent_phone_number}\n` : "");

          const toolResult = createTextResult(
            {
              status: "ok",
              provider: "fleetrunnr",
              order_id: tracking.order_id,
              message:
                (isRecord(payload) && asOptionalTrimmedString(payload.message)) ||
                "Order tracking retrieved successfully.",
              tracking,
              _customer_message: trackMsgEn,
              _customer_message_ar: trackMsgAr,
              _customer_message_en: trackMsgEn,
              _instruction: "RELAY the _customer_message to the customer as-is. You may adjust the language to match the conversation but you MUST keep the exact order ID, status, tracking URL, and driver number unchanged.",
            },
            {
              raw: payload,
              tracking,
            },
          );
          await recordGuardState("track_order", toolResult, ctx);
          return toolResult;
        }

        const payload = await ridersRequest(
          "GET",
          `/orders/${encodeURIComponent(orderId)}`,
        );
        const order = normalizeOrder(payload.data?.order);

        const ridersTrackMsgAr =
          `رقم الطلب: ${orderId}\n` +
          `الحالة: ${order?.status || "غير معروفة"}\n` +
          (order?.total ? `المبلغ: ${order.total} KWD\n` : "");
        const ridersTrackMsgEn =
          `Order status: ${orderId}\n` +
          `Status: ${order?.status || "Unknown"}\n` +
          (order?.total ? `Total: ${order.total} KWD\n` : "");

        const toolResult = createTextResult(
          {
            status: "ok",
            provider: "riders",
            order_id: orderId,
            message: payload.message || "Order retrieved successfully.",
            order,
            _customer_message: ridersTrackMsgEn,
            _customer_message_ar: ridersTrackMsgAr,
            _customer_message_en: ridersTrackMsgEn,
            _instruction: "RELAY the _customer_message to the customer as-is. You may adjust the language to match the conversation but you MUST keep the exact order ID, status, and amounts unchanged.",
          },
          {
            raw: payload,
            order,
          },
        );
        await recordGuardState("track_order", toolResult, ctx);
        return toolResult;
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  });

  api.registerTool((ctx: any) => ({
    name: "create_simple_order",
    label: "Create Simple Order",
    description:
      "Create a Riders order via the Grid API from chat-friendly fields such as area names, customer names, phones, and address details (block, street, house). The Grid backend resolves shipping methods and coordinates automatically. Requires the exact accepted quoted price for the selected delivery type and rejects mismatches against sheet pricing. If payer is null it defaults to sender. Returns the created order and payment link when available. This tool is disabled unless WRITE_ACTIONS_ENABLED is true.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        sender_name: { type: "string" },
        sender_phone: { type: "string" },
        recipient_name: { type: "string" },
        recipient_phone: { type: "string" },
        payer: {
          type: ["string", "null"],
          enum: ["sender", "recipient", null],
        },
        pickup_area: { type: "string" },
        delivery_area: { type: "string" },
        delivery_type: {
          type: "string",
          enum: ["sedan_normal", "sedan_fast", "van_normal", "van_fast"],
        },
        quoted_price: { type: "number" },
        payment_method: {
          type: ["string", "null"],
          enum: ["tap", "card", "knet", "apple_pay", null],
        },
        pickup_block: { type: ["string", "null"] },
        pickup_street: { type: ["string", "null"] },
        pickup_house: { type: ["string", "null"] },
        pickup_avenue: { type: ["string", "null"], description: "Kuwait 'جادة / jadda / jedda / avenue' value if the customer provided one." },
        pickup_extra: { type: ["string", "null"], description: "Free-form extra pickup detail: floor, apartment, landmark, etc." },
        pickup_notes: { type: ["string", "null"] },
        pickup_latitude: { type: ["number", "null"] },
        pickup_longitude: { type: ["number", "null"] },
        delivery_block: { type: ["string", "null"] },
        delivery_street: { type: ["string", "null"] },
        delivery_house: { type: ["string", "null"] },
        delivery_avenue: { type: ["string", "null"], description: "Kuwait 'جادة / jadda / jedda / avenue' value if the customer provided one." },
        delivery_extra: { type: ["string", "null"], description: "Free-form extra delivery detail: floor, apartment, landmark, etc." },
        delivery_notes: { type: ["string", "null"] },
        delivery_latitude: { type: ["number", "null"] },
        delivery_longitude: { type: ["number", "null"] },
        schedule_date: { type: ["string", "null"] },
        coupon: { type: ["string", "null"] },
      },
      required: [
        "sender_name",
        "sender_phone",
        "recipient_name",
        "recipient_phone",
        "payer",
        "pickup_area",
        "delivery_area",
        "delivery_type",
        "quoted_price",
        "payment_method",
        "pickup_block",
        "pickup_street",
        "pickup_house",
        "pickup_avenue",
        "pickup_extra",
        "pickup_notes",
        "pickup_latitude",
        "pickup_longitude",
        "delivery_block",
        "delivery_street",
        "delivery_house",
        "delivery_avenue",
        "delivery_extra",
        "delivery_notes",
        "delivery_latitude",
        "delivery_longitude",
        "schedule_date",
        "coupon",
      ],
    },

    async execute(
      _toolCallId: string,
      params: {
        sender_name: string;
        sender_phone: string;
        recipient_name: string;
        recipient_phone: string;
        payer?: "sender" | "recipient" | null;
        pickup_area: string;
        delivery_area: string;
        delivery_type: BookableDeliveryType;
        quoted_price: number;
        payment_method?: "tap" | "card" | "knet" | "apple_pay" | null;
        pickup_block?: string | null;
        pickup_street?: string | null;
        pickup_house?: string | null;
        pickup_avenue?: string | null;
        pickup_extra?: string | null;
        pickup_notes?: string | null;
        pickup_latitude?: number | null;
        pickup_longitude?: number | null;
        delivery_block?: string | null;
        delivery_street?: string | null;
        delivery_house?: string | null;
        delivery_avenue?: string | null;
        delivery_extra?: string | null;
        delivery_notes?: string | null;
        delivery_latitude?: number | null;
        delivery_longitude?: number | null;
        schedule_date?: string | null;
        coupon?: string | null;
      },
    ) {
      try {
        assertWriteActionsEnabled();
        const currentSession = getSessionFromCtx(ctx).session;
        const visibleText = getVisibleCustomerText(ctx);
        const authority = getNormalizedBookingAuthority(ctx);
        if (isCustomerOctopusContext(ctx)) {
          // ONE_BRAIN path: trust the LLM's passed params; validate via the
          // order-guard against the live session quote + booking draft. No
          // stage/step/hint gating — the guard is the single source of truth.
          if (RIDERS_ONE_BRAIN_ENABLED) {
            const draft = authority.controller?.bookingDraft;
            if (!draft) {
              throw new Error(
                "No booking draft found for this conversation. Collect the sender, recipient, pickup and delivery details via apply_booking_field first.",
              );
            }
            // Progressive disclosure: deterministic gate that blocks order
            // placement unless we have evidence the full summary has been
            // shown to the customer in this session. The output verification
            // loop flips stage → "summary_shown" whenever it substitutes a
            // canonical summary, and the legacy "summary_pending" /
            // "awaiting_summary_confirmation" flags do the same when the LLM
            // produces a real summary. Without that evidence, a model reply
            // like "Ready to confirm?" followed by the customer saying "yes"
            // could satisfy order-guard's confirmation_missing check without
            // the customer having actually read a summary. This gate closes
            // that loophole.
            const summaryShown =
              authority.stage === "summary_shown" ||
              authority.stage === "awaiting_confirmation" ||
              authority.bookingStep === "summary_pending" ||
              authority.bookingStep === "awaiting_summary_confirmation";
            if (!summaryShown) {
              return createTextResult({
                status: "rejected",
                code: "summary_not_shown",
                reason: "summary_not_shown",
                message:
                  "You have not shown the customer a full order summary yet. Write the complete summary (pickup + address, delivery + address, sender, recipient, service, price) and ask for confirmation. Only call create_simple_order AFTER the customer confirms that shown summary.",
                _instruction:
                  "The create_simple_order call was rejected because no summary has been shown to the customer in this session. Do NOT claim the order was created. Write the full order summary now and wait for the customer's explicit confirmation before retrying.",
              });
            }
            const guardResult = guardCreateSimpleOrder({
              draft,
              pickupAreaNameEn: String(params.pickup_area || ""),
              dropoffAreaNameEn: String(params.delivery_area || ""),
              deliveryType: String(params.delivery_type || ""),
              quotedPrice: Number(params.quoted_price),
              visibleCustomerText: visibleText,
              lastQuotedRoute: currentSession.lastQuotedRoute || null,
            });
            if (!guardResult.ok) {
              const code = describeRejection(guardResult);
              const humanMessage =
                "message" in guardResult
                  ? guardResult.message
                  : guardResult.code === "draft_incomplete"
                    ? `The booking draft is missing: ${guardResult.missing.join(", ")}. Collect the missing fields via apply_booking_field before calling create_simple_order.`
                    : `The booking draft has malformed fields: ${guardResult.invalid.map((i) => `${i.field}:${i.reason}`).join(", ")}. Ask the customer to resend them cleanly and overwrite via apply_booking_field.`;
              return createTextResult({
                status: "rejected",
                code: guardResult.code,
                reason: code,
                message: humanMessage,
                _instruction:
                  "The create_simple_order call was rejected by the server-side guard. Do NOT claim the order was created. Address the specific issue with the customer and retry only after it is resolved.",
              });
            }
            // Source-of-truth hydration: after the guard has validated the
            // draft, address fields (block/street/house/avenue/extra) always
            // come from the draft — not from whatever the LLM happened to
            // repeat in its tool call. This guarantees nothing the customer
            // said gets dropped en route to the driver (especially optional
            // Kuwait extensions like avenue/floor/apt/landmark).
            const hydrate = (v: string | null | undefined) =>
              typeof v === "string" && v.trim() ? v.trim() : null;
            if (draft.pickupLocation) {
              params.pickup_latitude = draft.pickupLocation.latitude;
              params.pickup_longitude = draft.pickupLocation.longitude;
            } else {
              params.pickup_block = hydrate(draft.pickupBlock) ?? params.pickup_block ?? null;
              params.pickup_street = hydrate(draft.pickupStreet) ?? params.pickup_street ?? null;
              params.pickup_house = hydrate(draft.pickupHouse) ?? params.pickup_house ?? null;
            }
            params.pickup_avenue = hydrate(draft.pickupAvenue) ?? params.pickup_avenue ?? null;
            params.pickup_extra = hydrate(draft.pickupExtra) ?? params.pickup_extra ?? null;
            if (draft.deliveryLocation) {
              params.delivery_latitude = draft.deliveryLocation.latitude;
              params.delivery_longitude = draft.deliveryLocation.longitude;
            } else {
              params.delivery_block = hydrate(draft.deliveryBlock) ?? params.delivery_block ?? null;
              params.delivery_street = hydrate(draft.deliveryStreet) ?? params.delivery_street ?? null;
              params.delivery_house = hydrate(draft.deliveryHouse) ?? params.delivery_house ?? null;
            }
            params.delivery_avenue = hydrate(draft.deliveryAvenue) ?? params.delivery_avenue ?? null;
            params.delivery_extra = hydrate(draft.deliveryExtra) ?? params.delivery_extra ?? null;
            currentSession.pendingOrderSummary = {
              fingerprint: buildPendingOrderFingerprint(params as Record<string, unknown>),
              createdAt: Date.now(),
            };
          } else {
            // LEGACY path: stage + canonicalize from controller + hint checks.
            const actionHint = getCustomerTurnActionHint(ctx);
            const awaitingConfirmation =
              authority.stage === "awaiting_confirmation" ||
              authority.bookingStep === "awaiting_summary_confirmation";
            if (!awaitingConfirmation) {
              const currentStep = authority.bookingStep || authority.stage || "current";
              throw new Error(
                `Do not call create_simple_order during the ${currentStep.replace(/_/g, " ")} booking step. Continue collecting the missing booking details first.`,
              );
            }
            if (actionHint !== "confirm summary" && !isExplicitSummaryConfirmation(visibleText)) {
              throw new Error(
                "Do not call create_simple_order until the customer explicitly confirms the final order summary you already showed. Ask for confirmation instead.",
              );
            }
            const directChatBlockReason = getDirectChatBookingBlockReason(authority.controller);
            if (directChatBlockReason) {
              throw new Error(directChatBlockReason);
            }
            const canonicalParams = buildCanonicalCreateOrderParamsFromController(authority.controller, params as Record<string, unknown>);
            if (!canonicalParams) {
              throw new Error(
                "Do not call create_simple_order until the canonical booking controller has the confirmed sender, recipient, address, service, and price fields ready.",
              );
            }
            const draft = authority.controller?.bookingDraft;
            if (draft) {
              const draftProblems = sanityCheckBookingDraft({
                senderName: draft.senderName,
                senderPhone: draft.senderPhone,
                recipientName: draft.recipientName,
                recipientPhone: draft.recipientPhone,
                pickupAddressBlock: draft.pickupBlock,
                pickupAddressStreet: draft.pickupStreet,
                pickupAddressHouse: draft.pickupHouse,
                deliveryAddressBlock: draft.deliveryBlock,
                deliveryAddressStreet: draft.deliveryStreet,
                deliveryAddressHouse: draft.deliveryHouse,
              }).filter((p) => p.reason !== "missing");
              if (draftProblems.length > 0) {
                const desc = draftProblems
                  .map((p) => `${p.field}:${p.reason}`)
                  .join(", ");
                throw new Error(
                  `Order blocked: the booking draft contains malformed fields (${desc}). Ask the customer to resend the affected fields cleanly and call apply_booking_field to overwrite them BEFORE retrying create_simple_order.`,
                );
              }
            }
            params = canonicalParams as typeof params;
            currentSession.pendingOrderSummary = {
              fingerprint: buildPendingOrderFingerprint(canonicalParams),
              createdAt: Date.now(),
            };
          }
        }

        let liveSettings: RidersGridLiveSettingsSummary | null = null;
        try {
          liveSettings = await loadRidersGridLiveSettingsSummary();
        } catch (settingsError) {
          console.warn(
            `[riders-settings] failed to load live settings before create_simple_order: ${settingsError instanceof Error ? settingsError.message : String(settingsError)}`,
          );
        }
        if (liveSettings && isOrderCreationBlockedByLiveMaintenance(liveSettings)) {
          return buildCreateOrderMaintenanceResult(liveSettings);
        }

        const pricing = await loadPricing();
        const pickupQueryResolution = await resolvePricingAreaQuery(params.pickup_area, pricing);
        const dropoffQueryResolution = await resolvePricingAreaQuery(params.delivery_area, pricing);

        if (pickupQueryResolution.status === "ambiguous") {
          return createAreaClarificationResult({
            field: "pickup_area",
            query: params.pickup_area,
            prompt_ar: pickupQueryResolution.prompt_ar,
            prompt_en: pickupQueryResolution.prompt_en,
            options: pickupQueryResolution.options,
          });
        }

        if (pickupQueryResolution.status === "suggested") {
          return createAreaSuggestionResult({
            field: "pickup_area",
            query: params.pickup_area,
            suggestedArea: pickupQueryResolution.area,
            prompt_ar: pickupQueryResolution.prompt_ar,
            prompt_en: pickupQueryResolution.prompt_en,
            alternativeAreas: pickupQueryResolution.alternative_areas,
          });
        }

        if (dropoffQueryResolution.status === "ambiguous") {
          return createAreaClarificationResult({
            field: "delivery_area",
            query: params.delivery_area,
            prompt_ar: dropoffQueryResolution.prompt_ar,
            prompt_en: dropoffQueryResolution.prompt_en,
            options: dropoffQueryResolution.options,
          });
        }

        if (dropoffQueryResolution.status === "suggested") {
          return createAreaSuggestionResult({
            field: "delivery_area",
            query: params.delivery_area,
            suggestedArea: dropoffQueryResolution.area,
            prompt_ar: dropoffQueryResolution.prompt_ar,
            prompt_en: dropoffQueryResolution.prompt_en,
            alternativeAreas: dropoffQueryResolution.alternative_areas,
          });
        }

        const pickup = await resolveAreaForOrdering(params.pickup_area);
        const dropoff = await resolveAreaForOrdering(params.delivery_area);

        if (!pickup) {
          return createAreaNotFoundResult({
            field: "pickup_area",
            query: params.pickup_area,
          });
        }

        if (!dropoff) {
          return createAreaNotFoundResult({
            field: "delivery_area",
            query: params.delivery_area,
          });
        }

        if (!pickup.geoArea.objectid) {
          throw new Error(`Pickup area ${pickup.geoArea.name} has no Grid objectid. Cannot create order via Grid API.`);
        }

        if (!dropoff.geoArea.objectid) {
          throw new Error(`Delivery area ${dropoff.geoArea.name} has no Grid objectid. Cannot create order via Grid API.`);
        }

        validateCreateSimpleOrderPreflight(params, {
          session: currentSession,
          pickupAreaNameEn: pickup.pricingArea.name_en,
          dropoffAreaNameEn: dropoff.pricingArea.name_en,
        });

        const expectedSheetPrice = getRouteSheetPrice(pickup.pricingArea, dropoff.pricingArea, params.delivery_type);

        if (expectedSheetPrice === null) {
          throw new Error(
            `Selected delivery type ${params.delivery_type} is not priced for route ${pickup.pricingArea.name_en} -> ${dropoff.pricingArea.name_en}. Do not create the order until the route is re-quoted or escalated.`,
          );
        }

        if (!pricesMatch(params.quoted_price, expectedSheetPrice)) {
          throw new Error(
            `Quoted price mismatch for ${params.delivery_type}. Accepted quote was ${formatPrice(params.quoted_price, "KWD")}, but the approved sheet price for this route is ${formatPrice(expectedSheetPrice, "KWD")}. Re-quote before creating the order.`,
          );
        }

        const senderName = splitFullName(params.sender_name);
        const recipientName = splitFullName(params.recipient_name);

        // Resolve shipping method
        const commonMethods = getCommonShippingMethods(
          pickup.geoArea.shipping_methods ?? [],
          dropoff.geoArea.shipping_methods ?? [],
        );
        const selectedMethod = selectShippingMethod(commonMethods, params.delivery_type);
        const defaultShippingMethodIds: Record<string, number> = {
          sedan_normal: 6,
          sedan_fast: 6,
          van_normal: 3,
          van_fast: 4,
        };
        const resolvedShippingMethodId = selectedMethod?.id
          ?? defaultShippingMethodIds[params.delivery_type]
          ?? 6;

        // Debug: write resolved areas to file for troubleshooting
        const _debugPayload = {
          ts: new Date().toISOString(),
          pickup: {
            query: params.pickup_area,
            pricingId: pickup.pricingArea.id,
            pricingName: pickup.pricingArea.name_en,
            govId: pickup.governorate.id,
            govName: pickup.governorate.name,
            geoAreaId: pickup.geoArea.id,
            geoAreaName: pickup.geoArea.name,
            objectid: pickup.geoArea.objectid,
            lat: pickup.geoArea.lat,
            lng: pickup.geoArea.lng,
          },
          dropoff: {
            query: params.delivery_area,
            pricingId: dropoff.pricingArea.id,
            pricingName: dropoff.pricingArea.name_en,
            govId: dropoff.governorate.id,
            govName: dropoff.governorate.name,
            geoAreaId: dropoff.geoArea.id,
            geoAreaName: dropoff.geoArea.name,
            objectid: dropoff.geoArea.objectid,
            lat: dropoff.geoArea.lat,
            lng: dropoff.geoArea.lng,
          },
          shippingMethodId: resolvedShippingMethodId,
        };
        const _fs = await import("fs");
        await _fs.promises.appendFile("/tmp/openclaw/create-order-debug.log",
          JSON.stringify(_debugPayload, null, 2) + "\n---\n");

        // Build full payload for POST /orders (order.store)
        const orderPayload: Record<string, unknown> = {
          sender_name_first: senderName.first,
          sender_name_last: senderName.last,
          sender_phone: params.sender_phone,
          recipient_name_first: recipientName.first,
          recipient_name_last: recipientName.last,
          recipient_phone: params.recipient_phone,
          payer: params.payer ?? "sender",
          payment_method: params.payment_method || "knet",
          terms_accepted: "on",
          order_type: "normal",
          shipping_method_id: resolvedShippingMethodId,
          pickup_address: buildAddressPayload(pickup, {
            block: params.pickup_block,
            street: params.pickup_street,
            house: params.pickup_house,
            avenue: params.pickup_avenue,
            extra: params.pickup_extra,
            notes: params.pickup_notes,
            latitude: params.pickup_latitude,
            longitude: params.pickup_longitude,
          }),
          delivery_address: buildAddressPayload(dropoff, {
            block: params.delivery_block,
            street: params.delivery_street,
            house: params.delivery_house,
            avenue: params.delivery_avenue,
            extra: params.delivery_extra,
            notes: params.delivery_notes,
            latitude: params.delivery_latitude,
            longitude: params.delivery_longitude,
          }),
        };

        if (params.schedule_date) {
          orderPayload.schedule_date = params.schedule_date;
        }
        if (params.coupon) {
          orderPayload.coupon = params.coupon;
        }

        const createResponse = await ridersFormDataRequest("POST", "/orders", orderPayload);
        const order = normalizeOrder(
          createResponse.data?.order ?? createResponse.data,
        );
        const paymentLink = order?.uid
          ? `https://order.tryriders.com/payorder/${order.uid}`
          : null;

        // Structured customer message for order confirmation
        const orderUid = order?.uid || "N/A";
        const orderCustomerMessageAr =
          `تم إنشاء طلبكم بنجاح.\n` +
          `رقم الطلب: ${orderUid}\n` +
          (paymentLink ? `رابط الدفع: ${paymentLink}\n` : "") +
          `السعر: ${params.quoted_price} KWD`;
        const orderCustomerMessageEn =
          `Your order has been created successfully.\n` +
          `Order ID: ${orderUid}\n` +
          (paymentLink ? `Payment link: ${paymentLink}\n` : "") +
          `Price: ${params.quoted_price} KWD`;

        const toolResult = createTextResult(
          {
            status: "ok",
            message: createResponse.message || "Order created successfully.",
            selected_delivery_type: params.delivery_type,
            validated_quoted_price: params.quoted_price,
            sheet_route_price: expectedSheetPrice,
            verified_quote_ref: currentSession.lastQuotedRoute?.quoteRef ?? null,
            shipping_method_id: resolvedShippingMethodId,
            payment_method: params.payment_method ?? "knet",
            payment_link: paymentLink,
            order,
            _customer_message: orderCustomerMessageEn,
            _customer_message_ar: orderCustomerMessageAr,
            _customer_message_en: orderCustomerMessageEn,
            _instruction: "RELAY the _customer_message to the customer as-is. You may adjust the language to match the conversation but you MUST keep the exact order ID, payment link, and price unchanged. Do NOT fabricate any order details.",
          },
          {
            raw_create: createResponse,
            order,
          },
        );
        await recordGuardState("create_simple_order", toolResult, ctx);
        return toolResult;
      } catch (err) {
        const isTimeout =
          (err instanceof RidersApiError && (err.status === 504 || err.status === 502 || err.status === 0)) ||
          (err instanceof Error && err.name === "AbortError");
        if (isTimeout) {
          return createTextResult({
            status: "error",
            message:
              "The order creation request timed out. This is a temporary upstream issue, NOT a problem with the booking details. Tell the customer there is a brief delay and you will try again in a moment. Do NOT escalate to a human agent for this. Wait a few seconds and retry the exact same create_simple_order call.",
            retryable: true,
          });
        }
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool({
    name: "create_order",
    label: "Create Order (DEPRECATED)",
    description:
      "DEPRECATED — DO NOT USE. Use create_simple_order instead. This low-level tool is disabled; it accepted raw address IDs which the model cannot reliably provide.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        sender_name_first: { type: "string" },
        sender_name_last: { type: "string" },
        sender_phone: { type: "string" },
        recipient_name_first: { type: "string" },
        recipient_name_last: { type: "string" },
        recipient_phone: { type: "string" },
        payer: {
          type: "string",
          enum: ["sender", "recipient"],
        },
        payment_method: {
          type: ["string", "null"],
          enum: ["wallet", "card", "knet", "apple_pay", "tap", null],
        },
        terms_accepted: {
          type: "string",
          enum: ["on", "1", "true"],
        },
        schedule_date: {
          type: ["string", "null"],
        },
        coupon: {
          type: ["string", "null"],
        },
        order_type: {
          type: "string",
          enum: ["normal", "roundtrip"],
        },
        shipping_method_id: { type: "integer" },
        proof_image: {
          type: ["string", "null"],
        },
        pickup_address: {
          type: "object",
          additionalProperties: false,
          properties: {
            coordinates: {
              type: "object",
              additionalProperties: false,
              properties: {
                lat: { type: "string" },
                lng: { type: "string" },
              },
              required: ["lat", "lng"],
            },
            governorate_id: { type: "integer" },
            area_id: { type: "integer" },
            block_id: { type: ["integer", "null"] },
            street_id: { type: ["integer", "null"] },
            avenue: { type: ["string", "null"] },
            house: { type: ["string", "null"] },
            notes: { type: ["string", "null"] },
          },
          required: ["coordinates", "governorate_id", "area_id"],
        },
        delivery_address: {
          type: "object",
          additionalProperties: false,
          properties: {
            coordinates: {
              type: "object",
              additionalProperties: false,
              properties: {
                lat: { type: "string" },
                lng: { type: "string" },
              },
              required: ["lat", "lng"],
            },
            governorate_id: { type: "integer" },
            area_id: { type: "integer" },
            block_id: { type: ["integer", "null"] },
            street_id: { type: ["integer", "null"] },
            avenue: { type: ["string", "null"] },
            house: { type: ["string", "null"] },
            notes: { type: ["string", "null"] },
          },
          required: ["coordinates", "governorate_id", "area_id"],
        },
        payment_token: {
          type: "object",
          additionalProperties: false,
          properties: {
            source: {
              type: "object",
              additionalProperties: false,
              properties: {
                id: { type: "string" },
              },
            },
            authentication: {
              type: ["object", "null"],
              additionalProperties: false,
              properties: {
                acsEci: { type: ["string", "null"] },
                authenticationToken: { type: ["string", "null"] },
                transactionId: { type: ["string", "null"] },
                dsTransactionId: { type: ["string", "null"] },
                threeDsTransactionId: { type: ["string", "null"] },
                version: { type: ["string", "null"] },
                messageVersion: { type: ["string", "null"] },
                transStatus: { type: ["string", "null"] },
              },
            },
          },
        },
      },
      required: [
        "sender_name_first",
        "sender_name_last",
        "sender_phone",
        "recipient_name_first",
        "recipient_name_last",
        "recipient_phone",
        "payer",
        "terms_accepted",
        "shipping_method_id",
        "pickup_address",
        "delivery_address",
      ],
    },

    async execute(_toolCallId: string, _params: any) {
      return createTextResult({
        status: "error",
        message:
          "create_order is DEPRECATED and permanently disabled. Use create_simple_order instead — it resolves area names automatically and validates pricing.",
      });
    },
  });

  api.registerTool({
    name: "pay_order",
    label: "Pay Order",
    description:
      "Initiate payment for an existing Riders order using POST /orders/{uid}/pay. This tool is disabled unless WRITE_ACTIONS_ENABLED is true.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        order_id: {
          type: "string",
          description: "The Riders order UID",
        },
        payment_method: {
          type: "string",
          enum: ["wallet", "card", "knet", "apple_pay", "tap"],
        },
        payment_token: {
          type: "object",
          additionalProperties: false,
          properties: {
            source: {
              type: "object",
              additionalProperties: false,
              properties: {
                id: { type: "string" },
              },
            },
            authentication: {
              type: ["array", "null"],
              items: { type: "string" },
            },
          },
        },
      },
      required: ["order_id", "payment_method"],
    },

    async execute(
      _toolCallId: string,
      params: {
        order_id: string;
        payment_method: string;
        payment_token?: { source?: { id?: string }; authentication?: string[] | null };
      },
    ) {
      try {
        assertWriteActionsEnabled();
        const payload = await ridersRequest(
          "POST",
          `/orders/${encodeURIComponent(params.order_id)}/pay`,
          {
            payment_method: params.payment_method,
            ...(params.payment_token ? { payment_token: params.payment_token } : {}),
          },
        );

        return createTextResult(
          {
            status: "ok",
            order_id: params.order_id,
            message: payload.message || "Order payment initialized successfully.",
            payment_link: payload.data?.payment_link ?? null,
            order_uid: payload.data?.order_uid ?? params.order_id,
          },
          payload,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  });

  api.registerTool({
    name: "cancel_order",
    label: "Cancel Order",
    description:
      "Cancel an existing Riders order using POST /orders/{uid}/cancel. This tool is disabled unless WRITE_ACTIONS_ENABLED is true.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        order_id: {
          type: "string",
          description: "The Riders order UID",
        },
      },
      required: ["order_id"],
    },

    async execute(_toolCallId: string, params: { order_id: string }) {
      try {
        assertWriteActionsEnabled();
        const payload = await ridersRequest(
          "POST",
          `/orders/${encodeURIComponent(params.order_id)}/cancel`,
        );

        return createTextResult(
          {
            status: "ok",
            order_id: params.order_id,
            message:
              payload.data?.message || payload.message || "Order cancelled successfully.",
            order_uid: payload.data?.order_uid ?? params.order_id,
          },
          payload,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  });

  api.registerTool((ctx: any) => ({
    name: "shadow_extract_booking_fields",
    label: "[Shadow] Extract Booking Fields",
    description:
      "SHADOW ANALYTICS TOOL — always safe to call. Call this IN ADDITION to your normal reply whenever the customer provides any booking-related field value OR corrects a previous one OR expresses a clear booking action (confirm, cancel, start, provide address, provide name, provide phone). This tool does NOT change conversation state or what the customer sees; it is a no-op used to record what fields you observed. Always pass the most faithful structured extraction you can. If the customer did not provide any booking field content this turn, do NOT call this tool.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        action_hint: {
          type: "string",
          description:
            "Short label describing the customer's intent this turn (e.g. 'booking_step_input', 'correct_booking_field', 'confirm_summary', 'cancel_booking', 'pricing_request', 'other').",
        },
        fields: {
          type: "object",
          additionalProperties: false,
          description:
            "The booking fields observed in this turn. Leave any field null/absent if the customer did not provide it. Use digits only for phones.",
          properties: {
            sender_name: { type: ["string", "null"] },
            sender_phone: { type: ["string", "null"] },
            phone_decision: {
              type: ["string", "null"],
              enum: ["use_whatsapp", "different", "none", null],
            },
            recipient_name: { type: ["string", "null"] },
            recipient_phone: { type: ["string", "null"] },
            address_block: { type: ["string", "null"] },
            address_street: { type: ["string", "null"] },
            address_house: { type: ["string", "null"] },
            address_role: {
              type: ["string", "null"],
              enum: ["pickup", "delivery", null],
              description: "Which address the block/street/house belong to, if the customer indicated it.",
            },
          },
        },
        source_quote: {
          type: "string",
          description:
            "The shortest verbatim snippet from the customer's latest message that supports the extracted fields.",
        },
      },
      required: ["action_hint"],
    },

    async execute(_toolCallId: string, params: any) {
      try {
        const conversationIdRaw = ctx?.ConversationId || ctx?.conversationId || ctx?.ConversationID || "na";
        const conversationId = String(conversationIdRaw);
        const actionHint = typeof params?.action_hint === "string" ? params.action_hint.trim() : "";
        const fields = params?.fields && typeof params.fields === "object" ? params.fields : null;
        const sourceQuoteRaw = typeof params?.source_quote === "string" ? params.source_quote : "";
        const sourceQuote = sourceQuoteRaw.slice(0, 200).replace(/\s+/g, " ").trim();
        const payload = {
          conversation: conversationId,
          action_hint: actionHint || "other",
          fields,
          source_quote: sourceQuote || null,
        };
        console.log(`[shadow-extract] ${JSON.stringify(payload)}`);
        } catch {}
        return createTextResult({ shadow: true, acknowledged: true });
      },
  }));

  api.registerTool((ctx: any) => ({
    name: "apply_booking_field",
    label: "Apply Booking Field",
    description:
      "BOOKING STATE TOOL — MANDATORY whenever the customer provides OR corrects any booking field. You MUST call this IN ADDITION to your customer reply, in the same turn, every single time the customer's message contains any of: sender full name, sender phone (or a decision to use/not use their WhatsApp number), recipient full name, recipient phone, or any pickup/delivery address part (block, street, house, avenue/jadda/jedda, floor, apartment, office, landmark, or any other address detail). This tool updates the server-side booking state — without it, the booking does not progress, even if your reply says it did. Rules: (1) include only fields the customer actually said this turn, leave the rest null; (2) use digits only for phones; (3) address_block/address_street/address_house are short identifiers (1-30 chars); (4) address_avenue is the Kuwait 'جادة / jadda / jedda / avenue' value, separate from street (e.g. 'farwaniya block 6, street 9, house 17, jedda 9' → address_block='6', address_street='9', address_house='17', address_avenue='9'); (5) address_extra is a free-form bag for floor, apartment, office, side-of-block, landmark, gate, or any additional address note ('Floor 3, Apt 12, next to the mosque') — include it verbatim; (6) pass address_role='pickup' or 'delivery' when the role is clear from context (current step, customer's own words, sender/recipient area names). Only leave address_role null when there is zero role signal at all. Never invent, never carry values over from earlier turns — only what the customer said this turn. Never mention this tool or its effects to the customer.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        sender_name: { type: ["string", "null"] },
        sender_phone: { type: ["string", "null"] },
        phone_decision: {
          type: ["string", "null"],
          enum: ["use_whatsapp", "different", null],
          description: "Set to 'use_whatsapp' if the customer confirmed using their WhatsApp number as the sender phone, or 'different' if they explicitly want to use a different one. Leave null otherwise.",
        },
        recipient_name: { type: ["string", "null"] },
        recipient_phone: { type: ["string", "null"] },
        address_block: { type: ["string", "null"] },
        address_street: { type: ["string", "null"] },
        address_house: {
          type: ["string", "null"],
          description: "Building / villa / tower number only — what a driver reads off the façade (e.g. '17', '23b', 'villa 4'). NEVER put apartment, flat, floor, door, office, gate, or their Arabic equivalents (شقة / دور / باب / طابق / مكتب / بوابة) here — those go into address_extra. The backend will reroute them if you do.",
        },
        address_avenue: {
          type: ["string", "null"],
          description: "Kuwait 'جادة / jadda / jedda / avenue' designation — a road type distinct from street. Short identifier (e.g. '9').",
        },
        address_extra: {
          type: ["string", "null"],
          description: "Free-form extra address detail — floor, apartment, office, side of block, landmark, gate, anything useful for the driver. Up to 200 chars.",
        },
        address_role: {
          type: ["string", "null"],
          enum: ["pickup", "delivery", null],
        },
        source_quote: {
          type: ["string", "null"],
          description: "The shortest verbatim snippet from the customer's latest message that supports this field update. Null only if there is no clean quote.",
        },
      },
      required: [
        "sender_name",
        "sender_phone",
        "phone_decision",
        "recipient_name",
        "recipient_phone",
        "address_block",
        "address_street",
        "address_house",
        "address_avenue",
        "address_extra",
        "address_role",
        "source_quote",
      ],
    },

    async execute(_toolCallId: string, params: any) {
      const conversationId = resolveToolConversationId(ctx);
      const turnId = resolveToolTurnId(ctx);
      if (!conversationId) {
        try {
          console.warn(`[responder-op] apply_booking_field dropped_no_conversation ctxKeys=${Object.keys(ctx || {}).join(",")}`);
        } catch {}
        return createTextResult({ applied: false, reason: "no_conversation_context" });
      }

      // Post-order gate. Once stage === "order_submitted", the booking draft
      // has been cleared and any further apply_booking_field call would write
      // into a dead draft — the customer's "correction" would never reach the
      // placed order. Reject deterministically and tell the LLM exactly which
      // flow to run instead: track_order → (unpaid) cancel_order +
      // create_simple_order, OR (paid) request_handoff. This is the backstop
      // for the hallucinated "we've passed this to the support team" bug.
      try {
        const authority = getNormalizedBookingAuthority(ctx);
        if (authority.stage === "order_submitted") {
          const submittedOrderUid =
            (authority.controller as any)?.submittedOrderUid || null;
          try {
            console.log(
              `[post-order] apply_booking_field rejected stage=order_submitted uid=${submittedOrderUid || "unknown"} conversation=${conversationId}`,
            );
          } catch {}
          return createTextResult({
            applied: false,
            reason: "order_already_submitted",
            code: "order_already_submitted",
            submitted_order_uid: submittedOrderUid,
            _instruction:
              "The customer's order has already been submitted, so there is no live booking draft to write to — this field update was NOT saved. Do NOT tell the customer the change was saved or that you passed it to support. Follow the post-order correction flow: (1) call track_order with the submitted order UID to get payment_status; (2) if payment_status indicates the order is NOT paid yet (e.g. 'pending' / 'unpaid' / 'awaiting_payment'), tell the customer you'll cancel the current order and create a new one with the corrected detail, then call cancel_order followed by create_simple_order with the updated field; (3) if the order IS already paid, call request_handoff so our team can update it manually. Never claim the change was applied unless a tool result confirms it.",
          });
        }
      } catch { /* fall through to normal handling if authority read fails */ }

      const safeStr = (value: unknown): string | null => {
        if (typeof value !== "string") return null;
        const trimmed = value.trim();
        return trimmed ? trimmed : null;
      };

      // Interior-detail reroute (deterministic backstop). If the LLM put
      // something like "door 312", "apt 5", "floor 2", "شقة ٨" into
      // `address_house`, we move it into `address_extra` before validation so
      // that (a) no customer data is lost, (b) `address_house` stays reserved
      // for building numbers the driver can read off the façade, and (c) the
      // LLM sees a clear repair-hint in its tool result and asks for the
      // missing building number.
      let rawHouse = safeStr(params?.address_house);
      let rawExtra = safeStr(params?.address_extra);
      let houseRerouted = false;
      if (rawHouse && looksLikeInteriorDetail(rawHouse)) {
        rawExtra = rawExtra ? `${rawExtra}, ${rawHouse}` : rawHouse;
        rawHouse = null;
        houseRerouted = true;
      }

      const rawOp: ResponderBookingFieldOp = {
        op: "apply_booking_field",
        sender_name: safeStr(params?.sender_name),
        sender_phone: safeStr(params?.sender_phone),
        phone_decision:
          params?.phone_decision === "use_whatsapp" || params?.phone_decision === "different"
            ? params.phone_decision
            : null,
        recipient_name: safeStr(params?.recipient_name),
        recipient_phone: safeStr(params?.recipient_phone),
        address_block: safeStr(params?.address_block),
        address_street: safeStr(params?.address_street),
        address_house: rawHouse,
        address_avenue: safeStr(params?.address_avenue),
        address_extra: rawExtra,
        address_role:
          params?.address_role === "pickup" || params?.address_role === "delivery"
            ? params.address_role
            : null,
        source_quote: safeStr(params?.source_quote),
        turn_id: turnId,
      };
      const validation = validateApplyBookingFieldOp(rawOp);
      if (validation.errors.length > 0) {
        try {
          console.warn(
            `[responder-op] apply_booking_field validation_errors conversation=${conversationId} errors=${JSON.stringify(validation.errors)}`,
          );
        } catch {}
      }
      if (!validation.hasAnyValidField) {
        return createTextResult({
          applied: false,
          reason: "all_fields_invalid",
          rejected_fields: validation.errors.map((e) => ({ field: e.field, reason: e.reason })),
          note:
            "None of the provided fields passed validation. Ask the customer to resend the specific field cleanly: phones must be digits only (no labels like 'thenumber is'), names must be letters only (no digits, no acknowledgements like 'Ok'), block/street/house/avenue must be short identifiers, and address_extra is a short sentence (floor, apt, landmark).",
        });
      }
      pushResponderStateOp(conversationId, validation.cleaned as ResponderStateOp);
      try {
        console.log(
          `[responder-op] apply_booking_field conversation=${conversationId} ${JSON.stringify(validation.cleaned)}`,
        );
      } catch {}
      if (validation.errors.length > 0) {
        return createTextResult({
          acknowledged: true,
          partial: true,
          rejected_fields: validation.errors.map((e) => ({ field: e.field, reason: e.reason })),
          rerouted_fields: houseRerouted
            ? [{ from: "address_house", to: "address_extra", reason: "interior_detail" }]
            : undefined,
          note: houseRerouted
            ? "Some fields were recorded. The value you put into address_house looked like interior detail (apartment / floor / door / gate) — it has been moved to address_extra where the driver reads it after finding the building. The actual building / villa / tower number is still MISSING. In your next reply, ask the customer for the building number (house number) at that address — do NOT skip to the summary."
            : "Some fields were recorded; the rejected ones were dropped because they failed shape validation. In your next reply, ask the customer to resend ONLY the rejected fields cleanly (digits-only for phones, letters-only for names, short values for address parts). Do not re-ask for the fields that were accepted.",
        });
      }
      return createTextResult({
        acknowledged: true,
        rerouted_fields: houseRerouted
          ? [{ from: "address_house", to: "address_extra", reason: "interior_detail" }]
          : undefined,
        note: houseRerouted
          ? "Field recorded. Interior detail you put in address_house (apartment / floor / door) was moved to address_extra. The building / villa / tower number is still missing — ask the customer for it in your next reply."
          : "Field recorded. Continue with the next step in your reply — do NOT just acknowledge.",
      });
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "start_booking",
    label: "Start Booking",
    description:
      "BOOKING STATE TOOL — MANDATORY when the customer accepts an active quote. You MUST call this IN ADDITION to your customer reply, in the same turn, whenever the customer clearly accepts an active quote to begin the booking (e.g. 'ok', 'yes', 'go ahead', 'اكمل', 'ابي اكمل', 'proceed') while a quote exists on the current route. Without this tool call the booking does not start, regardless of what your reply says. After calling it, your reply MUST move forward — ask for the sender full name and phone (or confirm using the WhatsApp number) — do NOT send a dead acknowledgement like 'we'll proceed'. Never mention this tool to the customer.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        selected_delivery_type: {
          type: ["string", "null"],
          description: "Which quoted service the customer chose (e.g. 'sedan_normal', 'van_fast', 'cooled_van_normal'). Use null to accept the default.",
        },
        source_quote: { type: "string" },
      },
    },
    async execute(_toolCallId: string, params: any) {
      const conversationId = resolveToolConversationId(ctx);
      const turnId = resolveToolTurnId(ctx);
      if (!conversationId) {
        try {
          console.warn(`[responder-op] start_booking dropped_no_conversation ctxKeys=${Object.keys(ctx || {}).join(",")}`);
        } catch {}
        return createTextResult({ applied: false, reason: "no_conversation_context" });
      }
      const op: ResponderStateOp = {
        op: "start_booking",
        selected_delivery_type:
          typeof params?.selected_delivery_type === "string" && params.selected_delivery_type.trim()
            ? params.selected_delivery_type.trim()
            : null,
        source_quote:
          typeof params?.source_quote === "string" && params.source_quote.trim()
            ? params.source_quote.trim()
            : null,
        turn_id: turnId,
      };
      pushResponderStateOp(conversationId, op);
      try {
        console.log(`[responder-op] start_booking conversation=${conversationId} ${JSON.stringify(op)}`);
      } catch {}
      return createTextResult({ acknowledged: true });
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "confirm_summary",
    label: "Confirm Order Summary",
    description:
      "BOOKING STATE TOOL — MANDATORY when the customer confirms the final summary. You MUST call this IN ADDITION to your customer reply, in the same turn, whenever the customer has been shown the order summary and they confirm (e.g. 'yes', 'go ahead', 'confirm', 'اكمل', 'تمام'). After calling it, immediately call create_simple_order to place the booking — do NOT send a dead 'okay we'll proceed' reply. Never call this before the summary has been shown. Never mention this tool to the customer.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        source_quote: { type: "string" },
      },
    },
    async execute(_toolCallId: string, params: any) {
      const conversationId = resolveToolConversationId(ctx);
      const turnId = resolveToolTurnId(ctx);
      if (!conversationId) {
        try {
          console.warn(`[responder-op] confirm_summary dropped_no_conversation ctxKeys=${Object.keys(ctx || {}).join(",")}`);
        } catch {}
        return createTextResult({ applied: false, reason: "no_conversation_context" });
      }
      const op: ResponderStateOp = {
        op: "confirm_summary",
        source_quote:
          typeof params?.source_quote === "string" && params.source_quote.trim()
            ? params.source_quote.trim()
            : null,
        turn_id: turnId,
      };
      pushResponderStateOp(conversationId, op);
      try {
        console.log(`[responder-op] confirm_summary conversation=${conversationId} ${JSON.stringify(op)}`);
      } catch {}
      return createTextResult({ acknowledged: true });
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "cancel_booking",
    label: "Cancel Booking",
    description:
      "BOOKING STATE TOOL — MANDATORY when the customer clearly cancels the booking in progress. You MUST call this IN ADDITION to your customer reply, in the same turn, whenever the customer unambiguously says they want to cancel or start over mid-booking (e.g. 'cancel', 'nvm', 'forget it', 'start over', 'الغي', 'ما ابي'). Do not call this for ambiguous messages or simple follow-up questions. Never mention this tool to the customer.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        reason: { type: ["string", "null"] },
        source_quote: { type: ["string", "null"] },
      },
      required: ["reason", "source_quote"],
    },
    async execute(_toolCallId: string, params: any) {
      const conversationId = resolveToolConversationId(ctx);
      const turnId = resolveToolTurnId(ctx);
      if (!conversationId) {
        try {
          console.warn(`[responder-op] cancel_booking dropped_no_conversation ctxKeys=${Object.keys(ctx || {}).join(",")}`);
        } catch {}
        return createTextResult({ applied: false, reason: "no_conversation_context" });
      }
      const op: ResponderStateOp = {
        op: "cancel_booking",
        reason:
          typeof params?.reason === "string" && params.reason.trim()
            ? params.reason.trim().slice(0, 200)
            : null,
        source_quote:
          typeof params?.source_quote === "string" && params.source_quote.trim()
            ? params.source_quote.trim()
            : null,
        turn_id: turnId,
      };
      pushResponderStateOp(conversationId, op);
      try {
        console.log(`[responder-op] cancel_booking conversation=${conversationId} ${JSON.stringify(op)}`);
      } catch {}
      return createTextResult({ acknowledged: true });
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "request_handoff",
    label: "Request Human Handoff",
    description:
      "BOOKING STATE TOOL — MANDATORY when escalation to a human agent is needed. You MUST call this IN ADDITION to your customer reply, in the same turn, whenever the customer explicitly asks for a human agent, or the situation clearly requires escalation (complaints, refund disputes, persistent misunderstanding that the bot cannot resolve). Never mention this tool to the customer.",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        reason: { type: ["string", "null"] },
        source_quote: { type: ["string", "null"] },
      },
      required: ["reason", "source_quote"],
    },
    async execute(_toolCallId: string, params: any) {
      const conversationId = resolveToolConversationId(ctx);
      const turnId = resolveToolTurnId(ctx);
      if (!conversationId) {
        try {
          console.warn(`[responder-op] request_handoff dropped_no_conversation ctxKeys=${Object.keys(ctx || {}).join(",")}`);
        } catch {}
        return createTextResult({ applied: false, reason: "no_conversation_context" });
      }
      const op: ResponderStateOp = {
        op: "request_handoff",
        reason:
          typeof params?.reason === "string" && params.reason.trim()
            ? params.reason.trim().slice(0, 200)
            : null,
        source_quote:
          typeof params?.source_quote === "string" && params.source_quote.trim()
            ? params.source_quote.trim()
            : null,
        turn_id: turnId,
      };
      pushResponderStateOp(conversationId, op);
      try {
        console.log(`[responder-op] request_handoff conversation=${conversationId} ${JSON.stringify(op)}`);
      } catch {}
      return createTextResult({ acknowledged: true });
    },
  }));

  api.registerTool({
    name: "offers",
    label: "Get Active Offers",
    description:
      "Return the currently active Riders offers and promo codes for customer support replies.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      return createTextResult(
        {
          status: "ok",
          offers: activeOffers,
        },
        { offers: activeOffers },
      );
    },
  });
}
