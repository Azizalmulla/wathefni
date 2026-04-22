#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — relocation 2 (A4 → layer) dispatch derivation.
//
// Verifies the new `deriveDispatch` policy rules, the
// `classifyDispatchAgreement` helper, the end-to-end wiring through
// `observeTurnDecision`, and the `[turn-decision/trace]` emit envelope
// surfacing `layer_source=` and `dispatch_agreement=` tokens.
//
// DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER expected in the module
// header and on the index.ts callsite (via `a4_inputs: {`).
//
// Source-only mode when tsx isn't installed; full import mode when it is.
//
// Run from `delivery/`:
//   node scripts/smoke-test-turn-decision-a4-dispatch.mjs
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

// Expected layer-dispatch decisions, one per policy rule. Organized
// as (inputs → derivation). MUST stay in sync with `deriveDispatch`.
const DISPATCH_CASES = [
  // Rule 1: A1 recovery intents.
  {
    name: "a1_recovery.replace_price_mismatch",
    inputs: {
      a1_substitute_intent: "replace_price_mismatch",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_recovery_template",
    expected_policy_rule: "layer.a1_recovery.replace_price_mismatch",
  },
  {
    name: "a1_recovery.fallback_empty_reply",
    inputs: {
      a1_substitute_intent: "fallback_empty_reply",
      llm_reply_empty: true,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_recovery_template",
    expected_policy_rule: "layer.a1_recovery.fallback_empty_reply",
  },

  // Rule 2: A1 substitute-text intents.
  {
    name: "a1_substitute.clarify_option",
    inputs: {
      a1_substitute_intent: "replace_clarify_option_before_proceed",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_substitute_text",
    expected_policy_rule:
      "layer.a1_substitute.replace_clarify_option_before_proceed",
  },
  {
    name: "a1_substitute.manual_confirm_address",
    inputs: {
      a1_substitute_intent: "replace_manual_confirm_address_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_substitute_text",
    expected_policy_rule:
      "layer.a1_substitute.replace_manual_confirm_address_ask",
  },
  {
    name: "a1_substitute.manual_confirm_handoff",
    inputs: {
      a1_substitute_intent: "replace_manual_confirm_handoff",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_substitute_text",
    expected_policy_rule: "layer.a1_substitute.replace_manual_confirm_handoff",
  },

  // Rule 3: summary fact drift.
  {
    name: "a1_summary_fact_drift",
    inputs: {
      a1_substitute_intent: "replace_summary_fact_drift",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_rendered_directive",
    expected_policy_rule: "layer.a1_summary_fact_drift",
  },

  // Rule 4: A1 replace_directive_ask + renderer + no semantic override.
  {
    name: "a1_directive_ask.render.no_semantic_override",
    inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: "high",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_rendered_directive",
    expected_policy_rule: "layer.a1_directive_ask.render",
  },

  // Rule 4a: **divergence** — ack passthrough.
  {
    name: "a1_directive_ask.ack_passthrough",
    inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
      proposer_ti_kind: "acknowledgement",
      proposer_ti_confidence: "medium",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "llm_authored",
    expected_policy_rule: "layer.a1_directive_ask.ack_passthrough",
  },

  // Rule 4b: **divergence** — clarifying passthrough.
  {
    name: "a1_directive_ask.clarifying_passthrough",
    inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
      proposer_ti_kind: "clarifying_question",
      proposer_ti_confidence: "high",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "llm_authored",
    expected_policy_rule: "layer.a1_directive_ask.clarifying_passthrough",
  },

  // Rule 4c: low confidence semantic signal → falls back to legacy-
  //          aligned render branch (we don't trust a low-confidence
  //          classifier to move behaviour).
  {
    name: "a1_directive_ask.ack_low_confidence_still_renders",
    inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
      proposer_ti_kind: "acknowledgement",
      proposer_ti_confidence: "low",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_rendered_directive",
    expected_policy_rule: "layer.a1_directive_ask.render",
  },

  // Rule 4d: A1 directive_ask without a renderer — can't substitute.
  {
    name: "a1_directive_ask.no_renderer_passthrough",
    inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: "high",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "llm_authored",
    expected_policy_rule: "layer.a1_directive_ask.no_renderer_passthrough",
  },

  // Rule 5: preserve_clarification passthrough.
  {
    name: "preserve_clarification",
    inputs: {
      a1_substitute_intent: "preserve_clarification",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "llm_authored",
    expected_policy_rule: "layer.a1_preserve_clarification",
  },

  // Rule 6: empty LLM reply, no A1 intent → recovery.
  {
    name: "empty_llm_fallback",
    inputs: {
      a1_substitute_intent: null,
      llm_reply_empty: true,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_recovery_template",
    expected_policy_rule: "layer.empty_llm_fallback",
  },

  // Rule 7: guard fired without A1 → recovery.
  {
    name: "hallucination_guard_standalone",
    inputs: {
      a1_substitute_intent: null,
      llm_reply_empty: false,
      hallucination_guard_fired: true,
      directive_has_server_renderer: false,
      proposer_ti_kind: null,
      proposer_ti_confidence: null,
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "server_recovery_template",
    expected_policy_rule: "layer.hallucination_guard",
  },

  // Default: allow.
  {
    name: "authority_allow",
    inputs: {
      a1_substitute_intent: null,
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: false,
      proposer_ti_kind: "answered_partial",
      proposer_ti_confidence: "high",
      proposer_ac_kind: null,
      proposer_po_kind: null,
    },
    expected_source: "llm_authored",
    expected_policy_rule: "layer.authority_allow",
  },
];

const AGREEMENT_CASES = [
  { observed: "llm_authored", derived: "llm_authored", expected: "agree" },
  {
    observed: "server_rendered_directive",
    derived: "server_rendered_directive",
    expected: "agree",
  },
  {
    observed: "server_rendered_directive",
    derived: "llm_authored",
    expected: "disagree_layer_passthrough",
  },
  {
    observed: "server_substitute_text",
    derived: "llm_authored",
    expected: "disagree_layer_passthrough",
  },
  {
    observed: "llm_authored",
    derived: "server_rendered_directive",
    expected: "disagree_layer_substitute",
  },
  {
    observed: "llm_authored",
    derived: "server_recovery_template",
    expected: "disagree_layer_substitute",
  },
  {
    observed: "server_rendered_directive",
    derived: "server_substitute_text",
    expected: "disagree_other",
  },
  {
    observed: "server_recovery_template",
    derived: "server_rendered_directive",
    expected: "disagree_other",
  },
];

// ---------------------------------------------------------------------------
// Source-level checks.
// ---------------------------------------------------------------------------

async function runSourceLevelChecks(fails) {
  const [moduleSrc, callsiteSrc] = await Promise.all([
    fs.readFile(MODULE_PATH, "utf8"),
    fs.readFile(CALLSITE_PATH, "utf8"),
  ]);

  if (!moduleSrc.includes("DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER")) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER missing from ${MODULE_REL}`,
    );
  }
  if (!moduleSrc.includes("export function deriveDispatch(")) {
    fails.push(`module: deriveDispatch export missing from ${MODULE_REL}`);
  }
  if (!moduleSrc.includes("export function classifyDispatchAgreement(")) {
    fails.push(
      `module: classifyDispatchAgreement export missing from ${MODULE_REL}`,
    );
  }
  if (!callsiteSrc.includes("a4_inputs: {")) {
    fails.push(
      `callsite: a4_inputs block missing from ${CALLSITE_REL} (TurnDecisionObservedContext literal)`,
    );
  }
  if (!callsiteSrc.includes("turnA1SubstituteIntent")) {
    fails.push(
      `callsite: turnA1SubstituteIntent variable missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("originalLlmReplyChars")) {
    fails.push(
      `callsite: originalLlmReplyChars snapshot missing from ${CALLSITE_REL}`,
    );
  }

  // Every expected policy_rule prefix appears in the module source.
  // Full id suffixes are template-constructed at runtime and verified
  // via the full (tsx) checks below, so source-only mode matches on
  // the stable prefix.
  const PREFIXES = [
    "layer.a1_recovery.",
    "layer.a1_substitute.",
    "layer.a1_summary_fact_drift",
    "layer.a1_directive_ask.render",
    "layer.a1_directive_ask.ack_passthrough",
    "layer.a1_directive_ask.clarifying_passthrough",
    "layer.a1_directive_ask.no_renderer_passthrough",
    "layer.a1_preserve_clarification",
    "layer.empty_llm_fallback",
    "layer.hallucination_guard",
    "layer.authority_allow",
  ];
  const missingPrefixes = PREFIXES.filter((p) => !moduleSrc.includes(p));
  if (missingPrefixes.length > 0) {
    fails.push(
      `module: deriveDispatch is missing policy rule prefixes: ${missingPrefixes.join(", ")}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Full checks.
// ---------------------------------------------------------------------------

async function runFullChecks(fails) {
  const mod = await import(pathToFileURL(MODULE_PATH).href);
  const {
    deriveDispatch,
    classifyDispatchAgreement,
    observeTurnDecision,
    formatTurnDecisionTrace,
  } = mod;

  if (typeof deriveDispatch !== "function") {
    fails.push("module: deriveDispatch is not a function");
    return;
  }
  if (typeof classifyDispatchAgreement !== "function") {
    fails.push("module: classifyDispatchAgreement is not a function");
    return;
  }

  // 1. deriveDispatch cases.
  for (const c of DISPATCH_CASES) {
    const got = deriveDispatch(c.inputs);
    if (!got || typeof got !== "object") {
      fails.push(`deriveDispatch(${c.name}): did not return an object`);
      continue;
    }
    if (got.source !== c.expected_source) {
      fails.push(
        `deriveDispatch(${c.name}): source=${got.source}, expected ${c.expected_source}`,
      );
    }
    if (got.policy_rule !== c.expected_policy_rule) {
      fails.push(
        `deriveDispatch(${c.name}): policy_rule=${got.policy_rule}, expected ${c.expected_policy_rule}`,
      );
    }
    if (typeof got.reason !== "string" || got.reason.length === 0) {
      fails.push(`deriveDispatch(${c.name}): reason is missing/empty`);
    }
  }

  // 2. classifyDispatchAgreement cases.
  for (const c of AGREEMENT_CASES) {
    const got = classifyDispatchAgreement(c.observed, c.derived);
    if (got !== c.expected) {
      fails.push(
        `classifyDispatchAgreement(${c.observed}, ${c.derived}): got ${got}, expected ${c.expected}`,
      );
    }
  }

  // 3. End-to-end through observeTurnDecision: supplying a4_inputs
  //    must produce derived_source / dispatch_agreement on the decision
  //    and surface them on the trace line.
  const e2eInputs = {
    conversation_id: "conv-e2e",
    turn_id: "t-e2e",
    outcome: {
      decision: "replace_authoritative",
      reason: "replace_directive_ask",
      reply_author: "server",
      reply_text_chars: 55,
      directive_action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      directive_render_context_present: true,
      marked_summary_shown: false,
    },
    proposer: {
      present: true,
      schema_valid: true,
      schema_version: "1.3",
      turn_kind: "booking_detail_collection",
      ti_kind: "acknowledgement",
      ti_confidence: "medium",
      ac_kind: null,
      po_kind: null,
    },
    a4_inputs: {
      a1_substitute_intent: "replace_directive_ask",
      llm_reply_empty: false,
      hallucination_guard_fired: false,
      directive_has_server_renderer: true,
    },
    drained_op_names: ["proposed_turn_decision"],
    apply_boundary_rejection_fields: [],
    state_summary: {
      stage_at_turn_start: "quoted",
      stage_at_turn_end: "quoted",
      has_active_quoted_route: true,
      has_draft: true,
      missing_fields_count: 3,
    },
    language: "en",
  };
  const e2eDecision = observeTurnDecision(e2eInputs);
  if (e2eDecision.reply.source !== "server_rendered_directive") {
    fails.push(
      `e2e: observed reply.source=${e2eDecision.reply.source}, expected server_rendered_directive`,
    );
  }
  if (e2eDecision.reply.derived_source !== "llm_authored") {
    fails.push(
      `e2e: reply.derived_source=${e2eDecision.reply.derived_source}, expected llm_authored (ack passthrough divergence)`,
    );
  }
  if (
    e2eDecision.reply.derived_policy_rule !==
    "layer.a1_directive_ask.ack_passthrough"
  ) {
    fails.push(
      `e2e: derived_policy_rule=${e2eDecision.reply.derived_policy_rule}, expected layer.a1_directive_ask.ack_passthrough`,
    );
  }
  if (e2eDecision.reply.dispatch_agreement !== "disagree_layer_passthrough") {
    fails.push(
      `e2e: dispatch_agreement=${e2eDecision.reply.dispatch_agreement}, expected disagree_layer_passthrough`,
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
      reply_text_chars: 55,
      schema_version: "1.3",
      proposer_present: true,
      proposer_valid: true,
    },
  });
  for (const tok of [
    "layer_source=llm_authored",
    "dispatch_agreement=disagree_layer_passthrough",
  ]) {
    if (!line.includes(tok)) {
      fails.push(`formatTurnDecisionTrace e2e: missing token "${tok}"`);
    }
  }
  const payloadIdx = line.indexOf("payload=");
  if (payloadIdx !== -1) {
    try {
      const obj = JSON.parse(line.slice(payloadIdx + "payload=".length));
      if (obj.layer?.derived_source !== "llm_authored") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.derived_source=${obj.layer?.derived_source}, expected llm_authored`,
        );
      }
      if (obj.layer?.dispatch_agreement !== "disagree_layer_passthrough") {
        fails.push(
          `formatTurnDecisionTrace e2e: payload.layer.dispatch_agreement mismatch`,
        );
      }
    } catch (e) {
      fails.push(
        `formatTurnDecisionTrace e2e: payload is not valid JSON — ${e.message}`,
      );
    }
  }

  // 4. When a4_inputs is absent, layer fields must be absent too
  //    (backward compatibility with the old scaffold contract).
  const bareInputs = {
    ...e2eInputs,
    a4_inputs: undefined,
  };
  delete bareInputs.a4_inputs;
  const bareDecision = observeTurnDecision(bareInputs);
  if (bareDecision.reply.derived_source !== undefined) {
    fails.push(
      `observeTurnDecision(no a4_inputs): derived_source should be undefined, got ${bareDecision.reply.derived_source}`,
    );
  }
  if (bareDecision.reply.dispatch_agreement !== undefined) {
    fails.push(
      `observeTurnDecision(no a4_inputs): dispatch_agreement should be undefined`,
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
        `[smoke-test-turn-decision-a4-dispatch] FAIL (source-only; tsx not installed):\n  - ${fails.join("\n  - ")}`,
      );
      process.exit(1);
    }
    console.log(
      `[smoke-test-turn-decision-a4-dispatch] OK (source-only mode; tsx not installed). ` +
        `Canaries present, ${DISPATCH_CASES.length} policy rule ids referenced in source.`,
    );
    process.exit(0);
  }

  if (!process.env.__TD_A4_SMOKE_TSX__) {
    const child = spawnSync(
      "node",
      ["--import", "tsx", fileURLToPath(import.meta.url)],
      {
        cwd: repoRoot,
        stdio: "inherit",
        env: { ...process.env, __TD_A4_SMOKE_TSX__: "1" },
      },
    );
    process.exit(child.status ?? 1);
  }

  await runFullChecks(fails);

  if (fails.length > 0) {
    console.error(
      `[smoke-test-turn-decision-a4-dispatch] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-turn-decision-a4-dispatch] OK — ${DISPATCH_CASES.length} policy rules, ${AGREEMENT_CASES.length} agreement cases, end-to-end divergence surfaced on trace.`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
