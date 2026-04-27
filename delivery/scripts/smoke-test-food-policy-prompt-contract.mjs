// Smoke test for Riders food-as-item policy prompt contract.
//
// Run from `delivery/` with:
//   node scripts/smoke-test-food-policy-prompt-contract.mjs

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

const promptText = [
  read("workspaces/riders/IDENTITY.md"),
  read("workspaces/riders/REFERENCE.md"),
].join("\n");

assert(
  "prepared food is allowed as courier item",
  /Prepared food counts as an item/i.test(promptText) ||
    /Food counts as an item/i.test(promptText),
  "food-as-item allowance missing",
);

assert(
  "restaurant ordering platform distinction present",
  /not a restaurant ordering platform/i.test(promptText) ||
    /does not transport people, buy items, place restaurant orders/i.test(promptText),
  "restaurant ordering distinction missing",
);

assert(
  "buying food remains out of scope",
  /does not transport people, buy items, place restaurant orders/i.test(promptText) ||
    /We do not choose, buy, or order food/i.test(promptText),
  "buying/ordering distinction missing",
);

assert(
  "prepared food answer stays concise",
  !/reject food (?:as unsupported|just because)/i.test(promptText),
  "old phrase-patch wording still present",
);

assert(
  "food policy lives in identity or reference only",
  !/workaround|regression|incident|conversation\s+\d{4,}/i.test(promptText),
  "food policy prompt contains bug-history wording",
);

assert(
  "booking start is delegated to doctrine, not examples",
  !/Send me the pickup area and delivery area and I.ll quote it\./.test(
    promptText,
  ),
  "old exact booking-start example still present",
);

console.log(`\n${failures.length === 0 ? "ALL PASS" : "FAILURES: " + failures.length}`);
if (failures.length > 0) process.exit(1);
