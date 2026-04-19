#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: fast-path address accepts `block + street + substantive-extra`
// (apartment / floor / door / …) as a complete address, matching the
// downstream `hasCompleteTextAddress` predicate in booking-flow.ts.
//
// Context: on 2026-04-19 the LLM dropped "apartment 11, floor 4, door 1"
// when the customer wrote "block 11,street7.apartment 11, floor 4, door 1",
// and the fast-path extractor silently bailed because its legacy rule
// hard-required `house`. That produced a re-ask for street and house
// even though the address was locatable. Aligning the fast-path with
// the completeness gate eliminates that re-ask.
//
// This smoke locks three properties:
//   (1) The fast-path fires with high confidence when block + street +
//       substantive-extra are present (house missing).
//   (2) It still fires when house is present (back-compat).
//   (3) The local `isSubstantiveExtra` predicate in the fast-path and the
//       canonical `hasSubstantiveAddressExtra` in booking-flow.ts AGREE
//       on a curated fixture, so future edits don't drift.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

async function loadTsModule(relativePath) {
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const { extractAddressForRole, extractForNextAction } = await loadTsModule(
  "plugins/shared/fast-path-extractor.ts",
);
const { hasSubstantiveAddressExtra } = await loadTsModule(
  "plugins/octopus-channel/lib/booking-flow.ts",
);

// ---------------------------------------------------------------------------
// (1) The canonical incident case.
// ---------------------------------------------------------------------------
{
  const text = "block 11,street7.apartment 11, floor 4, door 1";
  const res = extractAddressForRole({ text, role: "delivery" });
  assert.equal(res.confidence, "high", "E1: must fire high-confidence");
  assert.ok(res.patch, "E1: patch returned");
  assert.equal(res.patch.address_block, "11", "E1: block");
  assert.equal(res.patch.address_street, "7", "E1: street extracted from 'street7'");
  assert.equal(res.patch.address_role, "delivery", "E1: role");
  assert.ok(
    res.patch.address_extra && /apartment\s*11/.test(res.patch.address_extra),
    "E1: extra includes apartment",
  );
  assert.ok(
    res.reasons.includes("labeled_address_complete_via_extra"),
    "E1: reason tag points at the new branch",
  );
}

// ---------------------------------------------------------------------------
// (2) Back-compat: house present, no extra.
// ---------------------------------------------------------------------------
{
  const res = extractAddressForRole({
    text: "block 11, street 7, house 19",
    role: "pickup",
  });
  assert.equal(res.confidence, "high", "E2: block+street+house still fires");
  assert.equal(res.patch.address_house, "19", "E2: house captured");
  assert.ok(
    res.reasons.includes("labeled_address_complete"),
    "E2: legacy reason tag",
  );
}

// ---------------------------------------------------------------------------
// (3) House present AND extra present — both preserved.
// ---------------------------------------------------------------------------
{
  const res = extractAddressForRole({
    text: "block 11, street 7, house 19, apartment 3 floor 2",
    role: "delivery",
  });
  assert.equal(res.confidence, "high", "E3: house+extra both present");
  assert.equal(res.patch.address_house, "19", "E3: house kept");
  assert.ok(/apartment\s*3/.test(res.patch.address_extra), "E3: extra kept");
}

// ---------------------------------------------------------------------------
// (4) Still bails when street/avenue AND house/extra all missing. Block
//     alone doesn't even reach the new branch (`tryAddressLabeled`
//     requires ≥2 labeled parts to return anything at all), so we only
//     assert the outer confidence.
// ---------------------------------------------------------------------------
{
  const res = extractAddressForRole({
    text: "block 11",
    role: "delivery",
  });
  assert.equal(res.confidence, "none", "E4: block alone not enough");
}

// (4b) Two labeled parts but NEITHER a street/avenue NOR house/extra —
//      e.g. "block 11, avenue 3" is fine (street_or_avenue satisfied);
//      but "block 11, something-we-don't-parse" with only one label
//      reaches the inner partial gate. Construct a case with block +
//      house-less-and-extra-less to exercise the new gate branch.
{
  const res = extractAddressForRole({
    // Two valid labels but house is missing and no interior locator.
    // Note: our street regex needs the word "street". This has block +
    // avenue + (nothing house-like) — should bail on house_or_extra.
    text: "block 11, avenue 3",
    role: "delivery",
  });
  assert.equal(res.confidence, "none", "E4b: no house/extra bails");
  assert.ok(
    res.reasons.includes("labeled_address_partial_ignored"),
    "E4b: partial reason tag fired",
  );
  // Granular telemetry: bail reason must pinpoint WHICH gate failed so
  // prod logs show the recurring miss-class directly.
  assert.ok(
    res.reasons.includes("labeled_missing_house_or_extra"),
    "E4b: granular reason identifies house_or_extra as the missing gate",
  );
  assert.ok(
    !res.reasons.includes("labeled_missing_block"),
    "E4b: block present, must not be tagged missing",
  );
  assert.ok(
    !res.reasons.includes("labeled_missing_street_or_avenue"),
    "E4b: avenue satisfies street_or_avenue",
  );
}

// (4c) Text that matches neither tryAddressLabeled nor the bare-triplet
//      shape must surface `no_labeled_or_bare_shape` so prod logs flag
//      free-form address text as a coverage gap.
{
  const res = extractAddressForRole({
    text: "I'm at the blue tower near the highway",
    role: "delivery",
  });
  assert.equal(res.confidence, "none", "E4c: free-form text bails");
  assert.ok(
    res.reasons.includes("no_labeled_or_bare_shape"),
    "E4c: free-form telemetry reason emitted",
  );
}

// ---------------------------------------------------------------------------
// (5) Block + house/extra but no street — still bails (street_or_avenue
//     required to locate a place in Kuwait).
// ---------------------------------------------------------------------------
{
  const res = extractAddressForRole({
    text: "block 11, apartment 3",
    role: "delivery",
  });
  assert.equal(res.confidence, "none", "E5: missing street/avenue bails");
}

// ---------------------------------------------------------------------------
// (6) Arabic substantive extra also accepted.
// ---------------------------------------------------------------------------
{
  const res = extractAddressForRole({
    text: "قطعة 11 شارع 7 شقة 3",
    role: "delivery",
  });
  assert.equal(res.confidence, "high", "E6: Arabic labels + شقة accepted");
  assert.equal(res.patch.address_block, "11", "E6: block");
  assert.equal(res.patch.address_street, "7", "E6: street");
  assert.ok(/شقة/.test(res.patch.address_extra || ""), "E6: extra has شقة");
}

// ---------------------------------------------------------------------------
// (7) Top-level dispatch works the same way for ASK_DELIVERY_ADDRESS.
// ---------------------------------------------------------------------------
{
  const res = extractForNextAction({
    text: "block 11,street7.apartment 11, floor 4, door 1",
    action: "ASK_DELIVERY_ADDRESS",
    whatsappNumber: null,
  });
  assert.equal(res.confidence, "high", "E7: ASK_DELIVERY_ADDRESS dispatch");
  assert.equal(res.patch.address_role, "delivery", "E7: role");
}

// ---------------------------------------------------------------------------
// (8) Anti-drift: the fast-path's local `isSubstantiveExtra` mirror must
//     agree with the canonical `hasSubstantiveAddressExtra`. We can only
//     exercise strings the extractor's INTERIOR_RE patterns actually
//     capture into `labeled.extra` (free-form text outside those
//     patterns never reaches the predicate at all), so the fixture is
//     scoped to interior-locator phrases. A disagreement here means
//     someone edited the locator-keyword set on one side without
//     re-syncing the other.
// ---------------------------------------------------------------------------
const INTERIOR_FIXTURE = [
  // positives (all must hit INTERIOR_RE_EN or INTERIOR_RE_AR)
  "apartment 11",
  "apartment 11, floor 4, door 1",
  "apt 3",
  "flat 9",
  "floor 2",
  "office 5",
  "door 7",
  "gate 2",
  "suite 9",
  "unit 4",
  "شقة 3",
  "دور 2",
  "شقه 3 دور 2",
  "بوابة 7",
  "طابق 4",
  "مكتب 9",
];
for (const s of INTERIOR_FIXTURE) {
  const canonical = hasSubstantiveAddressExtra(s);
  const text = `block 11, street 7, ${s}`;
  const res = extractAddressForRole({ text, role: "pickup" });
  const extractorAccepts = res.confidence === "high";
  // Every entry in this fixture should be accepted by BOTH sides.
  assert.equal(
    canonical,
    true,
    `E8a: canonical predicate must accept interior fixture ${JSON.stringify(s)}`,
  );
  assert.equal(
    extractorAccepts,
    true,
    `E8b: fast-path must accept interior fixture ${JSON.stringify(s)}`,
  );
}

// Negative fixture — strings that shouldn't satisfy either side.
const NEGATIVE_FIXTURE = ["", "a", "ab", "abc", "lmno", "nothing special"];
for (const s of NEGATIVE_FIXTURE) {
  const canonical = hasSubstantiveAddressExtra(s);
  assert.equal(
    canonical,
    false,
    `E8c: canonical must reject ${JSON.stringify(s)}`,
  );
  const text = `block 11, street 7, ${s}`;
  const res = extractAddressForRole({ text, role: "pickup" });
  // Without house and without an interior-locator match, extractor
  // bails. We don't assert via the canonical predicate here because
  // these strings never reach the extractor's `extra` field.
  assert.equal(
    res.confidence,
    "none",
    `E8d: fast-path must bail for ${JSON.stringify(s)}`,
  );
}

console.log("ALL PASS smoke-test-fast-path-address-extra.mjs");
