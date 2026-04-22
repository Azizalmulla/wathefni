#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — relocation 4 (directive → layer) disposition derivation.
//
// Verifies the new `decideDirectiveDisposition` policy rules, the
// `classifyDirectiveDispositionAgreement` helper, the end-to-end wiring
// through `observeTurnDecision`, and the `[turn-decision/trace]` emit
// envelope surfacing `directive_disposition=` and
// `directive_agreement=` tokens.
//
// DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER expected in the
// module header and DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER
// on the index.ts callsite (directive_inputs wiring).
//
// Source-only mode when tsx isn't installed; full import mode when it is.
//
// Run from `delivery/`:
//   node scripts/smoke-test-turn-decision-directive-disposition.mjs
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const MODULE_REL = "plugins/shared/turn-decision.ts";
const CALLSITE_REL = "plugins/octopus-channel/index.ts";

const MODULE_PATH = path.join(repoRoot, MODULE_REL);
const CALLSITE_PATH = path.join(repoRoot, CALLSITE_REL);

function baseInputs(overrides = {}) {
  return {
    state_directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    proposer_turn_kind: null,
    proposer_ti_kind: null,
    proposer_ti_confidence: null,
    proposer_ac_kind: null,
    stage_at_turn_start: "collecting_booking_details",
    has_active_quoted_route_at_turn_start: true,
    route_intent_fresh_this_turn: false,
    same_route_quote_switch_option: false,
    hallucination_guard_fired: false,
    ...overrides,
  };
}

// Expected layer disposition decisions, one per policy rule.
// MUST stay in sync with `decideDirectiveDisposition`.
const DISPOSITION_CASES = [
  // Rule: allow when no state directive.
  {
    name: "no_state_directive",
    inputs: baseInputs({ state_directive_action: null }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_when_no_state_directive",
  },

  // Rule: allow on switch-option (legacy parity).
  {
    name: "switch_option_skip",
    inputs: baseInputs({
      same_route_quote_switch_option: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_on_same_route_switch_option",
  },

  // Rule: allow on hallucination guard (damage control).
  {
    name: "hallucination_guard_allow",
    inputs: baseInputs({
      hallucination_guard_fired: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_on_hallucination_guard",
  },

  // Rule: suppress on fresh route request (strict). Stage = collecting.
  {
    name: "fresh_route_collecting",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_fresh_route_request",
  },

  // Rule: suppress on fresh route request. Stage = quoted.
  {
    name: "fresh_route_quoted",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_fresh_route_request",
  },

  // Rule: suppress on fresh route request. Stage = summary_shown.
  {
    name: "fresh_route_summary",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "summary_shown",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_fresh_route_request",
  },

  // Route flag without an active quoted route → NOT a fresh route
  // suppress; falls through to default allow.
  {
    name: "fresh_route_flag_without_active_route_falls_through",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      has_active_quoted_route_at_turn_start: false,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Route flag on a stage where fresh route does not make sense →
  // default allow.
  {
    name: "fresh_route_flag_on_idle_stage_falls_through",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "idle",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Rule: suppress on clarifying question (high confidence).
  {
    name: "clarifying_high",
    inputs: baseInputs({
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_clarifying_question",
  },

  // Rule: suppress on clarifying question (medium confidence).
  {
    name: "clarifying_medium",
    inputs: baseInputs({
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "medium",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_clarifying_question",
  },

  // Low-confidence clarifying → falls through to default allow.
  {
    name: "clarifying_low_falls_through",
    inputs: baseInputs({
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "low",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Null-confidence clarifying → falls through too.
  {
    name: "clarifying_null_confidence_falls_through",
    inputs: baseInputs({
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: null,
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Rule: suppress on cancel intent (awaiting-confirmation classifier).
  {
    name: "cancel_intent",
    inputs: baseInputs({
      proposer_ac_kind: "cancel_order",
      stage_at_turn_start: "summary_shown",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_cancel_intent",
  },

  // Rule: suppress on correction intent (high confidence).
  {
    name: "correction_high",
    inputs: baseInputs({
      proposer_ti_kind: "corrected_prior",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_correction_intent",
  },

  // Low-confidence correction → falls through.
  {
    name: "correction_low_falls_through",
    inputs: baseInputs({
      proposer_ti_kind: "corrected_prior",
      proposer_ti_confidence: "low",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Priority: hallucination guard beats suppression gates.
  {
    name: "hallucination_guard_beats_clarifying",
    inputs: baseInputs({
      hallucination_guard_fired: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_on_hallucination_guard",
  },

  // Priority: switch-option skip beats every suppression gate.
  {
    name: "switch_option_beats_fresh_route",
    inputs: baseInputs({
      same_route_quote_switch_option: true,
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_on_same_route_switch_option",
  },

  // Priority: fresh route fires before clarifying.
  {
    name: "fresh_route_beats_clarifying",
    inputs: baseInputs({
      route_intent_fresh_this_turn: true,
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      proposer_turn_kind: "initial_route",
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "suppress",
    expected_policy_rule: "layer.directive.suppress_on_fresh_route_request",
  },

  // Normal collection turn answering the step → allow.
  {
    name: "answered_full_allow_default",
    inputs: baseInputs({
      proposer_ti_kind: "answered_full",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Acknowledgement → allow (no suppress rule covers it; the bot
  // should keep pushing on the step).
  {
    name: "acknowledgement_allow_default",
    inputs: baseInputs({
      proposer_ti_kind: "acknowledgement",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },

  // Unclear turn → allow (don't gamble on an unclear classification).
  {
    name: "unclear_allow_default",
    inputs: baseInputs({
      proposer_ti_kind: "unclear",
      proposer_ti_confidence: "high",
    }),
    expected_disposition: "allow",
    expected_policy_rule: "layer.directive.allow_default",
  },
];

// Agreement cases: legacy always allows, so mapping is binary.
const AGREEMENT_CASES = [
  { derived: "allow", expected: "agree" },
  { derived: "suppress", expected: "disagree_layer_suppress" },
];

// ---------------------------------------------------------------------------
// Source-level checks.
// ---------------------------------------------------------------------------

async function runSourceLevelChecks(fails) {
  const [moduleSrc, callsiteSrc] = await Promise.all([
    fs.readFile(MODULE_PATH, "utf8"),
    fs.readFile(CALLSITE_PATH, "utf8"),
  ]);

  if (!moduleSrc.includes("DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER")) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_RELOC_MARKER missing from ${MODULE_REL}`,
    );
  }
  if (!moduleSrc.includes("export function decideDirectiveDisposition(")) {
    fails.push(
      `module: decideDirectiveDisposition export missing from ${MODULE_REL}`,
    );
  }
  if (
    !moduleSrc.includes(
      "export function classifyDirectiveDispositionAgreement(",
    )
  ) {
    fails.push(
      `module: classifyDirectiveDispositionAgreement export missing from ${MODULE_REL}`,
    );
  }
  if (
    !callsiteSrc.includes(
      "DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER",
    )
  ) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DECISION_DIRECTIVE_CALLSITE_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("directive_inputs: {")) {
    fails.push(
      `callsite: directive_inputs block missing from ${CALLSITE_REL} (TurnDecisionObservedContext literal)`,
    );
  }

  // Expected policy_rule ids — these are string literals in the module.
  const RULE_IDS = [
    "layer.directive.allow_when_no_state_directive",
    "layer.directive.allow_on_same_route_switch_option",
    "layer.directive.allow_on_hallucination_guard",
    "layer.directive.suppress_on_fresh_route_request",
    "layer.directive.suppress_on_clarifying_question",
    "layer.directive.suppress_on_cancel_intent",
    "layer.directive.suppress_on_correction_intent",
    "layer.directive.allow_default",
  ];
  const missing = RULE_IDS.filter((p) => !moduleSrc.includes(p));
  if (missing.length > 0) {
    fails.push(
      `module: decideDirectiveDisposition is missing policy rule ids: ${missing.join(", ")}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Full checks.
// ---------------------------------------------------------------------------

async function runFullChecks(fails) {
  const mod = await import(pathToFileURL(MODULE_PATH).href);
  const {
    decideDirectiveDisposition,
    classifyDirectiveDispositionAgreement,
    observeTurnDecision,
    formatTurnDecisionTrace,
  } = mod;

  if (typeof decideDirectiveDisposition !== "function") {
    fails.push("module: decideDirectiveDisposition is not a function");
    return;
  }
  if (typeof classifyDirectiveDispositionAgreement !== "function") {
    fails.push("module: classifyDirectiveDispositionAgreement is not a function");
    return;
  }

  // 1. decideDirectiveDisposition cases.
  for (const c of DISPOSITION_CASES) {
    const got = decideDirectiveDisposition(c.inputs);
    if (!got || typeof got !== "object") {
      fails.push(
        `decideDirectiveDisposition(${c.name}): did not return an object`,
      );
      continue;
    }
    if (got.disposition !== c.expected_disposition) {
      fails.push(
        `decideDirectiveDisposition(${c.name}): disposition=${got.disposition}, expected ${c.expected_disposition}`,
      );
    }
    if (got.policy_rule !== c.expected_policy_rule) {
      fails.push(
        `decideDirectiveDisposition(${c.name}): policy_rule=${got.policy_rule}, expected ${c.expected_policy_rule}`,
      );
    }
    if (typeof got.reason !== "string" || got.reason.length === 0) {
      fails.push(
        `decideDirectiveDisposition(${c.name}): reason is missing/empty`,
      );
    }
  }

  // 2. classifyDirectiveDispositionAgreement cases.
  for (const c of AGREEMENT_CASES) {
    const got = classifyDirectiveDispositionAgreement(c.derived);
    if (got !== c.expected) {
      fails.push(
        `classifyDirectiveDispositionAgreement(${c.derived}): got ${got}, expected ${c.expected}`,
      );
    }
  }

  // 3. End-to-end through observeTurnDecision: supplying directive_inputs
  //    must produce derived_directive_disposition /
  //    directive_disposition_agreement on the decision and surface them
  //    on the trace line. Uses the canonical step-loop case: clarifying
  //    question while a directive was fired — legacy fires the form, the
  //    layer suppresses it.
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
      ac_kind: null,
      po_kind: null,
    },
    directive_inputs: {
      state_directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      same_route_quote_switch_option: false,
      hallucination_guard_fired: false,
      route_intent_fresh_this_turn: false,
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
  if (e2eDecision.reply.derived_directive_disposition !== "suppress") {
    fails.push(
      `e2e: reply.derived_directive_disposition=${e2eDecision.reply.derived_directive_disposition}, expected suppress (clarifying)`,
    );
  }
  if (
    e2eDecision.reply.derived_directive_policy_rule !==
    "layer.directive.suppress_on_clarifying_question"
  ) {
    fails.push(
      `e2e: derived_directive_policy_rule=${e2eDecision.reply.derived_directive_policy_rule}, expected layer.directive.suppress_on_clarifying_question`,
    );
  }
  if (
    e2eDecision.reply.directive_disposition_agreement !==
    "disagree_layer_suppress"
  ) {
    fails.push(
      `e2e: directive_disposition_agreement=${e2eDecision.reply.directive_disposition_agreement}, expected disagree_layer_suppress`,
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
    "directive_disposition=suppress",
    "directive_agreement=disagree_layer_suppress",
  ]) {
    if (!line.includes(tok)) {
      fails.push(`formatTurnDecisionTrace e2e: missing token "${tok}"`);
    }
  }
  const payloadIdx = line.indexOf("payload=");
  if (payloadIdx !== -1) {
    try {
      const obj = JSON.parse(line.slice(payloadIdx + "payload=".length));
      if (obj.layer?.directive_disposition !== "suppress") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.directive_disposition=${obj.layer?.directive_disposition}, expected suppress`,
        );
      }
      if (
        obj.layer?.directive_disposition_agreement !==
        "disagree_layer_suppress"
      ) {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.directive_disposition_agreement mismatch`,
        );
      }
      if (
        obj.layer?.directive_policy_rule !==
        "layer.directive.suppress_on_clarifying_question"
      ) {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.directive_policy_rule=${obj.layer?.directive_policy_rule}`,
        );
      }
    } catch (e) {
      fails.push(
        `formatTurnDecisionTrace e2e: payload is not valid JSON — ${e.message}`,
      );
    }
  }

  // 4. When directive_inputs is absent, the layer directive fields must
  //    be absent too (backward compatibility with pre-Reloc-4 contract).
  const bareInputs = { ...e2eInputs };
  delete bareInputs.directive_inputs;
  const bareDecision = observeTurnDecision(bareInputs);
  if (bareDecision.reply.derived_directive_disposition !== undefined) {
    fails.push(
      `observeTurnDecision(no directive_inputs): derived_directive_disposition should be undefined, got ${bareDecision.reply.derived_directive_disposition}`,
    );
  }
  if (bareDecision.reply.directive_disposition_agreement !== undefined) {
    fails.push(
      `observeTurnDecision(no directive_inputs): directive_disposition_agreement should be undefined`,
    );
  }

  // 5. Independence with Reloc 2 + Reloc 3: when all three input
  //    bundles are supplied, the directive-disposition derivation runs
  //    independently of the A1 and A4 derivations. This keeps the three
  //    shadows uncontaminated during the Reloc 4 bake.
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
  };
  const pairedDecision = observeTurnDecision(pairedInputs);
  if (pairedDecision.reply.derived_directive_disposition !== "suppress") {
    fails.push(
      `independence: derived_directive_disposition=${pairedDecision.reply.derived_directive_disposition}, expected suppress`,
    );
  }
  if (pairedDecision.reply.derived_a1_intent !== "allow") {
    fails.push(
      `independence: derived_a1_intent=${pairedDecision.reply.derived_a1_intent}, expected allow (Reloc 3 clarifying passthrough)`,
    );
  }
  if (pairedDecision.reply.derived_source !== "llm_authored") {
    fails.push(
      `independence: derived_source=${pairedDecision.reply.derived_source}, expected llm_authored (Reloc 2 clarifying passthrough)`,
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
        `[smoke-test-turn-decision-directive-disposition] FAIL (source-only; tsx not installed):\n  - ${fails.join("\n  - ")}`,
      );
      process.exit(1);
    }
    console.log(
      `[smoke-test-turn-decision-directive-disposition] OK (source-only mode; tsx not installed). ` +
        `Canaries present, ${DISPOSITION_CASES.length} policy rule ids referenced in source.`,
    );
    process.exit(0);
  }

  if (!process.env.__TD_DIRECTIVE_SMOKE_TSX__) {
    const child = spawnSync(
      "node",
      ["--import", "tsx", fileURLToPath(import.meta.url)],
      {
        cwd: repoRoot,
        stdio: "inherit",
        env: { ...process.env, __TD_DIRECTIVE_SMOKE_TSX__: "1" },
      },
    );
    process.exit(child.status ?? 1);
  }

  await runFullChecks(fails);

  if (fails.length > 0) {
    console.error(
      `[smoke-test-turn-decision-directive-disposition] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-turn-decision-directive-disposition] OK — ${DISPOSITION_CASES.length} policy rules, ${AGREEMENT_CASES.length} agreement cases, end-to-end suppress surfaced on trace.`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
