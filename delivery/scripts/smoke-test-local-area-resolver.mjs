#!/usr/bin/env node
import assert from "node:assert/strict";
import { parseToolText, resolveRegisteredTool } from "./_helpers/riders-plugin-loader.mjs";

const FIXTURE_PATH =
  "/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.resolver-fixture.json";

async function loadGetPriceTool() {
  return await resolveRegisteredTool(
    import.meta.url,
    "get_price",
    {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: FIXTURE_PATH,
        adminAllowlist: [],
      },
    },
  );
}

async function runCase(getPriceTool, testCase) {
  const result = await getPriceTool.execute(`resolver-${testCase.id}`, {
    pickup_area: testCase.pickup_area,
    dropoff_area: testCase.dropoff_area,
  });
  const text = result?.content?.find?.((item) => item?.type === "text")?.text || "";
  return parseToolText(text);
}

async function main() {
  const getPriceTool = await loadGetPriceTool();

  const groupedAlias = await runCase(getPriceTool, {
    id: "grouped-alias",
    pickup_area: "المطلاع",
    dropoff_area: "جنوب سعد العبدالله",
  });
  assert(groupedAlias.json, "Expected grouped alias case to return JSON");
  assert.equal(groupedAlias.json.route.dropoff.name_ar, "جنوب سعد العبدالله");
  assert.equal(groupedAlias.json.default_quote.price, 5);
  assert.equal(groupedAlias.json.recommended_customer_quote.quoted_price, 5);
  assert.match(groupedAlias.json._customer_message_ar, /السعر: 5\.000 KWD/);
  assert.doesNotMatch(groupedAlias.json._customer_message_ar, /تأكيد|التوفر/);
  console.log("ok - grouped alias resolves through pricing group metadata");

  const directAlias = await runCase(getPriceTool, {
    id: "direct-alias",
    pickup_area: "علي صباح",
    dropoff_area: "حولي",
  });
  assert(directAlias.json, "Expected direct alias case to return JSON");
  assert.equal(directAlias.json.route.pickup.name_ar, "ضاحية علي صباح السالم");
  assert.equal(directAlias.json.default_quote.price, 2.75);
  console.log("ok - direct alias resolves to canonical area metadata");

  const ambiguityAlias = await runCase(getPriceTool, {
    id: "ambiguity",
    pickup_area: "دسمان",
    dropoff_area: "الخيران",
  });
  assert(ambiguityAlias.json, "Expected ambiguity case to return JSON");
  assert.equal(ambiguityAlias.json.status, "clarification_required");
  assert.equal(ambiguityAlias.json.field, "dropoff_area");
  assert.equal(ambiguityAlias.json.prompt_ar, "الخيران السكنية أم شاليهات الخيران؟");
  console.log("ok - ambiguity alias asks for clarification instead of guessing");

  const hawallyTypo = await runCase(getPriceTool, {
    id: "hawally-typo",
    pickup_area: "Hawally",
    dropoff_area: "دسمان",
  });
  assert(hawallyTypo.json, "Expected Hawally typo case to return JSON");
  assert.equal(hawallyTypo.json.route.pickup.name_en, "Hawalli");
  assert.equal(hawallyTypo.json.default_quote.price, 1.5);
  console.log("ok - Hawally typo resolves through deterministic Latin normalization");

  const arabiziHawalli = await runCase(getPriceTool, {
    id: "arabizi-hawalli",
    pickup_area: "7walli",
    dropoff_area: "دسمان",
  });
  assert(arabiziHawalli.json, "Expected 7walli case to return JSON");
  assert.equal(arabiziHawalli.json.route.pickup.name_en, "Hawalli");
  assert.equal(arabiziHawalli.json.default_quote.price, 1.5);
  console.log("ok - 7walli resolves through Arabizi normalization");

  const refusedCollapse = await runCase(getPriceTool, {
    id: "unsafe-collapse",
    pickup_area: "جنوب صباح الاحمد",
    dropoff_area: "الأحمدي",
  });
  assert(refusedCollapse.json, "Expected unresolved area case to return structured JSON");
  assert(
    refusedCollapse.json.status === "clarification_required" || refusedCollapse.json.status === "area_not_found",
    `Expected clarification_required or area_not_found, got ${refusedCollapse.json.status}`,
  );
  assert.equal(refusedCollapse.json.field, "dropoff_area");
  assert.match(refusedCollapse.json.prompt_ar, /الأحمدي/);
  console.log(`ok - unsafe broad area triggers ${refusedCollapse.json.status} with disambiguation`);

  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
