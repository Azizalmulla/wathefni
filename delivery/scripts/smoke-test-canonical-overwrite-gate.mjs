#!/usr/bin/env node
/**
 * Smoke test: canonical-overwrite gate (post-2026-04-19 hardening).
 *
 * Background — the canonical-overwrite guard exists for ONE narrow case:
 *   The LLM called get_price on THIS turn and wrote a degenerate reply
 *   that lost the route+price grounding (e.g. "6.000 KWD" alone). In
 *   that case we resurrect the canonical tool message so the customer
 *   sees the full quote.
 *
 * Live regression incidents that motivated this gate:
 *
 *   2026-04-19 13:42 (Bug 1):
 *     Customer in `quoted` stage asked "Is this the cheapest option".
 *     LLM (correctly) replied with a natural answer mentioning the price.
 *     The OLD guard saw the price token + no "Delivery from" prefix,
 *     marked the reply "lossy", and overwrote it with the canonical
 *     route-and-price line. Customer never got their question answered.
 *
 *   2026-04-19 13:43 (Bug 3):
 *     Customer sent their phone number 90s after the original quote.
 *     The LLM called apply_booking_field — NOT get_price — but the OLD
 *     guard's 5-minute "sessionIsRecent" window meant `lastToolName ===
 *     "get_price"` from the prior turn was still considered current. The
 *     guard fired, overwriting the LLM's "got it, what's next" reply
 *     with the canonical route+price.
 *
 * The fix gates the guard on:
 *   1. `lastToolAgeMs < 30s` — must be turn-local. Kills Bug 3.
 *   2. controller stage === "idle" — only allowed BEFORE the controller
 *      promotes the entry to `quoted`. Kills Bug 1.
 *
 * This test exercises `isCanonicalOverwriteAllowed` directly. The
 * orchestrator wiring that consumes the gate is straightforward boolean
 * AND-with-other-conditions; the interesting policy is the gate itself,
 * which is what we verify here.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const textModulePath = path.join(
    deliveryRoot,
    "plugins/octopus-channel/lib/text.ts",
  );
  const mod = await loadDeliveryTsModule(import.meta.url, textModulePath);
  const { isCanonicalOverwriteAllowed } = mod;
  assert.equal(typeof isCanonicalOverwriteAllowed, "function", "missing isCanonicalOverwriteAllowed export");

  const FRESH = 5_000;       // 5s — clearly within turn-local window
  const STALE = 90_000;      // 90s — clearly past turn-local window
  const VERY_STALE = 240_000; // 4min — within old 5min sessionIsRecent but stale per new gate

  // --- Happy path: fresh tool + idle stage = allowed (the only allow case)

  {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: FRESH, controllerStage: "idle" });
    assert.equal(r.allowed, true, `idle+fresh must allow, got ${JSON.stringify(r)}`);
    assert.equal(r.reason, "fresh_quote_turn");
  }
  {
    // null stage = treat as idle (no controller entry yet)
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: FRESH, controllerStage: null });
    assert.equal(r.allowed, true, `null-stage+fresh must allow, got ${JSON.stringify(r)}`);
  }

  // --- Bug 1 regression: post-quote stages must NEVER allow overwrite
  // even when the tool age is fresh. Customer asked "is this cheapest"
  // in `quoted` stage; the LLM's natural reply must pass through.

  for (const stage of [
    "quoted",
    "collecting_booking_details",
    "summary_shown",
    "awaiting_confirmation",
    "order_submitted",
  ]) {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: FRESH, controllerStage: stage });
    assert.equal(
      r.allowed,
      false,
      `stage=${stage}+fresh must NOT allow overwrite (Bug 1 regression), got ${JSON.stringify(r)}`,
    );
    assert.equal(r.reason, `post_quote_stage:${stage}`);
  }

  // --- Bug 3 regression: stale tool must NEVER allow overwrite even in
  // idle stage. Customer sent phone 90s after a get_price; the LLM did
  // not call get_price this turn but the prior tool name is still
  // "get_price". The gate must reject because the tool is stale.

  for (const ageMs of [STALE, VERY_STALE]) {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: ageMs, controllerStage: "idle" });
    assert.equal(
      r.allowed,
      false,
      `idle+stale(${ageMs}ms) must NOT allow overwrite (Bug 3 regression), got ${JSON.stringify(r)}`,
    );
    assert.equal(r.reason, "tool_stale");
  }

  // Defense-in-depth: stale + post-quote = obviously not allowed.
  // The gate reports tool-staleness first because it's the dominant
  // signal (no fresh tool means no canonical-text source worth using).
  {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: STALE, controllerStage: "collecting_booking_details" });
    assert.equal(r.allowed, false);
    assert.equal(r.reason, "tool_stale");
  }

  // No tool session at all (Number.POSITIVE_INFINITY age) → not allowed.
  {
    const r = isCanonicalOverwriteAllowed({
      lastToolAgeMs: Number.POSITIVE_INFINITY,
      controllerStage: "idle",
    });
    assert.equal(r.allowed, false);
    assert.equal(r.reason, "no_tool_session");
  }

  // --- Boundary: exactly at the turn-local cutoff (30_000ms) is rejected.
  // Strictly-less-than semantics chosen so that "exactly stale" is treated
  // as stale (safer default — we don't want a tool from 30.0s ago to count
  // as the current turn).
  {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: 30_000, controllerStage: "idle" });
    assert.equal(r.allowed, false, "boundary at 30s must be treated as stale");
    assert.equal(r.reason, "tool_stale");
  }
  {
    const r = isCanonicalOverwriteAllowed({ lastToolAgeMs: 29_999, controllerStage: "idle" });
    assert.equal(r.allowed, true, "29.999s must still count as turn-local");
  }

  // --- Custom turn-local window (for future tuning): the parameter is
  // honored, so operators can tighten/loosen without code changes.
  {
    const r = isCanonicalOverwriteAllowed({
      lastToolAgeMs: 8_000,
      controllerStage: "idle",
      turnLocalWindowMs: 5_000,
    });
    assert.equal(r.allowed, false, "custom 5s window must reject 8s-old tool");
    assert.equal(r.reason, "tool_stale");
  }

  console.log("smoke-test-canonical-overwrite-gate: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
