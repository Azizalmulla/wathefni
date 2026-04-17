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
    assert.equal(parsed.route?.pickup?.name_en, testCase.pickup_area, `Pickup route name mismatch for ${testCase.pickup_area}`);
    assert.equal(parsed.route?.dropoff?.name_en, testCase.dropoff_area, `Dropoff route name mismatch for ${testCase.dropoff_area}`);
    assert.equal(parsed.default_quote?.delivery_type, "sedan_normal", "Expected sedan_normal default quote");
    assert.equal(typeof parsed.default_quote?.price, "number", "Expected numeric default quote price");
    assert(parsed.default_quote.price > 0, "Expected positive default quote price");
    assert(typeof parsed.recommended_customer_quote?.delivery_type === "string", "Expected recommended_customer_quote.delivery_type");
    assert.equal(typeof parsed.recommended_customer_quote?.quoted_price, "number", "Expected recommended_customer_quote.quoted_price");
    assert(parsed.recommended_customer_quote.quoted_price > 0, "Expected positive recommended quoted price");
    assert(
      Array.isArray(parsed.other_options_if_customer_asks) && parsed.other_options_if_customer_asks.length > 0,
      "Expected non-empty alternative options list",
    );
    assert(Array.isArray(parsed.supported_direct_chat_booking_types), "Expected supported direct-chat booking types array");
    assert(Array.isArray(parsed.manual_confirmation_service_types), "Expected manual confirmation service types array");
    assert.equal(typeof parsed._customer_message_en, "string", "Expected English customer message");
    assert(
      parsed._customer_message_en.includes(testCase.pickup_area) && parsed._customer_message_en.includes(testCase.dropoff_area),
      `Expected English customer message to mention ${testCase.pickup_area} and ${testCase.dropoff_area}`,
    );
    assert.equal(typeof parsed.live_booking?.status, "string", "Expected live booking status string");
    assert(
      /express sedan|box van|refrigerated van|helper/i.test(parsed.service_discovery?.default_prompt_en || ""),
      "Expected service discovery prompt to mention alternative service categories",
    );
    console.log(
      JSON.stringify(
        {
          route: `${testCase.pickup_area} -> ${testCase.dropoff_area}`,
          recommended_customer_quote: parsed.recommended_customer_quote,
          supported_direct_chat_booking_types: parsed.supported_direct_chat_booking_types,
          manual_confirmation_service_types: parsed.manual_confirmation_service_types,
          live_booking_status: parsed.live_booking?.status || null,
        },
        null,
        2,
      ),
    );
  }

  process.exit(0);
}

run().catch((err) => {
  console.error(`Failed: ${err.message}`);
  process.exit(1);
});
