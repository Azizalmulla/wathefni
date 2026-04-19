#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Rule-based alias generator for pricing.resolver.overlay.json.
//
// Goal: for every area in pricing.published.json, mechanically derive the
// common colloquial/Arabizi/misspelled forms that a Kuwaiti customer might
// type on WhatsApp, so the deterministic resolver pipeline hits an alias
// *before* it has to fall through to fuzzy matching or embeddings.
//
// Design principles
// -----------------
// 1. Rule-based, not LLM-based. Every alias produced here is explainable
//    from the canonical name + a named rule. Auditable line-by-line.
// 2. Don't generate aliases that would collide with a *different* area's
//    canonical lookup keys — the linter rejects those.
// 3. Generate in both scripts: a Latin alias covers customers typing in
//    English/Arabizi; an Arabic alias covers customers typing in Arabic.
//    The resolver treats Latin and Arabic lookup keys as separate worlds,
//    so we need both sides populated.
// 4. Emit a *patch*, not an overwrite. The output is a JSON patch the human
//    reviews before it's merged into the overlay file.
//
// Rules applied (per area)
// ------------------------
//  L1  Latin exact   — the published name_en as typed.
//  L2  Latin no Al-  — drop "Al-", "Al ", leading "The ".
//  L3  Latin no cat  — drop leading category words: Shalehat, Mina, Madinat,
//                      Jazirat, Dahiyat.
//  L4  Latin Arabizi — swap back common phonemes: kh→5, ha→7 (in ح-words),
//                      '→2 when the AR label has ء. We do NOT inject 3 for
//                      ع positionally — real Arabizi forms like `Jlai3a` are
//                      phonetic reshuffles, not substitutions, and belong in
//                      the hand-curated slang seed instead.
//  L6  Latin no space— concatenated form ("sabahalsalem").
//
//  A1  Arabic exact  — name_ar as published.
//  A2  Arabic no ال  — strip definite article from every token.
//  A3  Arabic no cat — drop leading category words: شاليهات، ميناء،
//                      مدينة، جزيرة، ضاحية.
//  A4  Arabic common — apply common WhatsApp-keyboard mis-spellings:
//                      ة↔ه, ى↔ي, أ/إ/آ↔ا.
//
// Every generated alias is stamped with its rule id in the patch so the
// human reviewer can eyeball whole rule classes at a time.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const CATALOG_PATH = path.join(ROOT, "workspaces/riders/data/pricing.published.json");
const OVERLAY_PATH = path.join(ROOT, "workspaces/riders/data/pricing.resolver.overlay.json");
const SLANG_PATH = path.join(ROOT, "workspaces/riders/data/pricing.resolver.slang-aliases.seed.json");
const OUT_PATH = path.join(ROOT, "workspaces/riders/data/pricing.resolver.overlay.aliases.generated.json");

// ---------- Load catalog + existing overlay ---------------------------------
const catalog = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
const areas = catalog.areas || catalog;
const overlay = JSON.parse(fs.readFileSync(OVERLAY_PATH, "utf8"));

// Normalize helpers that mirror the resolver's lookup-key logic so we can
// predict collisions before writing an alias.
function stripDefAr(s) {
  return s
    .split(/\s+/)
    .map((t) => t.replace(/^ال/, ""))
    .filter(Boolean)
    .join(" ")
    .trim();
}
function normAr(s) {
  return s
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/\s+/g, " ")
    .trim();
}
function normLatinToken(tok) {
  return tok
    .replace(/^el(?=[a-z])/g, "al")
    .replace(/ph/g, "f")
    .replace(/ou/g, "u")
    .replace(/oo+/g, "u")
    .replace(/ee+/g, "i")
    .replace(/ii+/g, "i")
    .replace(/yy+/g, "i")
    .replace(/y/g, "i")
    .replace(/aa+/g, "a")
    .replace(/ei/g, "ai")
    .replace(/q/g, "g")
    .replace(/([a-z])\1+/g, "$1")
    .replace(/ah$/g, "a")
    .replace(/iya$/g, "ia")
    .replace(/ieh$/g, "ia")
    .replace(/^(?:al|el)$/g, "");
}
function normLatin(s) {
  return s
    .toLowerCase()
    .replace(/['’`]/g, "")
    .replace(/5/g, "kh")
    .replace(/7/g, "ha")
    .replace(/8/g, "gh")
    .replace(/6/g, "t")
    .replace(/9/g, "s")
    .replace(/[23]/g, "a")
    .replace(/[^a-z\s]/g, " ")
    .split(/\s+/)
    .map(normLatinToken)
    .filter(Boolean)
    .join(" ")
    .trim();
}

// Resolver lookup keys (mirrors buildResolverLookupKeys in pricing-resolver.ts).
function lookupKeys(raw) {
  const keys = new Set();
  const trimmed = String(raw || "").trim();
  if (!trimmed) return keys;
  keys.add(`fuzzy:${trimmed}`);
  keys.add(`canon:${trimmed}`);

  const isArabic = /[\u0600-\u06FF]/.test(trimmed);
  if (isArabic) {
    const normalized = normAr(trimmed);
    keys.add(`fuzzy:${normalized}`);
    keys.add(`canon:${normalized}`);
    const stripped = stripDefAr(normalized);
    if (stripped && stripped !== normalized) {
      keys.add(`fuzzy:${stripped}`);
      keys.add(`canon:${stripped}`);
    }
  } else {
    const en = trimmed.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();
    if (en) keys.add(`en:${en}`);
    const lat = normLatin(trimmed);
    if (lat) keys.add(`latin:${lat}`);
  }
  return keys;
}

// ---------- Rule implementations --------------------------------------------

const CATEGORY_PREFIXES_EN = [
  "Shalehat ",
  "Mina ",
  "Madinat ",
  "Jazirat ",
  "Dahiyat ",
  "Dahiya ",
  "The ",
];
const CATEGORY_PREFIXES_AR = [
  "شاليهات ",
  "ميناء ",
  "مينا ",
  "مدينة ",
  "جزيرة ",
  "ضاحية ",
  "منطقة ",
];

function rulesLatin(nameEn, nameAr) {
  const out = [];
  if (!nameEn) return out;
  const raw = nameEn.trim();

  // Numbered-suffix areas ("Shuwaikh Industrial-1", "Al Mutlaa Residential 2",
  // "South Saad Al-Abdulla 3") must NOT get generic Latin aliases, because
  // the resolver's Latin normalization strips trailing digits and the ambiguity
  // group (e.g. `shuwaikh`, `mutlaa`, `saad_abdullah`) needs to handle these.
  // The existing pricing_groups / ambiguity_groups cover the disambiguation UX.
  const isNumberedSuffix = /[\s-]\d+$/.test(raw);
  if (isNumberedSuffix) {
    // Skip all Latin alias rules for numbered-suffix areas. Every rule
    // produces a lookup key that either collides with a sibling block or
    // with the bare parent name (e.g. "Shuwaikh Industrial") which MUST
    // route to the ambiguity group, not directly into block 1. The primary
    // catalog already exposes these rows for exact-canonical-name lookup.
    return out;
  }

  // L1 — exact
  out.push({ rule: "L1", alias: raw });

  // L2 — drop Al-/Al /The
  const noAl = raw
    .replace(/^The\s+/i, "")
    .replace(/^Al[-\s]+/i, "")
    .replace(/\s+Al[-\s]+/gi, " ")
    .trim();
  if (noAl && noAl !== raw) out.push({ rule: "L2", alias: noAl });

  // L3 — drop category prefix
  for (const cat of CATEGORY_PREFIXES_EN) {
    if (raw.toLowerCase().startsWith(cat.toLowerCase())) {
      const stripped = raw.slice(cat.length).trim();
      if (stripped) out.push({ rule: "L3", alias: stripped });
      break;
    }
  }

  // L4 — Arabizi digit form. We look at the AR label to decide which
  // digits to inject back into the Latin form.
  //   ع / ء  →  3 / 2  at positions where the AR source has them.
  //   خ      →  5
  //   ح      →  7
  //   ق / ك (when transliterated as q/k) → 8
  //   ش      →  often sh; leave alone (no unambiguous Arabizi digit).
  // We apply the simpler blanket variant: swap every 'kh' → '5', every
  // 'ha' → '7' in ح-originating words (detected from AR label containing ح).
  const ar = (nameAr || "").trim();
  if (ar) {
    let arabizi = raw;
    if (ar.includes("خ") && /kh/i.test(arabizi)) {
      arabizi = arabizi.replace(/kh/gi, "5");
    }
    if (ar.includes("ح") && /ha/i.test(arabizi)) {
      // Only swap the first 'ha' to 7 to avoid turning Sabah→Sab7; apply
      // to whole-word 'hah' pattern instead.
      arabizi = arabizi.replace(/\bha/gi, "7");
    }
    if (ar.includes("ء") && /'/.test(arabizi)) {
      arabizi = arabizi.replace(/'/g, "2");
    }
    if (arabizi !== raw && arabizi.length > 0) {
      out.push({ rule: "L4", alias: arabizi });
    }
  }

  const tokens = noAl.split(/\s+/).filter(Boolean);

  // L6 — no-space form (for multi-token names)
  if (tokens.length > 1) {
    const joined = tokens.join("").toLowerCase();
    if (joined.length >= 4) out.push({ rule: "L6", alias: joined });
  }

  return out;
}

function rulesArabic(nameAr, nameEn) {
  const out = [];
  if (!nameAr) return out;
  const raw = nameAr.trim();

  // Numbered-suffix Arabic labels (e.g. "الشويخ الصناعية 3") are excluded
  // for the same reason as the Latin side: the resolver's normalization
  // treats trailing digits as non-distinguishing, so aliases for these
  // rows would override the ambiguity-group routing that the tests and
  // DST layer both rely on.
  const enForCheck = String(nameEn || "").trim();
  if (/[\s-]\d+$/.test(raw) || /[\s-]\d+$/.test(enForCheck)) {
    return out;
  }

  // A1 — exact
  out.push({ rule: "A1", alias: raw });

  // A2 — drop ال from every token
  const noAl = stripDefAr(raw);
  if (noAl && noAl !== raw) out.push({ rule: "A2", alias: noAl });

  // A3 — drop category prefix
  for (const cat of CATEGORY_PREFIXES_AR) {
    if (raw.startsWith(cat)) {
      const stripped = raw.slice(cat.length).trim();
      if (stripped) out.push({ rule: "A3", alias: stripped });
      break;
    }
  }

  // A4 — common keyboard mis-spellings
  const alt = raw
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي");
  if (alt !== raw) out.push({ rule: "A4", alias: alt });

  return out;
}

// ---------- Collision detection ---------------------------------------------
// For each area, build the canonical lookup-key footprint. An alias for area
// A must not produce any key that is already owned by area B.

const footprintByArea = new Map();   // areaId -> Set<key>
const keyToOwner = new Map();        // key -> areaId (first one wins)
for (const a of areas) {
  const keys = new Set();
  for (const seed of [a.name_en, a.name_ar]) {
    if (!seed) continue;
    for (const k of lookupKeys(seed)) keys.add(k);
  }
  footprintByArea.set(a.id, keys);
  for (const k of keys) {
    if (!keyToOwner.has(k)) keyToOwner.set(k, a.id);
  }
}

// Existing overlay aliases are also owned.
for (const entry of overlay.resolver.aliases || []) {
  if (!entry.area_id) continue;
  for (const k of lookupKeys(entry.alias)) {
    if (!keyToOwner.has(k)) keyToOwner.set(k, entry.area_id);
  }
}

function collidesWithDifferentArea(areaId, alias) {
  const keys = lookupKeys(alias);
  for (const k of keys) {
    const owner = keyToOwner.get(k);
    if (owner && owner !== areaId) {
      return { key: k, owner };
    }
  }
  return null;
}

// ---------- Generate aliases ------------------------------------------------

const generatedAliases = [];
const skipped = [];
const existingLookup = new Set();
for (const entry of overlay.resolver.aliases || []) {
  if (entry.area_id) {
    existingLookup.add(`${entry.area_id}|${entry.alias.toLowerCase()}`);
  }
}

const stats = { accepted: 0, skipped_collision: 0, skipped_dup: 0 };
const byRule = {};

// Load slang seed and bucket entries by area_id / ambiguity_group_id /
// pricing_group_id so we can merge them into the right target during the
// main loop (for area_id) and emit them separately for group-scoped ones.
const slangSeed = (() => {
  try {
    return JSON.parse(fs.readFileSync(SLANG_PATH, "utf8"));
  } catch {
    return { entries: [] };
  }
})();
const slangByAreaId = new Map();
const slangGroupEntries = [];
for (const entry of slangSeed.entries || []) {
  const aliases = Array.isArray(entry.aliases) ? entry.aliases : [];
  if (entry.area_id) {
    if (!slangByAreaId.has(entry.area_id)) slangByAreaId.set(entry.area_id, []);
    for (const s of aliases) {
      slangByAreaId.get(entry.area_id).push({ rule: "S", alias: s, _slang_source: entry._source });
    }
  } else if (entry.ambiguity_group_id || entry.pricing_group_id) {
    slangGroupEntries.push(entry);
  }
}

for (const area of areas) {
  const latin = rulesLatin(area.name_en, area.name_ar);
  const arabic = rulesArabic(area.name_ar, area.name_en);
  const slang = slangByAreaId.get(area.id) || [];
  const candidates = [...latin, ...arabic, ...slang];

  for (const c of candidates) {
    if (!c.alias || !c.alias.trim()) continue;
    const normalized = c.alias.trim();
    const dupKey = `${area.id}|${normalized.toLowerCase()}`;
    if (existingLookup.has(dupKey)) {
      stats.skipped_dup += 1;
      continue;
    }
    const collision = collidesWithDifferentArea(area.id, normalized);
    if (collision) {
      stats.skipped_collision += 1;
      skipped.push({
        area_id: area.id,
        name_en: area.name_en,
        alias: normalized,
        rule: c.rule,
        reason: `collides with area ${collision.owner} on ${collision.key}`,
      });
      continue;
    }
    // Record it as an owner so later candidates for other areas don't also
    // claim this key.
    for (const k of lookupKeys(normalized)) {
      if (!keyToOwner.has(k)) keyToOwner.set(k, area.id);
    }
    existingLookup.add(dupKey);
    generatedAliases.push({
      alias: normalized,
      area_id: area.id,
      _source_rule: c.rule,
      _area_name_en: area.name_en,
      _area_name_ar: area.name_ar,
    });
    stats.accepted += 1;
    byRule[c.rule] = (byRule[c.rule] || 0) + 1;
  }
}

// ---------- Group-scoped slang entries (ambiguity_group / pricing_group) ----
// These don't belong to a specific area_id, so we can't collision-check them
// against a single area's footprint. Instead, we reject them only if they'd
// collide with an existing *area_id-owned* key. We also dedupe against any
// existing group aliases in the overlay.

const generatedGroupAliases = [];
const existingGroupAliasKeys = new Set();
for (const group of (overlay.resolver.ambiguity_groups || [])) {
  for (const a of (group.aliases || [])) {
    existingGroupAliasKeys.add(`${group.id}|${a.toLowerCase()}`);
  }
}
for (const group of (overlay.resolver.pricing_groups || [])) {
  for (const a of (group.aliases || [])) {
    existingGroupAliasKeys.add(`${group.id}|${a.toLowerCase()}`);
  }
}
for (const entry of slangGroupEntries) {
  const groupId = entry.ambiguity_group_id || entry.pricing_group_id;
  const groupKind = entry.ambiguity_group_id ? "ambiguity_group_id" : "pricing_group_id";
  const aliases = Array.isArray(entry.aliases) ? entry.aliases : [];
  for (const raw of aliases) {
    const normalized = String(raw).trim();
    if (!normalized) continue;
    if (existingGroupAliasKeys.has(`${groupId}|${normalized.toLowerCase()}`)) {
      stats.skipped_dup += 1;
      continue;
    }
    // Collision with a specific area's canonical footprint would confuse
    // the resolver. Reject.
    const keys = lookupKeys(normalized);
    let collidesAreaId = null;
    for (const k of keys) {
      const owner = keyToOwner.get(k);
      if (owner) { collidesAreaId = owner; break; }
    }
    if (collidesAreaId) {
      stats.skipped_collision += 1;
      skipped.push({
        [groupKind]: groupId,
        alias: normalized,
        rule: "S-group",
        reason: `collides with area ${collidesAreaId}`,
      });
      continue;
    }
    existingGroupAliasKeys.add(`${groupId}|${normalized.toLowerCase()}`);
    generatedGroupAliases.push({
      alias: normalized,
      [groupKind]: groupId,
      _source_rule: "S",
      _slang_source: entry._source,
    });
    stats.accepted += 1;
    byRule["S-group"] = (byRule["S-group"] || 0) + 1;
  }
}

// ---------- Coverage report -------------------------------------------------

const accepted = new Map();   // areaId -> array
for (const a of generatedAliases) {
  if (!accepted.has(a.area_id)) accepted.set(a.area_id, []);
  accepted.get(a.area_id).push(a);
}

const coverage = {
  total_areas: areas.length,
  areas_with_any_new_alias: accepted.size,
  areas_with_latin_alias: 0,
  areas_with_arabic_alias: 0,
  areas_uncovered: [],
};
for (const area of areas) {
  const mine = accepted.get(area.id) || [];
  const existing = (overlay.resolver.aliases || []).filter((e) => e.area_id === area.id);
  const all = [...mine, ...existing];
  const hasLatin = all.some((a) => !/[\u0600-\u06FF]/.test(a.alias));
  const hasArabic = all.some((a) => /[\u0600-\u06FF]/.test(a.alias));
  if (hasLatin) coverage.areas_with_latin_alias += 1;
  if (hasArabic) coverage.areas_with_arabic_alias += 1;
  if (!hasLatin || !hasArabic) {
    coverage.areas_uncovered.push({
      id: area.id,
      name_en: area.name_en,
      name_ar: area.name_ar,
      hasLatin,
      hasArabic,
    });
  }
}

// ---------- Emit patch ------------------------------------------------------

const patch = {
  _meta: {
    generator: "scripts/generate-area-aliases.mjs",
    generated_at: new Date().toISOString(),
    source_catalog: path.relative(ROOT, CATALOG_PATH),
    source_overlay: path.relative(ROOT, OVERLAY_PATH),
    stats,
    by_rule: byRule,
    coverage,
  },
  _skipped_for_collision: skipped,
  new_aliases: generatedAliases,
  new_group_aliases: generatedGroupAliases,
};
fs.writeFileSync(OUT_PATH, JSON.stringify(patch, null, 2));

console.log("=== alias generator ===");
console.log("accepted:", stats.accepted);
console.log("skipped(dup):", stats.skipped_dup);
console.log("skipped(collision):", stats.skipped_collision);
console.log("by_rule:", byRule);
console.log("coverage:", {
  total_areas: coverage.total_areas,
  with_latin: coverage.areas_with_latin_alias,
  with_arabic: coverage.areas_with_arabic_alias,
  uncovered: coverage.areas_uncovered.length,
});
console.log("wrote:", path.relative(ROOT, OUT_PATH));
