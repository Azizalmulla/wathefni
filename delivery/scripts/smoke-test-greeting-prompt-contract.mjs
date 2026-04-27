// Smoke test for Riders greeting prompt contract.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-greeting-prompt-contract.mjs
//
// Locks the customer prompt to a concise Riders greeting contract without
// requiring exact phrase examples in the prompt.

import { readFileSync } from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DELIVERY_ROOT = path.resolve(HERE, "..");

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

const identity = read("workspaces/riders/IDENTITY.md");
const soul = read("workspaces/riders/SOUL.md");
const agents = read("workspaces/riders/AGENTS.md");
const promptText = `${identity}\n${soul}\n${agents}`;

assert(
  "old English welcome greeting removed",
  !/Welcome to Riders\s*[—,-]\s*how can we help/i.test(promptText) &&
    !/Welcome to Riders,\s*how can we help you/i.test(promptText),
  "stiff Welcome to Riders greeting still present",
);

assert(
  "Riders brand role is present",
  /official WhatsApp delivery desk for Riders in Kuwait/i.test(identity) &&
    /Use "we" or "Riders"/i.test(identity),
  "brand role missing",
);

assert(
  "voice remains WhatsApp operations desk",
  /Kuwait operations desk/i.test(soul) &&
    /practical WhatsApp English/i.test(soul),
  "voice guidance missing",
);

assert(
  "customer replies avoid dash punctuation",
  /Avoid dash punctuation in customer replies/i.test(soul),
  "dash punctuation style guidance missing",
);

assert(
  "architecture says one customer reply",
  /Use one final customer-facing reply per incoming turn/i.test(agents),
  "single reply architecture rule missing",
);

console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
if (failures.length > 0) process.exit(1);
