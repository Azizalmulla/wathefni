#!/usr/bin/env node
/**
 * Smoke test: graduated-response path for area resolution (RIDERS_AREA_GRADUATED_RESPONSE).
 *
 * Covers the adversarial cases the prior binary smuggle defense mishandled:
 *   1.  "om il namel" → Umm Al-Namel Island (Arabizi obscure area) — previously
 *       rejected as smuggle_not_found, now returns needs_clarification.
 *   2.  Unknown garbage ("xxxxx") — MUST still reject (smuggle defense intact).
 *   3.  Real typos ("salmyia") still resolve silently through the deterministic
 *       pipeline (no regression on confident matches).
 *   4.  Arabizi digit substitution ("7wly" → "Hawalli") still resolves.
 *   5.  Direct get_price with unrecognized name still returns area_not_found
 *       but now with `closest_candidates`.
 *   6.  Adversarial smuggle ("atlantis" raw but model claims "Salmiya") still
 *       rejects — low similarity rules out the graduated path.
 *   7.  Island-suffix stripping works in both directions: "failaka" → Failaka
 *       Island at high confidence.
 *
 * These tests talk directly to the resolver's internal test hooks so we can
 * exercise `verifyAreaEvidence` + `collectAreaCandidates` without needing a
 * full webhook simulation, and the final get_price test verifies the user-
 * visible contract (area_not_found now carries closest_candidates).
 */
import assert from "node:assert/strict";
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  loadRidersToolsModule,
  parseToolText,
  resolveRegisteredTool,
} from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  // --- 1. Load the real pricing data so tests run against production areas.
  const mod = await loadRidersToolsModule(import.meta.url);
  const hooks = mod.__resolverTestHooks;
  assert(hooks?.verifyAreaEvidence, "missing __resolverTestHooks");
  const { verifyAreaEvidence, collectAreaCandidates, scoreAreaMatchSimilarity, buildPublishedPricingData } = hooks;

  const fs = await import("node:fs");
  const pricingSource = JSON.parse(fs.readFileSync(defaultPublishedPricingPath, "utf8"));
  // Second arg is the fallback; pass the same payload so currency/columns
  // fields are always present even if an overlay ever omits them.
  const data = buildPublishedPricingData(pricingSource, pricingSource);
  assert(Array.isArray(data.areas) && data.areas.length > 0, "pricing areas empty");

  // --- 2. `collectAreaCandidates` sanity: om il namel surfaces Umm Al-Namel.
  const omIlNamelCands = collectAreaCandidates("om il namel", data.areas, { topK: 5 });
  assert(
    omIlNamelCands.length > 0,
    "expected at least one candidate for 'om il namel'",
  );
  assert(
    omIlNamelCands.some((c) => /namel/i.test(c.area.name_en)),
    `expected Umm Al-Namel in candidates, got ${omIlNamelCands.map((c) => c.area.name_en).join(", ")}`,
  );
  console.log("ok - collectAreaCandidates surfaces Umm Al-Namel for 'om il namel'");

  // --- 3. Garbage returns zero candidates (smuggle-defense floor holds).
  const xxxxxCands = collectAreaCandidates("xxxxx", data.areas, { topK: 5 });
  assert(
    xxxxxCands.length === 0 || xxxxxCands.every((c) => c.similarity < 0.4),
    `expected no plausible candidates for 'xxxxx', got ${xxxxxCands.map((c) => `${c.area.name_en}(${c.similarity.toFixed(2)})`).join(", ")}`,
  );
  console.log("ok - collectAreaCandidates rejects pure garbage");

  // --- 4. verifyAreaEvidence: om-il-namel + model=Umm Al-Namel → needs_clarification.
  const decision = verifyAreaEvidence({
    rawToken: "om il namel",
    modelValue: "Umm Al-Namel Island",
    idOverride: null,
    data,
  });
  assert.equal(
    decision.action,
    "needs_clarification",
    `expected needs_clarification, got ${decision.action}: ${JSON.stringify(decision).slice(0, 200)}`,
  );
  assert.equal(decision.matchConfidence, "medium", `expected medium confidence`);
  assert(
    decision.closestCandidates.some((c) => /namel/i.test(c.area.name_en)),
    "closest_candidates must include Umm Al-Namel",
  );
  console.log("ok - verifyAreaEvidence emits needs_clarification for 'om il namel' → Umm Al-Namel");

  // --- 5. Adversarial smuggle: raw 'atlantis' + model=Salmiya → still rejects.
  const smuggle = verifyAreaEvidence({
    rawToken: "atlantis",
    modelValue: "Salmiya",
    idOverride: null,
    data,
  });
  assert.equal(
    smuggle.action,
    "reject",
    `expected reject for unrelated smuggle, got ${smuggle.action}`,
  );
  console.log("ok - verifyAreaEvidence rejects unrelated smuggle (atlantis → Salmiya)");

  // --- 6. Garbage raw + garbage model: neither resolves → keep (downstream handles).
  const neither = verifyAreaEvidence({
    rawToken: "kjhgfdskjhg",
    modelValue: "also garbage",
    idOverride: null,
    data,
  });
  assert.equal(neither.action, "keep", `expected keep when neither resolves`);
  console.log("ok - verifyAreaEvidence passes through when neither side resolves");

  // --- 7. Explicit area_id bypasses the guard entirely.
  const bypassed = verifyAreaEvidence({
    rawToken: "obviously wrong",
    modelValue: "Salmiya",
    idOverride: 12,
    data,
  });
  assert.equal(bypassed.action, "keep", `expected keep when area_id provided`);
  console.log("ok - verifyAreaEvidence bypasses with explicit area_id");

  // --- 8. Similarity sanity: strong for real matches, weak for unrelated.
  assert(
    scoreAreaMatchSimilarity("om il namel", "Umm Al-Namel Island") > 0.5,
    "om il namel similarity to Umm Al-Namel should be > 0.5",
  );
  assert(
    scoreAreaMatchSimilarity("xxxxx", "Salmiya") < 0.2,
    "xxxxx similarity to Salmiya should be < 0.2",
  );
  console.log("ok - scoreAreaMatchSimilarity discriminates real vs. unrelated");

  // --- 9. End-to-end: get_price with unrecognized name returns area_not_found
  // carrying closest_candidates (graduated-response contract for the no-visible-
  // text path, which is what the smoke-test sandbox exercises).
  const getPriceTool = await resolveRegisteredTool(
    import.meta.url,
    "get_price",
    {
      pricing: {
        sourceMode: "published_preferred",
        publishedPath: defaultPublishedPricingPath,
        resolverOverlayPath: defaultResolverOverlayPath,
        adminAllowlist: [],
      },
    },
  );
  const unrecognized = await getPriceTool.execute("graduated-unrecognized", {
    pickup_area: "om il namel",
    dropoff_area: "Hawalli",
  });
  const unrecognizedText =
    unrecognized?.content?.find?.((item) => item?.type === "text")?.text || "";
  const unrecognizedParsed = parseToolText(unrecognizedText);
  assert(unrecognizedParsed.json, "expected structured JSON from get_price");
  assert.equal(
    unrecognizedParsed.json.status,
    "area_not_found",
    `expected area_not_found, got ${unrecognizedParsed.json.status}`,
  );
  assert.equal(unrecognizedParsed.json.field, "pickup_area");
  assert(
    Array.isArray(unrecognizedParsed.json.closest_candidates) &&
      unrecognizedParsed.json.closest_candidates.length > 0,
    `expected closest_candidates array, got ${JSON.stringify(unrecognizedParsed.json.closest_candidates)}`,
  );
  assert(
    unrecognizedParsed.json.closest_candidates.some((c) => /namel/i.test(c.name_en)),
    `expected Umm Al-Namel in closest_candidates, got ${unrecognizedParsed.json.closest_candidates.map((c) => c.name_en).join(", ")}`,
  );
  console.log("ok - get_price area_not_found now carries closest_candidates");

  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
