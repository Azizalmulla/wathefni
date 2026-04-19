#!/usr/bin/env node
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const mod = await loadTsModule("plugins/riders-tools/lib/pricing-resolver.ts");
const am = await loadTsModule("plugins/riders-tools/lib/area-matching.ts");
const { buildResolverLookupKeys, matchesResolverAlias } = mod;

const inputs = [
  "jlai3a",
  "Jlai3a",
  "Julai3a",
  "julai3a",
  "Jlea'a",
  "jleaa",
  "shalehat jlai3a",
  "Shalehat Jlea'a",
  "جليعة",
  "شاليهات جليعة",
];

for (const s of inputs) {
  const keys = [...buildResolverLookupKeys(s)].sort();
  console.log(`[${s}]`);
  keys.forEach((k) => console.log(`  ${k}`));
  console.log();
}

console.log("--- Cross-match check ---");
const pairs = [
  ["jlai3a", "Jlai3a"],
  ["Julai3a", "Jlai3a"],
  ["Julai3a", "Jlea'a"],
  ["jleaa", "Jlea'a"],
  ["Julai3a", "Shalehat Jlea'a"],
];
for (const [q, a] of pairs) {
  const qKeys = buildResolverLookupKeys(q);
  const ok = matchesResolverAlias(qKeys, a);
  console.log(`query=${q.padEnd(22)} alias=${a.padEnd(22)} → match=${ok}`);
}

console.log("\n--- Normalizer trace ---");
console.log("normalizeLatinAreaKey('Julai3a') =", JSON.stringify(am.normalizeLatinAreaKey("Julai3a")));
console.log("normalizeLatinAreaKey('Jlai3a')  =", JSON.stringify(am.normalizeLatinAreaKey("Jlai3a")));
console.log("normalizeLatinAreaKey('jlai3a')  =", JSON.stringify(am.normalizeLatinAreaKey("jlai3a")));
console.log("normalizeLatinAreaKey('Jlea\\'a') =", JSON.stringify(am.normalizeLatinAreaKey("Jlea'a")));
console.log("normalizeLatinAreaKey('jleaa')   =", JSON.stringify(am.normalizeLatinAreaKey("jleaa")));
