#!/usr/bin/env node
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  resolveRegisteredTool,
} from "./_helpers/riders-plugin-loader.mjs";

const pickupArea = process.argv[2];
const dropoffArea = process.argv[3];

if (!pickupArea || !dropoffArea) {
  console.error("Usage: node scripts/check-price-route.mjs <pickup_area> <dropoff_area>");
  process.exit(1);
}

async function run() {
  const getPriceTool = await resolveRegisteredTool(
    import.meta.url,
    "get_price",
    {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath:
          process.env.RIDERS_PRICING_PUBLISHED_PATH || defaultPublishedPricingPath,
        resolverOverlayPath:
          process.env.RIDERS_PRICING_RESOLVER_OVERLAY_PATH || defaultResolverOverlayPath,
        adminAllowlist: [],
        googleSheet: {
          spreadsheetId: process.env.RIDERS_PRICING_SHEET_ID || "",
          sheetName: process.env.RIDERS_PRICING_SHEET_NAME || "",
          headerRow: Number(process.env.RIDERS_PRICING_SHEET_HEADER_ROW || "1"),
          autoSync: {
            enabled: true,
            minIntervalMs: 0,
          },
        },
      },
    },
  );

  const result = await getPriceTool.execute("check-route", {
    pickup_area: pickupArea,
    dropoff_area: dropoffArea,
  });
  const text = result?.content?.find?.((item) => item?.type === "text")?.text || "";
  console.log(text);
}

run().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
