#!/usr/bin/env node
import assert from "node:assert/strict";
import {
  defaultPublishedPricingPath,
  resolveRegisteredTool,
} from "./_helpers/riders-plugin-loader.mjs";

const cases = [
  { pickup_area: "Dasman", dropoff_area: "Mansouriya" },
  { pickup_area: "Dasman", dropoff_area: "Airport" },
  { pickup_area: "Dasman", dropoff_area: "Northern Artificial island" },
];

async function run() {
  const getPriceTool = await resolveRegisteredTool(
    import.meta.url,
    "get_price",
    {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath:
          process.env.RIDERS_PRICING_PUBLISHED_PATH || defaultPublishedPricingPath,
        adminAllowlist: [],
      },
    },
  );

  for (const testCase of cases) {
    const result = await getPriceTool.execute("smoke", testCase);
    const text = result?.content?.find?.((item) => item?.type === "text")?.text || "";
    const parsed = JSON.parse(text);
    const customerMessage = String(parsed._customer_message_en || parsed._customer_message || "");
    assert(customerMessage, `Expected customer-facing message for ${testCase.pickup_area} -> ${testCase.dropoff_area}`);
    assert(
      customerMessage.includes(testCase.pickup_area) && customerMessage.includes(testCase.dropoff_area),
      `Expected customer-facing message to mention ${testCase.pickup_area} and ${testCase.dropoff_area}`,
    );
    assert(/Price:\s*\d+\.\d{3}\s*KWD/i.test(customerMessage), `Expected structured price in customer message: ${customerMessage}`);
    console.log(`\n=== ${testCase.pickup_area} -> ${testCase.dropoff_area} ===\n`);
    console.log(customerMessage);
  }

  process.exit(0);
}

run().catch((err) => {
  console.error(`Failed: ${err.message}`);
  process.exit(1);
});
