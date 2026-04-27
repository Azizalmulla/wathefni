#!/usr/bin/env node
// Smoke test: requested-slot option binding.
//
// Short replies to an active area clarification must resolve inside the
// pending option set before any global Kuwait area search.

import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, {
    interopDefault: true,
  });
  return await jiti(path.join(root, relativePath));
}

const pricing = await loadTsModule("plugins/riders-tools/tools/pricing.ts");
const { resolveRequestedAreaOptionChoice } = pricing;

function expectResolved(name, query, options, expected) {
  const result = resolveRequestedAreaOptionChoice(query, options);
  assert.equal(
    result.status,
    "resolved",
    `${name}: expected resolved, got ${JSON.stringify(result)}`,
  );
  assert.equal(
    result.option,
    expected,
    `${name}: expected ${expected}, got ${JSON.stringify(result)}`,
  );
  console.log(`PASS ${name}`);
}

function expectAmbiguous(name, query, options, expectedOptions) {
  const result = resolveRequestedAreaOptionChoice(query, options);
  assert.equal(
    result.status,
    "ambiguous",
    `${name}: expected ambiguous, got ${JSON.stringify(result)}`,
  );
  assert.deepEqual(
    [...result.options].sort(),
    [...expectedOptions].sort(),
    `${name}: expected local ambiguous set ${JSON.stringify(expectedOptions)}, got ${JSON.stringify(result)}`,
  );
  console.log(`PASS ${name}`);
}

expectResolved(
  "North resolves within Sulaibikhat options",
  "North",
  ["Sulaibikhat", "Northwest Sulaibikhat", "Sulaibikhat Cemetery"],
  "Northwest Sulaibikhat",
);

expectResolved(
  "Northwest resolves within Sulaibikhat options",
  "Northwest",
  ["Sulaibikhat", "Northwest Sulaibikhat", "Sulaibikhat Cemetery"],
  "Northwest Sulaibikhat",
);

expectResolved(
  "res resolves within Wafra options",
  "res",
  ["Wafra", "Wafra Residential", "Wafra Farms"],
  "Wafra Residential",
);

expectResolved(
  "farms resolves within Wafra options",
  "farms",
  ["Wafra", "Wafra Residential", "Wafra Farms"],
  "Wafra Farms",
);

expectAmbiguous(
  "equally matching short reply stays inside local options",
  "nor",
  ["Northwest Sulaibikhat", "North West Jahra"],
  ["Northwest Sulaibikhat", "North West Jahra"],
);

console.log("requested-slot option binding smoke test passed");
