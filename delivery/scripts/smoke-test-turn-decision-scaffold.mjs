#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — relocation 1 (scaffold observer) for the unified
// turn-decision layer.
//
// DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER expected in the module
// header; DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER expected at the
// index.ts callsite. Source-only fallback when tsx isn't installed;
// full import mode when it is.
//
// Coverage:
//
//   1. Module canary + callsite canary both present in source.
//   2. `REPLY_SOURCES` exports exactly the six archetypes defined in
//      ARCHITECTURE_TURN_DECISION.md.
//   3. `classifyReplySource` is exhaustive against every value of
//      `OutboundDecisionReason` from `outbound-decision.ts`. Each
//      enum value produces the expected archetype.
//   4. `observeTurnDecision` produces a structurally valid
//      `TurnDecision` for every archetype-shaped observed context.
//   5. `formatTurnDecisionTrace` emits the expected envelope:
//        - begins with `[turn-decision/trace]`
//        - contains `conversation=`, `reply_source=`,
//          `observed_reason=`, `ti=`, `ac=`, `po=`, `payload=`
//        - `payload=` is a valid JSON object round-tripping the
//          decision shape
//   6. Regression-contract: every `OutboundDecisionReason` maps to a
//      `ReplySource` that makes sense given the reason's semantics
//      (encoded via an expected-pair table below).
//
// Run from `delivery/`:
//   node scripts/smoke-test-turn-decision-scaffold.mjs
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

// Expected mapping, keyed by the OutboundDecisionReason literal. MUST
// stay in sync with `classifyReplySource` in the module and with
// ARCHITECTURE_TURN_DECISION.md §Outputs > Reply composition.
const EXPECTED_MAPPING = {
  allow: "llm_authored",
  allow_sanitized: "llm_authored",
  replace_directive_ask: "server_rendered_directive",
  replace_summary_fact_drift: "server_rendered_directive",
  replace_clarify_option_before_proceed: "server_substitute_text",
  replace_manual_confirm_address_ask: "server_substitute_text",
  replace_manual_confirm_handoff: "server_substitute_text",
  replace_transaction_artifact_missing: "server_recovery_template",
  replace_price_mismatch: "server_recovery_template",
  replace_field_rejection_hallucination: "server_recovery_template",
  replace_order_placed_hallucination: "server_recovery_template",
  replace_get_price_bypass: "server_recovery_template",
  block_provider_error: "server_recovery_template",
  fallback_empty_reply: "server_recovery_template",
  preserve_clarification: "llm_authored",
};

const EXPECTED_SOURCES = [
  "server_rendered_directive",
  "server_ack_plus_directive",
  "server_substitute_text",
  "server_recovery_template",
  "deferred_confirm_prompt",
  "llm_authored",
];

// ---------------------------------------------------------------------------
// Shared source-level checks (run in both modes).
// ---------------------------------------------------------------------------

async function runSourceLevelChecks(fails) {
  const [moduleSrc, callsiteSrc, outboundSrc] = await Promise.all([
    fs.readFile(MODULE_PATH, "utf8"),
    fs.readFile(CALLSITE_PATH, "utf8"),
    fs.readFile(OUTBOUND_PATH, "utf8"),
  ]);

  // 1. Canary markers.
  if (!moduleSrc.includes("DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER")) {
    fails.push(
      `module: DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER missing from ${MODULE_REL}`,
    );
  }
  if (!callsiteSrc.includes("DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER")) {
    fails.push(
      `callsite: DEPLOY_CANARY_TURN_DECISION_CALLSITE_MARKER missing from ${CALLSITE_REL}`,
    );
  }
  if (!callsiteSrc.includes("[turn-decision/trace]")) {
    fails.push(
      `callsite: [turn-decision/trace] emit string missing from ${CALLSITE_REL}`,
    );
  }

  // 2. Every OutboundDecisionReason value is handled in
  //    classifyReplySource's switch. Extract the reason literal set
  //    from outbound-decision.ts and make sure every one appears as a
  //    `case "X":` in turn-decision.ts.
  const reasonUnionMatch = outboundSrc.match(
    /export type OutboundDecisionReason\s*=\s*([\s\S]*?);/,
  );
  if (!reasonUnionMatch) {
    fails.push(
      `outbound-decision: could not locate OutboundDecisionReason union`,
    );
    return [];
  }
  const reasonLiterals = Array.from(
    reasonUnionMatch[1].matchAll(/"([a-z_]+)"/g),
  ).map((m) => m[1]);
  const uniqueReasons = Array.from(new Set(reasonLiterals));

  const missing = uniqueReasons.filter(
    (r) => !new RegExp(`case\\s+"${r}"\\s*:`).test(moduleSrc),
  );
  if (missing.length > 0) {
    fails.push(
      `module: classifyReplySource is missing case branches for reasons: ${missing.join(", ")}`,
    );
  }

  // 3. Every reason in EXPECTED_MAPPING exists in the union.
  const unionSet = new Set(uniqueReasons);
  const stale = Object.keys(EXPECTED_MAPPING).filter((r) => !unionSet.has(r));
  if (stale.length > 0) {
    fails.push(
      `smoke: EXPECTED_MAPPING has entries not in OutboundDecisionReason union: ${stale.join(", ")}`,
    );
  }
  const untested = uniqueReasons.filter((r) => !(r in EXPECTED_MAPPING));
  if (untested.length > 0) {
    fails.push(
      `smoke: EXPECTED_MAPPING is missing entries for enum values: ${untested.join(", ")}`,
    );
  }

  return uniqueReasons;
}

// ---------------------------------------------------------------------------
// TSX-present full checks (import the module and exercise it).
// ---------------------------------------------------------------------------

async function runFullChecks(fails, uniqueReasons) {
  const mod = await import(pathToFileURL(MODULE_PATH).href);
  const {
    REPLY_SOURCES,
    classifyReplySource,
    observeTurnDecision,
    formatTurnDecisionTrace,
  } = mod;

  // 2. Exactly six archetypes.
  if (
    !Array.isArray(REPLY_SOURCES) ||
    REPLY_SOURCES.length !== EXPECTED_SOURCES.length ||
    !EXPECTED_SOURCES.every((s) => REPLY_SOURCES.includes(s))
  ) {
    fails.push(
      `REPLY_SOURCES mismatch: got ${JSON.stringify(REPLY_SOURCES)}, want ${JSON.stringify(EXPECTED_SOURCES)}`,
    );
  }

  // 3. classifyReplySource matches EXPECTED_MAPPING for every enum value.
  for (const reason of uniqueReasons) {
    const expected = EXPECTED_MAPPING[reason];
    const got = classifyReplySource(reason);
    if (!got || typeof got !== "object") {
      fails.push(`classifyReplySource(${reason}) did not return an object`);
      continue;
    }
    if (got.source !== expected) {
      fails.push(
        `classifyReplySource(${reason}) produced source=${got.source}, expected ${expected}`,
      );
    }
    if (got.source === "llm_authored" && !got.llm_authored_reason) {
      fails.push(
        `classifyReplySource(${reason}) returned llm_authored without llm_authored_reason`,
      );
    }
    if (got.source !== "llm_authored" && got.llm_authored_reason !== null) {
      fails.push(
        `classifyReplySource(${reason}) returned source=${got.source} but llm_authored_reason was non-null: ${got.llm_authored_reason}`,
      );
    }
  }

  // 4. observeTurnDecision produces a structurally valid TurnDecision
  //    for a sampling of archetype-shaped observed contexts. One case
  //    per reply source archetype (except `server_ack_plus_directive`
  //    which is the M1 flip target and `deferred_confirm_prompt` which
  //    is not exercised in the scaffold).
  const sampleCases = [
    {
      name: "llm_authored_allow",
      reason: "allow",
      reply_author: "llm",
      directive_action: null,
      expectedSource: "llm_authored",
    },
    {
      name: "server_rendered_directive_ask",
      reason: "replace_directive_ask",
      reply_author: "server",
      directive_action: "ASK_SENDER_PHONE",
      expectedSource: "server_rendered_directive",
    },
    {
      name: "server_substitute_clarify",
      reason: "replace_clarify_option_before_proceed",
      reply_author: "server",
      directive_action: null,
      expectedSource: "server_substitute_text",
    },
    {
      name: "server_recovery_price_mismatch",
      reason: "replace_price_mismatch",
      reply_author: "server",
      directive_action: null,
      expectedSource: "server_recovery_template",
    },
    {
      name: "server_recovery_empty_fallback",
      reason: "fallback_empty_reply",
      reply_author: "fallback",
      directive_action: null,
      expectedSource: "server_recovery_template",
    },
  ];

  for (const c of sampleCases) {
    const ctx = {
      conversation_id: "conv1",
      turn_id: "t-1",
      outcome: {
        decision:
          c.reason === "allow" || c.reason === "allow_sanitized"
            ? "allow"
            : c.reason.startsWith("replace_")
              ? "replace_authoritative"
              : "replace_fallback",
        reason: c.reason,
        reply_author: c.reply_author,
        reply_text_chars: 42,
        directive_action: c.directive_action,
        directive_render_context_present: !!c.directive_action,
        marked_summary_shown: false,
      },
      proposer: {
        present: true,
        schema_valid: true,
        schema_version: "1.3",
        turn_kind: "booking_detail_collection",
        ti_kind: "answered_partial",
        ti_confidence: "high",
        ac_kind: null,
        po_kind: null,
      },
      drained_op_names: ["apply_booking_field", "proposed_turn_decision"],
      apply_boundary_rejection_fields: [],
      state_summary: {
        stage_at_turn_start: "collecting_booking_details",
        stage_at_turn_end: "collecting_booking_details",
        has_active_quoted_route: true,
        has_draft: true,
        missing_fields_count: 3,
      },
      language: "en",
    };
    const decision = observeTurnDecision(ctx);
    if (!decision || typeof decision !== "object") {
      fails.push(`observeTurnDecision(${c.name}): did not return object`);
      continue;
    }
    if (decision.reply?.source !== c.expectedSource) {
      fails.push(
        `observeTurnDecision(${c.name}): reply.source=${decision.reply?.source}, expected ${c.expectedSource}`,
      );
    }
    if (
      !Array.isArray(decision.op_plan?.entries) ||
      decision.op_plan.entries.length !== ctx.drained_op_names.length
    ) {
      fails.push(
        `observeTurnDecision(${c.name}): op_plan.entries has wrong length`,
      );
    }
    if (!decision.trace || typeof decision.trace.decision_id !== "string") {
      fails.push(`observeTurnDecision(${c.name}): trace.decision_id missing`);
    }
    if (decision.trace.observed_reason !== c.reason) {
      fails.push(
        `observeTurnDecision(${c.name}): trace.observed_reason=${decision.trace.observed_reason}, expected ${c.reason}`,
      );
    }

    // 5. formatTurnDecisionTrace output shape.
    const line = formatTurnDecisionTrace({
      conversation_id: ctx.conversation_id,
      turn_id: ctx.turn_id,
      language: ctx.language,
      decision,
      input_summary: {
        stage_at_turn_start: "collecting_booking_details",
        stage_at_turn_end: "collecting_booking_details",
        has_active_quoted_route: true,
        drained_op_count: 2,
        reply_text_chars: 42,
        schema_version: "1.3",
        proposer_present: true,
        proposer_valid: true,
      },
    });

    const expectedTokens = [
      "[turn-decision/trace]",
      "conversation=conv1",
      "turn_id=t-1",
      "lang=en",
      `reply_source=${c.expectedSource}`,
      `observed_reason=${c.reason}`,
      "ti=answered_partial",
      "ac=-",
      "po=-",
      "payload=",
    ];
    for (const tok of expectedTokens) {
      if (!line.includes(tok)) {
        fails.push(
          `formatTurnDecisionTrace(${c.name}): missing token "${tok}"`,
        );
      }
    }
    const payloadIdx = line.indexOf("payload=");
    if (payloadIdx !== -1) {
      const payloadStr = line.slice(payloadIdx + "payload=".length);
      try {
        const obj = JSON.parse(payloadStr);
        if (obj.reply_source !== c.expectedSource) {
          fails.push(
            `formatTurnDecisionTrace(${c.name}): payload.reply_source mismatch`,
          );
        }
        if (obj.observed.reason !== c.reason) {
          fails.push(
            `formatTurnDecisionTrace(${c.name}): payload.observed.reason mismatch`,
          );
        }
      } catch (e) {
        fails.push(
          `formatTurnDecisionTrace(${c.name}): payload is not valid JSON — ${e.message}`,
        );
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Main.
// ---------------------------------------------------------------------------

async function main() {
  const fails = [];
  const uniqueReasons = await runSourceLevelChecks(fails);

  const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
    cwd: repoRoot,
    stdio: "ignore",
  });
  const hasTsx = tsxCheck.status === 0;

  if (!hasTsx) {
    if (fails.length > 0) {
      console.error(
        `[smoke-test-turn-decision-scaffold] FAIL (source-only; tsx not installed):\n  - ${fails.join("\n  - ")}`,
      );
      process.exit(1);
    }
    console.log(
      `[smoke-test-turn-decision-scaffold] OK (source-only mode; tsx not installed). ` +
        `Canaries present, ${uniqueReasons.length} OutboundDecisionReason values covered by classifyReplySource, ` +
        `expected mapping table aligned with union.`,
    );
    process.exit(0);
  }

  if (!process.env.__TURN_DECISION_SCAFFOLD_SMOKE_TSX__) {
    const child = spawnSync(
      "node",
      ["--import", "tsx", fileURLToPath(import.meta.url)],
      {
        cwd: repoRoot,
        stdio: "inherit",
        env: {
          ...process.env,
          __TURN_DECISION_SCAFFOLD_SMOKE_TSX__: "1",
        },
      },
    );
    process.exit(child.status ?? 1);
  }

  await runFullChecks(fails, uniqueReasons);

  if (fails.length > 0) {
    console.error(
      `[smoke-test-turn-decision-scaffold] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-turn-decision-scaffold] OK — 6 archetypes exported, ${uniqueReasons.length} reasons covered exhaustively, observer + trace emit shape verified.`,
  );
  process.exit(0);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
