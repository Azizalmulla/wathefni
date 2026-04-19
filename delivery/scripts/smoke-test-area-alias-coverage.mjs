#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: enforce that the resolver overlay has non-trivial alias
// coverage for every published area, and that specific known-problematic
// inputs resolve to the right area / ambiguity group.
//
// This is the regression net for the "Jlai3a → Shalehat Jlea'a" class of
// bugs. It runs against the SAME pricing-resolver code that production
// uses, so a failure here is a production failure.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const jiti = require(
  path.join(ROOT, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
)(pathToFileURL(import.meta.url).href, { interopDefault: true });
const pr = await jiti(
  path.join(ROOT, "plugins/riders-tools/lib/pricing-resolver.ts"),
);
const { buildResolverLookupKeys, matchesResolverAlias, normalizePricingResolverConfig } = pr;

const OVERLAY_PATH = path.join(
  ROOT,
  "workspaces/riders/data/pricing.resolver.overlay.json",
);
const CATALOG_PATH = path.join(
  ROOT,
  "workspaces/riders/data/pricing.published.json",
);
const catalog = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
const overlay = JSON.parse(fs.readFileSync(OVERLAY_PATH, "utf8"));
const areas = catalog.areas || catalog;

// Minimum alias coverage: every area must have ≥1 alias or a canonical
// name with ≥3 Latin tokens. Numbered-suffix blocks (e.g. "Sabah Al-Ahmad 2")
// are exempt because they fold into their parent ambiguity group.
const areaAliasCounts = new Map();
for (const a of overlay.resolver?.aliases || []) {
  if (!a.area_id) continue;
  areaAliasCounts.set(a.area_id, (areaAliasCounts.get(a.area_id) || 0) + 1);
}

let failures = 0;
const fail = (msg) => {
  console.error("FAIL:", msg);
  failures += 1;
};
const ok = (msg) => console.log("ok  :", msg);

// --- Case 1: config validates against real normalizer -----------------------
try {
  const cfg = normalizePricingResolverConfig(overlay.resolver, areas);
  if (!cfg.aliases || cfg.aliases.length < 200) {
    fail(
      `overlay has suspiciously low alias count (${cfg.aliases?.length}); expected ≥200`,
    );
  } else {
    ok(`overlay validates; aliases=${cfg.aliases.length}, groups=${cfg.ambiguity_groups?.length}`);
  }
} catch (e) {
  fail(`overlay fails normalizePricingResolverConfig: ${e.message}`);
}

// --- Case 2: coverage — every non-numbered area has ≥1 alias OR multi-word -
// Exception: duplicate rows (same name_en + governorate + prices) are allowed
// to share one canonical entry since they're functionally interchangeable.
const NUMBERED_SUFFIX_RE = /[\s-]\d+$/;
const canonicalSignature = (a) =>
  `${(a.name_en || "").toLowerCase()}|${(a.governorate || "").toLowerCase()}|${a.sedan_normal}|${a.van_normal}`;
const signatureGroups = new Map();
for (const a of areas) {
  const sig = canonicalSignature(a);
  if (!signatureGroups.has(sig)) signatureGroups.set(sig, []);
  signatureGroups.get(sig).push(a);
}
const duplicateIds = new Set();
for (const [, group] of signatureGroups) {
  if (group.length > 1) {
    // Treat all but the first as duplicates — the resolver will route to
    // the first one, which has identical pricing.
    for (const dup of group.slice(1)) duplicateIds.add(dup.id);
  }
}

let coverageMisses = 0;
const uncoveredSamples = [];
for (const a of areas) {
  if (NUMBERED_SUFFIX_RE.test(a.name_en || "")) continue;
  if (duplicateIds.has(a.id)) continue;
  const cnt = areaAliasCounts.get(a.id) || 0;
  if (cnt === 0) {
    coverageMisses += 1;
    if (uncoveredSamples.length < 10) {
      uncoveredSamples.push(`${a.id}:${a.name_en}`);
    }
  }
}
if (coverageMisses > 0) {
  fail(
    `${coverageMisses} non-numbered, non-duplicate areas have zero aliases: ${uncoveredSamples.join(", ")}${coverageMisses > 10 ? " ..." : ""}`,
  );
} else {
  ok(
    `every non-numbered, non-duplicate area has ≥1 alias (duplicates excluded=${duplicateIds.size})`,
  );
}

// --- Case 3: known-problematic customer inputs resolve correctly ------------
// These are the inputs that caused real live bugs. They must resolve.
const aliases = overlay.resolver?.aliases || [];
const ambiguityGroups = overlay.resolver?.ambiguity_groups || [];

function resolve(query) {
  const qk = buildResolverLookupKeys(query);
  const areaHits = new Set();
  for (const a of aliases) {
    if (a.area_id && matchesResolverAlias(qk, a.alias)) {
      areaHits.add(a.area_id);
    }
  }
  const groupHits = new Set();
  for (const g of ambiguityGroups) {
    for (const al of g.aliases || []) {
      if (matchesResolverAlias(qk, al)) {
        groupHits.add(g.id);
        break;
      }
    }
  }
  return { areaHits: [...areaHits], groupHits: [...groupHits] };
}

const golden = [
  // The live bug that kicked off this whole plan
  { input: "Jlai3a", expect: { area: 194 } },
  { input: "jlai3a", expect: { area: 194 } },
  { input: "Jliaa", expect: { area: 194 } },
  // Shalehat category-stripped
  { input: "Dba3ya", expect: { area: 182 } },
  { input: "Kathma", expect: { area: 119 } },
  { input: "Ka6ma", expect: { area: 119 } },
  { input: "Bnider", expect: { area: 197 } },
  { input: "Nwaisib", expect: { area: 163 } },
  // Arabizi ع → 3 (slang seed)
  { input: "Sha3ab", expect: { area: 49 } },
  { input: "3youn", expect: { area: 65 } },
  { input: "Na3eem", expect: { area: 110 } },
  { input: "3adan", expect: { area: 126 } },
  { input: "3igaila", expect: { area: 134 } },
  { input: "3adailiya", expect: { area: 39 } },
  { input: "3abdali", expect: { area: 106 } },
  { input: "Di3iya", expect: { area: 37 } },
  // Arabizi ح → 7
  { input: "Sub7an", expect: { area: 127 } },
  { input: "Saba7 Ahmad", expect: { group: "sabah_al_ahmad" } },
  { input: "Saba7 Al Salem", expect: { group: "sabah_al_salem" } },
  // Arabizi خ → 5
  { input: "Shuw3i5", expect: { area: 42 } },
  { input: "Sulaibi5at", expect: { area: 23 } },
  // Regression: existing hand-curated aliases still work
  { input: "mshrf", expect: { area: 57 } },
  { input: "frwnya", expect: { area: 204 } },
  { input: "fhaheel", expect: { area: 160 } },
  { input: "mngf", expect: { area: 190 } },
  // Arabic variants
  { input: "الجليعة", expect: { area: 194 } },
  { input: "الجليعه", expect: { area: 194 } },
  { input: "جليعة", expect: { area: 194 } },
  // Negative: garbage must not resolve
  { input: "nonexistent-place-xyz", expect: { nothing: true } },
];

for (const c of golden) {
  const r = resolve(c.input);
  if (c.expect.nothing) {
    if (r.areaHits.length === 0 && r.groupHits.length === 0) {
      ok(`negative: ${JSON.stringify(c.input)} → no match`);
    } else {
      fail(`negative: ${JSON.stringify(c.input)} should not resolve, got areas=${r.areaHits} groups=${r.groupHits}`);
    }
    continue;
  }
  if (c.expect.area !== undefined) {
    if (r.areaHits.includes(c.expect.area)) {
      ok(`area: ${JSON.stringify(c.input)} → ${c.expect.area}`);
    } else {
      fail(
        `area: ${JSON.stringify(c.input)} expected area=${c.expect.area}, got areas=${r.areaHits} groups=${r.groupHits}`,
      );
    }
  }
  if (c.expect.group !== undefined) {
    if (r.groupHits.includes(c.expect.group)) {
      ok(`group: ${JSON.stringify(c.input)} → ${c.expect.group}`);
    } else {
      fail(
        `group: ${JSON.stringify(c.input)} expected group=${c.expect.group}, got areas=${r.areaHits} groups=${r.groupHits}`,
      );
    }
  }
}

if (failures > 0) {
  console.error(`\nFAIL — ${failures} checks failed`);
  process.exit(1);
}
console.log(`\nok — all area-alias coverage checks passed`);
