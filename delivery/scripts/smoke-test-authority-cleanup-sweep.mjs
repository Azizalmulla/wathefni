#!/usr/bin/env node
// Smoke test for the Authority Cleanup Sweep invariants that are cheap to
// exercise without a live Octopus turn.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

async function loadTsModule(relativePath) {
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const { hasRouteEvidence } = await loadTsModule(
  "plugins/shared/conversation-policy.ts",
);

function read(relativePath) {
  return readFileSync(path.join(root, relativePath), "utf8");
}

const cases = [
  ["Hello i want to order food", false],
  ["I need to order food", false],
  ["want to order", false],
  ["Salmiya to Zahra", true],
  ["pickup Salmiya to delivery Zahra", true],
  ["from Salmiya to Zahra", true],
  ["price from Khaldiya to Salmiya", true],
  ["من الخالدية الى السالمية", true],
];

for (const [text, expected] of cases) {
  assert.equal(
    hasRouteEvidence(text),
    expected,
    `route evidence mismatch for ${JSON.stringify(text)}`,
  );
  console.log(`PASS  hasRouteEvidence(${JSON.stringify(text)}) === ${expected}`);
}

const octopusIndex = read("plugins/octopus-channel/index.ts");
const toolGuards = read("plugins/riders-tools/tools/guards.ts");

assert.match(
  octopusIndex,
  /const RIDERS_SINGLE_LIFECYCLE_ENGINE = true;/,
  "octopus channel must always run the single lifecycle path",
);
assert.match(
  toolGuards,
  /const RIDERS_SINGLE_LIFECYCLE_ENGINE = true;/,
  "tool guards must always demote legacy booking gates",
);
assert.match(
  octopusIndex,
  /final snapshot reply owns outbound decision/,
  "post-drain outbound decision must be owned by final snapshot reply",
);
assert.doesNotMatch(
  octopusIndex,
  /const postDecision = decidePostStateOutbound\(/,
  "octopus path must not call post-state outbound decision",
);
console.log("PASS  single lifecycle is the only runtime booking path");

console.log("\nAuthority cleanup sweep smoke assertions passed.");
