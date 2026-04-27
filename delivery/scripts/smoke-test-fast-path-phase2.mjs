#!/usr/bin/env node
/**
 * Smoke test: Phase 2 fast-path disposition gate (2026-04-24).
 *
 * Context
 * -------
 * Phase 1 deleted the free-form name extractors. The identity-phone cut
 * later removed phone writes too, leaving address as the remaining Phase-3
 * fast-path. Phase 2 tightens that remaining fast-path so it only runs when
 * the pre-LLM turn disposition is `continue_step`. If the customer is
 * asking a question, changing route, correcting, acknowledging, or
 * cancelling, the shape-matched address fields no longer write
 * to controller state pre-LLM.
 *
 * Rule (per user plan):
 *   "remaining fast paths only run when disposition === continue_step
 *    OR the branch is an explicit command."
 *
 * The address extractor is NOT an explicit command — it shape-matches
 * free-form text — so this gate fires for it. The
 * reuse-intent, pin-role, and declared-role-pin branches ARE explicit
 * command whitelists (narrow regex / keyword lists) and stay gated
 * by their own callsite whitelists; they are NOT routed through this
 * gate.
 *
 * What this test pins
 * -------------------
 *   1. Gate mode resolution reads the env flag correctly (off | log | on).
 *   2. `continue_step` disposition → fast-path runs in all three modes.
 *   3. Any non-continue_step disposition with mode=on → fast-path skipped.
 *   4. Any non-continue_step disposition with mode=log → fast-path runs
 *      AND the decision is flagged blocked (for log-only observability).
 *   5. Mode=off → fast-path always runs regardless of disposition
 *      (clean rollback).
 *   6. Null disposition (computation failed) → fail-closed when enabled.
 *   7. Identity fields are LLM-owned; address extraction remains intact.
 *   8. End-to-end simulation of the callsite behaviour under each mode.
 */

import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const fastPath = await loadDeliveryTsModule(
    import.meta.url,
    path.join(deliveryRoot, "plugins/shared/fast-path-extractor.ts"),
  );
  const {
    extractForNextAction,
    resolveFastPathDispositionGateMode,
    decideFastPathDispositionGate,
  } = fastPath;

  console.log("Phase 2 fast-path disposition gate smoke test");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 1 — Mode resolution reads env string robustly.
  // -----------------------------------------------------------------------
  console.log("Section 1: resolveFastPathDispositionGateMode");
  assert.equal(resolveFastPathDispositionGateMode("on"), "on", "explicit 'on' → on");
  assert.equal(resolveFastPathDispositionGateMode("off"), "off", "explicit 'off' → off");
  assert.equal(resolveFastPathDispositionGateMode("log"), "log", "explicit 'log' → log");
  assert.equal(resolveFastPathDispositionGateMode(""), "on", "empty string defaults to 'on'");
  assert.equal(resolveFastPathDispositionGateMode(undefined), "on", "undefined defaults to 'on'");
  assert.equal(resolveFastPathDispositionGateMode(null), "on", "null defaults to 'on'");
  assert.equal(resolveFastPathDispositionGateMode("  OFF  "), "off", "case + whitespace normalized to 'off'");
  assert.equal(resolveFastPathDispositionGateMode("ON"), "on", "upper-case 'ON' → on");
  assert.equal(resolveFastPathDispositionGateMode("LOG"), "log", "upper-case 'LOG' → log");
  assert.equal(resolveFastPathDispositionGateMode("garbage"), "on", "unknown value defaults to 'on'");
  console.log("  ok: mode resolver");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 2 — continue_step always runs.
  // -----------------------------------------------------------------------
  console.log("Section 2: disposition === continue_step always runs");
  for (const mode of ["on", "log", "off"]) {
    const d = decideFastPathDispositionGate({ disposition: "continue_step", mode });
    assert.equal(d.action, "run", `mode=${mode} + continue_step → run`);
    assert.equal(d.blocked_by_disposition, false, `mode=${mode} + continue_step → not blocked`);
  }
  console.log("  ok: continue_step runs in on/log/off");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 3 — non-continue_step + mode=on → skipped.
  // -----------------------------------------------------------------------
  console.log("Section 3: non-continue_step + mode=on → skip");
  const nonContinueDispositions = [
    "answer",
    "requote",
    "cancel_confirmation",
    "edit_field",
    "acknowledge",
    "handoff",
    "idle",
  ];
  for (const disp of nonContinueDispositions) {
    const d = decideFastPathDispositionGate({ disposition: disp, mode: "on" });
    assert.equal(d.action, "skip", `mode=on + disposition=${disp} → skip`);
    assert.equal(d.blocked_by_disposition, true, `mode=on + disposition=${disp} → blocked`);
  }
  console.log(`  ok: all ${nonContinueDispositions.length} non-continue dispositions skipped in mode=on`);
  console.log("");

  // -----------------------------------------------------------------------
  // Section 4 — non-continue_step + mode=log → run_log_only (observe only).
  // -----------------------------------------------------------------------
  console.log("Section 4: non-continue_step + mode=log → run_log_only");
  for (const disp of nonContinueDispositions) {
    const d = decideFastPathDispositionGate({ disposition: disp, mode: "log" });
    assert.equal(d.action, "run_log_only", `mode=log + ${disp} → run_log_only`);
    assert.equal(d.blocked_by_disposition, true, `mode=log + ${disp} → flagged blocked`);
  }
  console.log("  ok: log-mode flags blocked without skipping");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 5 — mode=off is rollback (always runs, never flags blocked).
  // -----------------------------------------------------------------------
  console.log("Section 5: mode=off is clean rollback");
  for (const disp of [...nonContinueDispositions, "continue_step"]) {
    const d = decideFastPathDispositionGate({ disposition: disp, mode: "off" });
    assert.equal(d.action, "run", `mode=off + ${disp} → run`);
    assert.equal(d.blocked_by_disposition, false, `mode=off + ${disp} → not blocked`);
  }
  console.log("  ok: off-mode never skips");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 6 — null disposition fails closed when gate is enabled.
  // -----------------------------------------------------------------------
  console.log("Section 6: null disposition fails closed when enabled");
  {
    const on = decideFastPathDispositionGate({ disposition: null, mode: "on" });
    assert.equal(on.action, "skip", "mode=on + null → skip");
    assert.equal(on.blocked_by_disposition, true, "mode=on + null → blocked");
    const log = decideFastPathDispositionGate({ disposition: null, mode: "log" });
    assert.equal(log.action, "run_log_only", "mode=log + null → run_log_only");
    assert.equal(log.blocked_by_disposition, true, "mode=log + null → blocked");
    const off = decideFastPathDispositionGate({ disposition: null, mode: "off" });
    assert.equal(off.action, "run", "mode=off + null → run");
    assert.equal(off.blocked_by_disposition, false, "mode=off + null → not blocked");
  }
  console.log("  ok: null disposition no longer writes state when enabled");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 7 — Phase-1 extractor contract is intact.
  // -----------------------------------------------------------------------
  console.log("Section 7: extractor contract unchanged by Phase 2");
  {
    const phoneOnly = extractForNextAction({
      text: "99887766",
      action: "ASK_SENDER_PHONE",
      whatsappNumber: "+96500000000",
    });
    assert.equal(phoneOnly.confidence, "none", "ASK_SENDER_PHONE digits → LLM-owned");
    assert.equal(phoneOnly.patch, null, "phone not captured pre-LLM");

    const labeled = extractForNextAction({
      text: "block 5 street 2 house 10",
      action: "ASK_PICKUP_ADDRESS",
      whatsappNumber: "+96500000000",
    });
    assert.equal(labeled.confidence, "high", "ASK_PICKUP_ADDRESS labeled → high confidence");
    assert.equal(labeled.patch?.address_role, "pickup", "pickup role set");
    assert.equal(labeled.patch?.address_block, "5", "block captured");
    assert.equal(labeled.patch?.address_street, "2", "street captured");
    assert.equal(labeled.patch?.address_house, "10", "house captured");

    const senderCombined = extractForNextAction({
      text: "Ahmed 99887766",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "+96500000000",
    });
    assert.equal(
      senderCombined.patch,
      null,
      "ASK_SENDER_NAME_AND_PHONE_DECISION writes no identity fields pre-LLM",
    );

    // "No the avenues mall" still fails closed (Phase 1).
    const avenues = extractForNextAction({
      text: "No the avenues mall",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "+96500000000",
    });
    assert.equal(avenues.patch, null, "Phase 1 regression guard: 'No the avenues mall' → no patch");
  }
  console.log("  ok: extractor contract intact");
  console.log("");

  // -----------------------------------------------------------------------
  // Section 8 — end-to-end simulation of the callsite.
  // -----------------------------------------------------------------------
  console.log("Section 8: simulated callsite behaviour");
  function simulatedCallsite({ text, action, whatsappNumber, disposition, mode }) {
    const gate = decideFastPathDispositionGate({ disposition, mode });
    if (gate.action === "skip") {
      return { called: false, gate };
    }
    const res = extractForNextAction({ text, action, whatsappNumber });
    return { called: true, result: res, gate };
  }

  // side question containing address-shaped text — must NOT be applied.
  const sideQ = simulatedCallsite({
    text: "block 5 street 2 house 10",
    action: "ASK_PICKUP_ADDRESS",
    whatsappNumber: "+96500000000",
    disposition: "answer",
    mode: "on",
  });
  assert.equal(sideQ.called, false, "mode=on + answer → extractor NOT called");
  assert.equal(sideQ.gate.action, "skip");

  // legit address while collecting — must be applied.
  const legit = simulatedCallsite({
    text: "block 5 street 2 house 10",
    action: "ASK_PICKUP_ADDRESS",
    whatsappNumber: "+96500000000",
    disposition: "continue_step",
    mode: "on",
  });
  assert.equal(legit.called, true, "mode=on + continue_step → extractor called");
  assert.equal(legit.result.confidence, "high");
  assert.equal(legit.result.patch?.address_block, "5");

  // log mode — runs AND flags blocked; identity phone extraction still
  // returns none because phones are LLM/tool-owned.
  const logged = simulatedCallsite({
    text: "99887766",
    action: "ASK_SENDER_PHONE",
    whatsappNumber: "+96500000000",
    disposition: "answer",
    mode: "log",
  });
  assert.equal(logged.called, true, "mode=log + answer → extractor called (observe only)");
  assert.equal(logged.gate.blocked_by_disposition, true, "mode=log + answer → flagged blocked");
  assert.equal(logged.result.confidence, "none");
  assert.equal(logged.result.patch, null);

  // off-mode rollback.
  const off = simulatedCallsite({
    text: "99887766",
    action: "ASK_SENDER_PHONE",
    whatsappNumber: "+96500000000",
    disposition: "answer",
    mode: "off",
  });
  assert.equal(off.called, true, "mode=off + answer → extractor called (rollback)");
  assert.equal(off.gate.action, "run");
  assert.equal(off.result.confidence, "none", "off-mode does not restore phone fast-path");
  assert.equal(off.result.patch, null);

  // cancel and requote — both skipped under mode=on.
  const cancel = simulatedCallsite({
    text: "block 5 street 2 house 10",
    action: "ASK_PICKUP_ADDRESS",
    whatsappNumber: "+96500000000",
    disposition: "cancel_confirmation",
    mode: "on",
  });
  assert.equal(cancel.called, false, "mode=on + cancel → extractor NOT called");

  const requote = simulatedCallsite({
    text: "99887766",
    action: "ASK_SENDER_PHONE",
    whatsappNumber: "+96500000000",
    disposition: "requote",
    mode: "on",
  });
  assert.equal(requote.called, false, "mode=on + requote → extractor NOT called");

  console.log("  ok: callsite simulation");
  console.log("");
  console.log("All Phase 2 fast-path disposition gate assertions passed.");
}

main().catch((err) => {
  console.error("FAILED:", err);
  process.exit(1);
});
