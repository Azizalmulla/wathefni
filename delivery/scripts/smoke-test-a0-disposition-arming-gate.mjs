#!/usr/bin/env node
/**
 * Smoke test for Cut 7b (A0 / A0a / A0b ARMING disposition gate,
 * 2026-04-23).
 *
 * Cut 7b is the structural authority downgrade for the three pre-LLM
 * Region-A substitution branches:
 *
 *   * A0  — `clarifyOptionBeforeProceed` → `replace_clarify_option_before_proceed`
 *   * A0a — `manualConfirmAddressAsk`    → `replace_manual_confirm_address_ask`
 *   * A0b — `manualConfirmHandoff`       → `replace_manual_confirm_handoff`
 *
 * Before the cut, all three armed from mechanical signals only
 * (state flags + raw-text regex). Once armed, they stamped their
 * server-rendered reply over whatever the LLM drafted. With the gate
 * on, arming is conditional on the pre-LLM disposition being
 * `continue_step` — i.e. the heuristic classifier agrees this turn
 * is actually advancing the booking step. On `answer` / `requote` /
 * `cancel_confirmation` / `acknowledge` / `idle` turns the three
 * arming flags are forced off and the LLM's draft passes through.
 *
 * The 2026-04-23 canonical transcript this cut targets:
 *
 *   customer (post-quote, manual-confirm catalog):
 *     "so i cant order rn if its manual confirmation"
 *
 * The legacy pipeline matched `"confirm"` as a substring inside
 * `"confirmation"` via `detectVagueProceedSignal`, armed A0, and
 * substituted the options menu over the LLM's direct answer. With
 * 7b on, `isContextualClarifyingQuestion` promotes the pre-LLM
 * disposition to `answer`, the arming gate suppresses A0, and the
 * LLM reply survives.
 *
 * Verifies (source-level):
 *
 *   On `plugins/shared/conversation-policy.ts`:
 *     1.  Detector canary marker.
 *     2.  `isContextualClarifyingQuestion` exported.
 *     3.  Modal-negation / conditional / mean / discourse-marker /
 *         modal-interrogative regex constants present.
 *
 *   On `plugins/shared/turn-disposition.ts`:
 *     4.  Injection canary marker.
 *     5.  `isContextualClarifyingQuestion` added to the detectors
 *         type.
 *     6.  Rule 6 has TWO answer paths (informational +
 *         contextual_clarifying_question).
 *     7.  Contextual path uses the new policy_rule id.
 *
 *   On `plugins/octopus-channel/index.ts`:
 *     8.  Detector import canary marker.
 *     9.  `isContextualClarifyingQuestion` imported.
 *    10.  Decision-unconditional canary marker.
 *    11.  `promptShapingDecision` is computed for all customer turns
 *         (the `if (senderRole === "customer")` guard, not the
 *         env-flag guard).
 *    12.  The new detector is passed in the `detectors` bundle.
 *    13.  Callsite canary marker in the Region-A block.
 *    14.  Env flag `RIDERS_A0_DISPOSITION_ARMING_GATE_LIVE` default
 *         "off".
 *    15.  Arming-gate boolean `a0ArmingGateBlocks` declared.
 *    16.  `clarifyOptionBeforeProceed` derives from the gate AND the
 *         "would have armed" shadow.
 *    17.  `manualConfirmAddressAsk` / `manualConfirmHandoff` derive
 *         from the gate AND their "would have" shadows.
 *    18.  Trace canary marker.
 *    19.  `[a0-arming/disposition]` trace carries all required
 *         tokens (flag, disposition, policy_rule, gated,
 *         clarify_would_have, clarify_armed, mc_ask_would_have,
 *         mc_ask_armed, mc_handoff_would_have, mc_handoff_armed,
 *         stage, has_quote).
 *
 *   On `scripts/deploy.sh`:
 *    20.  All six canary markers declared and referenced in check
 *         tuples.
 *
 *   Runtime behaviour of the detector:
 *    21.  Positive: the canonical transcript matches.
 *    22.  Positive: indirect / modal-interrogative / conditional
 *         shapes match.
 *    23.  Negative: explicit confirmations / greetings / start intents
 *         do not match.
 *    24.  Negative: bare proceed tokens ("go ahead", "yes", "proceed")
 *         do not match (no uncertainty marker).
 *
 *   Runtime behaviour of the prompt-shaping disposition:
 *    25.  Canonical transcript → `answer` via
 *         `shaping.disposition.answer.contextual_clarifying_question`.
 *
 * Live-traffic verification happens via the `[a0-arming/disposition]`
 * trace; this test pins only the source-level wiring and the
 * detector's classification of the target utterance class.
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
// (A) plugins/shared/conversation-policy.ts
// ---------------------------------------------------------------------------

const cpSrc = readFileSync(
  resolve(ROOT, "plugins/shared/conversation-policy.ts"),
  "utf8",
);

assert(
  cpSrc.includes("DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DETECTOR_MARKER"),
  "(1) detector canary marker present in conversation-policy.ts",
);
assert(
  /export function isContextualClarifyingQuestion\s*\(/.test(cpSrc),
  "(2) isContextualClarifyingQuestion exported",
);

const detectorConstants = [
  "CONTEXTUAL_MODAL_NEGATION_EN",
  "CONTEXTUAL_CONDITIONAL_EN",
  "CONTEXTUAL_MEAN_EN",
  "CONTEXTUAL_DISCOURSE_MARKER_EN",
  "CONTEXTUAL_MODAL_INTERROGATIVE_EN",
  "CONTEXTUAL_UNCERTAINTY_AR",
  "CONTEXTUAL_CONDITIONAL_AR",
  "CONTEXTUAL_DOMAIN_EN",
  "CONTEXTUAL_DOMAIN_AR",
];
for (const c of detectorConstants) {
  assert(cpSrc.includes(c), `(3) detector constant present: ${c}`);
}

// ---------------------------------------------------------------------------
// (B) plugins/shared/turn-disposition.ts
// ---------------------------------------------------------------------------

const tdSrc = readFileSync(
  resolve(ROOT, "plugins/shared/turn-disposition.ts"),
  "utf8",
);

assert(
  tdSrc.includes(
    "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DISPOSITION_INJECTION_MARKER",
  ),
  "(4) injection canary marker present in turn-disposition.ts",
);
assert(
  /isContextualClarifyingQuestion:\s*\(text:\s*string\s*\|\s*null\)\s*=>\s*boolean;/.test(
    tdSrc,
  ),
  "(5) isContextualClarifyingQuestion added to detectors type",
);

// Rule 6 has two answer paths — first the informational, then the
// contextual clarifying. Both exit via `buildShapingAuthored("answer", ...)`.
const informationalIdx = tdSrc.indexOf(
  "shaping.disposition.answer.informational_option_question",
);
const contextualIdx = tdSrc.indexOf(
  "shaping.disposition.answer.contextual_clarifying_question",
);
assert(informationalIdx > 0, "(6) informational answer policy_rule present");
assert(
  contextualIdx > 0,
  "(6) contextual_clarifying_question answer policy_rule present",
);
assert(
  informationalIdx < contextualIdx,
  "(6) informational path appears before contextual path (rule order)",
);
assert(
  /if\s*\(input\.detectors\.isContextualClarifyingQuestion\s*\(\s*rawText\s*\)\s*\)/.test(
    tdSrc,
  ),
  "(7) rule 6 calls isContextualClarifyingQuestion detector",
);

// ---------------------------------------------------------------------------
// (C) plugins/octopus-channel/index.ts
// ---------------------------------------------------------------------------

const idxSrc = readFileSync(
  resolve(ROOT, "plugins/octopus-channel/index.ts"),
  "utf8",
);

assert(
  idxSrc.includes(
    "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DETECTOR_IMPORT_MARKER",
  ),
  "(8) detector import canary marker present in index.ts",
);
assert(
  /^\s*isContextualClarifyingQuestion,\s*$/m.test(idxSrc),
  "(9) isContextualClarifyingQuestion imported in index.ts",
);

assert(
  idxSrc.includes(
    "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DECISION_UNCONDITIONAL_MARKER",
  ),
  "(10) decision-unconditional canary marker present",
);

// The `computePromptShapingDisposition` call is guarded only by
// `senderRole === "customer"` (not by the env flag) so both gates
// can read the same disposition value.
const computeCallSnippet = idxSrc.match(
  /if\s*\(senderRole\s*===\s*"customer"\)\s*\{\s*try\s*\{\s*promptShapingDecision\s*=\s*computePromptShapingDisposition\(/,
);
assert(
  computeCallSnippet !== null,
  "(11) promptShapingDecision computed for all customer turns (unconditional by flag)",
);

// Detector is injected into the detectors bundle.
const detectorsBundleSnippet = idxSrc.match(
  /detectors:\s*\{\s*\n[^}]*isContextualClarifyingQuestion,\s*\n\s*\}/,
);
assert(
  detectorsBundleSnippet !== null,
  "(12) isContextualClarifyingQuestion passed in detectors bundle",
);

assert(
  idxSrc.includes(
    "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_CALLSITE_MARKER",
  ),
  "(13) callsite canary marker present in index.ts",
);

// Env flag wired default "off" — explicit opt-in for bake.
const envFlagSnippet = idxSrc.match(
  /\(process\.env\.RIDERS_A0_DISPOSITION_ARMING_GATE_LIVE\s*\|\|\s*"off"\)\s*\.trim\(\)\s*\.toLowerCase\(\)\s*===\s*"on"/,
);
assert(
  envFlagSnippet !== null,
  '(14) RIDERS_A0_DISPOSITION_ARMING_GATE_LIVE default "off", explicit "on" enables',
);

// a0ArmingGateBlocks boolean declared.
assert(
  /const\s+a0ArmingGateBlocks\s*=\s*Boolean\s*\(\s*a0ArmingGateEnvLive\s*&&\s*a0ArmingDispositionIsNonContinue/.test(
    idxSrc,
  ),
  "(15) a0ArmingGateBlocks boolean declared (flag AND non-continue_step disposition)",
);

// clarifyOptionBeforeProceed derives from gate and shadow.
assert(
  /const\s+clarifyOptionBeforeProceed\s*=\s*!a0ArmingGateBlocks\s*&&\s*clarifyOptionBeforeProceedWouldHaveArmed/.test(
    idxSrc,
  ),
  "(16) clarifyOptionBeforeProceed = !gate && wouldHave (gated arming)",
);

// Manual-confirm address-ask / handoff derive from the gate.
assert(
  /const\s+manualConfirmAddressAsk\s*=\s*a0ArmingGateBlocks\s*\?\s*null\s*:\s*manualConfirmAddressAskWouldHave/.test(
    idxSrc,
  ),
  "(17) manualConfirmAddressAsk = gate ? null : wouldHave (gated arming)",
);
assert(
  /const\s+manualConfirmHandoff\s*=\s*a0ArmingGateBlocks\s*\?\s*null\s*:\s*manualConfirmHandoffWouldHave/.test(
    idxSrc,
  ),
  "(17) manualConfirmHandoff = gate ? null : wouldHave (gated arming)",
);

assert(
  idxSrc.includes("DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_TRACE_MARKER"),
  "(18) trace canary marker present in index.ts",
);

// Trace tokens — all required keys must be in the emit string.
const traceTokens = [
  "[a0-arming/disposition]",
  "flag=",
  "disposition=",
  "policy_rule=",
  "gated=",
  "clarify_would_have=",
  "clarify_armed=",
  "mc_ask_would_have=",
  "mc_ask_armed=",
  "mc_handoff_would_have=",
  "mc_handoff_armed=",
  "stage=",
  "has_quote=",
];
const traceMarkerIdx = idxSrc.indexOf(
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_TRACE_MARKER",
);
assert(traceMarkerIdx > 0, "(19) trace marker anchor found");
const traceWindow = idxSrc.slice(traceMarkerIdx, traceMarkerIdx + 3000);
for (const tok of traceTokens) {
  assert(
    traceWindow.includes(tok),
    `(19) trace emit carries token: ${tok}`,
  );
}

// ---------------------------------------------------------------------------
// (D) scripts/deploy.sh
// ---------------------------------------------------------------------------

const deploySrc = readFileSync(
  resolve(ROOT, "scripts/deploy.sh"),
  "utf8",
);

const deployMarkers = [
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DETECTOR_MARKER",
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DETECTOR_IMPORT_MARKER",
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DISPOSITION_INJECTION_MARKER",
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DECISION_UNCONDITIONAL_MARKER",
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_CALLSITE_MARKER",
  "DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_TRACE_MARKER",
];
for (const m of deployMarkers) {
  // Each marker must appear at least twice in deploy.sh: once as a
  // variable declaration and once (or more) inside a check tuple.
  const occurrences = deploySrc.split(m).length - 1;
  assert(
    occurrences >= 2,
    `(20) deploy.sh references ${m} in ≥2 places (declare + check tuple), got ${occurrences}`,
  );
}

// ---------------------------------------------------------------------------
// (E) Runtime behaviour of the detector
// ---------------------------------------------------------------------------

const policy = loadTs("plugins/shared/conversation-policy.ts");
const { isContextualClarifyingQuestion } = policy;

// Positive: the canonical transcript.
assert(
  isContextualClarifyingQuestion(
    "so i cant order rn if its manual confirmation",
  ) === true,
  "(21) canonical: 'so i cant order rn if its manual confirmation' → true",
);

// Positive: indirect / modal-interrogative / conditional shapes.
const positives = [
  "wait does that mean i cant proceed with this option",
  "if its manual confirm then i cant continue right",
  "i guess i cant book this rn",
  "can i still book this one",
  "does it mean i need to wait for approval",
  "so i need manual confirmation to order",
  "hmm if manual confirmation is needed how long does it take",
  "but i cant proceed with helper service",
];
for (const t of positives) {
  assert(
    isContextualClarifyingQuestion(t) === true,
    `(22) positive: ${JSON.stringify(t)} → true`,
  );
}

// Negative: unambiguous acts / greetings / empty / too long.
const negatives = [
  "go ahead",
  "yes",
  "ok lets do it",
  "proceed",
  "confirm",
  "hi",
  "hello",
  "",
  null,
  // Lacks a domain reference — "hello are you there" has no booking
  // vocab, so even though "are you" matches modal-interrogative the
  // detector requires BOTH halves.
  "are you there",
  // Genuine proceed with conditional filler but no uncertainty marker
  // on a domain term.
  "let us do it quickly",
];
for (const t of negatives) {
  assert(
    isContextualClarifyingQuestion(t) === false,
    `(23) negative: ${JSON.stringify(t)} → false`,
  );
}

// ---------------------------------------------------------------------------
// (F) Runtime behaviour of the prompt-shaping disposition
// ---------------------------------------------------------------------------

const shared = loadTs("plugins/shared/turn-disposition.ts");
const { computePromptShapingDisposition } = shared;

const {
  isSimpleGreeting,
  isExplicitOrderConfirmation,
  isInformationalOptionQuestion,
} = policy;

const canonicalDecision = computePromptShapingDisposition({
  customer_text: "so i cant order rn if its manual confirmation",
  stage_at_turn_start: "quoted",
  has_active_quoted_route: true,
  requested_slot_name: null,
  missing_fields_count: 6,
  detectors: {
    isInformationalOptionQuestion,
    isSimpleGreeting,
    isExplicitOrderConfirmation,
    isContextualClarifyingQuestion,
  },
});
assert(
  canonicalDecision.disposition === "answer",
  `(25) canonical transcript promotes to disposition=answer; got ${canonicalDecision.disposition}`,
);
assert(
  canonicalDecision.policy_rule ===
    "shaping.disposition.answer.contextual_clarifying_question",
  `(25) canonical transcript uses contextual policy_rule; got ${canonicalDecision.policy_rule}`,
);

console.log("smoke-test-a0-disposition-arming-gate: OK");
