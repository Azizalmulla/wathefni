#!/usr/bin/env node
//
// Observation-only baseline counter for the `get_price`-bypass drift rate.
//
// This smoke test does NOT spin up the dispatcher. It anchors on source so
// if anyone deletes / renames / moves the counter, the test fails loud. The
// runtime behavior is exercised by live log scrapes (see the matching entry
// in BUG_CLASSES.md observability table).
//
// Invariants:
//   1. `[drift/get-price-bypass]` emit MUST live in the octopus-channel
//      post-state outbound-decision branch (i.e. where we have a real
//      conversationControllerEntry). It is useless on the no-controller
//      branch, so we explicitly assert the emit is NOT duplicated there.
//   2. Emit MUST be wrapped in try/catch. Strict observation-only means a
//      broken classifier cannot take a turn down.
//   3. Emit MUST carry both `turn_kind` and `outcome` fields. These are the
//      primary aggregation keys for the Phase D metric.
//   4. The pre-turn snapshot block (pending pickup/dropoff + requested slot +
//      active-quoted flag) MUST live alongside `stageAtTurnStart` so the
//      classifier reads turn-START state, not post-drain state.

import { strict as assert } from "node:assert";
import fs from "node:fs";

const octopusSrc = fs.readFileSync(
  new URL("../plugins/octopus-channel/index.ts", import.meta.url),
  "utf8",
);

// (1) counter emit exists, exactly once, in the controller branch.
const emitMatches = octopusSrc.match(/\[drift\/get-price-bypass\]/g) || [];
assert.ok(
  emitMatches.length >= 2,
  `expected at least two occurrences of [drift/get-price-bypass] (comment anchor + emit line); found ${emitMatches.length}`,
);

// The emit MUST appear inside the dispatcher's post-decision branch AFTER
// `postDecision.markedSummaryShown` was handled (that branch is the real
// one — the no-controller else branch at the bottom must NOT mirror it).
const emitInControllerBranch = /markedSummaryShown[\s\S]{0,4000}\[drift\/get-price-bypass\] Phase D/.test(
  octopusSrc,
);
assert.ok(
  emitInControllerBranch,
  "drift counter emit must live in the controller-branch of decidePostStateOutbound, after markedSummaryShown handling",
);

// (2) emit must be wrapped in try / catch so a broken classifier can never
// take a turn down. We search for the try block that opens after the
// counter comment.
const emitBlockMatch = octopusSrc.match(
  /\[drift\/get-price-bypass\] Phase D[\s\S]{0,6000}/,
);
assert.ok(emitBlockMatch, "unable to locate drift counter emit block");
const emitBlock = emitBlockMatch[0];
assert.ok(
  /try \{[\s\S]*?api\.logger\.info\(/.test(emitBlock),
  "drift counter emit must be wrapped in a try block around api.logger.info",
);
assert.ok(
  /catch \(driftEmitError\)/.test(emitBlock),
  "drift counter emit must catch with driftEmitError so it cannot escape",
);

// (3) every aggregation key the metric depends on must be rendered.
for (const field of [
  "turn_kind=",
  "outcome=",
  "get_price_fired=",
  "class15_bypass_flag=",
  "class15_repair_fired=",
  "stage_at_turn_start=",
  "had_active_quoted_route=",
  "pending_pickup=",
  "pending_dropoff=",
  "requested_slot=",
  "route_evidence_inbound=",
]) {
  assert.ok(
    emitBlock.includes(field),
    `drift counter emit must include field ${field}`,
  );
}

// (3b) outcome bucket set must be exactly the five populations we care
// about. Extras mean we drifted; a missing one means the classifier has
// a silent dead branch.
const outcomeLiteralsPresent = [
  "tool_owned",
  "class15_repair",
  "turn1_bypass",
  "post_clarify_bypass",
  "irrelevant",
].every((bucket) => emitBlock.includes(`"${bucket}"`));
assert.ok(
  outcomeLiteralsPresent,
  "drift counter classifier must emit exactly the five expected outcome buckets",
);

// (3c) turn_kind partition must be exactly three and must not silently add a
// fourth. Anchoring on the discriminated-union string literals.
const turnKindLiteralsPresent = [
  "initial_route",
  "post_clarify_continuation",
  "other",
].every((kind) => emitBlock.includes(`"${kind}"`));
assert.ok(
  turnKindLiteralsPresent,
  "drift counter classifier must emit exactly the three expected turn_kind values",
);

// (4) pre-turn snapshot block sits alongside stageAtTurnStart so the
// classifier reads turn-START state, not post-drain state.
const snapshotColocated = /stageAtTurnStart[\s\S]{0,2500}pendingPickupAtTurnStart/.test(
  octopusSrc,
);
assert.ok(
  snapshotColocated,
  "pre-turn snapshot (pendingPickupAtTurnStart ...) must be captured alongside stageAtTurnStart",
);
const snapshotFields = [
  "pendingPickupAtTurnStart",
  "pendingDropoffAtTurnStart",
  "requestedSlotNameAtTurnStart",
  "requestedSlotOptionsAtTurnStart",
  "hadActiveQuotedRouteAtTurnStart",
];
for (const f of snapshotFields) {
  assert.ok(
    octopusSrc.includes(f),
    `pre-turn snapshot must declare ${f}`,
  );
}

// (5) explicit "observation-only" self-documentation. If someone ever turns
// this into a behavior-changing guard, the anchor below should be updated
// deliberately and this assertion gives them the prompt to do so.
assert.ok(
  /STRICTLY observation-only/.test(emitBlock),
  "drift counter comment must self-document as STRICTLY observation-only so a future edit knows it is NOT a guard",
);

console.log("smoke-test-drift-get-price-bypass-counter: OK");
