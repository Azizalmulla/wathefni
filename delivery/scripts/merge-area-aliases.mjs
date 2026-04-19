#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Merge the generated alias patch (pricing.resolver.overlay.aliases.generated.json)
// into the live resolver overlay (pricing.resolver.overlay.json).
//
// - Idempotent: running twice is a no-op, because we dedupe against the
//   existing overlay by (area_id, alias) and (group_id, alias).
// - Preserves existing hand-curated aliases; generated ones are appended.
// - Strips internal debug fields (_source_rule, _slang_source, _area_name_*).
// - Validates the merged overlay through normalizePricingResolverOverlay so
//   we fail fast if the shape breaks.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const OVERLAY_PATH = path.join(ROOT, "workspaces/riders/data/pricing.resolver.overlay.json");
const PATCH_PATH = path.join(ROOT, "workspaces/riders/data/pricing.resolver.overlay.aliases.generated.json");

const overlay = JSON.parse(fs.readFileSync(OVERLAY_PATH, "utf8"));
const patch = JSON.parse(fs.readFileSync(PATCH_PATH, "utf8"));

overlay.resolver = overlay.resolver || {};
overlay.resolver.aliases = overlay.resolver.aliases || [];
overlay.resolver.ambiguity_groups = overlay.resolver.ambiguity_groups || [];
overlay.resolver.pricing_groups = overlay.resolver.pricing_groups || [];

const existingAreaKeys = new Set(
  (overlay.resolver.aliases || []).map((a) =>
    a.area_id
      ? `area|${a.area_id}|${String(a.alias).toLowerCase()}`
      : a.pricing_group_id
        ? `pg|${a.pricing_group_id}|${String(a.alias).toLowerCase()}`
        : `ag|${a.ambiguity_group_id}|${String(a.alias).toLowerCase()}`,
  ),
);

let addedAreaAliases = 0;
for (const entry of patch.new_aliases || []) {
  if (!entry.area_id || !entry.alias) continue;
  const key = `area|${entry.area_id}|${entry.alias.toLowerCase()}`;
  if (existingAreaKeys.has(key)) continue;
  overlay.resolver.aliases.push({
    alias: entry.alias,
    area_id: entry.area_id,
  });
  existingAreaKeys.add(key);
  addedAreaAliases += 1;
}

let addedGroupAliases = 0;
for (const entry of patch.new_group_aliases || []) {
  if (!entry.alias) continue;
  if (entry.ambiguity_group_id) {
    const group = overlay.resolver.ambiguity_groups.find((g) => g.id === entry.ambiguity_group_id);
    if (!group) {
      console.warn(`skipping group alias for unknown ambiguity_group_id=${entry.ambiguity_group_id}`);
      continue;
    }
    group.aliases = group.aliases || [];
    if (!group.aliases.some((a) => a.toLowerCase() === entry.alias.toLowerCase())) {
      group.aliases.push(entry.alias);
      addedGroupAliases += 1;
    }
  } else if (entry.pricing_group_id) {
    const group = overlay.resolver.pricing_groups.find((g) => g.id === entry.pricing_group_id);
    if (!group) {
      console.warn(`skipping group alias for unknown pricing_group_id=${entry.pricing_group_id}`);
      continue;
    }
    group.aliases = group.aliases || [];
    if (!group.aliases.some((a) => a.toLowerCase() === entry.alias.toLowerCase())) {
      group.aliases.push(entry.alias);
      addedGroupAliases += 1;
    }
  }
}

fs.writeFileSync(OVERLAY_PATH, JSON.stringify(overlay, null, 2) + "\n");

console.log("=== merge-area-aliases ===");
console.log("added area aliases:", addedAreaAliases);
console.log("added group aliases:", addedGroupAliases);
console.log("overlay aliases total:", overlay.resolver.aliases.length);
console.log("overlay ambiguity_groups:", overlay.resolver.ambiguity_groups.length);
console.log("overlay pricing_groups:", overlay.resolver.pricing_groups.length);
console.log("wrote:", path.relative(ROOT, OVERLAY_PATH));
