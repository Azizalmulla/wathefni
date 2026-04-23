#!/usr/bin/env node
/**
 * Smoke test for Cut #6 (prompt-shaping disposition, 2026-04-23).
 *
 * Cut #6 is the INPUT-side counterpart of Cut #5's output-side
 * inversion. A pre-LLM heuristic disposition is computed from
 * server-side signals only (stage, active quote, requested slot,
 * missing fields, customer text) and, when it's anything other than
 * `continue_step`, the system prompt drops the state-machine's
 * authoring imperatives (`next_required_action`,
 * `forbidden_reply_shapes`, `requested_slot_rule`,
 * `pending_area_rule`, `slot_conflicts_rule`) and swaps hard rules 4
 * and 10 for a single meaning-mode rule. State FACTS (draft,
 * missing_fields, requested_slot value, pending areas, conflicts)
 * stay in the prompt either way.
 *
 * The post-LLM authoritative disposition (`decideTurnDisposition`,
 * Cut #5) stays unchanged and keeps driving the output gate. The
 * two layers are intentionally decoupled — neither reads the other's
 * output. Pre-LLM errors are absorbed by post-LLM authority.
 *
 * Verifies (source-level):
 *
 *   On `plugins/shared/turn-disposition.ts`:
 *     1. Module canary marker present.
 *     2. `computePromptShapingDisposition` exported.
 *     3. `PromptShapingDispositionInputs` interface exported.
 *     4. Rule order matches the design: idle → no_text →
 *        confirmation-short-circuit → cancel → requote → answer →
 *        acknowledge → default.
 *     5. Heuristic regex constants present (cancel, option-switch,
 *        bare-ack, route-pair).
 *
 *   On `plugins/octopus-channel/lib/one-brain-context.ts`:
 *     6. Gate canary marker present.
 *     7. `TurnDisposition` type imported from the shared module.
 *     8. `promptShapingDisposition` parameter on
 *        `formatOneBrainLiveChannelContext`.
 *     9. `dropStateAuthoringImperatives` boolean declared and
 *        gates each of the five imperative blocks:
 *          - `next_required_action` / `forbidden_reply_shapes`
 *          - `requested_slot_rule`
 *          - `pending_area_rule`
 *          - `slot_conflicts_rule`
 *          - hard rule 4 (swapped for meaning-mode rule 4')
 *          - hard rule 10 (dropped entirely)
 *    10. `prompt_shaping_disposition:` marker line emitted in the
 *        snapshot when the disposition is non-null (for
 *        observability on the turn-snapshot log).
 *
 *   On `plugins/octopus-channel/lib/live-channel-context.ts`:
 *    11. `promptShapingDisposition` option added and forwarded to
 *        the one-brain formatter.
 *
 *   On `plugins/octopus-channel/index.ts`:
 *    12. Import marker + import line for
 *        `computePromptShapingDisposition`.
 *    13. Callsite marker present between the fast-path block and the
 *        `formatLiveChannelContext` call (i.e. the disposition is
 *        computed BEFORE the prompt is built).
 *    14. Env flag `RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE` wired
 *        default "off", explicit "on" = live (the OPPOSITE of Cut
 *        #5's default-on convention — Cut #6 bakes first).
 *    15. `[prompt-disposition/shaping]` trace carries all required
 *        tokens (`flag`, `disposition`, `policy_rule`,
 *        `state_imperatives_skipped`, `hard_rules_shaped`, `stage`,
 *        `has_quote`, `requested_slot`, `fallthrough`).
 *    16. `promptShapingDisposition:` forwarded to
 *        `formatLiveChannelContext`.
 *
 *   On `scripts/deploy.sh`:
 *    17. All four canary markers declared and referenced in check
 *        tuples.
 *
 * Runtime-level verification of the heuristic's classification
 * quality lives in live traffic traces — we ship default-off and
 * read the `[prompt-disposition/shaping]` emit before flipping the
 * flag on.
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
// (A) plugins/shared/turn-disposition.ts
// ---------------------------------------------------------------------------

const tdSrc = readFileSync(
  resolve(ROOT, "plugins/shared/turn-disposition.ts"),
  "utf8",
);

assert(
  tdSrc.includes("DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER"),
  "(1) module canary marker present",
);
assert(
  /export function computePromptShapingDisposition\s*\(/.test(tdSrc),
  "(2) computePromptShapingDisposition exported",
);
assert(
  /export interface PromptShapingDispositionInputs\b/.test(tdSrc),
  "(3) PromptShapingDispositionInputs interface exported",
);

// Rule ordering — find each rule anchor and confirm the sequence.
const ruleAnchors = [
  { name: "idle",              needle: "shaping.disposition.idle" },
  { name: "no_text",           needle: "shaping.disposition.continue_step.no_text" },
  { name: "confirmation",      needle: "shaping.disposition.continue_step.confirmation" },
  { name: "cancel",            needle: "shaping.disposition.cancel_confirmation" },
  { name: "requote",           needle: "shaping.disposition.requote" },
  { name: "answer",            needle: "shaping.disposition.answer" },
  { name: "acknowledge",       needle: "shaping.disposition.acknowledge" },
  { name: "default",           needle: "shaping.disposition.continue_step.default" },
];
let prevIdx = -1;
for (const { name, needle } of ruleAnchors) {
  const idx = tdSrc.indexOf(needle);
  assert(idx > 0, `(4) rule anchor present: ${name} (${needle})`);
  assert(
    idx > prevIdx,
    `(4) rule order: ${name} appears after previous rule (${idx} > ${prevIdx})`,
  );
  prevIdx = idx;
}

for (const constName of [
  "PROMPT_SHAPING_CANCEL_REGEX",
  "PROMPT_SHAPING_OPTION_SWITCH_REGEX",
  "PROMPT_SHAPING_BARE_ACK_REGEX",
  "PROMPT_SHAPING_ROUTE_PAIR_REGEX",
]) {
  assert(
    tdSrc.includes(constName),
    `(5) heuristic regex constant present: ${constName}`,
  );
}

// ---------------------------------------------------------------------------
// (B) plugins/octopus-channel/lib/one-brain-context.ts
// ---------------------------------------------------------------------------

const obcSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/lib/one-brain-context.ts"),
  "utf8",
);

assert(
  obcSrc.includes("DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_GATE_MARKER"),
  "(6) gate canary marker present in one-brain-context.ts",
);
assert(
  /import\s+type\s*\{\s*TurnDisposition\s*\}\s*from\s*["']\.\.\/\.\.\/shared\/turn-disposition["']/.test(
    obcSrc,
  ),
  "(7) TurnDisposition type imported in one-brain-context.ts",
);
assert(
  /promptShapingDisposition\?:\s*TurnDisposition\s*\|\s*null\s*;/.test(obcSrc),
  "(8) promptShapingDisposition param declared on formatOneBrainLiveChannelContext",
);
assert(
  /const\s+dropStateAuthoringImperatives\s*=/.test(obcSrc),
  "(9) dropStateAuthoringImperatives boolean declared",
);

// Each imperative block must be gated. Anchor on the imperative
// string + the enclosing `if (!dropStateAuthoringImperatives)` guard.
const imperativeGates = [
  {
    label: "next_required_action",
    pattern:
      /if\s*\(\s*directive\s*&&\s*!dropStateAuthoringImperatives\s*\)/,
  },
  {
    label: "requested_slot_rule",
    needle: "requested_slot_rule:",
  },
  {
    label: "pending_area_rule",
    needle: "pending_area_rule:",
  },
  {
    label: "slot_conflicts_rule",
    needle: "slot_conflicts_rule:",
  },
];

for (const gate of imperativeGates) {
  if (gate.pattern) {
    assert(
      gate.pattern.test(obcSrc),
      `(9) gate wired for ${gate.label} (directive emission guarded)`,
    );
  } else {
    const needleIdx = obcSrc.indexOf(gate.needle);
    assert(needleIdx > 0, `(9) ${gate.label} imperative present`);
    // The `if (!dropStateAuthoringImperatives) {` must open WITHIN
    // the 400 chars before the imperative, and a closing brace
    // within 400 chars after. Keep the window generous so future
    // comment additions don't break the assertion.
    const preWindow = obcSrc.slice(Math.max(0, needleIdx - 400), needleIdx);
    assert(
      /if\s*\(\s*!dropStateAuthoringImperatives\s*\)\s*\{/.test(preWindow),
      `(9) gate opens before ${gate.label} imperative`,
    );
  }
}

// Rule 4 swap: dropStateAuthoringImperatives branch pushes the
// "Meaning-mode turn" rule; else branch pushes the legacy rule 4.
const rule4Swap =
  /if\s*\(\s*dropStateAuthoringImperatives\s*\)\s*\{\s*\n\s*lines\.push\(\s*"\s*4\.\s*Meaning-mode turn/;
assert(rule4Swap.test(obcSrc), "(9) hard rule 4 swapped for meaning-mode rule under gate");
assert(
  /lines\.push\(\s*"\s*4\.\s*Every reply must move the conversation forward/.test(
    obcSrc,
  ),
  "(9) hard rule 4 legacy form still pushed on continue_step branch",
);

// Rule 10 drop: the legacy rule 10 line must be inside an
// `if (!dropStateAuthoringImperatives) { ... }`.
const rule10LegacyIdx = obcSrc.indexOf("10. Server-composed directive replies");
assert(rule10LegacyIdx > 0, "(9) legacy rule 10 string still present for continue_step branch");
const rule10Pre = obcSrc.slice(
  Math.max(0, rule10LegacyIdx - 500),
  rule10LegacyIdx,
);
assert(
  /if\s*\(\s*!dropStateAuthoringImperatives\s*\)\s*\{/.test(rule10Pre),
  "(9) rule 10 gated behind !dropStateAuthoringImperatives",
);

// Snapshot marker line.
assert(
  /prompt_shaping_disposition:\s*\$\{promptShapingDisposition\}/.test(obcSrc),
  "(10) prompt_shaping_disposition: marker line emitted in snapshot",
);

// ---------------------------------------------------------------------------
// (C) plugins/octopus-channel/lib/live-channel-context.ts
// ---------------------------------------------------------------------------

const lccSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/lib/live-channel-context.ts"),
  "utf8",
);
assert(
  /promptShapingDisposition\?:\s*TurnDisposition\s*\|\s*null\s*;/.test(lccSrc),
  "(11) promptShapingDisposition option declared on formatLiveChannelContext",
);
assert(
  /promptShapingDisposition:\s*options\?\.promptShapingDisposition\s*\?\?\s*null/.test(
    lccSrc,
  ),
  "(11) promptShapingDisposition forwarded to formatOneBrainLiveChannelContext",
);

// ---------------------------------------------------------------------------
// (D) plugins/octopus-channel/index.ts
// ---------------------------------------------------------------------------

const idxSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/index.ts"),
  "utf8",
);

assert(
  idxSrc.includes("DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_IMPORT_MARKER"),
  "(12) import canary marker present in index.ts",
);
assert(
  /import\s*\{\s*computePromptShapingDisposition\s*\}\s*from\s*["']\.\.\/shared\/turn-disposition["']/.test(
    idxSrc,
  ),
  "(12) computePromptShapingDisposition imported",
);

assert(
  idxSrc.includes("DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_CALLSITE_MARKER"),
  "(13) callsite canary marker present in index.ts",
);

// Ordering: the callsite marker must appear BEFORE the
// `formatLiveChannelContext(...)` invocation on line ~4680.
const callsiteMarkerIdx = idxSrc.indexOf(
  "DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_CALLSITE_MARKER",
);
const formatCallIdx = idxSrc.indexOf(
  "const channelContext = formatLiveChannelContext(",
);
assert(
  callsiteMarkerIdx > 0 && formatCallIdx > 0 && callsiteMarkerIdx < formatCallIdx,
  `(13) callsite runs BEFORE formatLiveChannelContext (marker=${callsiteMarkerIdx}, format=${formatCallIdx})`,
);

// Env flag — DEFAULT OFF, explicit "on" = live.
assert(
  /process\.env\.RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE\s*\|\|\s*["']off["']/.test(
    idxSrc,
  ),
  "(14) RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE flag defaults 'off' (bake first)",
);
assert(
  /RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE[^}]*\.toLowerCase\(\)\s*===\s*["']on["']/s.test(
    idxSrc,
  ),
  "(14) RIDERS_PROMPT_DISPOSITION_SHAPE_LIVE explicit 'on' = live",
);

// Trace line — scan a window from the callsite marker to the format
// call (the full Cut #6 block) and check all required tokens.
const traceWindow = idxSrc.slice(callsiteMarkerIdx, formatCallIdx);
assert(
  /\[prompt-disposition\/shaping\]/.test(traceWindow),
  "(15) trace emit uses `[prompt-disposition/shaping]` prefix",
);
for (const token of [
  "flag=",
  "disposition=",
  "policy_rule=",
  "state_imperatives_skipped=",
  "hard_rules_shaped=",
  "stage=",
  "has_quote=",
  "requested_slot=",
  "fallthrough=",
]) {
  assert(
    traceWindow.includes(token),
    `(15) trace emit carries \`${token}\` token`,
  );
}

// (16) Disposition forwarded to the prompt builder.
assert(
  /promptShapingDisposition:\s*promptShapingDispositionForPrompt/.test(idxSrc),
  "(16) promptShapingDisposition forwarded to formatLiveChannelContext",
);

// Defensive shape: promptShapingDispositionForPrompt is the
// disposition value only when (a) the env flag is live, (b) the
// pre-LLM decision exists, and (c) the decision isn't
// `continue_step`. This keeps the gate identity-safe. The env-flag
// conjunct was added in Cut 7b so the DECISION itself can be
// computed unconditionally (consumed by both prompt shaping and the
// A0 arming gate, each with its own flag) while the PROMPT effect
// still only fires under the prompt-shape flag.
assert(
  /promptShapingDispositionForPrompt\s*=\s*\n?\s*promptShapingEnvLive\s*&&\s*\n?\s*promptShapingDecision\s*&&\s*\n?\s*promptShapingDecision\.disposition\s*!==\s*["']continue_step["']\s*\n?\s*\?\s*promptShapingDecision\.disposition\s*\n?\s*:\s*null/s.test(
    idxSrc,
  ),
  "(16) promptShapingDispositionForPrompt identity-safe when env-off, continue_step, or null",
);

// ---------------------------------------------------------------------------
// (E) scripts/deploy.sh
// ---------------------------------------------------------------------------

const deploySrc = readFileSync(
  resolve(ROOT, "scripts/deploy.sh"),
  "utf8",
);
for (const marker of [
  "DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER",
  "DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_IMPORT_MARKER",
  "DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_CALLSITE_MARKER",
  "DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_GATE_MARKER",
]) {
  assert(
    new RegExp(`${marker}='${marker}'`).test(deploySrc),
    `(17) deploy.sh declares ${marker}`,
  );
  const matches = deploySrc.match(new RegExp(marker, "g")) || [];
  // Declaration (LHS + RHS) + at least one check tuple = floor of 3.
  assert(
    matches.length >= 3,
    `(17) deploy.sh references ${marker} in ≥3 places (declare LHS+RHS + ≥1 check tuple), got ${matches.length}`,
  );
}

console.log("\nAll Cut #6 prompt-disposition-shaping assertions passed.");
