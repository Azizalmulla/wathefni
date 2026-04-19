#!/usr/bin/env node
/**
 * Smoke test: pending-area preservation across turns (Bug A from the
 * Jlai3a → Wafra live transcript).
 *
 * The previous behavior:
 *   Turn 1: customer "Jlai3a to wafra" → pickup resolves to Shalehat Jlea'a,
 *           dropoff is ambiguous (Wafra Residential vs Wafra Farms) →
 *           clarification asked. NO state was persisted because no full
 *           quote was produced.
 *   Turn 2: customer "wafra res" → LLM (correctly) calls get_price with
 *           pickup_area="Shalehat Jlea'a" + dropoff_area="Wafra Residential".
 *           The smuggle guard runs `verifyAreaEvidence` on pickup with
 *           rawToken extracted from the CURRENT message ("wafra res"),
 *           which contains no evidence for "Shalehat Jlea'a", so the guard
 *           wrongly rejects the leg as a smuggle.
 *
 * The fix this test exercises:
 *   - When a leg resolves on turn 1, the tool pushes a `set_pending_area`
 *     op which the orchestrator persists onto the controller entry as
 *     `pendingPickupAreaNameEn` / `pendingDropoffAreaNameEn`.
 *   - On turn 2, `verifyAreaEvidence` is called with the pending name as a
 *     hint. If the model's claim resolves to the same canonical area, the
 *     guard returns `keep` even when the current raw token has no evidence.
 *
 * This file uses the resolver test hooks (no orchestrator simulation
 * needed) — the orchestrator wiring is straightforward state copy and is
 * covered by the existing one-brain eval. The interesting logic is the
 * guard's pending-area shortcut, which we verify exhaustively here.
 *
 * Also covers Bug B (alias typo tolerance for `Julai3a` → `Jlai3a` →
 * Shalehat Jlea'a) by exercising `findAreaNearTypoMatch` against the
 * resolver overlay.
 */
import assert from "node:assert/strict";
import {
  defaultPublishedPricingPath,
  defaultResolverOverlayPath,
  loadRidersToolsModule,
} from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const mod = await loadRidersToolsModule(import.meta.url);
  const hooks = mod.__resolverTestHooks;
  assert(hooks?.verifyAreaEvidence, "missing __resolverTestHooks");
  const { verifyAreaEvidence, buildPublishedPricingData, normalizePricingResolverConfig, resolvePricingAreaQuery } =
    hooks;

  const fs = await import("node:fs");
  const pricingSource = JSON.parse(
    fs.readFileSync(defaultPublishedPricingPath, "utf8"),
  );
  const overlaySource = JSON.parse(
    fs.readFileSync(defaultResolverOverlayPath, "utf8"),
  );
  // Overlay nests resolver config under `.resolver`; unwrap for the
  // normalizer (matches how `applyPricingResolverOverlayIfConfigured`
  // wires it during plugin startup).
  const overlayConfig = overlaySource?.resolver || overlaySource;
  const data = buildPublishedPricingData(pricingSource, pricingSource);
  data.resolver = normalizePricingResolverConfig(overlayConfig);
  assert(Array.isArray(data.areas) && data.areas.length > 0, "areas empty");
  assert(
    Array.isArray(data.resolver?.aliases) && data.resolver.aliases.length > 0,
    "resolver aliases empty — overlay didn't load",
  );

  // --- Bug A regression: pending-area preservation -----------------------

  // The Jlai3a alias maps to Shalehat Jlea'a — sanity-check the overlay
  // before trusting any downstream behavior on it.
  const jlai3aResolution = await resolvePricingAreaQuery("Jlai3a", data);
  assert.equal(
    jlai3aResolution.status,
    "resolved",
    `expected Jlai3a to resolve via overlay, got ${jlai3aResolution.status}`,
  );
  assert(
    /jlea/i.test(jlai3aResolution.area.name_en) ||
      /shalehat/i.test(jlai3aResolution.area.name_en),
    `expected Jlai3a → Shalehat Jlea'a, got ${jlai3aResolution.area.name_en}`,
  );
  const jlea = jlai3aResolution.area;
  console.log(
    `ok - overlay maps "Jlai3a" → ${jlea.name_en} (${jlea.name_ar}) [id ${jlea.id}]`,
  );

  // Case 1 (regression): pickup model="Shalehat Jlea'a" but the raw token
  // for THIS turn is "wafra res" (because the customer is answering the
  // dropoff disambiguation, not re-stating the pickup). With NO pending
  // hint, the guard correctly considers this a potential smuggle.
  const noPendingDecision = verifyAreaEvidence({
    rawToken: "wafra res",
    modelValue: jlea.name_en,
    idOverride: null,
    data,
  });
  // It might end up as reject or needs_clarification depending on graduated
  // response settings — either way it is NOT "keep". That is the bug.
  assert(
    noPendingDecision.action !== "keep",
    `pre-fix sanity: without pending hint, guard should NOT keep — got ${noPendingDecision.action}`,
  );
  console.log(
    `ok - without pendingArea hint, "wafra res" + model="${jlea.name_en}" yields ${noPendingDecision.action} (would block carry-forward)`,
  );

  // Case 2 (the fix): same call, but we pass the prior-turn resolved name
  // as the pending hint. The guard must KEEP because the model is faithfully
  // carrying forward an area the customer already established.
  const withPendingDecision = verifyAreaEvidence({
    rawToken: "wafra res",
    modelValue: jlea.name_en,
    idOverride: null,
    data,
    pendingAreaNameEn: jlea.name_en,
    pendingAreaNameAr: jlea.name_ar,
  });
  assert.equal(
    withPendingDecision.action,
    "keep",
    `expected keep when pendingArea matches model, got ${withPendingDecision.action}: ${JSON.stringify(withPendingDecision).slice(0, 200)}`,
  );
  console.log(
    `ok - with pendingArea="${jlea.name_en}", guard keeps the carry-forward`,
  );

  // Case 3: pending hint is set, but the LLM tries to swap to a different
  // canonical area. The pending shortcut must NOT bypass the smuggle defense.
  const swapDecision = verifyAreaEvidence({
    rawToken: "wafra res",
    modelValue: "Salmiya", // totally different area
    idOverride: null,
    data,
    pendingAreaNameEn: jlea.name_en,
    pendingAreaNameAr: jlea.name_ar,
  });
  assert(
    swapDecision.action !== "keep",
    `pending-area shortcut must NOT mask a real area swap — got ${swapDecision.action}`,
  );
  console.log(
    "ok - pending hint does NOT bypass smuggle defense when model swaps to a different area",
  );

  // Case 4: pending hint provided as the Arabic name only — should still
  // resolve through the overlay and trigger the keep shortcut.
  const arabicOnlyDecision = verifyAreaEvidence({
    rawToken: "wafra res",
    modelValue: jlea.name_en,
    idOverride: null,
    data,
    pendingAreaNameEn: null,
    pendingAreaNameAr: jlea.name_ar,
  });
  assert.equal(
    arabicOnlyDecision.action,
    "keep",
    `expected keep with Arabic-only pending hint, got ${arabicOnlyDecision.action}`,
  );
  console.log("ok - pending hint works with Arabic-only name");

  // Case 5: empty pending hint (both null) falls back to the legacy code
  // path — equivalent to no hint provided.
  const emptyDecision = verifyAreaEvidence({
    rawToken: "wafra res",
    modelValue: jlea.name_en,
    idOverride: null,
    data,
    pendingAreaNameEn: null,
    pendingAreaNameAr: null,
  });
  assert.equal(
    emptyDecision.action,
    noPendingDecision.action,
    `null hints must behave identically to no hints, got ${emptyDecision.action} vs ${noPendingDecision.action}`,
  );
  console.log("ok - null pending hints behave identically to no hints");

  // --- Bug B regression: alias typo tolerance (Julai3a) ------------------

  // `Julai3a` is one transposed letter from the alias `Jlai3a`. Without
  // alias-aware fuzzy matching, this only sees canonical names (Jlea'a,
  // Shalehat Jlea'a, etc.) which are all >2 edits away from "Julai3a", so
  // it falls all the way through to LLM fallback (slow + costs tokens).
  // With alias-aware fuzzy matching, "Julai3a" → "Jlai3a" (alias) →
  // Shalehat Jlea'a, deterministically.
  const julai3aResolution = await resolvePricingAreaQuery("Julai3a", data);
  assert(
    julai3aResolution.status === "resolved" ||
      julai3aResolution.status === "suggested",
    `expected Julai3a to resolve or suggest deterministically, got ${julai3aResolution.status}`,
  );
  if (julai3aResolution.status === "resolved") {
    assert.equal(
      julai3aResolution.area.id,
      jlea.id,
      `expected Julai3a → Shalehat Jlea'a (id ${jlea.id}), got ${julai3aResolution.area.name_en} (id ${julai3aResolution.area.id})`,
    );
    console.log(
      `ok - "Julai3a" deterministically resolves to ${jlea.name_en} via alias fuzzy match`,
    );
  } else {
    assert.equal(
      julai3aResolution.area.id,
      jlea.id,
      `expected Julai3a suggested → Shalehat Jlea'a, got ${julai3aResolution.area.name_en}`,
    );
    console.log(
      `ok - "Julai3a" deterministically suggests ${jlea.name_en} via alias fuzzy match`,
    );
  }

  console.log("\nAll pending-area preservation assertions passed.");
  process.exit(0);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
