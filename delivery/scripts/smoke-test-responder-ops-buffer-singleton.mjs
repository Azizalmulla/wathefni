#!/usr/bin/env node
// smoke-test-responder-ops-buffer-singleton.mjs
//
// Regression test for class 10:
// `module_instance_isolation_drops_responder_ops`.
//
// Failure mode it prevents: the pricing tool (loaded under one plugin bundle)
// pushes `set_pending_area` / `set_requested_slot` ops into the responder-op
// buffer, but the Octopus drain (loaded under a different plugin bundle)
// sees an empty buffer because its copy of the module state is distinct.
// Every cross-plugin responder op silently vanishes, clarification turns
// never commit durable state, and the next turn falls through to recovery
// or symmetric rebind.
//
// Invariant: a push to the responder-op buffer must be visible to a
// subsequent drain in the SAME process, regardless of how many times the
// source module is imported. The fix pins the backing Map on `globalThis`
// so even split module instances share one buffer.
//
// This test enforces the invariant at the source level (the globalThis
// wrapper must be present) AND at the runtime level (pushing through one
// import + draining through another must roundtrip).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const OPS_PATH = join(ROOT, "plugins/shared/responder-state-ops.ts");
const source = readFileSync(OPS_PATH, "utf8");

// --- Source-level invariants ------------------------------------------------

// G1: globalThis-keyed buffer singleton exists.
assert.match(
  source,
  /__RESPONDER_OPS_BUFFER_KEY[\s\S]{0,400}globalThis as any\)\[__RESPONDER_OPS_BUFFER_KEY\]/,
  "G1: backing Map must be pinned on globalThis via a named key (see class-10 comment).",
);

// G2: a plain `new Map()` module-level declaration MUST NOT reappear. This
// would silently undo the fix and re-introduce the per-bundle isolation.
assert.ok(
  !/^const buffer = new Map<string, ResponderStateOp\[\]>\(\);$/m.test(source),
  "G2: buffer must not be declared as a plain per-module `new Map()` (class-10 regression).",
);

// G3: push/drain both emit observability lines so cross-plugin divergence
// is visible in production logs if it ever resurfaces.
assert.match(
  source,
  /\[responder-ops\/buffer-push\]/,
  "G3: pushResponderStateOp must log `[responder-ops/buffer-push]`.",
);
assert.match(
  source,
  /\[responder-ops\/buffer-drain\]/,
  "G3: drainResponderStateOps must log `[responder-ops/buffer-drain]`.",
);

// --- Runtime invariant: two dynamic imports share one buffer ---------------

// Simulate the cross-bundle shape by dynamically importing the module twice
// with different URL query strings. Under Node ESM, this produces TWO
// separate module instances (different cache keys). The globalThis pin must
// keep push/drain on the same Map anyway.
const aMod = await import(`../plugins/shared/responder-state-ops.ts?bundleA`);
const bMod = await import(`../plugins/shared/responder-state-ops.ts?bundleB`);

// Sanity check that the two imports are distinct module instances (if Node
// happens to dedup them, that's fine — the invariant still holds trivially).
const distinctInstances = aMod !== bMod;

const primary = "conv-smoke-class10";
const op = {
  op: "set_pending_area",
  field: "pickup_area",
  area_name_en: "Salmiya",
  area_name_ar: "السالمية",
  turn_id: "t-class10",
};

aMod.pushResponderStateOp(primary, op, ["alias-a"]);
const drained = bMod.drainResponderStateOps(primary, ["alias-a"]);

assert.equal(
  drained.length,
  1,
  `R1: push via bundle A must be visible to drain via bundle B (distinct_module_instances=${distinctInstances}, drained=${drained.length}).`,
);
assert.equal(drained[0].op, "set_pending_area", "R2: drained op shape preserved across bundles.");

// Second drain must be empty (buffer cleared).
const drainedAgain = bMod.drainResponderStateOps(primary, ["alias-a"]);
assert.equal(drainedAgain.length, 0, "R3: buffer must clear after drain.");

console.log("[smoke] responder-ops buffer singleton: OK (G1..G3, R1..R3)");
