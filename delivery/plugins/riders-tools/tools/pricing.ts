// Quote / price-lookup tools.
//
// Extracted from plugins/riders-tools/index.ts (originally lines 6599-7108)
// as part of Wave 1a of the surgical plugin split. Tool body is unchanged;
// it now pulls all its helpers from the shared `deps` bundle instead of
// relying on register()-scope closure state.
//
// Tools registered:
//   - get_price

import {
  extractTrackingOrderId,
  hasRouteEvidence,
  isBookingStartIntent,
  isGeneralServiceInquiry,
  isPassengerTransportRequest,
  isSimpleGreeting,
} from "../../shared/conversation-policy";

import type { ToolDeps } from "./deps";

export function registerPricingTools(api: any, deps: ToolDeps): void {
  const { intentGates, quoting, recordGuardState } = deps;
  const {
    isCustomerOctopusContext,
    getVisibleCustomerText,
    getCustomerTurnActionHint,
    getNormalizedBookingAuthority,
    getSessionFromCtx,
    isActiveBookingFlow,
    hasFreshLastQuotedRoute,
  } = intentGates;
  const {
    extractAreaTokensFromText,
    collectAreaEvidenceFromText,
    verifyAreaEvidence,
    createAreaSuggestionResult,
    createAreaNotFoundResult,
    createAreaNeedsClarificationResult,
    createAreaClarificationResult,
    collectAreaCandidates,
    resolvePricingAreaQuery,
    getBidirectionalRoutePrices,
    getSpecialDeliveryCapabilities,
    resolveAreaForOrdering,
    getCommonShippingMethods,
    selectShippingMethod,
    summarizeLiveDeliveryOption,
    parseNumericPrice,
    formatPrice,
    buildServiceCatalogEntry,
    getQuotedPriceForDeliveryType,
  } = quoting;

  // loadPricing is module-scope in index.ts; it is not passed through deps
  // because it would add another indirection. Instead we rely on the
  // caller passing a pre-loaded pricing snapshot via deps at construction
  // time. For wave 1a we just call the helper off deps.pricing.
  const { loadPricing } = deps.pricing;

  api.registerTool({
    name: "get_price",
    label: "Get Delivery Price",
    description:
      "MANDATORY: You MUST call this tool EVERY TIME before quoting ANY delivery price to a customer. NEVER quote a price from memory, previous orders, voice messages, or assumptions. Look up delivery prices between two areas in Kuwait. Returns pricing for all vehicle types and speeds. The price is the higher of the pickup and dropoff area prices (bidirectional max).",
    strict: true,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        pickup_area: {
          type: "string",
          description: "The pickup area name (Arabic or English)",
        },
        dropoff_area: {
          type: "string",
          description: "The dropoff/destination area name (Arabic or English)",
        },
        pickup_area_id: {
          type: ["number", "null"],
          description:
            "Numeric area ID for pickup. When provided, bypasses name resolution. Use this when the customer chose from a disambiguation list. Otherwise null.",
        },
        dropoff_area_id: {
          type: ["number", "null"],
          description:
            "Numeric area ID for dropoff. When provided, bypasses name resolution. Use this when the customer chose from a disambiguation list. Otherwise null.",
        },
      },
      required: [
        "pickup_area",
        "dropoff_area",
        "pickup_area_id",
        "dropoff_area_id",
      ],
    },

    async execute(
      _toolCallId: string,
      params: {
        pickup_area: string;
        dropoff_area: string;
        pickup_area_id?: number;
        dropoff_area_id?: number;
      },
      ctx?: any,
    ) {
      try {
        if (ctx && isCustomerOctopusContext(ctx)) {
          const visibleText = getVisibleCustomerText(ctx);
          const actionHint = getCustomerTurnActionHint(ctx);
          const bookingAuthority = getNormalizedBookingAuthority(ctx);
          const stageHint = bookingAuthority.stage;
          const bookingStepHint = bookingAuthority.bookingStep;
          const currentSession = getSessionFromCtx(ctx).session;
          const explicitLanguageHint = Boolean(
            ctx?.ExplicitLanguageHint || ctx?.explicitLanguageHint,
          );
          const looksLikeGreeting = isSimpleGreeting(visibleText);
          const looksLikePassengerTransport =
            isPassengerTransportRequest(visibleText);
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
              `[intent-gate-exec] blocked get_price same_quoted_route_followup`,
            );
            throw new Error(
              "Do not call get_price again when there is already an active quoted route and the customer did not provide a new route in this turn. Answer from the stored quote and service options for that same route instead. Only call get_price again if the customer clearly changes pickup or dropoff.",
            );
          }

          if (isGeneralServiceInquiry(visibleText) && !hasRouteEvidence(visibleText)) {
            console.log(`[intent-gate-exec] blocked get_price broad_service`);
            throw new Error(
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
              `[intent-gate-exec] blocked get_price intent=${actionHint} stage=${stageHint || "unknown"} bookingStep=${bookingStepHint || "unknown"}`,
            );
            throw new Error(
              "Do not call get_price during the booking collection or summary-confirmation flow. Continue the current booking step instead.",
            );
          }
        }

        const data = await loadPricing();

        // Evidence-binding area verification (Phase 4). See the comment in
        // index.ts (pre-extraction) or the commit message for the full
        // rationale; the behavior is unchanged.
        const visibleText =
          String(ctx?.BodyForAgent || ctx?.Body || ctx?.RawBody || "").trim() ||
          (() => {
            const store = (globalThis as any).__ridersLastCustomerText as
              | {
                  entries: Map<string, { text: string; ts: number }>;
                  lastConversationId: string;
                }
              | undefined;
            if (!store?.entries?.size) return "";
            const entry = store.entries.get(store.lastConversationId);
            if (!entry || Date.now() - entry.ts > 5 * 60_000) return "";
            return entry.text;
          })();

        if (visibleText) {
          const rawTokens = extractAreaTokensFromText(visibleText);
          // Full-text n-gram evidence set: every area the customer could
          // plausibly be referring to, regardless of phrasing or prefixes.
          // Used to suppress false-positive smuggle rejections when the
          // narrow separator-split raw token misses filler-wrapped names
          // like "Ok lets book slwa to slmya".
          const evidenceIds = collectAreaEvidenceFromText(visibleText, data);

          const applyDecision = (
            field: "pickup_area" | "dropoff_area",
            decision: any,
            rawToken: string | null,
            modelValue: string,
          ) => {
            const modelAreaId: number | null = decision.modelArea?.id ?? null;
            const evidenceCovers =
              modelAreaId !== null && evidenceIds.has(modelAreaId);

            if (decision.action === "override") {
              console.log(
                `[area-evidence] ${field} raw="${rawToken}" model="${modelValue}" decision=override value="${decision.value}"`,
              );
              return { override: decision.value as string, reject: null as any };
            }
            if (decision.action === "reject") {
              if (evidenceCovers) {
                console.log(
                  `[area-evidence] ${field} evidence_verified raw="${rawToken}" model="${modelValue}"→${decision.modelArea?.name_en ?? "?"} evidenceIds=[${Array.from(evidenceIds).join(",")}] (demoted from reject)`,
                );
                return { override: null as any, reject: null as any };
              }
              console.log(
                `[area-evidence] ${field} SMUGGLE raw="${rawToken}" unresolved, model="${modelValue}"→${decision.modelArea?.name_en ?? "?"}, reason=${decision.reason}, suggested=${decision.suggestedArea?.name_en ?? "none"}`,
              );
              const rejectResult = decision.suggestedArea
                ? createAreaSuggestionResult({
                    field,
                    query: decision.rawToken,
                    suggestedArea: decision.suggestedArea,
                    prompt_ar:
                      decision.suggestedPromptAr ||
                      `هل تقصد "${decision.suggestedArea.name_ar}"؟`,
                    prompt_en:
                      decision.suggestedPromptEn ||
                      `Did you mean "${decision.suggestedArea.name_en}"?`,
                    alternativeAreas: decision.suggestedAlternatives,
                  })
                : createAreaNotFoundResult({
                    field,
                    query: decision.rawToken,
                    closestCandidates: collectAreaCandidates(decision.rawToken, data.areas, {
                      topK: 5,
                    }),
                  });
              return { override: null as any, reject: rejectResult };
            }
            if (decision.action === "needs_clarification") {
              if (evidenceCovers) {
                console.log(
                  `[area-evidence] ${field} evidence_verified raw="${rawToken}" model="${modelValue}"→${decision.modelArea.name_en} evidenceIds=[${Array.from(evidenceIds).join(",")}] (demoted from needs_clarification)`,
                );
                return { override: null as any, reject: null as any };
              }
              console.log(
                `[area-evidence] ${field} NEEDS_CLARIFICATION raw="${rawToken}" model="${modelValue}"→${decision.modelArea.name_en}, modelSim=${decision.modelSimilarity.toFixed(3)}, candidates=${decision.closestCandidates.map((c: any) => `${c.area.name_en}(${c.similarity.toFixed(2)})`).join("|") || "none"}`,
              );
              return {
                override: null as any,
                reject: createAreaNeedsClarificationResult({
                  field,
                  query: decision.rawToken,
                  modelArea: decision.modelArea,
                  modelSimilarity: decision.modelSimilarity,
                  matchConfidence: decision.matchConfidence,
                  closestCandidates: decision.closestCandidates,
                }),
              };
            }
            return { override: null as any, reject: null as any };
          };

          const pickupDecision = verifyAreaEvidence({
            rawToken: rawTokens.pickup,
            modelValue: params.pickup_area,
            idOverride: params.pickup_area_id,
            data,
          });
          const pickupApplied = applyDecision(
            "pickup_area",
            pickupDecision,
            rawTokens.pickup,
            params.pickup_area,
          );
          if (pickupApplied.reject) return pickupApplied.reject;
          if (pickupApplied.override)
            params = { ...params, pickup_area: pickupApplied.override };

          const dropoffDecision = verifyAreaEvidence({
            rawToken: rawTokens.dropoff,
            modelValue: params.dropoff_area,
            idOverride: params.dropoff_area_id,
            data,
          });
          const dropoffApplied = applyDecision(
            "dropoff_area",
            dropoffDecision,
            rawTokens.dropoff,
            params.dropoff_area,
          );
          if (dropoffApplied.reject) return dropoffApplied.reject;
          if (dropoffApplied.override)
            params = { ...params, dropoff_area: dropoffApplied.override };
        }

        const findAreaById = (areaId: number): any => {
          const area = data.areas.find((a: any) => a.id === areaId);
          if (!area) return { status: "not_found" };
          return { status: "resolved", area };
        };

        const pickupResolution =
          typeof params.pickup_area_id === "number"
            ? findAreaById(params.pickup_area_id)
            : await resolvePricingAreaQuery(params.pickup_area, data);
        const dropoffResolution =
          typeof params.dropoff_area_id === "number"
            ? findAreaById(params.dropoff_area_id)
            : await resolvePricingAreaQuery(params.dropoff_area, data);

        if (pickupResolution.status === "ambiguous") {
          return createAreaClarificationResult({
            field: "pickup_area",
            query: params.pickup_area,
            prompt_ar: pickupResolution.prompt_ar,
            prompt_en: pickupResolution.prompt_en,
            options: pickupResolution.options,
          });
        }

        if (pickupResolution.status === "suggested") {
          return createAreaSuggestionResult({
            field: "pickup_area",
            query: params.pickup_area,
            suggestedArea: pickupResolution.area,
            prompt_ar: pickupResolution.prompt_ar,
            prompt_en: pickupResolution.prompt_en,
            alternativeAreas: pickupResolution.alternative_areas,
          });
        }

        if (dropoffResolution.status === "ambiguous") {
          return createAreaClarificationResult({
            field: "dropoff_area",
            query: params.dropoff_area,
            prompt_ar: dropoffResolution.prompt_ar,
            prompt_en: dropoffResolution.prompt_en,
            options: dropoffResolution.options,
          });
        }

        if (dropoffResolution.status === "suggested") {
          return createAreaSuggestionResult({
            field: "dropoff_area",
            query: params.dropoff_area,
            suggestedArea: dropoffResolution.area,
            prompt_ar: dropoffResolution.prompt_ar,
            prompt_en: dropoffResolution.prompt_en,
            alternativeAreas: dropoffResolution.alternative_areas,
          });
        }

        const pickup =
          pickupResolution.status === "resolved" ? pickupResolution.area : null;
        const dropoff =
          dropoffResolution.status === "resolved" ? dropoffResolution.area : null;

        if (!pickup) {
          return createAreaNotFoundResult({
            field: "pickup_area",
            query: params.pickup_area,
            closestCandidates: collectAreaCandidates(params.pickup_area, data.areas, {
              topK: 5,
            }),
          });
        }

        if (!dropoff) {
          return createAreaNotFoundResult({
            field: "dropoff_area",
            query: params.dropoff_area,
            closestCandidates: collectAreaCandidates(params.dropoff_area, data.areas, {
              topK: 5,
            }),
          });
        }

        const c = data.currency;
        const routePrices = getBidirectionalRoutePrices(pickup, dropoff);
        const specialDeliveryCapabilities = await getSpecialDeliveryCapabilities();
        const defaultStaticQuote: {
          delivery_type: "sedan_normal" | "sedan_fast" | "van_normal" | "van_fast";
          label_ar: string;
          label_en: string;
          quoted_price: number | null;
          formatted_price: string;
          available_for_direct_chat_booking: boolean | null;
          note: string;
        } = {
          delivery_type: "sedan_normal",
          label_ar: "سيارة عاديه + توصيل عادي",
          label_en: "Standard sedan",
          quoted_price: routePrices.sedan_normal,
          formatted_price: formatPrice(routePrices.sedan_normal, c),
          available_for_direct_chat_booking: null,
          note: "Live booking availability was not checked yet. Do not promise order creation or a payment link until the live ordering API confirms the selected option.",
        };

        let liveBooking: {
          status: "verified" | "lookup_failed";
          options?: Partial<Record<string, any>>;
          common_shipping_methods?: Array<Record<string, unknown>>;
          error?: string;
        } = {
          status: "lookup_failed",
        };

        let recommendedCustomerQuote = defaultStaticQuote;

        try {
          const pickupForOrdering = await resolveAreaForOrdering(params.pickup_area);
          const dropoffForOrdering = await resolveAreaForOrdering(params.dropoff_area);

          if (!pickupForOrdering || !dropoffForOrdering) {
            throw new Error("Unable to resolve route for live ordering availability.");
          }

          const commonShippingMethods = getCommonShippingMethods(
            pickupForOrdering.geoArea.shipping_methods,
            dropoffForOrdering.geoArea.shipping_methods,
          );

          const gridBookable = Boolean(
            pickupForOrdering.geoArea.objectid &&
              dropoffForOrdering.geoArea.objectid,
          );

          const liveOptions = {
            sedan_normal: summarizeLiveDeliveryOption(
              "sedan_normal",
              selectShippingMethod(commonShippingMethods, "sedan_normal"),
              c,
              gridBookable,
            ),
            sedan_fast: summarizeLiveDeliveryOption(
              "sedan_fast",
              selectShippingMethod(commonShippingMethods, "sedan_fast"),
              c,
              gridBookable,
            ),
            van_normal: summarizeLiveDeliveryOption(
              "van_normal",
              selectShippingMethod(commonShippingMethods, "van_normal"),
              c,
              gridBookable,
            ),
            van_fast: summarizeLiveDeliveryOption(
              "van_fast",
              selectShippingMethod(commonShippingMethods, "van_fast"),
              c,
              gridBookable,
            ),
          };

          liveBooking = {
            status: "verified",
            options: liveOptions,
            common_shipping_methods: commonShippingMethods.map((method: any) => ({
              id: method.id,
              name: method.name,
              type: method.type,
              default_price: method.default_price ?? null,
              formatted_price:
                parseNumericPrice(method.default_price) === null
                  ? null
                  : formatPrice(parseNumericPrice(method.default_price), c),
            })),
          };

          recommendedCustomerQuote = {
            delivery_type: "sedan_normal",
            label_ar: "سيارة عاديه + توصيل عادي",
            label_en: "Standard sedan",
            quoted_price: routePrices.sedan_normal,
            formatted_price: formatPrice(routePrices.sedan_normal, c),
            available_for_direct_chat_booking:
              liveOptions.sedan_normal.available_for_direct_chat_booking,
            note: liveOptions.sedan_normal.available_for_direct_chat_booking
              ? "Use this as the default customer quote and default chat booking option."
              : "Always quote standard sedan as the default customer price. If the customer proceeds to book and this option is not available for direct chat booking, use the nearest available live option or assign_agent.",
          };
        } catch (error: any) {
          liveBooking = {
            status: "lookup_failed",
            error: error?.message || String(error),
          };
        }

        const serviceCatalog = [
          buildServiceCatalogEntry("sedan_normal", routePrices.sedan_normal, c, {
            visibility: "default",
            liveOption: liveBooking.options?.sedan_normal,
          }),
          buildServiceCatalogEntry("sedan_fast", routePrices.sedan_fast, c, {
            visibility: "available_on_request",
            liveOption: liveBooking.options?.sedan_fast,
          }),
          buildServiceCatalogEntry("van_normal", routePrices.van_normal, c, {
            visibility: "available_on_request",
            liveOption: liveBooking.options?.van_normal,
          }),
          buildServiceCatalogEntry("van_fast", routePrices.van_fast, c, {
            visibility: "available_on_request",
            liveOption: liveBooking.options?.van_fast,
          }),
          buildServiceCatalogEntry(
            "cooled_van_normal",
            routePrices.cooled_van_normal,
            c,
            {
              visibility: "available_on_request",
              specialCapability: specialDeliveryCapabilities.cooled_van_normal,
            },
          ),
          buildServiceCatalogEntry("cooled_van_fast", routePrices.cooled_van_fast, c, {
            visibility: "available_on_request",
            specialCapability: specialDeliveryCapabilities.cooled_van_fast,
          }),
          buildServiceCatalogEntry("helper_standard", routePrices.helper_standard, c, {
            visibility: "available_on_request",
            specialCapability: specialDeliveryCapabilities.helper_standard,
          }),
        ];

        const recommendedDirectChatBookingOption =
          serviceCatalog
            .filter((entry: any) => entry.direct_chat_booking_status === "verified")
            .map((entry: any) => ({
              delivery_type: entry.delivery_type,
              label_ar: entry.label_ar,
              label_en: entry.label_en,
              quoted_price: getQuotedPriceForDeliveryType(
                routePrices,
                entry.delivery_type,
              ),
              formatted_price: formatPrice(
                getQuotedPriceForDeliveryType(routePrices, entry.delivery_type),
                c,
              ),
              reason:
                entry.delivery_type === "sedan_normal"
                  ? "This is the default quoted option and it is verified for direct chat booking."
                  : "The default quoted option is not verified for direct chat booking on this route, so use this verified option if the customer wants to book in chat.",
            }))[0] ?? null;

        const result = {
          ROUTE_SCOPE_WARNING: `CRITICAL: These prices are ONLY valid for ${pickup.name_ar} → ${dropoff.name_ar}. For ANY other route — even similar-sounding areas — you MUST call get_price again. NEVER estimate, interpolate, or reuse prices from this or any previous get_price call for a different route.`,
          default_quote: {
            instruction:
              "ALWAYS quote this price to the customer. This is the standard sedan delivery price. Do NOT use any other price from this response unless the customer explicitly asks for a different delivery type.",
            delivery_type: "sedan_normal",
            label_en: "Standard sedan delivery",
            label_ar: "سيارة عادية + توصيل عادي",
            price: routePrices.sedan_normal,
            formatted_price: formatPrice(routePrices.sedan_normal, c),
            currency: c,
          },
          route: {
            pickup: {
              name_ar: pickup.name_ar,
              name_en: pickup.name_en,
              governorate: pickup.governorate,
            },
            dropoff: {
              name_ar: dropoff.name_ar,
              name_en: dropoff.name_en,
              governorate: dropoff.governorate,
            },
          },
          recommended_customer_quote: recommendedCustomerQuote,
          recommended_direct_chat_booking_option: recommendedDirectChatBookingOption,
          other_options_if_customer_asks: serviceCatalog.filter(
            (entry: any) => entry.delivery_type !== "sedan_normal",
          ),
          supported_direct_chat_booking_types: serviceCatalog
            .filter((entry: any) => entry.direct_chat_booking_status === "verified")
            .map((entry: any) => entry.delivery_type),
          manual_confirmation_service_types: serviceCatalog
            .filter(
              (entry: any) =>
                entry.direct_chat_booking_status === "manual_confirmation_required",
            )
            .map((entry: any) => entry.delivery_type),
          service_discovery: {
            default_prompt_ar:
              "إذا تحتاجون خيارات ثانية مثل التوصيل السريع أو البوكس أو السيارة المبردة أو خدمة المساعد، نقدر نعطيكم تسعيرتها.",
            default_prompt_en:
              "If you need other options such as express sedan, box van, refrigerated van, or helper service, we can quote them too.",
          },
          live_booking: liveBooking,
        };

        const pickupLabel = pickup.name_ar;
        const dropoffLabel = dropoff.name_ar;
        const defaultPrice = routePrices.sedan_normal;

        let customerMessage: string;
        let customerMessageAr: string;
        let customerMessageEn: string;
        if (defaultPrice === null) {
          customerMessageAr =
            `التوصيل من ${pickupLabel} إلى ${dropoffLabel}\n` +
            `السعر غير متوفر حالياً لهذا المسار.`;
          customerMessageEn =
            `Delivery from ${pickup.name_en} to ${dropoff.name_en}\n` +
            `Price is not available for this route at the moment.`;
        } else {
          const fp = formatPrice(defaultPrice, c);
          customerMessageAr =
            `التوصيل من ${pickupLabel} إلى ${dropoffLabel}\n` +
            `السعر: ${fp} (سيارة عادية)`;
          customerMessageEn =
            `Delivery from ${pickup.name_en} to ${dropoff.name_en}\n` +
            `Price: ${fp} (standard sedan)`;
        }
        customerMessage = customerMessageEn;

        (result as any)._customer_message = customerMessage;
        (result as any)._customer_message_ar = customerMessageAr;
        (result as any)._customer_message_en = customerMessageEn;
        (result as any)._instruction =
          "RELAY the _customer_message to the customer as-is. You may adjust the language to match the conversation language (Arabic-only or English-only) but you MUST keep the exact prices and area names unchanged. Do NOT add, change, or omit any prices or facts.";

        const toolResult = {
          content: [
            {
              type: "text",
              text: JSON.stringify(result, null, 2),
            },
          ],
          details: result,
        };
        await recordGuardState("get_price", toolResult, ctx);
        return toolResult;
      } catch (err: any) {
        return {
          content: [
            {
              type: "text",
              text: `خطأ في نظام الأسعار: ${err.message}. يرجى التحويل لموظف الدعم.`,
            },
          ],
        };
      }
    },
  });
}
