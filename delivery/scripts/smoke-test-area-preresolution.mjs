#!/usr/bin/env node
import assert from "node:assert/strict";
import { loadRidersToolsModule } from "./_helpers/riders-plugin-loader.mjs";

const PUBLISHED_PATH =
  "/Users/azizalmulla/Desktop/claw/delivery/workspaces/riders/data/pricing.published.json";

async function main() {
  const mod = await loadRidersToolsModule(import.meta.url);
  const {
    extractAreaTokensFromText,
    resolveAreaDeterministicSync,
    isAreaMismatch,
    buildPublishedPricingData,
  } = mod.__resolverTestHooks;

  // Load pricing data
  const fs = await import("node:fs");
  const raw = fs.readFileSync(PUBLISHED_PATH, "utf-8");
  const data = JSON.parse(raw);

  // --- extractAreaTokensFromText ---

  const t1 = extractAreaTokensFromText("بكم التوصيل من 9bya الى حولي");
  assert.equal(t1.pickup, "9bya");
  assert.equal(t1.dropoff, "حولي");
  console.log("ok - extractAreaTokensFromText: Arabic pricing phrase with Arabizi area");

  const t2 = extractAreaTokensFromText("9bya");
  assert.equal(t2.pickup, "9bya");
  assert.equal(t2.dropoff, null);
  console.log("ok - extractAreaTokensFromText: bare Arabizi token");

  const t3 = extractAreaTokensFromText("delivery from farwanya to salmya");
  assert.equal(t3.pickup, "farwanya");
  assert.equal(t3.dropoff, "salmya");
  console.log("ok - extractAreaTokensFromText: English delivery phrase");

  const t4 = extractAreaTokensFromText("hi");
  assert.equal(t4.pickup, null);
  assert.equal(t4.dropoff, null);
  console.log("ok - extractAreaTokensFromText: greeting returns null");

  const t5 = extractAreaTokensFromText("من حولي الى السالمية");
  assert.equal(t5.pickup, "حولي");
  assert.equal(t5.dropoff, "السالمية");
  console.log("ok - extractAreaTokensFromText: Arabic from-to pattern");

  const t6 = extractAreaTokensFromText("بكم التوصيل من الرقة لصباح الاحمد السكنية");
  assert.equal(t6.pickup, "الرقة");
  assert.equal(t6.dropoff, "صباح الاحمد السكنية");
  console.log("ok - extractAreaTokensFromText: ل prefix as separator");

  const t7 = extractAreaTokensFromText("how much from 9bya to hawalli");
  assert.equal(t7.pickup, "9bya");
  assert.equal(t7.dropoff, "hawalli");
  console.log("ok - extractAreaTokensFromText: English how-much with Arabizi");

  // --- resolveAreaDeterministicSync ---

  const r1 = resolveAreaDeterministicSync("9bya", data);
  assert.ok(r1, "Expected 9bya to resolve");
  assert.equal(r1.area.name_en, "Subiya");
  console.log(`ok - resolveAreaDeterministicSync: 9bya → ${r1.area.name_en} (${r1.status})`);

  const r2 = resolveAreaDeterministicSync("7walli", data);
  assert.ok(r2, "Expected 7walli to resolve");
  assert.equal(r2.status, "resolved");
  assert.equal(r2.area.name_en, "Hawalli");
  console.log(`ok - resolveAreaDeterministicSync: 7walli → ${r2.area.name_en} (${r2.status})`);

  const r3 = resolveAreaDeterministicSync("salmya", data);
  assert.ok(r3, "Expected salmya to resolve");
  assert.equal(r3.area.name_en, "Salmiya");
  console.log(`ok - resolveAreaDeterministicSync: salmya → ${r3.area.name_en} (${r3.status})`);

  const r4 = resolveAreaDeterministicSync("حولي", data);
  assert.ok(r4, "Expected حولي to resolve");
  assert.equal(r4.status, "resolved");
  assert.equal(r4.area.name_en, "Hawalli");
  console.log(`ok - resolveAreaDeterministicSync: حولي → ${r4.area.name_en} (${r4.status})`);

  const r5 = resolveAreaDeterministicSync("الجابرية", data);
  assert.ok(r5, "Expected الجابرية to resolve");
  assert.equal(r5.status, "resolved");
  assert.equal(r5.area.name_en, "Jabriya");
  console.log(`ok - resolveAreaDeterministicSync: الجابرية → ${r5.area.name_en} (${r5.status})`);

  // --- isAreaMismatch ---

  // 9bya resolves to Subiya; model said الجابرية (Jabriya) → mismatch
  const subiya = resolveAreaDeterministicSync("9bya", data);
  assert.ok(subiya?.status === "resolved" || subiya?.status === "suggested");
  const mismatch1 = isAreaMismatch(subiya.area, "الجابرية", data);
  assert.equal(mismatch1, true, "9bya→Subiya vs model's الجابرية should be a mismatch");
  console.log("ok - isAreaMismatch: 9bya (Subiya) vs الجابرية (Jabriya) = mismatch");

  // 7walli resolves to Hawalli; model said حولي → no mismatch (same area)
  const hawalli = resolveAreaDeterministicSync("7walli", data);
  assert.ok(hawalli?.status === "resolved");
  const mismatch2 = isAreaMismatch(hawalli.area, "حولي", data);
  assert.equal(mismatch2, false, "7walli→Hawalli vs model's حولي should match");
  console.log("ok - isAreaMismatch: 7walli (Hawalli) vs حولي = match");

  // salmya resolves to Salmiya; model said Salmy → mismatch
  const salmiya = resolveAreaDeterministicSync("salmya", data);
  assert.ok(salmiya);
  const mismatch3 = isAreaMismatch(salmiya.area, "Salmy", data);
  assert.equal(mismatch3, true, "salmya→Salmiya vs model's Salmy should be a mismatch");
  console.log("ok - isAreaMismatch: salmya (Salmiya) vs Salmy = mismatch");

  // Correct match: model passes Salmiya for salmya → no mismatch
  const mismatch4 = isAreaMismatch(salmiya.area, "Salmiya", data);
  assert.equal(mismatch4, false, "salmya→Salmiya vs model's Salmiya should match");
  console.log("ok - isAreaMismatch: salmya (Salmiya) vs Salmiya = match");

  console.log("\nAll pre-resolution regression tests passed.");
  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
