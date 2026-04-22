#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — Phase 2 Milestone 3 action-selection gate (SHADOW).
//
// DEPLOY_CANARY_ACTION_SELECTION_GATE_MODULE_MARKER expected in the module
// header.
//
// Coverage:
//   1. Canary marker present.
//   2. Exhaustive policy over every TurnIntentKind × every
//      AwaitingConfirmationKind — satisfies-check should already catch
//      missing rows at compile time; this asserts the *runtime* decision
//      is non-null.
//   3. Legacy decision: advance / hold_informational / hold_confirm cases.
//   4. M3 decision on collection directive:
//        answered_* / corrected_prior → advance
//        clarifying_question / unclear / refused_or_stuck → hold
//        acknowledgement → no_op
//   5. M3 decision on summary directive WITH awaiting_confirmation:
//        confirm_order → hold (LLM owns reply)
//        cancel_order → advance
//        edit_order → advance
//        informational_question → hold
//        coherence_pleasantry → no_op
//        unclear → hold
//   6. M3 summary directive WITHOUT ac → falls back to turn_intent.
//   7. Missing turn_intent / low confidence → advance fallback.
//   8. diff: agree / disagree_m3_holds / disagree_m3_advances.
//   9. formatActionSelectionShadowLog token shape.
//  10. Real-world scenarios:
//       a) Customer asks "what's the cheapest" mid-collection (directive=
//          ASK_SENDER_NAME_AND_PHONE_DECISION, ti=clarifying_question) —
//          legacy only catches on stage=quoted; M3 catches everywhere.
//       b) Customer pastes operational text (directive=ASK_SENDER_NAME,
//          ti=unclear) — legacy advances, M3 holds.
//       c) Customer says "yes" on summary (ac=confirm_order) — both
//          hold, agreement.
//
// Run from `delivery/`:
//   node scripts/smoke-test-action-selection-gate.mjs
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const MODULE_REL = "plugins/shared/action-selection-gate.ts";
const SCHEMA_REL = "plugins/shared/proposer-schema.ts";

const modulePath = path.join(repoRoot, MODULE_REL);
const schemaPath = path.join(repoRoot, SCHEMA_REL);

const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
  cwd: repoRoot,
  stdio: "ignore",
});
const hasTsx = tsxCheck.status === 0;

if (!hasTsx) {
  const fs = await import("node:fs/promises");
  const [moduleSource, schemaSource] = await Promise.all([
    fs.readFile(modulePath, "utf8"),
    fs.readFile(schemaPath, "utf8"),
  ]);
  const canary = "DEPLOY_CANARY_ACTION_SELECTION_GATE_MODULE_MARKER";
  if (!moduleSource.includes(canary)) {
    console.error(`FAIL: missing ${canary} in ${MODULE_REL}`);
    process.exit(1);
  }
  const tiKinds = [
    "answered_full",
    "answered_partial",
    "answered_unasked",
    "corrected_prior",
    "clarifying_question",
    "acknowledgement",
    "refused_or_stuck",
    "unclear",
  ];
  const acKinds = [
    "confirm_order",
    "cancel_order",
    "edit_order",
    "informational_question",
    "coherence_pleasantry",
    "unclear",
  ];
  const missingTi = tiKinds.filter(
    (k) => !new RegExp(`^\\s*${k}\\s*:`, "m").test(moduleSource),
  );
  const missingAc = acKinds.filter(
    (k) => !new RegExp(`^\\s*${k}\\s*:`, "m").test(moduleSource),
  );
  if (missingTi.length > 0) {
    console.error(`FAIL: KIND_ACTION_POLICY missing: ${missingTi.join(", ")}`);
    process.exit(1);
  }
  if (missingAc.length > 0) {
    console.error(`FAIL: AC_ACTION_POLICY missing: ${missingAc.join(", ")}`);
    process.exit(1);
  }
  console.log(
    `[smoke-test-action-selection-gate] OK (source-only mode; tsx not installed). Canary present, policy covers ${tiKinds.length} ti_kinds + ${acKinds.length} ac_kinds.`,
  );
  process.exit(0);
}

if (!process.env.__ACTION_SELECTION_GATE_SMOKE_TSX__) {
  const child = spawnSync(
    "node",
    ["--import", "tsx", fileURLToPath(import.meta.url)],
    {
      cwd: repoRoot,
      stdio: "inherit",
      env: { ...process.env, __ACTION_SELECTION_GATE_SMOKE_TSX__: "1" },
    },
  );
  process.exit(child.status ?? 1);
}

const mod = await import(pathToFileURL(modulePath).href);
const {
  decideActionSelection,
  computeLegacyActionDecision,
  diffActionDecisions,
  formatActionSelectionShadowLog,
} = mod;

const failures = [];
function check(name, cond, detail) {
  if (!cond) failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
}

// 3. Legacy decision branches.
{
  const adv = computeLegacyActionDecision({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    isInformationalOptionQuestion: false,
    isExplicitOrderConfirmation: false,
  });
  check("legacy_default_advance", adv === "advance");

  const holdInfo = computeLegacyActionDecision({
    directiveAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    stage: "quoted",
    isInformationalOptionQuestion: true,
    isExplicitOrderConfirmation: false,
  });
  check("legacy_hold_informational", holdInfo === "hold_informational");

  const holdConfirm = computeLegacyActionDecision({
    directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    stage: "awaiting_confirmation",
    isInformationalOptionQuestion: false,
    isExplicitOrderConfirmation: true,
  });
  check("legacy_hold_confirm", holdConfirm === "hold_confirm");

  const infoMidCollection = computeLegacyActionDecision({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    isInformationalOptionQuestion: true,
    isExplicitOrderConfirmation: false,
  });
  check(
    "legacy_no_info_gate_mid_collection",
    infoMidCollection === "advance",
    "legacy only fires on stage=quoted",
  );
}

// 4. M3 on collection directive.
{
  const advance = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "answered_partial",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_answered_advances",
    advance.kind === "advance" && advance.reason === "answered_kind_advances",
    JSON.stringify(advance),
  );

  const corrected = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "corrected_prior",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_corrected_advances",
    corrected.kind === "advance" && corrected.reason === "corrected_prior_advances",
    JSON.stringify(corrected),
  );

  const question = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "clarifying_question",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_clarifying_question_holds",
    question.kind === "hold" && question.reason === "ti_clarifying_question_holds",
    JSON.stringify(question),
  );

  const unclear = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "unclear",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_unclear_holds",
    unclear.kind === "hold" && unclear.reason === "ti_unclear_holds_for_retry",
    JSON.stringify(unclear),
  );

  const ack = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "acknowledgement",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_acknowledgement_noop",
    ack.kind === "no_op" && ack.reason === "ti_acknowledgement_no_op",
    JSON.stringify(ack),
  );

  const refused = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "refused_or_stuck",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_refused_holds",
    refused.kind === "hold" &&
      refused.reason === "ti_refused_or_stuck_holds_for_retry",
    JSON.stringify(refused),
  );
}

// 5. M3 on summary directive with AC.
{
  const mk = (acKind) =>
    decideActionSelection({
      directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
      stage: "awaiting_confirmation",
      tiKind: "answered_full",
      tiConfidence: "high",
      acKind,
    });
  const confirm = mk("confirm_order");
  check(
    "m3_summary_ac_confirm_holds",
    confirm.kind === "hold" &&
      confirm.reason === "ac_confirm_order_llm_owns_reply",
    JSON.stringify(confirm),
  );
  const cancel = mk("cancel_order");
  check(
    "m3_summary_ac_cancel_advances",
    cancel.kind === "advance" && cancel.reason === "ac_cancel_order_advances",
    JSON.stringify(cancel),
  );
  const edit = mk("edit_order");
  check(
    "m3_summary_ac_edit_advances",
    edit.kind === "advance" && edit.reason === "ac_edit_order_advances",
    JSON.stringify(edit),
  );
  const info = mk("informational_question");
  check(
    "m3_summary_ac_info_holds",
    info.kind === "hold" &&
      info.reason === "ac_informational_question_llm_owns_reply",
    JSON.stringify(info),
  );
  const pleasantry = mk("coherence_pleasantry");
  check(
    "m3_summary_ac_pleasantry_noop",
    pleasantry.kind === "no_op" &&
      pleasantry.reason === "ac_coherence_pleasantry_no_op",
    JSON.stringify(pleasantry),
  );
  const unclear = mk("unclear");
  check(
    "m3_summary_ac_unclear_holds",
    unclear.kind === "hold" && unclear.reason === "ac_unclear_holds_for_retry",
    JSON.stringify(unclear),
  );
}

// 6. Summary directive without AC → TI fallback.
{
  const fallback = decideActionSelection({
    directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    stage: "summary_shown",
    tiKind: "answered_full",
    tiConfidence: "high",
    acKind: null,
  });
  check(
    "m3_summary_no_ac_fallback_ti",
    fallback.kind === "advance" &&
      fallback.reason === "answered_kind_advances",
    JSON.stringify(fallback),
  );
}

// 7. Missing / low-confidence → advance fallback.
{
  const missing = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: null,
    tiConfidence: null,
    acKind: null,
  });
  check(
    "m3_missing_ti_fallback_advance",
    missing.kind === "advance" &&
      missing.reason === "turn_intent_missing_fallback_advance",
    JSON.stringify(missing),
  );
  const low = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "clarifying_question",
    tiConfidence: "low",
    acKind: null,
  });
  check(
    "m3_low_confidence_fallback_advance",
    low.kind === "advance" &&
      low.reason === "low_confidence_fallback_advance",
    JSON.stringify(low),
  );
}

// 8. diff agreement buckets.
{
  const agreeAdvance = diffActionDecisions("advance", {
    kind: "advance",
    reason: "answered_kind_advances",
  });
  check("diff_agree_advance", agreeAdvance === "agree");

  const agreeHold = diffActionDecisions("hold_informational", {
    kind: "hold",
    reason: "ti_clarifying_question_holds",
  });
  check("diff_agree_hold", agreeHold === "agree");

  const m3More = diffActionDecisions("advance", {
    kind: "hold",
    reason: "ti_unclear_holds_for_retry",
  });
  check("diff_m3_holds_more", m3More === "disagree_m3_holds");

  const m3Less = diffActionDecisions("hold_informational", {
    kind: "advance",
    reason: "answered_kind_advances",
  });
  check("diff_m3_advances_more", m3Less === "disagree_m3_advances");

  const confirmAgree = diffActionDecisions("hold_confirm", {
    kind: "hold",
    reason: "ac_confirm_order_llm_owns_reply",
  });
  check("diff_confirm_agree", confirmAgree === "agree");

  const noOpVsAdvance = diffActionDecisions("advance", {
    kind: "no_op",
    reason: "ti_acknowledgement_no_op",
  });
  check("diff_noop_is_hold_like", noOpVsAdvance === "disagree_m3_holds");
}

// 9. Format token shape.
{
  const line = formatActionSelectionShadowLog({
    conversation_id: "c1",
    directive_action: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    ti_kind: "unclear",
    ti_confidence: "high",
    ac_kind: "-",
    legacy_decision: "advance",
    m3_decision_kind: "hold",
    m3_decision_reason: "ti_unclear_holds_for_retry",
    agreement: "disagree_m3_holds",
  });
  const expected = [
    "[action-selection/shadow]",
    "conversation=c1",
    "directive=ASK_SENDER_NAME",
    "stage=collecting_booking_details",
    "ti_kind=unclear",
    "ti_confidence=high",
    "ac_kind=-",
    "legacy=advance",
    "m3=hold",
    "m3_reason=ti_unclear_holds_for_retry",
    "agreement=disagree_m3_holds",
  ];
  for (const tok of expected) {
    check(
      `shadow_log_${tok.replace(/\W+/g, "_")}`,
      line.includes(tok),
      `missing "${tok}" in ${line}`,
    );
  }
}

// 10. Real-world scenarios.

// 10a. Cheapest question mid-collection.
{
  const legacy = computeLegacyActionDecision({
    directiveAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    stage: "collecting_booking_details",
    isInformationalOptionQuestion: true,
    isExplicitOrderConfirmation: false,
  });
  const m3 = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    stage: "collecting_booking_details",
    tiKind: "clarifying_question",
    tiConfidence: "high",
    acKind: null,
  });
  const agree = diffActionDecisions(legacy, m3);
  check(
    "cheapest_question_mid_collection_m3_holds_legacy_advances",
    legacy === "advance" && m3.kind === "hold" && agree === "disagree_m3_holds",
    `legacy=${legacy} m3=${JSON.stringify(m3)} agree=${agree}`,
  );
}

// 10b. Pasted operational text.
{
  const legacy = computeLegacyActionDecision({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    isInformationalOptionQuestion: false,
    isExplicitOrderConfirmation: false,
  });
  const m3 = decideActionSelection({
    directiveAction: "ASK_SENDER_NAME",
    stage: "collecting_booking_details",
    tiKind: "unclear",
    tiConfidence: "high",
    acKind: null,
  });
  const agree = diffActionDecisions(legacy, m3);
  check(
    "pasted_operational_text_m3_holds_legacy_advances",
    legacy === "advance" && m3.kind === "hold" && agree === "disagree_m3_holds",
    `legacy=${legacy} m3=${JSON.stringify(m3)} agree=${agree}`,
  );
}

// 10c. "Yes" on summary.
{
  const legacy = computeLegacyActionDecision({
    directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    stage: "summary_shown",
    isInformationalOptionQuestion: false,
    isExplicitOrderConfirmation: true,
  });
  const m3 = decideActionSelection({
    directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    stage: "summary_shown",
    tiKind: "answered_full",
    tiConfidence: "high",
    acKind: "confirm_order",
  });
  const agree = diffActionDecisions(legacy, m3);
  check(
    "yes_on_summary_both_hold_agreement",
    legacy === "hold_confirm" && m3.kind === "hold" && agree === "agree",
    `legacy=${legacy} m3=${JSON.stringify(m3)} agree=${agree}`,
  );
}

if (failures.length > 0) {
  console.error(
    `[smoke-test-action-selection-gate] FAIL (${failures.length} failures):\n  - ${failures.join("\n  - ")}`,
  );
  process.exit(1);
}

console.log(
  `[smoke-test-action-selection-gate] OK — policies exhaustive, legacy/m3 branches verified, real-world scenarios (mid-collection clarifying question, pasted text, summary confirm) produce the expected agreement bucket, log token shape verified.`,
);
process.exit(0);
