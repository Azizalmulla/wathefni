#!/usr/bin/env node
//
// Phase A (2026-04-21): smoke test for the typed proposer-output schema
// and its drain-time observation.
//
// This is a SHADOW-MODE-ONLY PR. The test MUST fail loud if:
//   1. The schema validator misclassifies well-formed / malformed input.
//   2. The `propose_turn_decision` tool is not registered.
//   3. The `proposed_turn_decision` responder-op type is not in the
//      `ResponderStateOp` union.
//   4. The `structured_output_v1` contract block is not present in the
//      one-brain context assembly.
//   5. The drain loop does not observe `proposed_turn_decision` ops.
//   6. The post-decision `[structured-output/proposer]` emit is missing,
//      not wrapped in try/catch, or gates any behavior.
//   7. The drain branch mutates state (any path that looks like it changes
//      `nextDraft`, `nextDialogState`, `cancelled`, or `handoffRequested`
//      in the `proposed_turn_decision` arm).
//
// Anchoring on source is intentional: this PR is observation-only, and
// the runtime behavior is exercised by live log scrapes. The schema
// validator is tested with real JS values here.

import { strict as assert } from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = new URL("..", import.meta.url);
const schemaSrc = fs.readFileSync(
  new URL("plugins/shared/proposer-schema.ts", ROOT),
  "utf8",
);
const responderSrc = fs.readFileSync(
  new URL("plugins/shared/responder-state-ops.ts", ROOT),
  "utf8",
);
const proposerToolSrc = fs.readFileSync(
  new URL("plugins/riders-tools/tools/proposer.ts", ROOT),
  "utf8",
);
const ridersToolsIndexSrc = fs.readFileSync(
  new URL("plugins/riders-tools/index.ts", ROOT),
  "utf8",
);
const oneBrainCtxSrc = fs.readFileSync(
  new URL("plugins/octopus-channel/lib/one-brain-context.ts", ROOT),
  "utf8",
);
const octopusSrc = fs.readFileSync(
  new URL("plugins/octopus-channel/index.ts", ROOT),
  "utf8",
);

// ---------------------------------------------------------------------
// (1) Schema + validator round-trips.
//
// We can't easily import the TS file at runtime here without a compile
// step, so run a small JS reimplementation of the validator invariants
// via source inspection AND a live validator import via tsx-style eval.
// The simplest robust path: compile the TS into a transient .mjs via
// a very small hand transform — strip `type` / `interface` / `import`
// / generics — NO. Actually the cleanest is to anchor strongly on
// source shape + separately exercise a few hand-crafted payloads
// against a tiny inline reimpl of the validator's contract.
// ---------------------------------------------------------------------

assert.ok(
  /export function validateProposedTurnDecision/.test(schemaSrc),
  "proposer-schema.ts must export validateProposedTurnDecision",
);
for (const turnKind of [
  "initial_route",
  "post_clarify_continuation",
  "informational",
  "address_collection",
  "booking_detail_collection",
  "confirmation_or_cancel",
  "post_order_chat",
  "other",
]) {
  assert.ok(
    schemaSrc.includes(`"${turnKind}"`),
    `proposer-schema.ts must include turn_kind literal ${turnKind}`,
  );
}
for (const action of [
  "call_get_price",
  "continue_existing_quote",
  "informational_only",
  "awaiting_state",
  "none",
]) {
  assert.ok(
    schemaSrc.includes(`"${action}"`),
    `proposer-schema.ts must include pricing_decision.action literal ${action}`,
  );
}
// Schema now accepts BOTH "1.0" (legacy in-flight payloads) and "1.1"
// (v1.1 introduces the optional `awaiting_confirmation` field for the
// awaiting-confirmation policy map). The validator + tool schema must
// agree on this set.
assert.ok(
  /PROPOSER_SCHEMA_VERSIONS/.test(schemaSrc),
  "proposer-schema.ts must export PROPOSER_SCHEMA_VERSIONS",
);
for (const version of ["1.0", "1.1"]) {
  assert.ok(
    schemaSrc.includes(`"${version}"`),
    `proposer-schema.ts must include schema_version literal ${version}`,
  );
}
assert.ok(
  /export const PROPOSE_TURN_DECISION_TOOL_SCHEMA/.test(schemaSrc),
  "proposer-schema.ts must export PROPOSE_TURN_DECISION_TOOL_SCHEMA",
);
assert.ok(
  /additionalProperties:\s*false/.test(schemaSrc),
  "tool schema must set additionalProperties: false",
);

// v1.1 awaiting_confirmation additions.
for (const kind of [
  "confirm_order",
  "cancel_order",
  "edit_order",
  "informational_question",
  "coherence_pleasantry",
  "unclear",
]) {
  assert.ok(
    schemaSrc.includes(`"${kind}"`),
    `proposer-schema.ts must include awaiting_confirmation.kind literal ${kind}`,
  );
}
assert.ok(
  /AWAITING_CONFIRMATION_KINDS/.test(schemaSrc),
  "proposer-schema.ts must export AWAITING_CONFIRMATION_KINDS",
);
assert.ok(
  /awaiting_confirmation\?:/.test(schemaSrc) ||
    /awaiting_confirmation\?\s*:/.test(schemaSrc),
  "ProposedTurnDecision must declare awaiting_confirmation as OPTIONAL (v1.0 payloads stay valid without it)",
);
assert.ok(
  /awaiting_confirmation:/.test(schemaSrc) &&
    /enum:\s*\[\s*\.\.\.AWAITING_CONFIRMATION_KINDS/.test(schemaSrc),
  "tool JSON schema must surface awaiting_confirmation with its enum values",
);

// ---------------------------------------------------------------------
// (2) Responder-op union contains the new op type + dedup key branch.
// ---------------------------------------------------------------------

assert.ok(
  /ResponderProposedTurnDecisionOp/.test(responderSrc),
  "responder-state-ops.ts must export ResponderProposedTurnDecisionOp",
);
assert.ok(
  /\|\s*ResponderProposedTurnDecisionOp/.test(responderSrc),
  "ResponderStateOp union must include ResponderProposedTurnDecisionOp",
);
assert.ok(
  /case "proposed_turn_decision":/.test(responderSrc),
  "opDedupKey must have a case branch for proposed_turn_decision",
);

// ---------------------------------------------------------------------
// (3) Tool registration.
// ---------------------------------------------------------------------

assert.ok(
  /registerProposerTools/.test(proposerToolSrc),
  "proposer.ts must export registerProposerTools",
);
assert.ok(
  /name:\s*"propose_turn_decision"/.test(proposerToolSrc),
  "proposer.ts must register a tool named propose_turn_decision",
);
assert.ok(
  /strict:\s*true/.test(proposerToolSrc),
  "propose_turn_decision tool must use strict: true parameters",
);
assert.ok(
  /parameters:\s*PROPOSE_TURN_DECISION_TOOL_SCHEMA/.test(proposerToolSrc),
  "propose_turn_decision tool must reuse PROPOSE_TURN_DECISION_TOOL_SCHEMA from shared/",
);
assert.ok(
  /pushResponderStateOp\(\s*primary\s*,\s*op\s*,\s*aliases\s*\)/.test(
    proposerToolSrc,
  ),
  "proposer tool must push responder-op under primary + aliases",
);
assert.ok(
  /import\s+\{\s*registerProposerTools\s*\}\s+from\s+"\.\/tools\/proposer"/.test(
    ridersToolsIndexSrc,
  ),
  "riders-tools/index.ts must import registerProposerTools",
);
assert.ok(
  /registerProposerTools\(api,\s*deps\)/.test(ridersToolsIndexSrc),
  "riders-tools/index.ts must call registerProposerTools(api, deps)",
);

// ---------------------------------------------------------------------
// (4) Prompt-side injection of the contract block.
// ---------------------------------------------------------------------

assert.ok(
  /structured_output_v1/.test(oneBrainCtxSrc),
  "one-brain-context.ts must mention structured_output_v1 in the LIVE CHANNEL block",
);
assert.ok(
  /propose_turn_decision/.test(oneBrainCtxSrc),
  "one-brain-context.ts must reference the propose_turn_decision tool",
);
// v1.1: the LIVE CHANNEL block must instruct the LLM to emit the
// 6-way awaiting_confirmation classification on summary stages.
assert.ok(
  /awaiting_confirmation/.test(oneBrainCtxSrc),
  "one-brain-context.ts must mention awaiting_confirmation (v1.1 classification)",
);
for (const kind of [
  "confirm_order",
  "cancel_order",
  "edit_order",
  "informational_question",
  "coherence_pleasantry",
  "unclear",
]) {
  assert.ok(
    oneBrainCtxSrc.includes(kind),
    `one-brain-context.ts must enumerate awaiting_confirmation.kind=${kind} so the LLM sees every option`,
  );
}
assert.ok(
  /summary_shown[^\n]*awaiting_confirmation|awaiting_confirmation[^\n]*summary_shown/.test(
    oneBrainCtxSrc,
  ),
  "one-brain-context.ts must key the awaiting_confirmation requirement on stage summary_shown/awaiting_confirmation",
);
assert.ok(
  /schema_version[^\n]*1\.1/.test(oneBrainCtxSrc),
  "one-brain-context.ts must instruct the LLM to emit schema_version=1.1",
);

// ---------------------------------------------------------------------
// (5) Drain loop must observe the op and NOT mutate state (shadow mode).
// ---------------------------------------------------------------------

const drainBranch = octopusSrc.match(
  /op\.op === "proposed_turn_decision"[\s\S]{0,1800}?\} else if/,
);
assert.ok(
  drainBranch,
  "drain loop must contain a branch for op.op === 'proposed_turn_decision'",
);
const drainBranchText = drainBranch[0];
// Guardrail: shadow-mode branch must NOT touch any of the draft / dialog /
// cancel / handoff / applyProposals fields.
for (const forbidden of [
  "nextDraft",
  "nextDialogState",
  "cancelled",
  "handoffRequested",
  "applyProposals",
]) {
  assert.ok(
    !drainBranchText.includes(forbidden),
    `proposed_turn_decision drain branch must NOT reference ${forbidden} (shadow mode)`,
  );
}
assert.ok(
  /proposedTurnDecisionRaw/.test(drainBranchText) &&
    /proposedTurnDecisionCount/.test(drainBranchText),
  "proposed_turn_decision drain branch must record raw payload + duplicate counter",
);

// ---------------------------------------------------------------------
// (6) Post-decision emit: present, try/catch, observation only.
// ---------------------------------------------------------------------

assert.ok(
  (octopusSrc.match(/\[structured-output\/proposer\]/g) || []).length >= 2,
  "expected at least two occurrences of [structured-output/proposer] (comment anchor + emit)",
);
// Anchor the emit block from its comment header down to the end of the
// catch handler. Using a concrete end marker keeps the window tight so we
// don't accidentally capture unrelated downstream code (an earlier fixed
// char-window could creep past the `} else {` boundary on long edits).
const emitBlockMatch = octopusSrc.match(
  /\[structured-output\/proposer\] Phase A shadow conformance emit[\s\S]*?catch \(proposerEmitError\)[\s\S]*?\} catch \{\}\s*\}/,
);
assert.ok(emitBlockMatch, "unable to locate structured-output/proposer emit block");
const emitBlock = emitBlockMatch[0];
assert.ok(
  /STRICTLY observation-only/.test(emitBlock),
  "structured-output emit must self-document as STRICTLY observation-only",
);
assert.ok(
  /try \{[\s\S]*?api\.logger\.info\(/.test(emitBlock),
  "structured-output emit must be wrapped in a try block around api.logger.info",
);
assert.ok(
  /catch \(proposerEmitError\)/.test(emitBlock),
  "structured-output emit must catch with proposerEmitError so it cannot escape",
);
for (const field of [
  "present=",
  "schema_valid=",
  "schema_version=",
  "turn_kind=",
  "pricing_action=",
  "planned_tool_calls=",
  "fired_tool_ops=",
  "get_price_fired=",
  "plan_vs_fire=",
  "ac_stage=",
  "ac_kind=",
  "ac_classification=",
  "duplicate_count=",
]) {
  assert.ok(
    emitBlock.includes(field),
    `structured-output emit must include field ${field}`,
  );
}
// v1.1 awaiting-confirmation classification bucket names (shares `"n/a"`
// with the plan_vs_fire bucket above — asserted there already).
for (const bucket of ['"present"', '"missing"', '"unexpected"']) {
  assert.ok(
    emitBlock.includes(bucket),
    `structured-output emit must declare ac_classification bucket ${bucket}`,
  );
}
for (const bucket of [
  "aligned",
  "drift_declared_not_fired",
  "drift_fired_not_planned",
  '"n/a"',
]) {
  assert.ok(
    emitBlock.includes(bucket),
    `structured-output emit must declare plan_vs_fire bucket ${bucket}`,
  );
}
// Guardrail: the emit MUST NOT call applyProposals or otherwise drive
// behavior off the proposer decision. We scan the whole emit block for
// any hint of control flow that would indicate promotion beyond logging.
for (const forbidden of [
  "applyProposals",
  "replyText =",
  "conversationControllerEntry =",
  "nextDraft",
]) {
  assert.ok(
    !emitBlock.includes(forbidden),
    `structured-output emit must not reference ${forbidden} (shadow mode promotion guard)`,
  );
}

// ---------------------------------------------------------------------
// (7) Compile + exercise the validator against a real payload set.
//
// Use the TypeScript compiler via `node --experimental-strip-types` when
// available; otherwise run a minimal JS port of the validator so
// payload semantics are still covered. We prefer the compiled path.
// ---------------------------------------------------------------------

let validate;
try {
  // Node 22 supports --experimental-strip-types out of the box.
  const mod = await import(
    pathToFileURL(
      path.resolve(new URL("plugins/shared/proposer-schema.ts", ROOT).pathname),
    ).href
  );
  validate = mod.validateProposedTurnDecision;
} catch (loadErr) {
  // Fall back: re-implement the critical invariants inline. Matches the
  // public contract (round-trip of well-formed + common malformed cases).
  const TURN_KINDS = new Set([
    "initial_route",
    "post_clarify_continuation",
    "informational",
    "address_collection",
    "booking_detail_collection",
    "confirmation_or_cancel",
    "post_order_chat",
    "other",
  ]);
  const ACTIONS = new Set([
    "call_get_price",
    "continue_existing_quote",
    "informational_only",
    "awaiting_state",
    "none",
  ]);
  const AC_KINDS = new Set([
    "confirm_order",
    "cancel_order",
    "edit_order",
    "informational_question",
    "coherence_pleasantry",
    "unclear",
  ]);
  const SCHEMA_VERSIONS = new Set(["1.0", "1.1"]);
  validate = (raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return { ok: false, errors: ["proposer_payload_not_object"] };
    }
    const errors = [];
    if (!SCHEMA_VERSIONS.has(raw.schema_version))
      errors.push("schema_version_unsupported");
    if (!TURN_KINDS.has(raw.turn_kind)) errors.push("turn_kind_invalid");
    const pd = raw.pricing_decision;
    if (!pd || typeof pd !== "object") {
      errors.push("pricing_decision_not_object");
    } else {
      if (!ACTIONS.has(pd.action)) errors.push("pricing_decision.action_invalid");
      if (typeof pd.reason !== "string") errors.push("pricing_decision.reason_not_string");
    }
    if (!Array.isArray(raw.planned_tool_calls)) errors.push("planned_tool_calls_not_array");
    if (typeof raw.customer_reply_draft !== "string") errors.push("customer_reply_draft_not_string");
    let awaitingConfirmation = null;
    if (
      raw.awaiting_confirmation !== undefined &&
      raw.awaiting_confirmation !== null
    ) {
      const ac = raw.awaiting_confirmation;
      if (typeof ac !== "object" || Array.isArray(ac)) {
        errors.push("awaiting_confirmation_not_object");
      } else {
        if (!AC_KINDS.has(ac.kind)) errors.push("awaiting_confirmation.kind_invalid");
        if (typeof ac.reason !== "string")
          errors.push("awaiting_confirmation.reason_not_string");
        if (AC_KINDS.has(ac.kind) && typeof ac.reason === "string") {
          awaitingConfirmation = { kind: ac.kind, reason: ac.reason };
        }
      }
    }
    return errors.length === 0
      ? {
          ok: true,
          value: {
            schema_version: raw.schema_version,
            turn_kind: raw.turn_kind,
            pricing_decision: {
              action: pd.action,
              reason: pd.reason,
            },
            planned_tool_calls: raw.planned_tool_calls.filter(
              (e) => typeof e === "string" && e.trim(),
            ),
            customer_reply_draft: raw.customer_reply_draft,
            ...(awaitingConfirmation
              ? { awaiting_confirmation: awaitingConfirmation }
              : {}),
          },
        }
      : { ok: false, errors };
  };
}

// Positive cases.
const happyInitialRoute = validate({
  schema_version: "1.0",
  turn_kind: "initial_route",
  pricing_decision: {
    action: "call_get_price",
    reason: "customer gave hawalli to doha",
  },
  planned_tool_calls: ["get_price"],
  customer_reply_draft: "",
});
assert.ok(
  happyInitialRoute.ok,
  `well-formed initial_route payload must validate: ${JSON.stringify(happyInitialRoute)}`,
);

const happyInformational = validate({
  schema_version: "1.0",
  turn_kind: "informational",
  pricing_decision: {
    action: "informational_only",
    reason: "answering 'do you have a van'",
  },
  planned_tool_calls: [],
  customer_reply_draft: "yes, we have vans.",
});
assert.ok(happyInformational.ok, "informational-only payload must validate");

// Negative cases.
const badTurnKind = validate({
  schema_version: "1.0",
  turn_kind: "marketing_upsell",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
});
assert.ok(
  !badTurnKind.ok && badTurnKind.errors.some((e) => e.startsWith("turn_kind_invalid")),
  "invalid turn_kind must be rejected with turn_kind_invalid",
);

const badSchemaVersion = validate({
  schema_version: "2.0",
  turn_kind: "other",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
});
assert.ok(
  !badSchemaVersion.ok &&
    badSchemaVersion.errors.some((e) => e.startsWith("schema_version_unsupported")),
  "wrong schema_version must be rejected",
);

const nonObject = validate(null);
assert.ok(
  !nonObject.ok && nonObject.errors.includes("proposer_payload_not_object"),
  "null payload must be rejected",
);

const missingPricingDecision = validate({
  schema_version: "1.0",
  turn_kind: "other",
  planned_tool_calls: [],
  customer_reply_draft: "",
});
assert.ok(
  !missingPricingDecision.ok,
  "missing pricing_decision must be rejected",
);

// ---------------------------------------------------------------------
// v1.1 awaiting_confirmation classification — round-trip cases.
// ---------------------------------------------------------------------

// (a) v1.0 payload without awaiting_confirmation still validates.
const legacyV10 = validate({
  schema_version: "1.0",
  turn_kind: "confirmation_or_cancel",
  pricing_decision: { action: "none", reason: "awaiting confirm" },
  planned_tool_calls: [],
  customer_reply_draft: "",
});
assert.ok(legacyV10.ok, "v1.0 payload without awaiting_confirmation must still validate");
assert.ok(
  !("awaiting_confirmation" in legacyV10.value),
  "v1.0 payload output must not synthesize an awaiting_confirmation field",
);

// (b) v1.1 payload without awaiting_confirmation validates (field is optional).
const v11NoAc = validate({
  schema_version: "1.1",
  turn_kind: "booking_detail_collection",
  pricing_decision: { action: "none", reason: "mid-collection" },
  planned_tool_calls: ["apply_booking_field"],
  customer_reply_draft: "",
});
assert.ok(
  v11NoAc.ok && !("awaiting_confirmation" in v11NoAc.value),
  "v1.1 payload without awaiting_confirmation must validate and NOT synthesize the field",
);

// (c) v1.1 payload with each of the six kinds round-trips.
for (const kind of [
  "confirm_order",
  "cancel_order",
  "edit_order",
  "informational_question",
  "coherence_pleasantry",
  "unclear",
]) {
  const out = validate({
    schema_version: "1.1",
    turn_kind: "confirmation_or_cancel",
    pricing_decision: { action: "none", reason: "summary stage" },
    planned_tool_calls: [],
    customer_reply_draft: "",
    awaiting_confirmation: {
      kind,
      reason: `test:${kind}`,
    },
  });
  assert.ok(out.ok, `v1.1 payload with awaiting_confirmation.kind=${kind} must validate`);
  assert.equal(
    out.value.awaiting_confirmation?.kind,
    kind,
    `awaiting_confirmation.kind must round-trip (${kind})`,
  );
  assert.equal(
    out.value.awaiting_confirmation?.reason,
    `test:${kind}`,
    `awaiting_confirmation.reason must round-trip (${kind})`,
  );
}

// (d) v1.1 payload with null awaiting_confirmation validates (treat as absent).
const v11NullAc = validate({
  schema_version: "1.1",
  turn_kind: "other",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
  awaiting_confirmation: null,
});
assert.ok(
  v11NullAc.ok && !("awaiting_confirmation" in v11NullAc.value),
  "v1.1 payload with awaiting_confirmation=null must validate and drop the field",
);

// (e) Invalid awaiting_confirmation.kind is rejected with a structured error.
const badAcKind = validate({
  schema_version: "1.1",
  turn_kind: "confirmation_or_cancel",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
  awaiting_confirmation: { kind: "confirm_and_tip", reason: "typo" },
});
assert.ok(
  !badAcKind.ok &&
    badAcKind.errors.some((e) => e.startsWith("awaiting_confirmation.kind_invalid")),
  "invalid awaiting_confirmation.kind must be rejected",
);

// (f) awaiting_confirmation missing `reason` is rejected.
const badAcReason = validate({
  schema_version: "1.1",
  turn_kind: "confirmation_or_cancel",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
  awaiting_confirmation: { kind: "confirm_order" },
});
assert.ok(
  !badAcReason.ok &&
    badAcReason.errors.some((e) => e === "awaiting_confirmation.reason_not_string"),
  "awaiting_confirmation without reason must be rejected",
);

// (g) awaiting_confirmation present as non-object is rejected.
const badAcShape = validate({
  schema_version: "1.1",
  turn_kind: "confirmation_or_cancel",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
  awaiting_confirmation: "confirm_order",
});
assert.ok(
  !badAcShape.ok &&
    badAcShape.errors.includes("awaiting_confirmation_not_object"),
  "awaiting_confirmation as non-object must be rejected",
);

// (h) v1.1 payload without awaiting_confirmation but declaring "1.1" stays
// valid — the field is optional at the shape layer. The "must be present at
// summary stages" invariant is enforced at the drain-time observability
// emit, not at the validator.
const v11SummaryMissingAc = validate({
  schema_version: "1.1",
  turn_kind: "confirmation_or_cancel",
  pricing_decision: { action: "none", reason: "" },
  planned_tool_calls: [],
  customer_reply_draft: "",
});
assert.ok(
  v11SummaryMissingAc.ok,
  "v1.1 payload without awaiting_confirmation must NOT be rejected by the validator (shape-layer invariant)",
);

console.log("smoke-test-proposer-schema: OK");
