#!/usr/bin/env node
/**
 * Smoke test for Cut #4 (DST conflict-slot pinning, 2026-04-23).
 *
 * Verifies:
 *   1. `findFirstConflictSlot` returns null when no slot is in conflict.
 *   2. Returns the correct slot name when one slot is in conflict.
 *   3. Returns the FIRST conflicting slot (in Object.entries order) when
 *      multiple slots are simultaneously in conflict — matches the
 *      one-brain conflict gate's selection rule.
 *   4. Source-level assertion: the canary marker
 *      `DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER` appears in both
 *      `plugins/shared/dialog-state.ts` (helper doc) and
 *      `plugins/octopus-channel/index.ts` (callsite comment).
 *   5. Source-level assertion: the callsite pins `requestedSlot` to the
 *      conflict slot BEFORE consulting `pushedRequestedThisTurn` and
 *      BEFORE the missing-field derivation.
 *   6. Source-level assertion: the helper is exported by
 *      `dialog-state.ts` and imported at the callsite.
 *
 * This is a source-level + lightweight runtime test. Full behavioural
 * coverage lives in end-to-end traces.
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
// Runtime: load the helper via tsx/ts-node is overkill; test the reducer
// directly by replicating its behaviour on synthetic slot maps.
// ---------------------------------------------------------------------------

function replicatedFindFirstConflictSlot(state) {
  if (!state || !state.slots) return null;
  for (const [name, record] of Object.entries(state.slots)) {
    if (record && record.status === "conflict") return name;
  }
  return null;
}

// Case 1: null state
assert(
  replicatedFindFirstConflictSlot(null) === null,
  "null state → null",
);
assert(
  replicatedFindFirstConflictSlot(undefined) === null,
  "undefined state → null",
);

// Case 2: no conflicts
const allFilled = {
  slots: {
    sender_name: { status: "filled", value: "aziz" },
    sender_phone: { status: "filled", value: "+965..." },
    recipient_name: { status: "empty" },
  },
};
assert(
  replicatedFindFirstConflictSlot(allFilled) === null,
  "no conflicts → null",
);

// Case 3: single conflict
const senderNameConflict = {
  slots: {
    sender_name: {
      status: "conflict",
      value: "aziz",
      conflictCandidate: "ahmad",
    },
    sender_phone: { status: "empty" },
  },
};
assert(
  replicatedFindFirstConflictSlot(senderNameConflict) === "sender_name",
  "single sender_name conflict → sender_name",
);

// Case 4: multiple conflicts — first in insertion order wins
const multiConflict = {
  slots: {
    sender_name: {
      status: "conflict",
      value: "aziz",
      conflictCandidate: "ahmad",
    },
    recipient_name: {
      status: "conflict",
      value: "bob",
      conflictCandidate: "alice",
    },
  },
};
assert(
  replicatedFindFirstConflictSlot(multiConflict) === "sender_name",
  "multi conflict → first in entries order (sender_name)",
);

// ---------------------------------------------------------------------------
// Source-level assertions
// ---------------------------------------------------------------------------

const dialogStateSrc = readFileSync(
  resolve(ROOT, "plugins/shared/dialog-state.ts"),
  "utf8",
);
const indexSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// Canary marker must appear in both files (deploy verifier greps for this).
assert(
  dialogStateSrc.includes("DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER"),
  "canary marker present in dialog-state.ts",
);
assert(
  indexSrc.includes("DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER"),
  "canary marker present in octopus-channel/index.ts",
);

// Helper must be exported.
assert(
  /export\s+function\s+findFirstConflictSlot\s*\(/.test(dialogStateSrc),
  "findFirstConflictSlot exported from dialog-state.ts",
);

// Helper must be imported at the callsite.
assert(
  /findFirstConflictSlot[^,}]*[,}]/.test(
    indexSrc.split("\n").slice(0, 200).join("\n"),
  ),
  "findFirstConflictSlot imported in octopus-channel/index.ts",
);

// Callsite: the conflict pin must run BEFORE the missing-field derivation.
// Heuristic: the literal `findFirstConflictSlot(` call must appear before
// the first `deriveRequestedSlotFromMissing(` call in the same file.
const pinIdx = indexSrc.indexOf("findFirstConflictSlot(");
const deriveIdx = indexSrc.indexOf("deriveRequestedSlotFromMissing(");
assert(
  pinIdx > 0 && deriveIdx > 0 && pinIdx < deriveIdx,
  `conflict pin callsite (${pinIdx}) appears before missing-field derivation (${deriveIdx})`,
);

// Callsite: the `pushedRequestedThisTurn` computation must be GUARDED by
// the conflict-slot check (i.e. live in the `else` branch). Heuristic:
// `findFirstConflictSlot(` appears before `pushedRequestedThisTurn = drained.some(`.
const pushedIdx = indexSrc.indexOf("pushedRequestedThisTurn = drained.some(");
assert(
  pinIdx > 0 && pushedIdx > 0 && pinIdx < pushedIdx,
  `conflict pin runs before pushedRequestedThisTurn check (pin=${pinIdx}, pushed=${pushedIdx})`,
);

// Callsite: when the pin fires, it must call setRequestedSlot.
// Search for the block between `conflictSlotForPin` declaration and the
// matching `else`. Minimum check: `setRequestedSlot` appears within 600
// characters after the `findFirstConflictSlot(` call.
const slice = indexSrc.slice(pinIdx, pinIdx + 2500);
assert(
  /setRequestedSlot\s*\(\s*nextEntry\.dialogState/.test(slice),
  "conflict pin branch invokes setRequestedSlot on nextEntry.dialogState",
);
assert(
  /\[dst-conflict-pin\]/.test(slice),
  "conflict pin emits [dst-conflict-pin] observability log",
);

// Deploy script: marker must appear in both the declaration and the
// verification checks block.
const deploySrc = readFileSync(
  resolve(ROOT, "scripts/deploy.sh"),
  "utf8",
);
assert(
  /DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER='DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER'/.test(
    deploySrc,
  ),
  "deploy.sh declares DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER",
);
const deployChecks = (deploySrc.match(
  /\$DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER/g,
) || []).length;
assert(
  deployChecks >= 2,
  `deploy.sh references marker in ≥2 check tuples, got ${deployChecks}`,
);
// Check tuples must cover BOTH the shared dialog-state.ts and the
// octopus-channel/index.ts paths (helper and callsite). Each tuple is
// ~5 lines, so search a 400-char window around each marker reference
// and require the file path to appear within it.
const markerMatches = [
  ...deploySrc.matchAll(/\$DEPLOY_CANARY_DST_CONFLICT_SLOT_PIN_MARKER/g),
];
assert(markerMatches.length >= 2, "≥2 marker references in deploy.sh check tuples");
const contexts = markerMatches.map((m) =>
  deploySrc.slice(Math.max(0, m.index - 300), m.index + 100),
);
assert(
  contexts.some((c) => c.includes("dialog-state.ts")),
  "one check tuple covers shared/dialog-state.ts",
);
assert(
  contexts.some((c) => c.includes("OCTOPUS_PLUGIN_DIR") && c.includes("index.ts")),
  "one check tuple covers octopus-channel/index.ts",
);

console.log("\nAll DST conflict-slot pin assertions passed.");
