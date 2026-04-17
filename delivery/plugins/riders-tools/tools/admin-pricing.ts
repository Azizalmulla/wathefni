// Admin pricing-management tools.
//
// Extracted from plugins/riders-tools/index.ts (originally lines 8434-8543
// and 8552-9041) as part of Wave 1a of the surgical plugin split. Tool
// bodies are unchanged. All helpers live in `deps` so this file does not
// import from index.ts.
//
// Tools registered:
//   - admin_pricing_source_status
//   - admin_validate_pricing_resolver_overlay
//   - admin_refresh_pricing_cache
//   - admin_publish_pricing_snapshot
//   - admin_publish_pricing_sheet_rows
//   - admin_add_pricing_area_to_google_sheet
//   - admin_update_area_price_in_google_sheet
//   - admin_update_area_price

import type { ToolDeps } from "./deps";

// Local re-declaration of the delivery-type union used by the admin
// update-area tools. The runtime shape matches `QuoteableDeliveryType`
// in index.ts; wave 1b will consolidate this into lib/types.ts.
type QuoteableDeliveryType =
  | "sedan_normal"
  | "sedan_fast"
  | "cooled_van_normal"
  | "cooled_van_fast"
  | "van_normal"
  | "van_fast"
  | "helper_standard";

export function registerAdminPricingTools(api: any, deps: ToolDeps): void {
  const {
    createTextResult,
    errorPayload,
    assertPricingAdminAuthorized,
    pricing,
    behavior,
  } = deps;
  const { normalizeAdminSenderId } = behavior;
  const {
    getPricingSourceStatus,
    loadPricingBaseDataForStatus,
    inspectPricingResolverOverlay,
    summarizePricingResolver,
    clearPricingCache,
    loadPricing,
    loadPricingFallbackData,
    writePublishedPricing,
    buildPublishedPricingData,
    resolvePublishedAreasInput,
    resolvePublishedColumnsInput,
    resolvePublishedResolverInput,
    resolveSheetRowsInput,
    resolveSheetHeaderMapInput,
    normalizeSheetRowsToPublishedAreas,
    resolveAdminPricingArea,
    normalizePricingNumber,
    isPricingGoogleSheetConfigured,
    executeAdminAddPricingAreaToGoogleSheet,
    executeAdminGoogleSheetPriceUpdate,
  } = pricing;

  api.registerTool((ctx: any) => ({
    name: "admin_pricing_source_status",
    label: "Admin Pricing Source Status",
    description:
      "Return the active Riders pricing source, published snapshot path, cache status, and resolver overlay diagnostics. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertPricingAdminAuthorized(ctx);
        const status = await getPricingSourceStatus();
        return createTextResult(
          {
            status: "ok",
            ...status,
          },
          status,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_validate_pricing_resolver_overlay",
    label: "Admin Validate Pricing Resolver Overlay",
    description:
      "Validate the configured Riders pricing resolver overlay file against the active base pricing snapshot without publishing changes. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertPricingAdminAuthorized(ctx);
        const baseData = await loadPricingBaseDataForStatus();
        const overlay = await inspectPricingResolverOverlay(baseData);
        if (!overlay.status.configured) {
          return createTextResult(
            {
              status: "ok",
              message: "No pricing resolver overlay is configured.",
              pricing_resolver_overlay: overlay.status,
            },
            {
              pricing_resolver_overlay: overlay.status,
            },
          );
        }
        if (overlay.status.state !== "active") {
          return createTextResult(
            errorPayload(
              new Error(
                overlay.status.error || "Resolver overlay validation failed.",
              ),
            ),
            {
              pricing_resolver_overlay: overlay.status,
            },
          );
        }

        const mergedResolverSummary = summarizePricingResolver(
          overlay.mergedResolver,
        );
        return createTextResult(
          {
            status: "ok",
            message: "Pricing resolver overlay validated successfully.",
            pricing_resolver_overlay: overlay.status,
            resolver: mergedResolverSummary,
          },
          {
            pricing_resolver_overlay: overlay.status,
            resolver: mergedResolverSummary,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_refresh_pricing_cache",
    label: "Admin Refresh Pricing Cache",
    description:
      "Clear the in-memory Riders pricing cache and report which pricing source is active now. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },

    async execute() {
      try {
        assertPricingAdminAuthorized(ctx);
        clearPricingCache();
        const status = await getPricingSourceStatus();
        return createTextResult(
          {
            status: "ok",
            message: "Pricing cache refreshed.",
            ...status,
          },
          status,
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_publish_pricing_snapshot",
    label: "Admin Publish Pricing Snapshot",
    description:
      "Validate and publish a full Riders pricing areas payload to the live published snapshot. Designed for allowlisted admin workflows that read or update Google Sheets outside the plugin.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        areas: {
          type: ["array", "null"],
          items: {
            type: "object",
            additionalProperties: false,
            properties: {
              id: { type: ["integer", "string"] },
              governorate: { type: "string" },
              name_en: { type: "string" },
              name_ar: { type: "string" },
              sedan_normal: { type: ["number", "string", "null"] },
              sedan_fast: { type: ["number", "string", "null"] },
              cooled_van_normal: { type: ["number", "string", "null"] },
              cooled_van_fast: { type: ["number", "string", "null"] },
              van_normal: { type: ["number", "string", "null"] },
              van_fast: { type: ["number", "string", "null"] },
              helper_standard: { type: ["number", "string", "null"] },
              geo: {
                type: ["object", "null"],
                additionalProperties: false,
                properties: {
                  governorate: { type: ["string", "null"] },
                  area_name_ar: { type: ["string", "null"] },
                  area_name_en: { type: ["string", "null"] },
                  objectid: { type: ["string", "null"] },
                },
              },
            },
          },
        },
        areas_json: {
          type: ["string", "null"],
        },
        columns: {
          type: ["object", "null"],
          additionalProperties: {
            type: "string",
          },
        },
        columns_json: {
          type: ["string", "null"],
        },
        resolver: {
          type: ["object", "null"],
          additionalProperties: true,
        },
        resolver_json: {
          type: ["string", "null"],
        },
        currency: {
          type: ["string", "null"],
        },
        last_updated: {
          type: ["string", "null"],
        },
        dry_run: {
          type: ["boolean", "null"],
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: {
        areas?: unknown[] | null;
        areas_json?: string | null;
        columns?: Record<string, string> | null;
        columns_json?: string | null;
        resolver?: Record<string, unknown> | null;
        resolver_json?: string | null;
        currency?: string | null;
        last_updated?: string | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const rawFallback = await loadPricingFallbackData();
        const parsedAreas = resolvePublishedAreasInput(params);
        const parsedColumns = resolvePublishedColumnsInput(params);
        const parsedResolver = resolvePublishedResolverInput(params);

        const nextData = buildPublishedPricingData(
          {
            currency: params.currency,
            last_updated: params.last_updated,
            columns: parsedColumns,
            resolver: parsedResolver,
            areas: parsedAreas,
          },
          rawFallback,
        );

        if (!params.dry_run) {
          await writePublishedPricing(nextData);
        }

        const status = await getPricingSourceStatus();
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Pricing snapshot validated successfully."
              : "Pricing snapshot published successfully.",
            published: !params.dry_run,
            updated_by_sender:
              normalizeAdminSenderId(ctx.requesterSenderId) || null,
            area_count: nextData.areas.length,
            currency: nextData.currency,
            last_updated: nextData.last_updated,
            active_source: status.active_source,
            published_path: status.published_path,
          },
          {
            pricing_source: status,
            pricing_data: nextData,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_publish_pricing_sheet_rows",
    label: "Admin Publish Pricing Sheet Rows",
    description:
      "Normalize raw pricing sheet rows from the current Google integration into the Riders pricing snapshot, validate them, and publish live. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        rows: {
          type: ["array", "null"],
          items: {
            type: "object",
            additionalProperties: true,
          },
        },
        rows_json: {
          type: ["string", "null"],
        },
        header_map: {
          type: ["object", "null"],
          additionalProperties: {
            type: "string",
          },
        },
        header_map_json: {
          type: ["string", "null"],
        },
        columns: {
          type: ["object", "null"],
          additionalProperties: {
            type: "string",
          },
        },
        columns_json: {
          type: ["string", "null"],
        },
        currency: {
          type: ["string", "null"],
        },
        last_updated: {
          type: ["string", "null"],
        },
        dry_run: {
          type: ["boolean", "null"],
        },
      },
    },

    async execute(
      _toolCallId: string,
      params: {
        rows?: unknown[] | null;
        rows_json?: string | null;
        header_map?: Record<string, string> | null;
        header_map_json?: string | null;
        columns?: Record<string, string> | null;
        columns_json?: string | null;
        currency?: string | null;
        last_updated?: string | null;
        dry_run?: boolean | null;
      },
    ) {
      try {
        assertPricingAdminAuthorized(ctx);
        const rawFallback = await loadPricingFallbackData();
        const rawRows = resolveSheetRowsInput(params);
        const headerMap = resolveSheetHeaderMapInput(params);
        const normalizedRows = normalizeSheetRowsToPublishedAreas(
          rawRows,
          headerMap,
        );
        const parsedColumns = resolvePublishedColumnsInput(params);

        const nextData = buildPublishedPricingData(
          {
            currency: params.currency,
            last_updated: params.last_updated,
            columns: parsedColumns,
            areas: normalizedRows.areas,
          },
          rawFallback,
        );

        if (!params.dry_run) {
          await writePublishedPricing(nextData);
        }

        const status = await getPricingSourceStatus();
        return createTextResult(
          {
            status: "ok",
            message: params.dry_run
              ? "Pricing sheet rows validated successfully."
              : "Pricing sheet rows published successfully.",
            published: !params.dry_run,
            updated_by_sender:
              normalizeAdminSenderId(ctx.requesterSenderId) || null,
            input_row_count: rawRows.length,
            skipped_row_count: normalizedRows.skipped_row_count,
            area_count: nextData.areas.length,
            currency: nextData.currency,
            last_updated: nextData.last_updated,
            active_source: status.active_source,
            published_path: status.published_path,
          },
          {
            pricing_source: status,
            pricing_data: nextData,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_add_pricing_area_to_google_sheet",
    label: "Admin Add Pricing Area To Google Sheet",
    description:
      "Add one new Riders pricing area row to the configured Google Sheet, automatically choose the next available positive integer area id when one is not provided, validate the resulting pricing data, and publish it live. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        area_id: {
          type: ["integer", "null"],
        },
        governorate: {
          type: "string",
        },
        name_en: {
          type: "string",
        },
        name_ar: {
          type: "string",
        },
        sedan_normal: {
          type: ["number", "null"],
        },
        sedan_fast: {
          type: ["number", "null"],
        },
        cooled_van_normal: {
          type: ["number", "null"],
        },
        cooled_van_fast: {
          type: ["number", "null"],
        },
        van_normal: {
          type: ["number", "null"],
        },
        van_fast: {
          type: ["number", "null"],
        },
        helper_standard: {
          type: ["number", "null"],
        },
        profile_id: {
          type: ["string", "null"],
        },
        header_map: {
          type: ["object", "null"],
          additionalProperties: {
            type: "string",
          },
        },
        header_map_json: {
          type: ["string", "null"],
        },
      },
      required: ["governorate", "name_en", "name_ar"],
    },

    async execute(
      _toolCallId: string,
      params: {
        area_id?: number | null;
        governorate: string;
        name_en: string;
        name_ar: string;
        sedan_normal?: number | null;
        sedan_fast?: number | null;
        cooled_van_normal?: number | null;
        cooled_van_fast?: number | null;
        van_normal?: number | null;
        van_fast?: number | null;
        helper_standard?: number | null;
        profile_id?: string | null;
        header_map?: Record<string, string> | null;
        header_map_json?: string | null;
      },
    ) {
      return executeAdminAddPricingAreaToGoogleSheet(ctx, params);
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_update_area_price_in_google_sheet",
    label: "Admin Update Area Price In Google Sheet",
    description:
      "Update one Riders area price in the configured Google Sheet, then immediately validate and republish the live pricing snapshot. Only for allowlisted pricing admins. Use only after the admin explicitly confirms the exact area, delivery type, and new price.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        area_id: {
          type: ["integer", "null"],
        },
        area_name: {
          type: ["string", "null"],
        },
        governorate: {
          type: ["string", "null"],
        },
        delivery_type: {
          type: "string",
          enum: [
            "sedan_normal",
            "sedan_fast",
            "cooled_van_normal",
            "cooled_van_fast",
            "van_normal",
            "van_fast",
            "helper_standard",
          ],
        },
        price: {
          type: ["number", "null"],
        },
        profile_id: {
          type: ["string", "null"],
        },
        header_map: {
          type: ["object", "null"],
          additionalProperties: {
            type: "string",
          },
        },
        header_map_json: {
          type: ["string", "null"],
        },
      },
      required: ["delivery_type", "price"],
    },

    async execute(
      _toolCallId: string,
      params: {
        area_id?: number | null;
        area_name?: string | null;
        governorate?: string | null;
        delivery_type: QuoteableDeliveryType;
        price: number | null;
        profile_id?: string | null;
        header_map?: Record<string, string> | null;
        header_map_json?: string | null;
      },
    ) {
      return executeAdminGoogleSheetPriceUpdate(ctx, params);
    },
  }));

  api.registerTool((ctx: any) => ({
    name: "admin_update_area_price",
    label: "Admin Update Area Price",
    description:
      "Emergency fallback for updating one Riders area price when the Google Sheet write path is unavailable. If the Google Sheet path is configured, this tool will use that live sheet-update path first. Only for allowlisted pricing admins.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        area_id: {
          type: ["integer", "null"],
        },
        area_name: {
          type: ["string", "null"],
        },
        governorate: {
          type: ["string", "null"],
        },
        delivery_type: {
          type: "string",
          enum: [
            "sedan_normal",
            "sedan_fast",
            "cooled_van_normal",
            "cooled_van_fast",
            "van_normal",
            "van_fast",
            "helper_standard",
          ],
        },
        price: {
          type: ["number", "null"],
        },
      },
      required: ["delivery_type", "price"],
    },

    async execute(
      _toolCallId: string,
      params: {
        area_id?: number | null;
        area_name?: string | null;
        governorate?: string | null;
        delivery_type: QuoteableDeliveryType;
        price: number | null;
      },
    ) {
      if (isPricingGoogleSheetConfigured()) {
        return executeAdminGoogleSheetPriceUpdate(ctx, params);
      }

      try {
        assertPricingAdminAuthorized(ctx);
        const data = await loadPricing({ skipAutoSync: true });
        const area = resolveAdminPricingArea(params, data.areas);
        const nextPrice =
          params.price === null ? null : normalizePricingNumber(params.price);
        const previousPrice = area[params.delivery_type];
        const nextArea: any = {
          ...area,
          [params.delivery_type]: nextPrice,
        };
        const nextData: any = {
          ...data,
          last_updated: new Date().toISOString(),
          areas: data.areas.map((item: any) =>
            item.id === area.id ? nextArea : item,
          ),
        };

        await writePublishedPricing(nextData);
        const status = await getPricingSourceStatus();

        return createTextResult(
          {
            status: "ok",
            message: "Pricing updated and published.",
            updated_by_sender:
              normalizeAdminSenderId(ctx.requesterSenderId) || null,
            area: {
              id: nextArea.id,
              governorate: nextArea.governorate,
              name_en: nextArea.name_en,
              name_ar: nextArea.name_ar,
            },
            delivery_type: params.delivery_type,
            previous_price: previousPrice,
            new_price: nextPrice,
            active_source: status.active_source,
            published_path: status.published_path,
            last_updated: status.last_updated,
          },
          {
            pricing_source: status,
            area: nextArea,
          },
        );
      } catch (err) {
        return createTextResult(errorPayload(err));
      }
    },
  }));
}
