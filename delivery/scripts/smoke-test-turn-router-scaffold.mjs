#!/usr/bin/env node
/**
 * Smoke test for Cut 9.0 (Turn Router — meaning-first dispatcher
 * scaffold, 2026-04-23).
 *
 * Cut 9.0 is the first architectural inversion cut. Before this, the
 * state machine authored every turn by default and three narrow gates
 * (Cut #5 / #6 / 7b) vetoed one branch each when meaning disagreed.
 * Cut 9 introduces `plugins/shared/turn-router.ts` — a top-level
 * dispatcher that classifies each customer turn into a MODE before any
 * state-machine subroutine runs, and exposes three consumer flags:
 *
 *   * `invoke_state_machine`           — should the state-machine
 *                                        directive's output be CONSUMED
 *                                        as this turn's author?
 *   * `shape_prompt_imperatives`       — should the prompt carry
 *                                        next_required_action / hard
 *                                        rules 4 & 10?
 *   * `invoke_region_a_substitutions`  — should A0 / A0a / A0b arm?
 *
 * Scaffold landing: module + callsite + trace emit + ONE consumer
 * (state-machine authoring gate). The env flag
 * `RIDERS_TURN_ROUTER_DEFAULT_MODE` stays at the legacy `"advance_form"`
 * default — downstream consumers additionally guard on
 * `default_mode === "meaning_first"` before honouring flags, so under
 * the legacy default behaviour is byte-for-byte unchanged.
 *
 * Verifies (source-level):
 *
 *   On `plugins/shared/turn-router.ts`:
 *     1.  Module canary marker.
 *     2.  `classifyTurn` exported.
 *     3.  `parseTurnRouterDefaultModeEnv` exported.
 *     4.  `TURN_ROUTER_MODES` readonly array present and complete.
 *
 *   On `plugins/octopus-channel/index.ts`:
 *     5.  Import canary marker.
 *     6.  `classifyTurn` + `parseTurnRouterDefaultModeEnv` imported.
 *     7.  `TurnRouterDecision` + `TurnRouterDefaultMode` type-imported.
 *     8.  Callsite canary marker in the pre-LLM dispatch block.
 *     9.  Env flag `RIDERS_TURN_ROUTER_DEFAULT_MODE` read via the
 *         exported parse helper.
 *    10.  Router decision computed for customer turns and wrapped in
 *         try/catch (never block the turn on classifier errors).
 *    11.  `[turn-router/dispatch]` trace carries mode, reason,
 *         default_mode, default_applied, positive_evidence, all three
 *         consumer flags, classifier attributions, stage, has_quote.
 *    12.  State-machine gate canary marker.
 *    13.  `routerStateMachineGateFires` gated on
 *         `default_mode === "meaning_first"` AND
 *         `!invoke_state_machine`.
 *    14.  `stateMachineAuthoringSkipped` ORs the router gate into the
 *         existing Cut #5 disposition skip.
 *    15.  `[turn-disposition/authoring]` trace carries
 *         `router_gate_fired` + `router_mode` tokens so triagers can
 *         distinguish Cut #5 skips from router skips without
 *         cross-referencing two traces.
 *
 *   On `scripts/deploy.sh`:
 *    16.  All four Cut 9 canary markers declared and referenced in
 *         check tuples.
 *
 *   Runtime behaviour of the router (pure function, no env):
 *    17.  No classifier decision + `advance_form` default → mode
 *         `advance_form`, default_applied=true.
 *    18.  No classifier decision + `meaning_first` default → mode
 *         `answer`, default_applied=true.
 *    19.  Classifier `answer` → mode `answer` regardless of default,
 *         default_applied=false.
 *    20.  Classifier `continue_step` with POSITIVE rule
 *         (`no_text` / `confirmation`) → mode `advance_form`
 *         regardless of default, default_applied=false.
 *    21.  Classifier `continue_step` with FALLTHROUGH rule (`default`)
 *         + `advance_form` default → mode `advance_form`,
 *         default_applied=true.
 *    22.  Classifier `continue_step` with FALLTHROUGH rule (`default`)
 *         + `meaning_first` default → mode `answer`,
 *         default_applied=true.
 *    23.  Consumer flags mirror `mode === "advance_form"` exactly.
 *    24.  `parseTurnRouterDefaultModeEnv` is lenient (unset / empty /
 *         unknown → advance_form; "meaning_first" → meaning_first).
 *
 * Live-traffic verification happens via the `[turn-router/dispatch]`
 * trace; this test pins only the source-level wiring and the pure
 * classifier's decision shape.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createJiti } from "./_helpers/riders-plugin-loader.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, "..");
const jiti = createJiti(import.meta.url);

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  } else {
    console.log(`ok  : ${msg}`);
  }
}

function loadTs(relativePath) {
  return jiti(resolve(ROOT, relativePath));
}

// ---------------------------------------------------------------------------
// (A) plugins/shared/turn-router.ts
// ---------------------------------------------------------------------------

const routerSrc = readFileSync(
  resolve(ROOT, "plugins/shared/turn-router.ts"),
  "utf8",
);

assert(
  routerSrc.includes("DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER"),
  "(1) module canary marker present in turn-router.ts",
);
assert(
  /export function classifyTurn\s*\(/.test(routerSrc),
  "(2) classifyTurn exported",
);
assert(
  /export function parseTurnRouterDefaultModeEnv\s*\(/.test(routerSrc),
  "(3) parseTurnRouterDefaultModeEnv exported",
);
const modes = [
  "advance_form",
  "answer",
  "requote",
  "acknowledge",
  "cancel_confirmation",
  "edit_field",
  "handoff",
  "idle",
];
const modesArrayMatch = routerSrc.match(
  /export const TURN_ROUTER_MODES:\s*readonly TurnRouterMode\[\]\s*=\s*\[([\s\S]*?)\]\s*as const/,
);
assert(modesArrayMatch, "(4) TURN_ROUTER_MODES readonly array present");
for (const m of modes) {
  assert(
    modesArrayMatch && modesArrayMatch[1].includes(`"${m}"`),
    `(4) TURN_ROUTER_MODES contains "${m}"`,
  );
}

// ---------------------------------------------------------------------------
// (B) plugins/octopus-channel/index.ts
// ---------------------------------------------------------------------------

const idxSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/index.ts"),
  "utf8",
);

assert(
  idxSrc.includes("DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER"),
  "(5) import canary marker present in index.ts",
);
// Phase 5 (2026-04-23): `parseTurnRouterDefaultModeEnv` and the
// `RIDERS_TURN_ROUTER_DEFAULT_MODE` env flag were removed — the router
// default is hardcoded `meaning_first`. Only `classifyTurn` is imported.
assert(
  /import\s*\{\s*classifyTurn\s*,?\s*\}\s*from\s*["']\.\.\/shared\/turn-router["']/.test(
    idxSrc,
  ),
  "(6) classifyTurn imported from ../shared/turn-router",
);
assert(
  /import type\s*\{\s*(?:[\w,\s]*\b)?TurnRouterDecision\b[\s\S]*?TurnRouterDefaultMode[\s\S]*?\}\s*from\s*["']\.\.\/shared\/turn-router["']/.test(
    idxSrc,
  ) ||
    /import type\s*\{\s*(?:[\w,\s]*\b)?TurnRouterDefaultMode\b[\s\S]*?TurnRouterDecision[\s\S]*?\}\s*from\s*["']\.\.\/shared\/turn-router["']/.test(
      idxSrc,
    ),
  "(7) TurnRouterDecision + TurnRouterDefaultMode type-imported",
);
assert(
  idxSrc.includes("DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER"),
  "(8) callsite canary marker present in index.ts",
);
assert(
  !/process\.env\.RIDERS_TURN_ROUTER_DEFAULT_MODE/.test(idxSrc),
  "(9) RIDERS_TURN_ROUTER_DEFAULT_MODE env read removed (baked meaning_first)",
);
assert(
  /turnRouterDefaultMode\s*:\s*TurnRouterDefaultMode\s*=\s*["']meaning_first["']/.test(
    idxSrc,
  ),
  "(9b) turnRouterDefaultMode hardcoded to meaning_first",
);
const callsiteIdx = idxSrc.indexOf(
  "DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER",
);
const callsiteWindow = idxSrc.slice(callsiteIdx, callsiteIdx + 4000);
assert(
  /if\s*\(senderRole\s*===\s*"customer"\s*\)\s*\{[\s\S]*?turnRouterDecision\s*=\s*classifyTurn\s*\(\s*\{/.test(
    callsiteWindow,
  ),
  "(10a) classifyTurn invoked inside customer-only guard",
);
assert(
  /try\s*\{\s*turnRouterDecision\s*=\s*classifyTurn/.test(callsiteWindow),
  "(10b) classifyTurn wrapped in try/catch",
);
assert(
  /catch\s*\([\s\S]*?\)\s*\{[\s\S]*?turnRouterDecision\s*=\s*null/.test(
    callsiteWindow,
  ),
  "(10c) classifyTurn catch falls back to null",
);
const traceTokens = [
  "[turn-router/dispatch]",
  "default_mode=",
  "mode=",
  "reason=",
  "default_applied=",
  "positive_evidence=",
  "invoke_state_machine=",
  "shape_prompt_imperatives=",
  "invoke_region_a_substitutions=",
  "classifier_disposition=",
  "classifier_policy_rule=",
  "classifier_fallthrough=",
  "stage=",
  "has_quote=",
];
for (const token of traceTokens) {
  assert(
    callsiteWindow.includes(token),
    `(11) [turn-router/dispatch] trace carries "${token}"`,
  );
}

assert(
  idxSrc.includes("DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER"),
  "(12) state-machine gate canary marker present in index.ts",
);
const gateIdx = idxSrc.indexOf(
  "DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER",
);
const gateWindow = idxSrc.slice(gateIdx, gateIdx + 2000);
assert(
  /const\s+routerStateMachineGateFires\s*=\s*Boolean\s*\(\s*[\s\S]*?turnRouterDecision\s*&&[\s\S]*?default_mode\s*===\s*["']meaning_first["'][\s\S]*?!\s*turnRouterDecision\.invoke_state_machine/.test(
    gateWindow,
  ),
  "(13) routerStateMachineGateFires gated on default_mode=meaning_first AND !invoke_state_machine",
);
assert(
  /const\s+stateMachineAuthoringSkipped\s*=\s*Boolean\s*\(\s*\(\s*authoringDisposition[\s\S]*?authoringDisposition\.disposition\s*!==\s*["']continue_step["']\s*\)\s*\|\|\s*routerStateMachineGateFires/.test(
    gateWindow,
  ),
  "(14) stateMachineAuthoringSkipped ORs routerStateMachineGateFires into Cut #5 skip",
);

// Find the actual emit-site occurrence of `[turn-disposition/authoring]`:
// the file has three matches total (two in comments, one in the logger
// call). We locate the logger call by walking matches forward until one
// sits inside an `api.logger.info(` window.
const authoringTraceToken = "[turn-disposition/authoring]";
let authoringTraceWindow = null;
let searchFrom = 0;
while (true) {
  const hit = idxSrc.indexOf(authoringTraceToken, searchFrom);
  if (hit < 0) break;
  const lookBehind = idxSrc.slice(Math.max(0, hit - 400), hit);
  if (/api\.logger\.info\s*\(\s*$|api\.logger\.info\s*\(\s*`$/m.test(
    lookBehind,
  )) {
    authoringTraceWindow = idxSrc.slice(hit, hit + 4000);
    break;
  }
  searchFrom = hit + 1;
}
assert(
  authoringTraceWindow !== null,
  "(15a) [turn-disposition/authoring] emit-site trace located",
);
assert(
  authoringTraceWindow.includes("router_gate_fired="),
  "(15b) [turn-disposition/authoring] trace carries router_gate_fired token",
);
assert(
  authoringTraceWindow.includes("router_mode="),
  "(15c) [turn-disposition/authoring] trace carries router_mode token",
);

// ---------------------------------------------------------------------------
// (C) scripts/deploy.sh
// ---------------------------------------------------------------------------

const deploySrc = readFileSync(resolve(ROOT, "scripts/deploy.sh"), "utf8");
const deployMarkers = [
  "DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER",
  "DEPLOY_CANARY_TURN_ROUTER_IMPORT_MARKER",
  "DEPLOY_CANARY_TURN_ROUTER_CALLSITE_MARKER",
  "DEPLOY_CANARY_TURN_ROUTER_STATE_MACHINE_GATE_MARKER",
];
for (const m of deployMarkers) {
  const decl = deploySrc.indexOf(`${m}='${m}'`);
  assert(decl > 0, `(16a) ${m} declared in deploy.sh`);
  const ref = deploySrc.indexOf(`'$${m}'`);
  assert(
    ref > 0 && ref !== decl,
    `(16b) ${m} referenced in verify-tuples list`,
  );
}

// ---------------------------------------------------------------------------
// (D) Runtime behaviour of the router module.
// ---------------------------------------------------------------------------

const router = loadTs("plugins/shared/turn-router.ts");
const { classifyTurn, parseTurnRouterDefaultModeEnv } = router;

function buildClassifierDecision(disposition, policyRule, fallthroughReason) {
  return {
    disposition,
    authored_directive: null,
    policy_rule: policyRule,
    decision_inputs: {},
    trace_annotations: {
      fallthrough_reason: fallthroughReason ?? null,
    },
  };
}

// (17) No classifier + advance_form default.
{
  const d = classifyTurn({
    classifier_decision: null,
    default_mode: "advance_form",
  });
  assert(d.mode === "advance_form", "(17a) no-classifier advance_form → advance_form");
  assert(d.default_applied === true, "(17b) no-classifier advance_form default_applied=true");
  assert(d.reason === "router.no_classifier_decision", "(17c) no-classifier reason");
  assert(
    d.invoke_state_machine === true &&
      d.shape_prompt_imperatives === true &&
      d.invoke_region_a_substitutions === true,
    "(17d) no-classifier advance_form flags all true",
  );
}

// (18) No classifier + meaning_first default.
{
  const d = classifyTurn({
    classifier_decision: null,
    default_mode: "meaning_first",
  });
  assert(d.mode === "answer", "(18a) no-classifier meaning_first → answer");
  assert(d.default_applied === true, "(18b) no-classifier meaning_first default_applied=true");
  assert(
    d.invoke_state_machine === false &&
      d.shape_prompt_imperatives === false &&
      d.invoke_region_a_substitutions === false,
    "(18c) no-classifier meaning_first flags all false",
  );
}

// (19) Classifier `answer` regardless of default.
for (const dm of ["advance_form", "meaning_first"]) {
  const d = classifyTurn({
    classifier_decision: buildClassifierDecision(
      "answer",
      "shaping.disposition.answer.informational_option_question",
      null,
    ),
    default_mode: dm,
  });
  assert(d.mode === "answer", `(19a/${dm}) classifier=answer → mode=answer`);
  assert(
    d.default_applied === false,
    `(19b/${dm}) classifier=answer default_applied=false`,
  );
  assert(
    d.reason === "router.from_classifier.answer",
    `(19c/${dm}) classifier=answer reason`,
  );
}

// (20) Positive continue_step rules.
for (const rule of [
  "shaping.disposition.continue_step.no_text",
  "shaping.disposition.continue_step.confirmation",
]) {
  for (const dm of ["advance_form", "meaning_first"]) {
    const d = classifyTurn({
      classifier_decision: buildClassifierDecision("continue_step", rule, null),
      default_mode: dm,
    });
    assert(
      d.mode === "advance_form",
      `(20a/${rule}/${dm}) positive continue_step → advance_form`,
    );
    assert(
      d.default_applied === false,
      `(20b/${rule}/${dm}) positive continue_step default_applied=false`,
    );
    assert(
      d.positive_evidence === rule,
      `(20c/${rule}/${dm}) positive_evidence=${rule}`,
    );
    assert(
      d.invoke_state_machine === true,
      `(20d/${rule}/${dm}) positive continue_step invoke_state_machine=true`,
    );
  }
}

// (21) Fallthrough continue_step + advance_form default.
{
  const d = classifyTurn({
    classifier_decision: buildClassifierDecision(
      "continue_step",
      "shaping.disposition.continue_step.default",
      null,
    ),
    default_mode: "advance_form",
  });
  assert(d.mode === "advance_form", "(21a) fallthrough advance_form → advance_form");
  assert(d.default_applied === true, "(21b) fallthrough advance_form default_applied=true");
  assert(
    d.reason === "router.default_advance_form.classifier_fell_through",
    "(21c) fallthrough advance_form reason",
  );
  assert(
    d.invoke_state_machine === true,
    "(21d) fallthrough advance_form invoke_state_machine=true (legacy preserve)",
  );
}

// (22) Fallthrough continue_step + meaning_first default.
{
  const d = classifyTurn({
    classifier_decision: buildClassifierDecision(
      "continue_step",
      "shaping.disposition.continue_step.default",
      null,
    ),
    default_mode: "meaning_first",
  });
  assert(d.mode === "answer", "(22a) fallthrough meaning_first → answer");
  assert(d.default_applied === true, "(22b) fallthrough meaning_first default_applied=true");
  assert(
    d.reason === "router.default_meaning_first.classifier_fell_through",
    "(22c) fallthrough meaning_first reason",
  );
  assert(
    d.invoke_state_machine === false &&
      d.shape_prompt_imperatives === false &&
      d.invoke_region_a_substitutions === false,
    "(22d) fallthrough meaning_first flags all false (inversion bites)",
  );
}

// (23) Consumer flags mirror mode === advance_form in every case above.
// Spot-check one non-advance_form disposition.
{
  const d = classifyTurn({
    classifier_decision: buildClassifierDecision(
      "requote",
      "shaping.disposition.requote.route_pair_on_active_quote",
      null,
    ),
    default_mode: "advance_form",
  });
  assert(d.mode === "requote", "(23a) classifier=requote → mode=requote");
  assert(
    d.invoke_state_machine === false &&
      d.shape_prompt_imperatives === false &&
      d.invoke_region_a_substitutions === false,
    "(23b) requote flags all false (non-advance_form)",
  );
}

// (24) parseTurnRouterDefaultModeEnv leniency.
{
  assert(
    parseTurnRouterDefaultModeEnv(undefined) === "advance_form",
    "(24a) unset → advance_form",
  );
  assert(
    parseTurnRouterDefaultModeEnv("") === "advance_form",
    "(24b) empty → advance_form",
  );
  assert(
    parseTurnRouterDefaultModeEnv("   ") === "advance_form",
    "(24c) whitespace → advance_form",
  );
  assert(
    parseTurnRouterDefaultModeEnv("garbage") === "advance_form",
    "(24d) unknown → advance_form (safe default)",
  );
  assert(
    parseTurnRouterDefaultModeEnv("advance_form") === "advance_form",
    "(24e) advance_form → advance_form",
  );
  assert(
    parseTurnRouterDefaultModeEnv("MEANING_FIRST") === "meaning_first",
    "(24f) case-insensitive meaning_first",
  );
  assert(
    parseTurnRouterDefaultModeEnv("  meaning_first  ") === "meaning_first",
    "(24g) whitespace-tolerant meaning_first",
  );
}

console.log("\nAll Cut 9.0 (Turn Router scaffold) smoke assertions passed.");
