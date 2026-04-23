#!/usr/bin/env node
/**
 * Smoke test for Cut #5 (Turn-disposition AUTHORING gate, 2026-04-23).
 *
 * This is the Reloc 5 inversion: `decideTurnDisposition` runs live BEFORE
 * the state-machine directive is consumed. When the layer classifies the
 * turn as anything other than `continue_step`, the state-machine directive
 * is NOT assigned to `directiveActionForRender` — the LLM's draft
 * survives through Region A.
 *
 * Verifies (source-level):
 *   1. Both canary markers are present in octopus-channel/index.ts:
 *      - `DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER`
 *      - `DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER`
 *   2. `decideTurnDisposition` is imported from `../shared/turn-disposition`
 *      (the direct path; it is not re-exported by `turn-decision.ts`).
 *   3. Type `TurnDispositionDecision` is imported (the local binding used
 *      to annotate `authoringDisposition`).
 *   4. The authoring-gate block runs BETWEEN `computeOneBrainNextRequiredAction`
 *      and `if (directive && directiveHasServerRenderer(...))`. The
 *      ordering matters: disposition must be derived AFTER the state
 *      machine produced its candidate directive (so the trace emits
 *      `legacy_would_have=`) and BEFORE the registry dispatch gate (so
 *      the gate can read `stateMachineAuthoringSkipped`).
 *   5. Env flag `RIDERS_TURN_DISPOSITION_AUTHOR_LIVE` is wired with
 *      default "on", explicit "off" rollback (the repo convention).
 *   6. The gate condition on the `if (!customerConfirmedOrder && ...)`
 *      site now includes `&& !stateMachineAuthoringSkipped`.
 *   7. The else-branch `skipReason` derivation includes the
 *      `skipped_on_disposition_<kind>` reason token, and puts it FIRST
 *      (so a meaning-driven skip is reported even when legacy gates
 *      would also fire).
 *   8. The `[turn-disposition/authoring]` trace line carries all four
 *      tokens the user asked for:
 *        - `disposition=`
 *        - `sm_skipped=`
 *        - `prompt_skipped=`
 *        - `legacy_would_have=`
 *      plus the supporting context (`policy_rule=`, `ti_kind=`,
 *      `ti_confidence=`, `ac_kind=`, `turn_kind=`, `stage=`,
 *      `fallthrough=`).
 *   9. Deploy.sh declares both markers and references each in ≥1 check
 *      tuple pointing at octopus-channel/index.ts.
 *
 * Runtime-level verification of `decideTurnDisposition` classification
 * behaviour lives in `plugins/shared/turn-disposition.ts`'s own unit
 * tests — this smoke test covers the CALLSITE wiring only, which is
 * the part that can silently fall out of a future refactor without any
 * type-error signal.
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
// Source-level assertions on octopus-channel/index.ts
// ---------------------------------------------------------------------------

const indexSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// 1. Both canary markers present.
assert(
  indexSrc.includes("DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER"),
  "import marker present in octopus-channel/index.ts",
);
assert(
  indexSrc.includes("DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER"),
  "callsite marker present in octopus-channel/index.ts",
);

// 2. decideTurnDisposition imported from ../shared/turn-disposition.
assert(
  /import\s*\{\s*decideTurnDisposition\s*\}\s*from\s*["']\.\.\/shared\/turn-disposition["']/.test(
    indexSrc,
  ),
  "decideTurnDisposition imported from ../shared/turn-disposition",
);

// 3. TurnDispositionDecision type imported.
assert(
  /import\s+type\s*\{\s*TurnDispositionDecision\s*\}\s*from\s*["']\.\.\/shared\/turn-disposition["']/.test(
    indexSrc,
  ),
  "TurnDispositionDecision type imported",
);

// 4. Authoring-gate block ordering: after computeOneBrainNextRequiredAction,
//    before the `if (directive && directiveHasServerRenderer(...))` block.
const computeDirectiveIdx = indexSrc.indexOf(
  "const directive = computeOneBrainNextRequiredAction(",
);
const authoringGateMarkerIdx = indexSrc.indexOf(
  "DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER",
);
const directiveRenderIfIdx = indexSrc.indexOf(
  "if (directive && directiveHasServerRenderer(directive.action)) {",
);
assert(
  computeDirectiveIdx > 0,
  `computeOneBrainNextRequiredAction call found (${computeDirectiveIdx})`,
);
assert(
  authoringGateMarkerIdx > computeDirectiveIdx,
  `authoring-gate block runs AFTER directive computation (marker=${authoringGateMarkerIdx}, compute=${computeDirectiveIdx})`,
);
assert(
  directiveRenderIfIdx > authoringGateMarkerIdx,
  `authoring-gate block runs BEFORE registry dispatch (marker=${authoringGateMarkerIdx}, if=${directiveRenderIfIdx})`,
);

// 5. Authority cutover phase 5 (2026-04-23): the
//    `RIDERS_TURN_DISPOSITION_AUTHOR_LIVE` env flag is gone — the gate
//    is baked on. Assert the env read no longer exists.
assert(
  !/RIDERS_TURN_DISPOSITION_AUTHOR_LIVE/.test(indexSrc),
  "RIDERS_TURN_DISPOSITION_AUTHOR_LIVE env read removed (baked on)",
);

// 6. Gate condition on the directive assignment includes the new flag.
assert(
  /!customerConfirmedOrder\s*&&\s*\n?\s*!customerAskingInformational\s*&&\s*\n?\s*!stateMachineAuthoringSkipped/s.test(
    indexSrc,
  ),
  "directive-assignment gate includes !stateMachineAuthoringSkipped",
);

// 7. skipReason includes `skipped_on_disposition_<kind>` and puts it FIRST
//    (i.e. before the two legacy word-list reasons).
assert(
  /stateMachineAuthoringSkipped\s*\?\s*`skipped_on_disposition_/.test(
    indexSrc,
  ),
  "skipReason dispatches `skipped_on_disposition_<kind>` when the authoring gate fires",
);
// Ordering inside the ternary expression (not the surrounding comment):
// the disposition branch is the FIRST condition so a meaning-driven skip
// is reported even when the legacy word-list gates would also fire.
// Anchor on the `const skipReason = stateMachineAuthoringSkipped` token
// so we scope to the executable region, not doc references.
const ternaryStart = indexSrc.indexOf(
  "const skipReason = stateMachineAuthoringSkipped",
);
assert(ternaryStart > 0, "skipReason ternary expression found");
const ternaryWindow = indexSrc.slice(ternaryStart, ternaryStart + 400);
const ternaryDispositionIdx = ternaryWindow.indexOf(
  "`skipped_on_disposition_",
);
const ternaryInformationalIdx = ternaryWindow.indexOf(
  '"skipped_on_informational_option_question"',
);
assert(
  ternaryDispositionIdx > 0 &&
    ternaryInformationalIdx > 0 &&
    ternaryDispositionIdx < ternaryInformationalIdx,
  `disposition skip precedes legacy word-list skip in skipReason ternary (${ternaryDispositionIdx} < ${ternaryInformationalIdx})`,
);

// 8. `[turn-disposition/authoring]` trace emit contains all four required
//    tokens + supporting context. Extract the emit string window
//    anchored by the marker and scan within ~3000 chars (the emit is a
//    multi-line template literal; the context window is generous to
//    tolerate future re-indenting).
// Window: from the callsite marker (inside the block's intro comment)
// up to the directive-registry dispatch `if`, which is the end of the
// gate block. The intro comment is ~170 lines, so a fixed-char window
// would miss the trace emit; anchoring on the next structural landmark
// keeps the window tight without being brittle.
const traceWindow = indexSrc.slice(
  authoringGateMarkerIdx,
  directiveRenderIfIdx,
);
assert(
  /\[turn-disposition\/authoring\]/.test(traceWindow),
  "trace emit uses `[turn-disposition/authoring]` prefix",
);
for (const token of [
  "disposition=",
  "policy_rule=",
  "sm_skipped=",
  "prompt_skipped=",
  "legacy_would_have=",
  "ti_kind=",
  "ti_confidence=",
  "ac_kind=",
  "turn_kind=",
  "stage=",
  "fallthrough=",
]) {
  assert(
    traceWindow.includes(token),
    `trace emit carries \`${token}\` token`,
  );
}

// 9. Defensive posture: stateMachineAuthoringSkipped is true when
//    (a) Cut #5: the layer returned a non-continue disposition, OR
//    (b) Cut 9.0: the router's state-machine gate fired
//        (meaning_first default AND !invoke_state_machine).
//    Phase 5 (2026-04-23): the `RIDERS_TURN_DISPOSITION_AUTHOR_LIVE`
//    env flag was removed, so the guard on the Cut #5 branch is now
//    just the disposition check (no env predicate).
assert(
  /stateMachineAuthoringSkipped\s*=\s*Boolean\s*\(\s*\n?\s*\(\s*authoringDisposition\s*&&\s*\n?\s*authoringDisposition\.disposition\s*!==\s*["']continue_step["']\s*\)\s*\|\|\s*\n?\s*routerStateMachineGateFires\s*,?\s*\n?\s*\)/s.test(
    indexSrc,
  ),
  "stateMachineAuthoringSkipped guarded by (Cut #5 non-continue disposition) OR (Cut 9 router gate)",
);

// ---------------------------------------------------------------------------
// Source-level assertions on deploy.sh (canary + check tuples)
// ---------------------------------------------------------------------------

const deploySrc = readFileSync(
  resolve(ROOT, "scripts/deploy.sh"),
  "utf8",
);
for (const marker of [
  "DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_IMPORT_MARKER",
  "DEPLOY_CANARY_TURN_DISPOSITION_AUTHORING_GATE_CALLSITE_MARKER",
]) {
  assert(
    new RegExp(`${marker}='${marker}'`).test(deploySrc),
    `deploy.sh declares ${marker}`,
  );
  // Count "usages" where the marker name appears — the declaration
  // shows it twice (LHS + RHS of the = assignment) and each check
  // tuple adds one $-prefixed reference, so the floor is 3: declare
  // (LHS+RHS) + one check tuple.
  const matches = deploySrc.match(new RegExp(marker, "g")) || [];
  assert(
    matches.length >= 3,
    `deploy.sh references ${marker} in ≥3 places (declare LHS+RHS + ≥1 check tuple), got ${matches.length}`,
  );
}

console.log("\nAll Cut #5 turn-disposition authoring-gate assertions passed.");
