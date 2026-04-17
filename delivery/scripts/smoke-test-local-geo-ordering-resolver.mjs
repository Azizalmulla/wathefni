#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { loadRidersToolsModule } from "./_helpers/riders-plugin-loader.mjs";

const FIXTURE_PATH =
  "/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.resolver-fixture.json";

function buildGeoArea(overrides) {
  return {
    id: 1,
    objectid: null,
    name: "",
    lat: "29.0000",
    lng: "47.0000",
    governorate_id: 1,
    governorate_name: "Test Governorate",
    shipping_methods: [],
    ...overrides,
  };
}

async function main() {
  const fixture = JSON.parse(await fs.readFile(FIXTURE_PATH, "utf-8"));
  const mod = await loadRidersToolsModule(import.meta.url);
  const hooks = mod.__resolverTestHooks;
  if (!hooks) {
    throw new Error("Resolver test hooks not exported");
  }

  const normalized = hooks.buildPublishedPricingData(
    {
      currency: fixture.currency,
      last_updated: fixture.last_updated,
      columns: fixture.columns,
      resolver: fixture.resolver,
      areas: fixture.areas,
    },
    fixture,
  );

  const groupedResolution = await hooks.resolvePricingAreaQuery("جنوب سعد العبدالله", normalized);
  assert.equal(groupedResolution.status, "resolved");
  assert.equal(groupedResolution.area.geo.objectid, "geo-south-saad");
  const groupedGeoMatch = hooks.resolveGeoAreaMatch(groupedResolution.area, [
    buildGeoArea({ id: 10, objectid: "geo-other", name: "جنوب سعد العبدالله" }),
    buildGeoArea({ id: 11, objectid: "geo-south-saad", name: "جنوب سعد العبدالله قطاع خاص" }),
  ]);
  assert(groupedGeoMatch, "Expected grouped geo match");
  assert.equal(groupedGeoMatch.id, 11);
  console.log("ok - pricing group geo metadata chooses exact Grid objectid");

  const directResolution = await hooks.resolvePricingAreaQuery("علي صباح", normalized);
  assert.equal(directResolution.status, "resolved");
  assert.equal(directResolution.area.geo.area_name_ar, "علي صباح السالم");
  const directGeoMatch = hooks.resolveGeoAreaMatch(directResolution.area, [
    buildGeoArea({ id: 20, objectid: "geo-other", name: "ضاحية علي صباح السالم" }),
    buildGeoArea({ id: 21, objectid: "geo-ali-sabah", name: "علي صباح السالم" }),
  ]);
  assert(directGeoMatch, "Expected direct geo match");
  assert.equal(directGeoMatch.id, 21);
  console.log("ok - direct area geo metadata matches Grid area variant");

  const fallbackResolution = await hooks.resolvePricingAreaQuery("المطلاع", normalized);
  assert.equal(fallbackResolution.status, "resolved");
  assert.equal(fallbackResolution.area.geo, undefined);
  const fallbackGeoMatch = hooks.resolveGeoAreaMatch(fallbackResolution.area, [
    buildGeoArea({ id: 30, objectid: "geo-mutlaa", name: "المطلاع" }),
  ]);
  assert(fallbackGeoMatch, "Expected fallback geo match");
  assert.equal(fallbackGeoMatch.id, 30);
  console.log("ok - geo resolver still falls back to name matching when metadata is absent");

  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
