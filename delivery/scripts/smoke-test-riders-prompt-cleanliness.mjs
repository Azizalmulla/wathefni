// Smoke test for Riders customer prompt cleanliness.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-riders-prompt-cleanliness.mjs

import { readFileSync } from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");

const files = [
  "workspaces/riders/AGENTS.md",
  "workspaces/riders/IDENTITY.md",
  "workspaces/riders/SKILL.md",
  "workspaces/riders/SOUL.md",
  "workspaces/riders/TOOLS.md",
];

const failures = [];
function assert(name, cond, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    console.log(`FAIL  ${name} -- ${detail || ""}`);
    failures.push(name);
  }
}

function read(rel) {
  return readFileSync(path.join(DELIVERY_ROOT, rel), "utf8");
}

const contents = Object.fromEntries(files.map((file) => [file, read(file)]));
const promptText = Object.values(contents).join("\n");

assert(
  "customer prompt files stay compact",
  promptText.split(/\r?\n/).length <= 260,
  `prompt line count is ${promptText.split(/\r?\n/).length}`,
);

assert(
  "no dated bug-history narratives",
  !/\b20\d{2}-\d{2}-\d{2}\b/.test(promptText) &&
    !/\bconversation\s+\d{4,}\b/i.test(promptText) &&
    !/\bconv\s+\d{4,}\b/i.test(promptText),
  "dated incident or conversation id found",
);

assert(
  "no cleanup-era mini brain terms",
  !/\bnext_required_action\b/i.test(promptText) &&
    !/\bdirective\b/i.test(promptText) &&
    !/\bstate machine\b/i.test(promptText),
  "legacy authority wording found",
);

assert(
  "file roles are separated",
  /voice and tone only/i.test(contents["workspaces/riders/AGENTS.md"]) &&
    /high-level booking behavior only/i.test(contents["workspaces/riders/AGENTS.md"]) &&
    /concise tool contracts only/i.test(contents["workspaces/riders/AGENTS.md"]),
  "workspace role boundaries missing",
);

assert(
  "single lifecycle doctrine is present",
  /bookingTruthSnapshot\.nextAction`? is the single booking next step/i.test(promptText) &&
    /Submit only after explicit semantic confirmation(?: of [^.]+)? and (?:a )?matching summary hash/i.test(promptText),
  "single lifecycle doctrine missing",
);

console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
if (failures.length > 0) process.exit(1);
