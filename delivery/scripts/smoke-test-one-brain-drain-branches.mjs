#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: anchor the live one-brain drain's op-handling branches.
//
// Background:
// The step-2 dead-code sweep deleted `applyResponderStateOps` and its legacy
// `else if (RESPONDER_FIRST_FLAG && ...)` drain branch, leaving the live
// one-brain drain inside `dispatchReplyWithBufferedBlockDispatcher` as the
// ONLY path that processes responder state ops. Because the drain is an
// inline `for (const op of drained) { ... }` block (not an extracted helper),
// it cannot be unit-tested in isolation. This smoke anchors the shape of that
// block so future refactors that accidentally remove or rename a branch fail
// loudly here instead of silently in production.
//
// For each op shape we declare must survive:
//   - apply_booking_field       → replaced `applyBookingFieldCorrection`
//   - carry_over_from_last_order → replaced the legacy branch's handler
//   - cancel_booking             → drives stage reset
//   - request_handoff            → flags handoff to admin
//   - set_requested_slot         → updates DST.requestedSlot
//   - set_pending_area           → persists resolver-confirmed area legs
//   - start_booking              → intentional no-op (log-only)
//   - confirm_summary            → intentional no-op (log-only)
//
// We also anchor that the drain delegates to `applyProposals` with an
// `llmProposal` for apply_booking_field (post step-2/3 refactor: the
// ambiguous-pair guard, coherence gate, and `applyBookingFieldPatch`
// call all now live inside the apply-boundary module — the drain is
// a thin wrapper), and `applyCarryOverOp` for carry_over_from_last_order.
// The apply boundary, in turn, must still route the underlying write
// through `applyBookingFieldPatch` with `dstSource: "llm_apply"` — that
// invariant now lives in `apply-boundary.ts`.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import path from "node:path";

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const indexSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// Anchor each surviving op branch in the live drain.
const requiredBranches = [
  { label: "apply_booking_field", needle: `if (op.op === "apply_booking_field")` },
  {
    label: "carry_over_from_last_order",
    needle: `op.op === "carry_over_from_last_order"`,
  },
  { label: "cancel_booking", needle: `op.op === "cancel_booking"` },
  { label: "request_handoff", needle: `op.op === "request_handoff"` },
  { label: "set_requested_slot", needle: `op.op === "set_requested_slot"` },
  { label: "set_pending_area", needle: `op.op === "set_pending_area"` },
  {
    label: "start_booking / confirm_summary (no-op branch)",
    needle: `op.op === "start_booking" || op.op === "confirm_summary"`,
  },
];

for (const b of requiredBranches) {
  assert(
    indexSrc.includes(b.needle),
    `live one-brain drain must keep ${b.label} branch (needle: ${JSON.stringify(b.needle)})`,
  );
}
console.log(
  `PASS: all ${requiredBranches.length} live-drain op branches present`,
);

// Anchor that apply_booking_field is routed through the apply-boundary
// module (`applyProposals` + `llmProposal`). The channel code must NOT
// call `applyBookingFieldPatch` directly for LLM-emitted ops anymore —
// that write is the boundary's job, not the drain's.
assert(
  indexSrc.includes(`applyProposals(`),
  "live drain must delegate apply_booking_field through applyProposals (apply-boundary)",
);
assert(
  indexSrc.includes(`llmProposal({`) || indexSrc.includes(`llmProposal(`),
  "live drain must wrap LLM ops in llmProposal() before handing them to the boundary",
);
console.log("PASS: apply_booking_field delegates through applyProposals + llmProposal");

// Anchor that carryover still uses the direct primitive (its path is
// intentionally outside the apply boundary for this slice — it has no
// `source_quote` or coherence to validate).
assert(
  indexSrc.includes(`applyCarryOverOp({`),
  "live drain must delegate carry_over_from_last_order to applyCarryOverOp",
);
console.log("PASS: carry_over_from_last_order delegates to applyCarryOverOp");

// Anchor that the apply-boundary module — the single write funnel for
// LLM and fast-path proposals — still routes through applyBookingFieldPatch
// with dstSource: "llm_apply" internally. If this anchor breaks, the LLM
// path has either stopped writing through applyBookingFieldPatch or lost
// its dstSource tag, both of which corrupt slot provenance.
const boundarySrc = fs.readFileSync(
  path.join(root, "plugins/shared/apply-boundary.ts"),
  "utf8",
);
assert(
  boundarySrc.includes(`applyBookingFieldPatch({`) &&
    boundarySrc.includes(`"llm_apply"`),
  "apply-boundary must still route LLM proposals through applyBookingFieldPatch with dstSource: 'llm_apply'",
);
console.log("PASS: apply-boundary routes LLM proposals to applyBookingFieldPatch with llm_apply tag");

// Anchor that the deleted legacy code really is gone (defense-in-depth).
const mustBeGone = [
  { label: "applyResponderStateOps function", needle: "function applyResponderStateOps(" },
  { label: "applyBookingFieldCorrection function", needle: "function applyBookingFieldCorrection(" },
  {
    label: "advanceBookingControllerFromCustomerText function",
    needle: "function advanceBookingControllerFromCustomerText(",
  },
  {
    label: "alignBookingFieldsToCurrentStep function",
    needle: "function alignBookingFieldsToCurrentStep(",
  },
  {
    label: "legacy `else if (RESPONDER_FIRST_FLAG ...)` drain branch",
    needle: "else if (RESPONDER_FIRST_FLAG",
  },
  {
    label: "isOneBrainConversation helper definition",
    needle: "function isOneBrainConversation(",
  },
];

for (const g of mustBeGone) {
  assert(
    !indexSrc.includes(g.needle),
    `${g.label} must stay deleted (step-2 sweep)`,
  );
}
console.log(
  `PASS: all ${mustBeGone.length} deleted legacy symbols stay gone`,
);

// Anchor the `tool_override` SlotSource variant is gone from dialog-state.
const dialogStateSrc = fs.readFileSync(
  path.join(root, "plugins/shared/dialog-state.ts"),
  "utf8",
);
assert(
  !dialogStateSrc.includes(`"tool_override"`),
  "tool_override SlotSource variant must stay removed",
);
console.log("PASS: tool_override SlotSource variant stays removed");

console.log("ALL PASS smoke-test-one-brain-drain-branches.mjs");
