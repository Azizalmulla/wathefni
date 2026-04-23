#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — relocation 3 (A1 → layer) substitute derivation.
//
// Verifies the new `deriveA1Substitute` policy rules, the
// `classifyA1Agreement` helper, the end-to-end wiring through
// `observeTurnDecision`, and the `[turn-decision/trace]` emit envelope
// surfacing `layer_a1_intent=` and `a1_agreement=` tokens.
//
// DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER expected in the module
// header and DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER on the
// index.ts callsite (a1_inputs wiring).
//
// Source-only mode when tsx isn't installed; full import mode when it is.
//
// Run from `delivery/`:
//   node scripts/smoke-test-turn-decision-a1-substitute.mjs
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
const OUTBOUND_REL = "plugins/octopus-channel/lib/outbound-decision.ts";

const MODULE_PATH = path.join(repoRoot, MODULE_REL);
const CALLSITE_PATH = path.join(repoRoot, CALLSITE_REL);
const OUTBOUND_PATH = path.join(repoRoot, OUTBOUND_REL);

function baseInputs(overrides = {}) {
  return {
    clarify_option_before_proceed_flag: false,
    manual_confirm_address_ask: null,
    manual_confirm_handoff: null,
    directive_action: null,
    directive_has_server_renderer: false,
    same_route_quote_switch_option: false,
    proposer_turn_kind: null,
    proposer_ti_kind: null,
    proposer_ti_confidence: null,
    stage_at_turn_start: null,
    has_active_quoted_route_at_turn_start: false,
    route_intent_fresh_this_turn: false,
    ...overrides,
  };
}

// Expected layer-A1 decisions, one per policy rule. (inputs → derivation).
// MUST stay in sync with `deriveA1Substitute`.
const A1_CASES = [
  // Rule 1: Clarify-before-proceed.
  {
    name: "clarify_option_before_proceed",
    inputs: baseInputs({ clarify_option_before_proceed_flag: true }),
    expected_intent: "replace_clarify_option_before_proceed",
    expected_policy_rule: "layer.a1.clarify_option_before_proceed",
  },

  // Rule 2: Manual-confirm address ask.
  {
    name: "manual_confirm_address_ask.pickup",
    inputs: baseInputs({
      manual_confirm_address_ask: { side: "pickup", option_type: "refrigerator_v1" },
    }),
    expected_intent: "replace_manual_confirm_address_ask",
    expected_policy_rule: "layer.a1.manual_confirm_address_ask",
  },
  {
    name: "manual_confirm_address_ask.delivery",
    inputs: baseInputs({
      manual_confirm_address_ask: { side: "delivery", option_type: "refrigerator_v1" },
    }),
    expected_intent: "replace_manual_confirm_address_ask",
    expected_policy_rule: "layer.a1.manual_confirm_address_ask",
  },

  // Rule 3: Manual-confirm handoff.
  {
    name: "manual_confirm_handoff",
    inputs: baseInputs({
      manual_confirm_handoff: { option_type: "refrigerator_v1" },
    }),
    expected_intent: "replace_manual_confirm_handoff",
    expected_policy_rule: "layer.a1.manual_confirm_handoff",
  },

  // Rule: switch-option skip — never substitute on switch-option turns.
  {
    name: "same_route_quote_switch_option_skip",
    inputs: baseInputs({
      same_route_quote_switch_option: true,
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.no_substitute",
  },

  // Rule 4: Semantic gate — pass on clarifying.
  {
    name: "directive_ask.pass_on_clarifying.high",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_clarifying",
  },
  {
    name: "directive_ask.pass_on_clarifying.medium",
    inputs: baseInputs({
      directive_action: "ASK_PICKUP_ADDRESS",
      directive_has_server_renderer: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "medium",
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_clarifying",
  },

  // Rule 5: Semantic gate — pass on partial answer.
  {
    name: "directive_ask.pass_on_partial_answer.high",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: "high",
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_partial_answer",
  },

  // Rule 6: Semantic gate — pass on route change (strict).
  {
    name: "directive_ask.pass_on_route_change.quoted",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_turn_kind: "initial_route",
      proposer_ti_kind: "answered_unasked",
      proposer_ti_confidence: "high",
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      route_intent_fresh_this_turn: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_route_change",
  },
  {
    name: "directive_ask.pass_on_route_change.collecting",
    inputs: baseInputs({
      directive_action: "ASK_PICKUP_ADDRESS",
      directive_has_server_renderer: true,
      proposer_turn_kind: "initial_route",
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
      route_intent_fresh_this_turn: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_route_change",
  },

  // Strictness: route_intent_fresh_this_turn=false must NOT satisfy the
  // route-change gate, even when other fields are otherwise aligned.
  {
    name: "directive_ask.render.strict_route_change_not_fresh",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_turn_kind: "initial_route",
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      route_intent_fresh_this_turn: false, // strict
    }),
    expected_intent: "replace_directive_ask",
    expected_policy_rule: "layer.a1.directive_ask.render",
  },

  // Route-change gate requires an active quoted route at turn start.
  {
    name: "directive_ask.render.route_change_without_active_quote",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_turn_kind: "initial_route",
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: false,
      route_intent_fresh_this_turn: true,
    }),
    expected_intent: "replace_directive_ask",
    expected_policy_rule: "layer.a1.directive_ask.render",
  },

  // Low-confidence classifier never triggers passthrough.
  {
    name: "directive_ask.render.low_confidence_clarifying_falls_through",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "low",
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "replace_directive_ask",
    expected_policy_rule: "layer.a1.directive_ask.render",
  },
  {
    name: "directive_ask.render.null_confidence_partial_falls_through",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: null,
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "replace_directive_ask",
    expected_policy_rule: "layer.a1.directive_ask.render",
  },

  // Rule 7: Directive-ask render (legacy-aligned default; no gate fires).
  {
    name: "directive_ask.render.default",
    inputs: baseInputs({
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_has_server_renderer: true,
      proposer_ti_kind: "answered_full",
      proposer_ti_confidence: "high",
      stage_at_turn_start: "collecting_booking_details",
      has_active_quoted_route_at_turn_start: true,
    }),
    expected_intent: "replace_directive_ask",
    expected_policy_rule: "layer.a1.directive_ask.render",
  },

  // Rule 8: Directive with no server renderer → pass (layer can't substitute).
  {
    name: "directive_ask.no_renderer",
    inputs: baseInputs({
      directive_action: "CUSTOM_UNRENDERED_DIRECTIVE",
      directive_has_server_renderer: false,
      proposer_ti_kind: "answered_full",
      proposer_ti_confidence: "high",
      stage_at_turn_start: "collecting_booking_details",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.no_renderer",
  },

  // Rule 9: No A1 precondition at all → pass.
  {
    name: "no_substitute.idle",
    inputs: baseInputs({
      stage_at_turn_start: "idle",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.no_substitute",
  },

  // ------------------------------------------------------------------
  // 2026-04-23 semantic-gate hoist (Rule 0 family):
  //   the 3 semantic gates now run BEFORE A0 / A0a / A0b. A0 / A0a /
  //   A0b still own the substitution when the turn does NOT present a
  //   trustworthy clarifying / partial-answer / fresh-route signal.
  // ------------------------------------------------------------------

  // Hoist: pass_on_clarifying outranks A0 (clarify-before-proceed).
  {
    name: "hoist.pass_on_clarifying_beats_a0",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_clarifying",
  },

  // Hoist: pass_on_clarifying outranks A0a (manual_confirm_address_ask).
  {
    name: "hoist.pass_on_clarifying_beats_a0a",
    inputs: baseInputs({
      manual_confirm_address_ask: {
        side: "pickup",
        option_type: "refrigerator_v1",
      },
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "medium",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_clarifying",
  },

  // Hoist: pass_on_clarifying outranks A0b (manual_confirm_handoff).
  {
    name: "hoist.pass_on_clarifying_beats_a0b",
    inputs: baseInputs({
      manual_confirm_handoff: { option_type: "refrigerator_v1" },
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_clarifying",
  },

  // Hoist: pass_on_partial_answer outranks A0 / A0a / A0b.
  {
    name: "hoist.pass_on_partial_answer_beats_a0",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_partial_answer",
  },

  // Hoist: pass_on_route_change outranks A0 / A0a / A0b.
  {
    name: "hoist.pass_on_route_change_beats_a0",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_turn_kind: "initial_route",
      stage_at_turn_start: "quoted",
      has_active_quoted_route_at_turn_start: true,
      route_intent_fresh_this_turn: true,
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.directive_ask.pass_on_route_change",
  },

  // Safeguard: A0 still fires when the turn is NOT a clarifying /
  // partial / fresh-route signal. Hoisted gates only apply to the
  // three semantic kinds with trustworthy confidence.
  {
    name: "hoist.a0_still_fires_on_answered_full",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_ti_kind: "answered_full",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "replace_clarify_option_before_proceed",
    expected_policy_rule: "layer.a1.clarify_option_before_proceed",
  },

  // Safeguard: A0 still fires when classifier confidence is too low
  // to trust the semantic signal (hoisted gates check trustworthiness).
  {
    name: "hoist.a0_still_fires_on_low_confidence_clarifying",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "low",
    }),
    expected_intent: "replace_clarify_option_before_proceed",
    expected_policy_rule: "layer.a1.clarify_option_before_proceed",
  },

  // Safeguard: switch-option turns bypass the hoisted gates entirely
  // (A4 owns the same-route recap composition on switch).
  {
    name: "hoist.switch_option_bypasses_semantic_gates",
    inputs: baseInputs({
      same_route_quote_switch_option: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
    }),
    expected_intent: "allow",
    expected_policy_rule: "layer.a1.no_substitute",
  },

  // Safeguard: the route-change gate itself is still strict even after
  // the hoist — when stage is NOT one of quoted/collecting/summary,
  // the gate must NOT fire and A0 retains priority.
  {
    name: "hoist.a0_still_fires_when_route_change_gate_stage_mismatched",
    inputs: baseInputs({
      clarify_option_before_proceed_flag: true,
      proposer_turn_kind: "initial_route",
      stage_at_turn_start: "idle",
      has_active_quoted_route_at_turn_start: false,
      route_intent_fresh_this_turn: true,
    }),
    expected_intent: "replace_clarify_option_before_proceed",
    expected_policy_rule: "layer.a1.clarify_option_before_proceed",
  },
];

const A1_AGREEMENT_CASES = [
  // Null observed (no legacy override) is normalized to "allow".
  { observed: null, derived: "allow", expected: "agree" },
  {
    observed: null,
    derived: "replace_directive_ask",
    expected: "disagree_layer_substitute",
  },

  // Exact matches.
  {
    observed: "replace_directive_ask",
    derived: "replace_directive_ask",
    expected: "agree",
  },
  { observed: "allow", derived: "allow", expected: "agree" },

  // Passthrough divergences.
  {
    observed: "replace_directive_ask",
    derived: "allow",
    expected: "disagree_layer_passthrough",
  },
  {
    observed: "replace_clarify_option_before_proceed",
    derived: "allow",
    expected: "disagree_layer_passthrough",
  },

  // Substitute divergences.
  {
    observed: "allow",
    derived: "replace_directive_ask",
    expected: "disagree_layer_substitute",
  },
  {
    observed: "allow",
    derived: "replace_clarify_option_before_proceed",
    expected: "disagree_layer_substitute",
  },

  // Both substituted but different intent.
  {
    observed: "replace_directive_ask",
    derived: "replace_clarify_option_before_proceed",
    expected: "disagree_other",
  },

  // allow_sanitized / preserve_clarification normalize to "allow".
  { observed: "allow_sanitized", derived: "allow", expected: "agree" },
  {
    observed: "preserve_clarification",
    derived: "replace_directive_ask",
    expected: "disagree_layer_substitute",
  },
];

// ---------------------------------------------------------------------------
// Source-level checks.
// ---------------------------------------------------------------------------

async function runSourceLevelChecks(fails) {
  const [moduleSrc, callsiteSrc, outboundSrc] = await Promise.all([
    fs.readFile(MODULE_PATH, "utf8"),
    fs.readFile(CALLSITE_PATH, "utf8"),
    fs.readFile(OUTBOUND_PATH, "utf8"),
  ]);

  if (!moduleSrc.includes("DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER")) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DECISION_A1_RELOC_MARKER missing from ${MODULE_REL}`,
    );
  }
  if (!moduleSrc.includes("export function deriveA1Substitute(")) {
    fails.push(`module: deriveA1Substitute export missing from ${MODULE_REL}`);
  }
  if (!moduleSrc.includes("export function classifyA1Agreement(")) {
    fails.push(
      `module: classifyA1Agreement export missing from ${MODULE_REL}`,
    );
  }
  if (!callsiteSrc.includes("DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER")) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DECISION_A1_CALLSITE_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("a1_inputs: {")) {
    fails.push(
      `callsite: a1_inputs block missing from ${CALLSITE_REL} (TurnDecisionObservedContext literal)`,
    );
  }
  if (!callsiteSrc.includes("turnA1ClarifyOptionBeforeProceed")) {
    fails.push(
      `callsite: turnA1ClarifyOptionBeforeProceed hoist missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("turnA1ManualConfirmAddressAskSnapshot")) {
    fails.push(
      `callsite: turnA1ManualConfirmAddressAskSnapshot hoist missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("turnA1ManualConfirmHandoffSnapshot")) {
    fails.push(
      `callsite: turnA1ManualConfirmHandoffSnapshot hoist missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("route_intent_fresh_this_turn")) {
    fails.push(
      `callsite: route_intent_fresh_this_turn not computed in ${CALLSITE_REL}`,
    );
  }

  // Relocation 3 FLIP (2026-04-22) — live-mode wiring checks.
  if (!outboundSrc.includes("DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER")) {
    fails.push(
      `outbound: DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER missing from ${OUTBOUND_REL}`,
    );
  }
  if (!callsiteSrc.includes("DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER")) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CALLSITE_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (!outboundSrc.includes("layerA1Passthrough")) {
    fails.push(
      `outbound: layerA1Passthrough input field missing from ${OUTBOUND_REL}`,
    );
  }
  if (
    !outboundSrc.includes("skipRegionAForLayerA1Passthrough")
  ) {
    fails.push(
      `outbound: skipRegionAForLayerA1Passthrough guard missing from ${OUTBOUND_REL}`,
    );
  }
  if (!outboundSrc.includes("[turn-decision/flip]")) {
    fails.push(
      `outbound: [turn-decision/flip] log line missing from ${OUTBOUND_REL}`,
    );
  }
  if (!outboundSrc.includes("legacyBranch")) {
    fails.push(
      `outbound: legacyBranch field (A0-family passthrough) missing from ${OUTBOUND_REL}`,
    );
  }
  // 2026-04-23 hoist — semantic gates must run before legacy A0 family.
  if (
    !moduleSrc.includes("DEPLOY_CANARY_TURN_DECISION_A1_SEMANTIC_GATE_HOIST_MARKER")
  ) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DECISION_A1_SEMANTIC_GATE_HOIST_MARKER missing from ${MODULE_REL}`,
    );
  }
  if (!callsiteSrc.includes("a1FlipLegacyBranch")) {
    fails.push(
      `callsite: a1FlipLegacyBranch derivation missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("RIDERS_TURN_DECISION_A1_FLIP")) {
    fails.push(
      `callsite: RIDERS_TURN_DECISION_A1_FLIP env flag missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("A1_FLIP_PASSTHROUGH_RULES")) {
    fails.push(
      `callsite: A1_FLIP_PASSTHROUGH_RULES set missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("a1FlipHallucinationGuardFired")) {
    fails.push(
      `callsite: a1FlipHallucinationGuardFired safeguard missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("layerA1Passthrough: a1FlipPayload")) {
    fails.push(
      `callsite: layerA1Passthrough injection missing from ${CALLSITE_REL}`,
    );
  }
  // 2026-04-23 Job-A authority removal — the blanket callsite
  // `a1FlipConfidenceOk` gate was deleted. `deriveA1Substitute` now
  // owns per-rule confidence policy as the single source of truth.
  // The removal marker must be present and no live second-guess check
  // may reappear at the callsite.
  if (
    !callsiteSrc.includes(
      "DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER",
    )
  ) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DECISION_A1_FLIP_CONFIDENCE_GATE_REMOVAL_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (/\bconst\s+a1FlipConfidenceOk\s*=/.test(callsiteSrc)) {
    fails.push(
      `callsite: a1FlipConfidenceOk declaration must be REMOVED from ${CALLSITE_REL} (Job-A authority removal); the derivation owns per-rule confidence policy`,
    );
  }
  if (/\ba1FlipConfidenceOk\s*&&/.test(callsiteSrc)) {
    fails.push(
      `callsite: a1FlipConfidenceOk must NOT participate in a1FlipAllowed in ${CALLSITE_REL} (Job-A authority removal)`,
    );
  }

  // Expected policy_rule ids — these are string literals in the module.
  const RULE_IDS = [
    "layer.a1.clarify_option_before_proceed",
    "layer.a1.manual_confirm_address_ask",
    "layer.a1.manual_confirm_handoff",
    "layer.a1.directive_ask.pass_on_clarifying",
    "layer.a1.directive_ask.pass_on_partial_answer",
    "layer.a1.directive_ask.pass_on_route_change",
    "layer.a1.directive_ask.render",
    "layer.a1.directive_ask.no_renderer",
    "layer.a1.no_substitute",
  ];
  const missing = RULE_IDS.filter((p) => !moduleSrc.includes(p));
  if (missing.length > 0) {
    fails.push(
      `module: deriveA1Substitute is missing policy rule ids: ${missing.join(", ")}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Full checks.
// ---------------------------------------------------------------------------

async function runFullChecks(fails) {
  const mod = await import(pathToFileURL(MODULE_PATH).href);
  const {
    deriveA1Substitute,
    classifyA1Agreement,
    observeTurnDecision,
    formatTurnDecisionTrace,
  } = mod;

  if (typeof deriveA1Substitute !== "function") {
    fails.push("module: deriveA1Substitute is not a function");
    return;
  }
  if (typeof classifyA1Agreement !== "function") {
    fails.push("module: classifyA1Agreement is not a function");
    return;
  }

  // 1. deriveA1Substitute cases.
  for (const c of A1_CASES) {
    const got = deriveA1Substitute(c.inputs);
    if (!got || typeof got !== "object") {
      fails.push(`deriveA1Substitute(${c.name}): did not return an object`);
      continue;
    }
    if (got.intent !== c.expected_intent) {
      fails.push(
        `deriveA1Substitute(${c.name}): intent=${got.intent}, expected ${c.expected_intent}`,
      );
    }
    if (got.policy_rule !== c.expected_policy_rule) {
      fails.push(
        `deriveA1Substitute(${c.name}): policy_rule=${got.policy_rule}, expected ${c.expected_policy_rule}`,
      );
    }
    if (typeof got.reason !== "string" || got.reason.length === 0) {
      fails.push(`deriveA1Substitute(${c.name}): reason is missing/empty`);
    }
  }

  // 2. classifyA1Agreement cases.
  for (const c of A1_AGREEMENT_CASES) {
    const got = classifyA1Agreement(c.observed, c.derived);
    if (got !== c.expected) {
      fails.push(
        `classifyA1Agreement(${String(c.observed)}, ${c.derived}): got ${got}, expected ${c.expected}`,
      );
    }
  }

  // 3. End-to-end through observeTurnDecision: supplying a1_inputs
  //    must produce derived_a1_intent / a1_agreement on the decision
  //    and surface them on the trace line. Uses the validated-tonight
  //    divergence case: clarifying_question with a directive that has
  //    a renderer — legacy renders, layer passes through.
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
    drained_op_names: ["proposed_turn_decision"],
    apply_boundary_rejection_fields: [],
    state_summary: {
      stage_at_turn_start: "quoted",
      stage_at_turn_end: "quoted",
      has_active_quoted_route: true,
      has_draft: true,
      missing_fields_count: 4,
    },
    language: "en",
  };
  const e2eDecision = observeTurnDecision(e2eInputs);
  if (e2eDecision.reply.source !== "server_rendered_directive") {
    fails.push(
      `e2e: observed reply.source=${e2eDecision.reply.source}, expected server_rendered_directive`,
    );
  }
  if (e2eDecision.reply.derived_a1_intent !== "allow") {
    fails.push(
      `e2e: reply.derived_a1_intent=${e2eDecision.reply.derived_a1_intent}, expected allow (clarifying passthrough)`,
    );
  }
  if (
    e2eDecision.reply.derived_a1_policy_rule !==
    "layer.a1.directive_ask.pass_on_clarifying"
  ) {
    fails.push(
      `e2e: derived_a1_policy_rule=${e2eDecision.reply.derived_a1_policy_rule}, expected layer.a1.directive_ask.pass_on_clarifying`,
    );
  }
  if (e2eDecision.reply.a1_agreement !== "disagree_layer_passthrough") {
    fails.push(
      `e2e: a1_agreement=${e2eDecision.reply.a1_agreement}, expected disagree_layer_passthrough`,
    );
  }

  const line = formatTurnDecisionTrace({
    conversation_id: e2eInputs.conversation_id,
    turn_id: e2eInputs.turn_id,
    language: e2eInputs.language,
    decision: e2eDecision,
    input_summary: {
      stage_at_turn_start: "quoted",
      stage_at_turn_end: "quoted",
      has_active_quoted_route: true,
      drained_op_count: 1,
      reply_text_chars: 65,
      schema_version: "1.3",
      proposer_present: true,
      proposer_valid: true,
    },
  });
  for (const tok of [
    "layer_a1_intent=allow",
    "a1_agreement=disagree_layer_passthrough",
  ]) {
    if (!line.includes(tok)) {
      fails.push(`formatTurnDecisionTrace e2e: missing token "${tok}"`);
    }
  }
  const payloadIdx = line.indexOf("payload=");
  if (payloadIdx !== -1) {
    try {
      const obj = JSON.parse(line.slice(payloadIdx + "payload=".length));
      if (obj.layer?.a1_intent !== "allow") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.a1_intent=${obj.layer?.a1_intent}, expected allow`,
        );
      }
      if (obj.layer?.a1_agreement !== "disagree_layer_passthrough") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.a1_agreement mismatch`,
        );
      }
      if (
        obj.layer?.a1_policy_rule !==
        "layer.a1.directive_ask.pass_on_clarifying"
      ) {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.a1_policy_rule=${obj.layer?.a1_policy_rule}`,
        );
      }
    } catch (e) {
      fails.push(
        `formatTurnDecisionTrace e2e: payload is not valid JSON — ${e.message}`,
      );
    }
  }

  // 4. Independence with Reloc 2: when BOTH a1_inputs and a4_inputs are
  //    supplied, the A1 derivation runs independently of the A4 dispatch.
  //    The observed a1_substitute_intent that feeds deriveDispatch is
  //    the *legacy* one — not the layer-derived intent. This keeps the
  //    two shadows uncontaminated during the Reloc 3 bake.
  const pairedInputs = {
    ...e2eInputs,
    a4_inputs: {
      a1_substitute_intent: "replace_directive_ask", // legacy observed
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
    },
  };
  const pairedDecision = observeTurnDecision(pairedInputs);
  if (pairedDecision.reply.derived_a1_intent !== "allow") {
    fails.push(
      `independence: derived_a1_intent=${pairedDecision.reply.derived_a1_intent}, expected allow`,
    );
  }
  // Reloc 2 sees observed intent replace_directive_ask + clarifying
  // question → it should also choose passthrough at A4 (that's the
  // existing ack/clarifying_passthrough rule in Reloc 2).
  if (pairedDecision.reply.derived_source !== "llm_authored") {
    fails.push(
      `independence: derived_source=${pairedDecision.reply.derived_source}, expected llm_authored (Reloc 2 clarifying passthrough)`,
    );
  }

  // 5. When a1_inputs is absent, layer A1 fields must be absent too
  //    (backward compatibility with the pre-Reloc-3 contract).
  const bareInputs = { ...e2eInputs };
  delete bareInputs.a1_inputs;
  const bareDecision = observeTurnDecision(bareInputs);
  if (bareDecision.reply.derived_a1_intent !== undefined) {
    fails.push(
      `observeTurnDecision(no a1_inputs): derived_a1_intent should be undefined, got ${bareDecision.reply.derived_a1_intent}`,
    );
  }
  if (bareDecision.reply.a1_agreement !== undefined) {
    fails.push(
      `observeTurnDecision(no a1_inputs): a1_agreement should be undefined`,
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
        `[smoke-test-turn-decision-a1-substitute] FAIL (source-only; tsx not installed):\n  - ${fails.join("\n  - ")}`,
      );
      process.exit(1);
    }
    console.log(
      `[smoke-test-turn-decision-a1-substitute] OK (source-only mode; tsx not installed). ` +
        `Canaries present, ${A1_CASES.length} policy rule ids referenced in source.`,
    );
    process.exit(0);
  }

  if (!process.env.__TD_A1_SMOKE_TSX__) {
    const child = spawnSync(
      "node",
      ["--import", "tsx", fileURLToPath(import.meta.url)],
      {
        cwd: repoRoot,
        stdio: "inherit",
        env: { ...process.env, __TD_A1_SMOKE_TSX__: "1" },
      },
    );
    process.exit(child.status ?? 1);
  }

  await runFullChecks(fails);

  if (fails.length > 0) {
    console.error(
      `[smoke-test-turn-decision-a1-substitute] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-turn-decision-a1-substitute] OK — ${A1_CASES.length} policy rules, ${A1_AGREEMENT_CASES.length} agreement cases, end-to-end divergence surfaced on trace.`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
