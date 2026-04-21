#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 2 hotfix — informational option/price question gate
// (2026-04-21).
//
// Product rule:
//   On a quoted route (stage=quoted) before booking collection has begun,
//   a customer message that is an informational option or price question
//   is an ANSWER-ONLY turn per SKILL.md hard rule 5. The LLM's reply
//   (which should carry the answer) must survive; the directive-reply
//   registry MUST NOT substitute it with the next server-rendered slot
//   ask.
//
// Regression this fixes:
//   Canonical transcript 2026-04-21 00:14 — conversation=18989.
//   Customer: "whats the most expensive option"
//   stage=quoted, next_required_action=ASK_SENDER_NAME_AND_PHONE_DECISION
//   Pre-hotfix: Region A substituted with "Great. Sender's full name
//   please…". The LLM's rule-5-compliant answer was discarded.
//
// Cases covered:
//   D1-D7  isInformationalOptionQuestion recognises the canonical
//          EN / AR / Arabizi phrasings.
//   N1-N5  isInformationalOptionQuestion returns false for explicit
//          confirmations, proceed signals, greetings, address values,
//          phone numbers.
//   G1     The specific regression transcript case —
//          "whats the most expensive option" with stage=quoted and
//          ASK_SENDER_NAME_AND_PHONE_DECISION — triggers the gate.
//   G2-G4  Other rule-5 canonical phrasings ("whats the cheapest",
//          "do you have a van", "how much for express") trigger it.
//   G5     Mid-collection stage (not "quoted") does NOT trigger the
//          gate — user scope decision.
//   G6     CLARIFY_OPTION_BEFORE_PROCEED is never skipped — the gate
//          only applies to collection / summary directives.
//   G7     CONFIRM_SLOT_CONFLICT is never skipped.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function loadTs(relativePath) {
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const policy = loadTs("plugins/shared/conversation-policy.ts");
const { isInformationalOptionQuestion } = policy;

// -------------------------------------------------------------------------
// D1-D7: detector positives — exact and near-exact phrasings from
// hard rule 5 plus the regression transcript.
// -------------------------------------------------------------------------
const POSITIVES = [
  // Regression anchor
  "whats the most expensive option",
  // Hard rule 5 canon
  "what is the cheapest?",
  "most expensive option?",
  "do you have a van?",
  "is there a faster one?",
  "how much for express?",
  "شنو أرخص خيار؟",
  "عندكم باص؟",
  // Close neighbours
  "whats the cheapest",
  "which is the fastest?",
  "do you have a refrigerated van",
  "any other options?",
  "is there a cheaper one",
  "cheapest one please",
  "هل عندكم فان",
  "كم سعر السريع",
  "shnu arkhass option",
  "bkm express",
];

for (const text of POSITIVES) {
  assert.equal(
    isInformationalOptionQuestion(text),
    true,
    `D: must detect informational: ${JSON.stringify(text)}`,
  );
}

// -------------------------------------------------------------------------
// N1-N5: detector negatives — values that are NOT informational
// questions and must not trigger the gate.
// -------------------------------------------------------------------------
const NEGATIVES = [
  // Proceed / confirm signals
  "yes",
  "go ahead",
  "proceed",
  "confirm",
  "اكمل",
  "نعم",
  // Greeting
  "hi",
  "hello",
  "هلا",
  // Explicit selections (not questions)
  "express refrigerated van",
  "standard sedan please",
  // Address / phone / name values
  "block 6 street 9 house 17",
  "96597485757",
  "Aziz Almulla",
  "apartment 12 floor 3",
  // Simple acknowledgements
  "ok",
  "thanks",
  "noted",
  // Booking-step content that happens to contain a vocab word (no
  // interrogative + no superlative → false)
  "my sender phone is 96597485757",
];

for (const text of NEGATIVES) {
  assert.equal(
    isInformationalOptionQuestion(text),
    false,
    `N: must NOT detect informational: ${JSON.stringify(text)}`,
  );
}

// -------------------------------------------------------------------------
// G1-G7: structural gate contract — the index.ts Region-A block must
// skip substitution in the right conditions. We grep the source to
// anchor the shape of the gate rather than invoke the full handler,
// which would require a sprawling fixture. The Region-A gate is pure
// logic; the smoke keeps the shape locked.
// -------------------------------------------------------------------------
const indexSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/index.ts"),
  "utf8",
);

// G1: detector imported and wired into the dispatch block.
assert.ok(
  /import\s*\{[\s\S]*?isInformationalOptionQuestion[\s\S]*?\}\s*from\s*["']\.\.\/shared\/conversation-policy["']/.test(
    indexSrc,
  ),
  "G1: isInformationalOptionQuestion must be imported in index.ts",
);
assert.ok(
  /customerAskingInformational\s*=[\s\S]{0,200}isInformationalOptionQuestion\(rawBody/.test(
    indexSrc,
  ),
  "G1: gate variable must be computed from isInformationalOptionQuestion(rawBody)",
);

// G2: the gate is scoped to stage=quoted.
assert.ok(
  /customerAskingInformational\s*=[\s\S]{0,200}conversationControllerEntry\?\.stage\s*===\s*"quoted"/.test(
    indexSrc,
  ),
  "G2: gate must require stage === 'quoted'",
);

// G3: substitution is skipped when the gate fires.
assert.ok(
  /if\s*\(!customerConfirmedOrder\s*&&\s*!customerAskingInformational\)/.test(
    indexSrc,
  ),
  "G3: registry dispatch must skip when customerAskingInformational is true",
);

// G4: skip reason surfaced in the log emitter.
assert.ok(
  /skipped_on_informational_option_question/.test(indexSrc),
  "G4: skip log line must carry informational-question reason",
);

// G5: gate only applies to collection / summary directives — the set
// must match exactly the 9 directive actions listed in the hotfix plan.
const directiveSetMatch = indexSrc.match(
  /const\s+directiveIsCollectionOrSummary\s*=\s*([\s\S]{0,800}?);/,
);
assert.ok(directiveSetMatch, "G5: directiveIsCollectionOrSummary predicate must exist");
const directiveSetBody = directiveSetMatch[1];
const requiredActions = [
  "ASK_SENDER_NAME_AND_PHONE_DECISION",
  "ASK_SENDER_PHONE",
  "ASK_RECIPIENT_NAME_AND_PHONE",
  "ASK_PICKUP_ADDRESS",
  "ASK_DELIVERY_ADDRESS",
  "ASK_MISSING_AREAS",
  "ASK_PICKUP_AREA",
  "ASK_DELIVERY_AREA",
  "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
];
for (const action of requiredActions) {
  assert.ok(
    directiveSetBody.includes(`"${action}"`),
    `G5: directiveIsCollectionOrSummary must include ${action}`,
  );
}
// Forbid the directives the user explicitly said must still fire.
const forbiddenActions = [
  "CLARIFY_OPTION_BEFORE_PROCEED",
  "CONFIRM_SLOT_CONFLICT",
  "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM",
  "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM",
  "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM",
  "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
];
for (const action of forbiddenActions) {
  assert.ok(
    !directiveSetBody.includes(`"${action}"`),
    `G6: directiveIsCollectionOrSummary must NOT include ${action}`,
  );
}

// G7: the gate short-circuit preserves CLARIFY_OPTION_BEFORE_PROCEED and
// CONFIRM_SLOT_CONFLICT — confirm via the gate predicate bailing out
// when directive.action isn't in the scoped set. This is implicit in
// the above checks but worth an explicit assertion: searching for the
// gate declaration followed by each forbidden action as a |-arm should
// fail.
for (const action of forbiddenActions) {
  const re = new RegExp(
    `directiveIsCollectionOrSummary\\s*=\\s*[\\s\\S]{0,600}\\|\\|\\s*directive\\.action\\s*===\\s*"${action}"`,
  );
  assert.ok(
    !re.test(indexSrc),
    `G7: ${action} must not appear inside directiveIsCollectionOrSummary`,
  );
}

console.log("smoke-test-informational-question-gate: OK");
