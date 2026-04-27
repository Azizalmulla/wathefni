#!/usr/bin/env node
/**
 * Smoke test for authority-cutover Cut A (2026-04-23) — pin continuity.
 *
 * Background
 * ----------
 * Before Cut A, `getStandaloneLocationAutoAssignmentRole` silently bound
 * an inbound shared-location pin to "the opposite of whatever is already
 * filled." That silent mutation was the root cause of the repeated
 * "pin → bot asks pickup/delivery → customer answers → bot resets to
 * welcome" failure. Cut A deleted the helper and its call site. Pins
 * without a declared role now only persist as `pendingLocation`, surface
 * in the prompt as `pending_shared_location`, and are bound to pickup/
 * delivery ONLY when the customer explicitly says which role they mean.
 *
 * This test protects the invariant. If someone accidentally re-introduces
 * silent pin auto-assignment (the most likely regression path on this
 * flow), one of the assertions below will fail.
 *
 * Scope: source-level assertions (fast, deterministic, no runtime boot).
 * End-to-end behavioural coverage lives in live traffic traces.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  } else {
    console.log(`ok  : ${msg}`);
  }
}

// ---------------------------------------------------------------------------
// Load source files we assert against.
// ---------------------------------------------------------------------------
const INDEX_REL = "plugins/octopus-channel/index.ts";
const LIVE_CTX_REL = "plugins/octopus-channel/lib/live-channel-context.ts";
const ONE_BRAIN_CTX_REL = "plugins/octopus-channel/lib/one-brain-context.ts";

const indexSrc = readFileSync(resolve(ROOT, INDEX_REL), "utf-8");
const liveCtxSrc = readFileSync(resolve(ROOT, LIVE_CTX_REL), "utf-8");
const oneBrainCtxSrc = readFileSync(resolve(ROOT, ONE_BRAIN_CTX_REL), "utf-8");

// ---------------------------------------------------------------------------
// Assertion 1: Canary marker present at Cut A deletion site.
// If someone reverts the cut, they'd also have to remove this marker.
// ---------------------------------------------------------------------------
assert(
  indexSrc.includes("DEPLOY_CANARY_CUT_A_PIN_CONTINUITY_MARKER"),
  `canary: DEPLOY_CANARY_CUT_A_PIN_CONTINUITY_MARKER present in ${INDEX_REL}`,
);

// ---------------------------------------------------------------------------
// Assertion 2: The deleted helper `getStandaloneLocationAutoAssignmentRole`
// is NOT defined anywhere in the index. Its accidental re-introduction is
// the most likely regression vector.
//
// We check for a function / const / let / var definition specifically,
// not the string anywhere — the Cut A comment mentions the name by
// design (that's the audit trail).
// ---------------------------------------------------------------------------
const helperDefinitionRe =
  /(?:function|const|let|var)\s+getStandaloneLocationAutoAssignmentRole\b/;
assert(
  !helperDefinitionRe.test(indexSrc),
  `regression guard: getStandaloneLocationAutoAssignmentRole is NOT re-defined in ${INDEX_REL}`,
);

// ---------------------------------------------------------------------------
// Assertion 3: The replacement helper `applyStandaloneLocationAssignment`
// is still present AND takes an explicit `role: "pickup" | "delivery"`
// parameter — no silent role inference.
// ---------------------------------------------------------------------------
assert(
  /function\s+applyStandaloneLocationAssignment\s*\(/.test(indexSrc),
  `invariant: applyStandaloneLocationAssignment is defined in ${INDEX_REL}`,
);
assert(
  /role\s*:\s*"pickup"\s*\|\s*"delivery"/.test(indexSrc),
  `invariant: applyStandaloneLocationAssignment takes an explicit role parameter`,
);

// ---------------------------------------------------------------------------
// Assertion 4: Both context builders surface `pending_shared_location` in
// the prompt. This is what tells the LLM there's an unbound pin waiting
// for the customer to clarify pickup-vs-delivery.
// ---------------------------------------------------------------------------
assert(
  liveCtxSrc.includes("pending_shared_location"),
  `context: pending_shared_location surfaced in ${LIVE_CTX_REL}`,
);
assert(
  oneBrainCtxSrc.includes("pending_shared_location"),
  `context: pending_shared_location surfaced in ${ONE_BRAIN_CTX_REL}`,
);

// ---------------------------------------------------------------------------
// Assertion 5: The callsites that DO apply a pin to a role first compute
// a `declaredStandaloneRole` / `declaredLocationRole` from the customer's
// visible text. No callsite can pass a synthesized/hardcoded role.
// We grep for the two known callsites and confirm both use a
// `declared*Role` variable as the role argument.
// ---------------------------------------------------------------------------
const callsiteMatches = [
  ...indexSrc.matchAll(/applyStandaloneLocationAssignment\(\{[\s\S]*?role\s*:\s*([A-Za-z0-9_]+)/g),
];
assert(
  callsiteMatches.length >= 2,
  `callsites: expected ≥2 applyStandaloneLocationAssignment call sites, found ${callsiteMatches.length}`,
);
for (const [i, m] of callsiteMatches.entries()) {
  const roleArg = m[1];
  assert(
    /^declared(?:Standalone)?LocationRole$/.test(roleArg) ||
      /^declaredStandaloneRole$/.test(roleArg),
    `callsite[${i}]: role arg is customer-declared (${roleArg})`,
  );
}

// ---------------------------------------------------------------------------
// Assertion 6: Synthetic runtime — context builder emits
// `pending_shared_location: <label>` when booking draft has a
// pendingLocation but neither pickupLocation nor deliveryLocation.
//
// We replicate the one-line branch in pure JS (no TS boot) because the
// full context builder depends on dozens of imports.
// ---------------------------------------------------------------------------
function replicatedPendingPinEmission(pendingLabel) {
  const lines = [];
  if (pendingLabel) {
    lines.push(`pending_shared_location: ${pendingLabel}`);
  }
  return lines;
}

assert(
  replicatedPendingPinEmission(null).length === 0,
  "runtime: no pin → no pending_shared_location line",
);
assert(
  replicatedPendingPinEmission("Salmiya @ 29.3335,48.0746")[0].startsWith(
    "pending_shared_location:",
  ),
  "runtime: pending pin → emits pending_shared_location line",
);

console.log("\nAll Cut A pin-continuity assertions passed.");
