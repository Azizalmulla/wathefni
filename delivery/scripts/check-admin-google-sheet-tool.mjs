#!/usr/bin/env node
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  loadPluginRegistrations,
} from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const registeredTools = await loadPluginRegistrations(import.meta.url, {
      pricing: {
        sourceMode: process.env.RIDERS_PRICING_SOURCE_MODE || "published_preferred",
        publishedPath: process.env.RIDERS_PRICING_PUBLISHED_PATH || defaultPublishedPricingPath,
        resolverOverlayPath:
          process.env.RIDERS_PRICING_RESOLVER_OVERLAY_PATH || defaultResolverOverlayPath,
        adminAllowlist: [],
        googleSheet: {
          spreadsheetId: process.env.RIDERS_PRICING_SHEET_ID,
          sheetName: process.env.RIDERS_PRICING_SHEET_NAME,
          headerRow: Number(process.env.RIDERS_PRICING_SHEET_HEADER_ROW || "1"),
        },
      },
    });

  const builtTools = registeredTools.map((definition) =>
    typeof definition === "function"
      ? definition({ requesterSenderId: "99338566", senderIsOwner: false })
      : definition,
  );

  console.log(
    JSON.stringify(
      {
        tool_count: builtTools.length,
        has_google_sheet_update_tool: builtTools.some(
          (tool) => tool?.name === "admin_update_area_price_in_google_sheet",
        ),
      },
      null,
      2,
    ),
  );
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exit(1);
  });
