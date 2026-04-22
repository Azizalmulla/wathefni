#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — relocation 5 Phase 5.0 shadow (turn disposition).
//
// Verifies `decideTurnDisposition` policy rules, `classifyStateConsistency`,
// the end-to-end wiring through `observeTurnDecision`, and the
// `[turn-decision/trace]` emit envelope surfacing `disposition=` /
// `authored_directive=` / `state_consistency=` tokens.
//
// DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER expected in the module
// header and DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER on the
// index.ts callsite (disposition_inputs wiring).
//
// Source-only mode when tsx isn't installed; full import mode when it is.
//
// Run from `delivery/`:
//   node scripts/smoke-test-turn-disposition.mjs
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const DISPOSITION_MODULE_REL = "plugins/shared/turn-disposition.ts";
const TD_MODULE_REL = "plugins/shared/turn-decision.ts";
const CALLSITE_REL = "plugins/octopus-channel/index.ts";

const DISPOSITION_MODULE_PATH = path.join(repoRoot, DISPOSITION_MODULE_REL);
const TD_MODULE_PATH = path.join(repoRoot, TD_MODULE_REL);
const CALLSITE_PATH = path.join(repoRoot, CALLSITE_REL);

function baseInputs(overrides = {}) {
  return {
    proposer: {
      turn_kind: "booking_detail_collection",
      ti_kind: null,
      ti_confidence: null,
      ti_addressed_fields: [],
      ac_kind: null,
      po_kind: null,
      ...(overrides.proposer || {}),
    },
    addressed_missing_fields: overrides.addressed_missing_fields ?? [],
    addressed_non_missing_fields: overrides.addressed_non_missing_fields ?? [],
    state: {
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route: true,
      active_quoted_route_has_manual_confirm_option: false,
      has_summary_shown: false,
      is_post_order: false,
      missing_fields_count: 4,
      ...(overrides.state || {}),
    },
    tool_context: {
      get_price_ran_this_turn: false,
      start_booking_drained_this_turn: false,
      hallucination_guard_fired: false,
      ...(overrides.tool_context || {}),
    },
    hints: {
      same_route_switch_option: false,
      ...(overrides.hints || {}),
    },
    state_machine_candidate_directive:
      overrides.state_machine_candidate_directive ??
      "ASK_SENDER_NAME_AND_PHONE_DECISION",
  };
}

// Expected per-rule cases — MUST stay in sync with decideTurnDisposition.
const DISPOSITION_CASES = [
  // Rule 1: idle — pre-booking chit-chat.
  {
    name: "idle_pre_booking",
    inputs: baseInputs({
      proposer: { turn_kind: "informational" },
      state: {
        stage_at_turn_start: null,
        has_active_quoted_route: false,
        missing_fields_count: 0,
      },
      state_machine_candidate_directive: null,
    }),
    expected_disposition: "idle",
    expected_policy_rule: "layer.disposition.idle",
  },

  // Rule 2: no_proposer fallthrough → continue_step.
  {
    name: "no_proposer_continue_step",
    inputs: (() => {
      const i = baseInputs();
      i.proposer = null;
      return i;
    })(),
    expected_disposition: "continue_step",
    expected_policy_rule: "layer.disposition.continue_step.no_proposer",
    expected_fallthrough: "no_proposer",
  },

  // Rule 3: handoff — hallucination guard on a manual-confirm-capable route.
  {
    name: "handoff_manual_confirm_guard",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "acknowledgement",
        ti_confidence: "medium",
      },
      state: {
        active_quoted_route_has_manual_confirm_option: true,
      },
      tool_context: { hallucination_guard_fired: true },
    }),
    expected_disposition: "handoff",
    expected_policy_rule: "layer.disposition.handoff.manual_confirm_guard",
  },

  // Rule 3 exempt: clarifying_question must NOT be handoff even with guard.
  {
    name: "handoff_exempt_on_clarifying",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "clarifying_question",
        ti_confidence: "high",
      },
      state: {
        active_quoted_route_has_manual_confirm_option: true,
      },
      tool_context: { hallucination_guard_fired: true },
    }),
    expected_disposition: "answer",
    expected_policy_rule: "layer.disposition.answer.clarifying_question",
  },

  // Rule 4: cancel_confirmation at summary.
  {
    name: "cancel_at_summary",
    inputs: baseInputs({
      proposer: {
        turn_kind: "confirmation_or_cancel",
        ti_kind: "refused_or_stuck",
        ti_confidence: "high",
        ac_kind: "cancel_order",
      },
      state: {
        stage_at_turn_start: "summary_shown",
        has_summary_shown: true,
      },
    }),
    expected_disposition: "cancel_confirmation",
    expected_policy_rule:
      "layer.disposition.cancel_confirmation.at_eligible_stage",
  },

  // Rule 4: cancel_confirmation mid-collection (Phase 5.2 live flip; 5.0
  // still classifies).
  {
    name: "cancel_mid_collection",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "refused_or_stuck",
        ti_confidence: "high",
        ac_kind: "cancel_order",
      },
      state: {
        stage_at_turn_start: "collecting_booking_details",
      },
    }),
    expected_disposition: "cancel_confirmation",
    expected_policy_rule:
      "layer.disposition.cancel_confirmation.at_eligible_stage",
  },

  // Rule 5: requote — fresh initial_route on active quote.
  {
    name: "requote_fresh_route_on_quote",
    inputs: baseInputs({
      proposer: {
        turn_kind: "initial_route",
        ti_kind: null,
        ti_confidence: null,
      },
      state: {
        stage_at_turn_start: "quoted",
        has_active_quoted_route: true,
      },
    }),
    expected_disposition: "requote",
    expected_policy_rule: "layer.disposition.requote.fresh_route_or_get_price",
  },

  // Rule 5: requote — get_price drained this turn (intent proven by tool).
  {
    name: "requote_on_get_price_drained",
    inputs: baseInputs({
      proposer: {
        turn_kind: "informational",
        ti_kind: "unclear",
        ti_confidence: "low",
      },
      state: { stage_at_turn_start: "quoted", has_active_quoted_route: true },
      tool_context: { get_price_ran_this_turn: true },
    }),
    expected_disposition: "requote",
    expected_policy_rule: "layer.disposition.requote.fresh_route_or_get_price",
  },

  // Rule 6: edit_field — corrected_prior with non-missing field.
  {
    name: "edit_field_corrected",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "corrected_prior",
        ti_confidence: "high",
        ti_addressed_fields: ["sender_name"],
      },
      addressed_non_missing_fields: ["sender_name"],
    }),
    expected_disposition: "edit_field",
    expected_policy_rule: "layer.disposition.edit_field.corrected_prior",
  },

  // Rule 6 low-confidence: falls through to continue_step.
  {
    name: "edit_field_low_confidence_falls_through",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "corrected_prior",
        ti_confidence: "low",
      },
      addressed_non_missing_fields: ["sender_name"],
    }),
    expected_disposition: "continue_step",
    expected_policy_rule: "layer.disposition.continue_step.default",
    expected_fallthrough: "low_confidence_corrected_prior",
  },

  // Rule 7: answer — clarifying_question high confidence.
  {
    name: "answer_clarifying_question",
    inputs: baseInputs({
      proposer: {
        turn_kind: "informational",
        ti_kind: "clarifying_question",
        ti_confidence: "high",
      },
    }),
    expected_disposition: "answer",
    expected_policy_rule: "layer.disposition.answer.clarifying_question",
  },

  // Rule 7: answer — answered_partial with addressed missing field.
  {
    name: "answer_partial_with_missing_field",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "answered_partial",
        ti_confidence: "medium",
        ti_addressed_fields: ["sender_name"],
      },
      addressed_missing_fields: ["sender_name"],
    }),
    expected_disposition: "answer",
    expected_policy_rule: "layer.disposition.answer.answered_partial",
  },

  // Rule 7 safeguard: answered_partial with NO addressed missing field
  // must NOT route to answer — falls through to default.
  {
    name: "answer_partial_without_addressed_falls_through",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "answered_partial",
        ti_confidence: "high",
        ti_addressed_fields: [],
      },
      addressed_missing_fields: [],
    }),
    expected_disposition: "continue_step",
    expected_policy_rule: "layer.disposition.continue_step.default",
  },

  // Rule 8: acknowledge — acknowledgement ti_kind.
  {
    name: "acknowledge_ti_acknowledgement",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "acknowledgement",
        ti_confidence: "high",
      },
    }),
    expected_disposition: "acknowledge",
    expected_policy_rule: "layer.disposition.acknowledge.passthrough",
  },

  // Rule 8: acknowledge — post-order customer_support chit-chat.
  {
    name: "acknowledge_post_order_customer_support",
    inputs: baseInputs({
      proposer: {
        turn_kind: "post_order_chat",
        ti_kind: null,
        ti_confidence: null,
        po_kind: "customer_support",
      },
      state: {
        stage_at_turn_start: "order_submitted",
        is_post_order: true,
        has_active_quoted_route: false,
      },
      state_machine_candidate_directive: null,
    }),
    expected_disposition: "acknowledge",
    expected_policy_rule: "layer.disposition.acknowledge.passthrough",
  },

  // Rule 9 default: no rule matches → continue_step.
  {
    name: "default_continue_step_no_match",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "answered_full",
        ti_confidence: "high",
        ti_addressed_fields: ["sender_name", "sender_phone"],
      },
      addressed_missing_fields: ["sender_name", "sender_phone"],
    }),
    expected_disposition: "continue_step",
    expected_policy_rule: "layer.disposition.continue_step.default",
  },

  // Rule 9 switch-option skip.
  {
    name: "default_switch_option_skip",
    inputs: baseInputs({
      proposer: {
        turn_kind: "booking_detail_collection",
        ti_kind: "answered_partial",
        ti_confidence: "high",
        ti_addressed_fields: [],
      },
      addressed_missing_fields: [],
      hints: { same_route_switch_option: true },
    }),
    expected_disposition: "continue_step",
    expected_policy_rule: "layer.disposition.continue_step.switch_option_skip",
    expected_fallthrough: "same_route_switch_option",
  },
];

// Expected state-consistency cases.
const STATE_CONSISTENCY_CASES = [
  {
    name: "continue_step_is_agree_delegated",
    args: ["continue_step", "ASK_X", "ASK_X"],
    expected: "agree_delegated",
  },
  {
    name: "both_null_is_agree",
    args: ["answer", null, null],
    expected: "agree",
  },
  {
    name: "layer_null_state_nonnull_is_suppress",
    args: ["answer", null, "ASK_X"],
    expected: "disagree_layer_suppress",
  },
  {
    name: "layer_nonnull_state_null_is_author",
    args: ["handoff", "REQUEST_HANDOFF", null],
    expected: "disagree_layer_author",
  },
  {
    name: "nonnull_mismatch_is_disagree_mismatch",
    args: ["edit_field", "EDIT_NAME", "ASK_PHONE"],
    expected: "disagree_mismatch",
  },
  {
    name: "nonnull_match_is_agree",
    args: ["edit_field", "EDIT_NAME", "EDIT_NAME"],
    expected: "agree",
  },
];

// ---------------------------------------------------------------------------
// Source-level checks.
// ---------------------------------------------------------------------------

async function runSourceLevelChecks(fails) {
  const [dispSrc, tdSrc, callsiteSrc] = await Promise.all([
    fs.readFile(DISPOSITION_MODULE_PATH, "utf8"),
    fs.readFile(TD_MODULE_PATH, "utf8"),
    fs.readFile(CALLSITE_PATH, "utf8"),
  ]);

  if (!dispSrc.includes("DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER")) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER missing from ${DISPOSITION_MODULE_REL}`,
    );
  }
  if (!dispSrc.includes("export function decideTurnDisposition(")) {
    fails.push(
      `module: decideTurnDisposition export missing from ${DISPOSITION_MODULE_REL}`,
    );
  }
  if (!dispSrc.includes("export function classifyStateConsistency(")) {
    fails.push(
      `module: classifyStateConsistency export missing from ${DISPOSITION_MODULE_REL}`,
    );
  }
  if (
    !tdSrc.includes("DEPLOY_CANARY_TURN_DECISION_DISPOSITION_RELOC_MARKER")
  ) {
    fails.push(
      `turn-decision module: DEPLOY_CANARY_TURN_DECISION_DISPOSITION_RELOC_MARKER missing from ${TD_MODULE_REL}`,
    );
  }
  if (!tdSrc.includes("disposition_inputs?:")) {
    fails.push(
      `turn-decision module: disposition_inputs field missing from TurnDecisionObservedContext in ${TD_MODULE_REL}`,
    );
  }
  if (!tdSrc.includes("decideTurnDisposition(")) {
    fails.push(
      `turn-decision module: decideTurnDisposition call site missing from ${TD_MODULE_REL}`,
    );
  }
  if (!callsiteSrc.includes("DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER")) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("disposition_inputs:")) {
    fails.push(
      `callsite: disposition_inputs block missing from ${CALLSITE_REL}`,
    );
  }

  const RULE_IDS = [
    "layer.disposition.idle",
    "layer.disposition.continue_step.no_proposer",
    "layer.disposition.handoff.manual_confirm_guard",
    "layer.disposition.cancel_confirmation.at_eligible_stage",
    "layer.disposition.requote.fresh_route_or_get_price",
    "layer.disposition.edit_field.corrected_prior",
    "layer.disposition.answer.clarifying_question",
    "layer.disposition.answer.answered_partial",
    "layer.disposition.acknowledge.passthrough",
    "layer.disposition.continue_step.switch_option_skip",
    "layer.disposition.continue_step.default",
  ];
  const missing = RULE_IDS.filter((p) => !dispSrc.includes(p));
  if (missing.length > 0) {
    fails.push(
      `module: decideTurnDisposition is missing policy rule ids: ${missing.join(", ")}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Full checks.
// ---------------------------------------------------------------------------

async function runFullChecks(fails) {
  const dispMod = await import(pathToFileURL(DISPOSITION_MODULE_PATH).href);
  const tdMod = await import(pathToFileURL(TD_MODULE_PATH).href);
  const { decideTurnDisposition, classifyStateConsistency } = dispMod;
  const { observeTurnDecision, formatTurnDecisionTrace } = tdMod;

  if (typeof decideTurnDisposition !== "function") {
    fails.push("module: decideTurnDisposition is not a function");
    return;
  }
  if (typeof classifyStateConsistency !== "function") {
    fails.push("module: classifyStateConsistency is not a function");
    return;
  }

  // 1. decideTurnDisposition policy-rule cases.
  for (const c of DISPOSITION_CASES) {
    const got = decideTurnDisposition(c.inputs);
    if (!got || typeof got !== "object") {
      fails.push(`decideTurnDisposition(${c.name}): did not return an object`);
      continue;
    }
    if (got.disposition !== c.expected_disposition) {
      fails.push(
        `decideTurnDisposition(${c.name}): disposition=${got.disposition}, expected ${c.expected_disposition}`,
      );
    }
    if (got.policy_rule !== c.expected_policy_rule) {
      fails.push(
        `decideTurnDisposition(${c.name}): policy_rule=${got.policy_rule}, expected ${c.expected_policy_rule}`,
      );
    }
    if (typeof got.reason !== "string" || got.reason.length === 0) {
      fails.push(`decideTurnDisposition(${c.name}): reason missing/empty`);
    }
    if (c.expected_fallthrough) {
      if (
        got.trace_annotations?.fallthrough_reason !== c.expected_fallthrough
      ) {
        fails.push(
          `decideTurnDisposition(${c.name}): fallthrough_reason=${got.trace_annotations?.fallthrough_reason}, expected ${c.expected_fallthrough}`,
        );
      }
    }
    // Continue_step must delegate (state_machine_call.called === true,
    // authored_directive mirrors state_machine_candidate_directive).
    if (got.disposition === "continue_step") {
      if (got.state_machine_call?.called !== true) {
        fails.push(
          `decideTurnDisposition(${c.name}): continue_step did not set state_machine_call.called=true`,
        );
      }
      if (
        got.authored_directive !== c.inputs.state_machine_candidate_directive
      ) {
        fails.push(
          `decideTurnDisposition(${c.name}): continue_step authored_directive=${got.authored_directive}, expected delegation to ${c.inputs.state_machine_candidate_directive}`,
        );
      }
    } else if (got.disposition !== "idle") {
      // Non-continue, non-idle dispositions must have called=false in
      // Phase 5.0 (shadow-only authoring; state machine not consulted).
      if (got.state_machine_call?.called !== false) {
        fails.push(
          `decideTurnDisposition(${c.name}): non-continue disposition ${got.disposition} should not call state machine in 5.0`,
        );
      }
    }
  }

  // 2. classifyStateConsistency cases.
  for (const c of STATE_CONSISTENCY_CASES) {
    const got = classifyStateConsistency(...c.args);
    if (got !== c.expected) {
      fails.push(
        `classifyStateConsistency(${c.name}): got ${got}, expected ${c.expected}`,
      );
    }
  }

  // 3. End-to-end through observeTurnDecision: supplying disposition_inputs
  //    must produce the layer's disposition / authored_directive /
  //    state_consistency tokens. Canonical step-loop case: clarifying
  //    question while the state machine would have authored a directive
  //    — layer authors `answer` (null directive), consistency says
  //    `disagree_layer_suppress`.
  const e2eInputs = {
    conversation_id: "conv-e2e",
    turn_id: "t-e2e",
    outcome: {
      decision: "replace_authoritative",
      reason: "replace_directive_ask",
      reply_author: "server",
      reply_text_chars: 65,
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_render_context_present: true,
      marked_summary_shown: false,
    },
    proposer: {
      present: true,
      schema_valid: true,
      schema_version: "1.3",
      turn_kind: "informational",
      ti_kind: "clarifying_question",
      ti_confidence: "high",
      ti_addressed_fields: [],
      ac_kind: null,
      po_kind: null,
    },
    disposition_inputs: {
      addressed_missing_fields: [],
      addressed_non_missing_fields: [],
      state: {
        stage_at_turn_start: "collecting_booking_details",
        has_active_quoted_route: true,
        active_quoted_route_has_manual_confirm_option: false,
        has_summary_shown: false,
        is_post_order: false,
        missing_fields_count: 4,
      },
      tool_context: {
        get_price_ran_this_turn: false,
        start_booking_drained_this_turn: false,
        hallucination_guard_fired: false,
      },
      hints: { same_route_switch_option: false },
      state_machine_candidate_directive: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    },
    drained_op_names: ["proposed_turn_decision"],
    apply_boundary_rejection_fields: [],
    state_summary: {
      stage_at_turn_start: "collecting_booking_details",
      stage_at_turn_end: "collecting_booking_details",
      has_active_quoted_route: true,
      has_draft: true,
      missing_fields_count: 4,
    },
    language: "en",
  };
  const e2eDecision = observeTurnDecision(e2eInputs);
  if (e2eDecision.reply.derived_disposition !== "answer") {
    fails.push(
      `e2e: reply.derived_disposition=${e2eDecision.reply.derived_disposition}, expected answer (clarifying)`,
    );
  }
  if (
    e2eDecision.reply.derived_disposition_rule !==
    "layer.disposition.answer.clarifying_question"
  ) {
    fails.push(
      `e2e: derived_disposition_rule=${e2eDecision.reply.derived_disposition_rule}, expected layer.disposition.answer.clarifying_question`,
    );
  }
  if (e2eDecision.reply.derived_authored_directive !== null) {
    fails.push(
      `e2e: derived_authored_directive=${e2eDecision.reply.derived_authored_directive}, expected null (answer authors no directive in 5.0)`,
    );
  }
  if (e2eDecision.reply.state_consistency !== "disagree_layer_suppress") {
    fails.push(
      `e2e: state_consistency=${e2eDecision.reply.state_consistency}, expected disagree_layer_suppress`,
    );
  }

  const line = formatTurnDecisionTrace({
    conversation_id: e2eInputs.conversation_id,
    turn_id: e2eInputs.turn_id,
    language: e2eInputs.language,
    decision: e2eDecision,
    input_summary: {
      stage_at_turn_start: "collecting_booking_details",
      stage_at_turn_end: "collecting_booking_details",
      has_active_quoted_route: true,
      drained_op_count: 1,
      reply_text_chars: 65,
      schema_version: "1.3",
      proposer_present: true,
      proposer_valid: true,
    },
  });
  for (const tok of [
    "disposition=answer",
    "state_consistency=disagree_layer_suppress",
    "authored_directive=-", // authored null
  ]) {
    if (!line.includes(tok)) {
      fails.push(`formatTurnDecisionTrace e2e: missing token "${tok}"`);
    }
  }
  const payloadIdx = line.indexOf("payload=");
  if (payloadIdx !== -1) {
    try {
      const obj = JSON.parse(line.slice(payloadIdx + "payload=".length));
      if (obj.layer?.disposition !== "answer") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.disposition=${obj.layer?.disposition}, expected answer`,
        );
      }
      if (obj.layer?.state_consistency !== "disagree_layer_suppress") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.state_consistency=${obj.layer?.state_consistency}, expected disagree_layer_suppress`,
        );
      }
      if (obj.layer?.authored_directive !== null) {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.authored_directive=${obj.layer?.authored_directive}, expected null`,
        );
      }
    } catch (e) {
      fails.push(
        `formatTurnDecisionTrace e2e: payload is not valid JSON — ${e.message}`,
      );
    }
  }

  // 4. When disposition_inputs absent, fields must be absent (backcompat).
  const bareInputs = { ...e2eInputs };
  delete bareInputs.disposition_inputs;
  const bareDecision = observeTurnDecision(bareInputs);
  if (bareDecision.reply.derived_disposition !== undefined) {
    fails.push(
      `observeTurnDecision(no disposition_inputs): derived_disposition should be undefined, got ${bareDecision.reply.derived_disposition}`,
    );
  }
  if (bareDecision.reply.state_consistency !== undefined) {
    fails.push(
      `observeTurnDecision(no disposition_inputs): state_consistency should be undefined`,
    );
  }

  // 5. continue_step delegates through to state machine directive.
  const delegatedInputs = {
    ...e2eInputs,
    proposer: {
      ...e2eInputs.proposer,
      ti_kind: "answered_full",
      ti_addressed_fields: ["sender_name", "sender_phone"],
    },
    disposition_inputs: {
      ...e2eInputs.disposition_inputs,
      addressed_missing_fields: ["sender_name", "sender_phone"],
    },
  };
  const delegatedDecision = observeTurnDecision(delegatedInputs);
  if (delegatedDecision.reply.derived_disposition !== "continue_step") {
    fails.push(
      `delegation: expected continue_step, got ${delegatedDecision.reply.derived_disposition}`,
    );
  }
  if (
    delegatedDecision.reply.derived_authored_directive !==
    "ASK_SENDER_NAME_AND_PHONE_DECISION"
  ) {
    fails.push(
      `delegation: expected delegated authored_directive=ASK_SENDER_NAME_AND_PHONE_DECISION, got ${delegatedDecision.reply.derived_authored_directive}`,
    );
  }
  if (delegatedDecision.reply.state_consistency !== "agree_delegated") {
    fails.push(
      `delegation: expected state_consistency=agree_delegated, got ${delegatedDecision.reply.state_consistency}`,
    );
  }

  // 6. Independence with Reloc 2/3/4 — supplying all input bundles
  //    must not contaminate the disposition derivation.
  const pairedInputs = {
    ...e2eInputs,
    a1_inputs: {
      clarify_option_before_proceed_flag: false,
      manual_confirm_address_ask: null,
      manual_confirm_handoff: null,
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      same_route_quote_switch_option: false,
      route_intent_fresh_this_turn: false,
      observed_a1_intent: "replace_directive_ask",
    },
    a4_inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
    },
    directive_inputs: {
      state_directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      same_route_quote_switch_option: false,
      hallucination_guard_fired: false,
      route_intent_fresh_this_turn: false,
    },
  };
  const pairedDecision = observeTurnDecision(pairedInputs);
  if (pairedDecision.reply.derived_disposition !== "answer") {
    fails.push(
      `independence: derived_disposition=${pairedDecision.reply.derived_disposition}, expected answer`,
    );
  }
  if (pairedDecision.reply.derived_directive_disposition !== "suppress") {
    fails.push(
      `independence: Reloc-4 derived_directive_disposition=${pairedDecision.reply.derived_directive_disposition} polluted, expected suppress`,
    );
  }
  if (pairedDecision.reply.derived_a1_intent !== "allow") {
    fails.push(
      `independence: Reloc-3 derived_a1_intent=${pairedDecision.reply.derived_a1_intent} polluted, expected allow`,
    );
  }
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

async function main() {
  const fails = [];
  await runSourceLevelChecks(fails);

  const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
    cwd: repoRoot,
    stdio: "ignore",
  });
  const hasTsx = tsxCheck.status === 0;

  if (!hasTsx) {
    if (fails.length > 0) {
      console.error(
        `[smoke-test-turn-disposition] FAIL (source-only; tsx not installed):\n  - ${fails.join("\n  - ")}`,
      );
      process.exit(1);
    }
    console.log(
      `[smoke-test-turn-disposition] OK (source-only mode; tsx not installed). ` +
        `Canaries present, ${DISPOSITION_CASES.length} policy rule cases referenced in source.`,
    );
    process.exit(0);
  }

  if (!process.env.__TD_DISPOSITION_SMOKE_TSX__) {
    const child = spawnSync(
      "node",
      ["--import", "tsx", fileURLToPath(import.meta.url)],
      {
        cwd: repoRoot,
        stdio: "inherit",
        env: { ...process.env, __TD_DISPOSITION_SMOKE_TSX__: "1" },
      },
    );
    process.exit(child.status ?? 1);
  }

  await runFullChecks(fails);

  if (fails.length > 0) {
    console.error(
      `[smoke-test-turn-disposition] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-turn-disposition] OK — ${DISPOSITION_CASES.length} disposition cases, ${STATE_CONSISTENCY_CASES.length} state-consistency cases, end-to-end answer+suppress surfaced on trace.`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
