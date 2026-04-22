// Phase C / hybrid harness — unit schema-validator contract tests.
//
// These are in-process checks over the `propose_turn_decision` schema and
// validator. They don't hit the network; they contribute a boolean pass
// signal to the corpus rollup. Any failure indicates the Phase A in-repo
// contract is broken — which is a hard-fail for the corpus runner.
//
// Kept deliberately small (no brittle snapshot-style checks) so the
// contract cost is clear. The detailed 27-assertion smoke test over the
// schema lives in `scripts/smoke-test-proposer-schema.mjs`; this file is
// the subset that must pass to keep the corpus honest.

import path from "node:path";
import url from "node:url";

async function loadValidator() {
  const here = path.dirname(url.fileURLToPath(import.meta.url));
  const modulePath = path.resolve(
    here,
    "../../plugins/shared/proposer-schema.ts",
  );
  // The shared schema is .ts; use the same tsx/esbuild loader the rest of
  // the repo uses. We fall back to a direct dynamic import in case the
  // runtime already has ts hooks registered (as under `npx tsx`).
  try {
    return await import(modulePath);
  } catch (err) {
    throw new Error(
      `unit-schema-contract: could not load proposer-schema.ts (${err?.message || err}). ` +
        `Run via \`npx tsx scripts/eval-corpus/runner.mjs\` so ts imports resolve.`,
    );
  }
}

function makeWellFormed() {
  return {
    schema_version: "1.0",
    turn_kind: "initial_route",
    pricing_decision: { action: "call_get_price", reason: "route intent present" },
    planned_tool_calls: ["get_price"],
    customer_reply_draft: "One sec while I quote that.",
  };
}

export async function runSchemaContractTests() {
  const checks = [];
  const failures = [];

  let validate;
  let PROPOSED_TURN_KINDS;
  let PROPOSED_PRICING_ACTIONS;
  let AWAITING_CONFIRMATION_KINDS;
  let SCHEMA;
  try {
    const mod = await loadValidator();
    validate = mod.validateProposedTurnDecision;
    PROPOSED_TURN_KINDS = mod.PROPOSED_TURN_KINDS;
    PROPOSED_PRICING_ACTIONS = mod.PROPOSED_PRICING_ACTIONS;
    AWAITING_CONFIRMATION_KINDS = mod.AWAITING_CONFIRMATION_KINDS;
    SCHEMA = mod.PROPOSE_TURN_DECISION_TOOL_SCHEMA;
  } catch (err) {
    return {
      passed: false,
      checks: [],
      failures: [{ id: "load_module", error: err?.message || String(err) }],
    };
  }

  function check(id, condition, detail) {
    checks.push({ id, passed: !!condition });
    if (!condition) failures.push({ id, detail: detail || "failed" });
  }

  const wf = makeWellFormed();
  const r = validate(wf);
  check("well_formed_validates", r.ok === true, r.ok ? "" : JSON.stringify(r.errors));
  if (r.ok) {
    check(
      "well_formed_roundtrip_turn_kind",
      r.value.turn_kind === "initial_route",
    );
    check(
      "well_formed_roundtrip_action",
      r.value.pricing_decision?.action === "call_get_price",
    );
    check(
      "well_formed_planned_tool_calls_preserved",
      Array.isArray(r.value.planned_tool_calls) &&
        r.value.planned_tool_calls.length === 1 &&
        r.value.planned_tool_calls[0] === "get_price",
    );
  }

  const badVersion = validate({ ...wf, schema_version: "2.0" });
  check(
    "rejects_unsupported_schema_version",
    badVersion.ok === false &&
      badVersion.errors.some((e) => e.startsWith("schema_version_unsupported")),
  );

  const badKind = validate({ ...wf, turn_kind: "totally_bogus_kind" });
  check(
    "rejects_unknown_turn_kind",
    badKind.ok === false &&
      badKind.errors.some((e) => e.startsWith("turn_kind_invalid")),
  );

  const badAction = validate({
    ...wf,
    pricing_decision: { action: "destroy_universe", reason: "no" },
  });
  check(
    "rejects_unknown_pricing_action",
    badAction.ok === false &&
      badAction.errors.some((e) => e.startsWith("pricing_decision.action_invalid")),
  );

  const missingPricing = validate({ ...wf, pricing_decision: undefined });
  check(
    "rejects_missing_pricing_decision",
    missingPricing.ok === false &&
      missingPricing.errors.some((e) => e === "pricing_decision_not_object"),
  );

  const badArray = validate({ ...wf, planned_tool_calls: "nope" });
  check(
    "rejects_non_array_planned_tool_calls",
    badArray.ok === false &&
      badArray.errors.some((e) => e === "planned_tool_calls_not_array"),
  );

  const badDraft = validate({ ...wf, customer_reply_draft: 42 });
  check(
    "rejects_non_string_reply_draft",
    badDraft.ok === false &&
      badDraft.errors.some((e) => e === "customer_reply_draft_not_string"),
  );

  const nullInput = validate(null);
  check(
    "rejects_null_input",
    nullInput.ok === false &&
      nullInput.errors.some((e) => e === "proposer_payload_not_object"),
  );

  check(
    "turn_kinds_enum_nonempty",
    Array.isArray(PROPOSED_TURN_KINDS) && PROPOSED_TURN_KINDS.length > 0,
  );
  check(
    "pricing_actions_enum_nonempty",
    Array.isArray(PROPOSED_PRICING_ACTIONS) &&
      PROPOSED_PRICING_ACTIONS.length > 0,
  );
  check(
    "schema_shape_has_required",
    SCHEMA &&
      Array.isArray(SCHEMA.required) &&
      SCHEMA.required.includes("schema_version") &&
      SCHEMA.required.includes("turn_kind") &&
      SCHEMA.required.includes("pricing_decision"),
  );
  check(
    "schema_turn_kind_enum_matches_runtime",
    SCHEMA?.properties?.turn_kind?.enum?.length === PROPOSED_TURN_KINDS.length,
  );
  check(
    "schema_pricing_action_enum_matches_runtime",
    SCHEMA?.properties?.pricing_decision?.properties?.action?.enum?.length ===
      PROPOSED_PRICING_ACTIONS.length,
  );

  // v1.1 (2026-04-22): awaiting_confirmation classification. Minimal
  // contract coverage here; the full 20+ assertions live in the
  // smoke-test-proposer-schema.mjs suite.
  const v11Confirm = validate({
    ...wf,
    schema_version: "1.1",
    turn_kind: "confirmation_or_cancel",
    pricing_decision: { action: "none", reason: "summary stage" },
    planned_tool_calls: [],
    customer_reply_draft: "",
    awaiting_confirmation: {
      kind: "confirm_order",
      reason: "customer said 'yes go ahead'",
    },
  });
  check(
    "v11_awaiting_confirmation_roundtrips",
    v11Confirm.ok === true &&
      v11Confirm.value?.awaiting_confirmation?.kind === "confirm_order",
    v11Confirm.ok ? "" : JSON.stringify(v11Confirm.errors),
  );

  const v11BadKind = validate({
    ...wf,
    schema_version: "1.1",
    awaiting_confirmation: { kind: "tip_generously", reason: "n/a" },
  });
  check(
    "v11_rejects_unknown_awaiting_confirmation_kind",
    v11BadKind.ok === false &&
      v11BadKind.errors.some((e) =>
        e.startsWith("awaiting_confirmation.kind_invalid"),
      ),
  );

  const v10LegacyPayload = validate(wf);
  check(
    "v10_legacy_payload_still_validates",
    v10LegacyPayload.ok === true,
  );

  check(
    "awaiting_confirmation_kinds_enum_nonempty",
    Array.isArray(AWAITING_CONFIRMATION_KINDS) &&
      AWAITING_CONFIRMATION_KINDS.length === 6,
  );

  check(
    "schema_awaiting_confirmation_enum_matches_runtime",
    SCHEMA?.properties?.awaiting_confirmation?.properties?.kind?.enum?.length ===
      (AWAITING_CONFIRMATION_KINDS?.length || 0),
  );

  return {
    passed: failures.length === 0,
    checks,
    failures,
  };
}
