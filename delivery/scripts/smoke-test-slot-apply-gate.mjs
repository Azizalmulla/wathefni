#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — Phase 2 Milestone 2 slot-apply gate (SHADOW).
//
// DEPLOY_CANARY_SLOT_APPLY_GATE_MODULE_MARKER expected in the module
// header. Smoke covers:
//
//   1. Module canary present.
//   2. Exhaustive policy over every TurnIntentKind (drives off the schema
//      export so a new kind without a row fails loudly).
//   3. `carryover` source is always allowed.
//   4. Missing turn_intent → allow (turn_intent_missing).
//   5. Low-confidence turn_intent → allow (low_confidence).
//   6. Block-all kinds: unclear / acknowledgement / refused_or_stuck /
//      clarifying_question → block_all with the right reason.
//   7. Answer-like kinds with addressed_fields=[] → allow permissive.
//   8. Answer-like kinds with addressed_fields covering every patch field
//      → allow all_fields_addressed.
//   9. Answer-like kinds with addressed_fields NOT covering a patch field
//      → block_partial with the right blockedFields list.
//  10. Address-role mapping: block/street/house/avenue/extra with
//      `address_role=pickup` maps to `pickup_address`; `delivery` maps to
//      `delivery_address`; missing role → ungateable.
//  11. phone_decision maps to `sender_phone` token.
//  12. "route" token expands to pickup_area / dropoff_area.
//  13. Empty patch (only address_role, no data) → allow
//      empty_patch_after_meta_filter.
//  14. End-to-end regression: the 2026-04-22 pasted-operational-text case
//      — patch has sender_phone from an extracted 8-digit run, turn_intent
//      kind=unclear high → block_all.
//  15. formatSlotApplyGateShadowLog token shape.
//
// Run from `delivery/`:
//   node scripts/smoke-test-slot-apply-gate.mjs
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const MODULE_REL = "plugins/shared/slot-apply-gate.ts";
const SCHEMA_REL = "plugins/shared/proposer-schema.ts";

const modulePath = path.join(repoRoot, MODULE_REL);
const schemaPath = path.join(repoRoot, SCHEMA_REL);

const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
  cwd: repoRoot,
  stdio: "ignore",
});
const hasTsx = tsxCheck.status === 0;

if (!hasTsx) {
  // Source-level fallback: canary present + every kind has a policy row.
  const fs = await import("node:fs/promises");
  const [moduleSource, schemaSource] = await Promise.all([
    fs.readFile(modulePath, "utf8"),
    fs.readFile(schemaPath, "utf8"),
  ]);
  const canary = "DEPLOY_CANARY_SLOT_APPLY_GATE_MODULE_MARKER";
  if (!moduleSource.includes(canary)) {
    console.error(`FAIL: missing ${canary} in ${MODULE_REL}`);
    process.exit(1);
  }
  const kindMatches = Array.from(
    schemaSource.matchAll(
      /"(answered_full|answered_partial|answered_unasked|corrected_prior|clarifying_question|acknowledgement|refused_or_stuck|unclear)"/g,
    ),
  ).map((m) => m[1]);
  const uniqueKinds = Array.from(new Set(kindMatches));
  const missing = [];
  for (const k of uniqueKinds) {
    const pattern = new RegExp(`^\\s*${k}\\s*:`, "m");
    if (!pattern.test(moduleSource)) {
      missing.push(k);
    }
  }
  if (missing.length > 0) {
    console.error(
      `FAIL: policy missing rows for kinds: ${missing.join(", ")}`,
    );
    process.exit(1);
  }
  console.log(
    `[smoke-test-slot-apply-gate] OK (source-only mode; tsx not installed). Canary present, policy covers ${uniqueKinds.length} kinds.`,
  );
  process.exit(0);
}

if (!process.env.__SLOT_APPLY_GATE_SMOKE_TSX__) {
  const child = spawnSync(
    "node",
    ["--import", "tsx", fileURLToPath(import.meta.url)],
    {
      cwd: repoRoot,
      stdio: "inherit",
      env: { ...process.env, __SLOT_APPLY_GATE_SMOKE_TSX__: "1" },
    },
  );
  process.exit(child.status ?? 1);
}

const gateModule = await import(pathToFileURL(modulePath).href);
const proposerSchema = await import(pathToFileURL(schemaPath).href);

const {
  decideSlotApplyGate,
  formatSlotApplyGateShadowLog,
  extractDataFieldsFromPatch,
  countUngateablePatchFields,
  patchFieldToAddressedToken,
} = gateModule;
const { TURN_INTENT_KINDS } = proposerSchema;

const failures = [];
function check(name, cond, detail) {
  if (!cond) failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
}

// 3. Carryover always allowed.
{
  const res = decideSlotApplyGate({
    tiKind: "unclear",
    tiConfidence: "high",
    tiAddressedFields: [],
    proposalSource: "carryover",
    patch: { sender_phone: "55512345" },
  });
  check(
    "carryover_always_allowed",
    res.kind === "allow" && res.reason === "source_carryover_exempt",
    JSON.stringify(res),
  );
}

// 4. Missing turn_intent → allow.
{
  const res = decideSlotApplyGate({
    tiKind: null,
    tiConfidence: null,
    tiAddressedFields: null,
    proposalSource: "llm",
    patch: { sender_phone: "55512345" },
  });
  check(
    "missing_turn_intent_allows",
    res.kind === "allow" && res.reason === "turn_intent_missing",
    JSON.stringify(res),
  );
}

// 5. Low-confidence → allow.
{
  const res = decideSlotApplyGate({
    tiKind: "answered_full",
    tiConfidence: "low",
    tiAddressedFields: ["sender_phone"],
    proposalSource: "llm",
    patch: { sender_phone: "55512345" },
  });
  check(
    "low_confidence_allows",
    res.kind === "allow" && res.reason === "low_confidence",
    JSON.stringify(res),
  );
}

// 6. Block-all kinds.
const BLOCK_ALL_CASES = [
  ["unclear", "ti_kind_unclear"],
  ["acknowledgement", "ti_kind_acknowledgement"],
  ["refused_or_stuck", "ti_kind_refused_or_stuck"],
  ["clarifying_question", "ti_kind_clarifying_question"],
];
for (const [kind, expectedReason] of BLOCK_ALL_CASES) {
  const res = decideSlotApplyGate({
    tiKind: kind,
    tiConfidence: "high",
    tiAddressedFields: ["sender_phone"],
    proposalSource: "llm",
    patch: { sender_phone: "55512345" },
  });
  check(
    `block_all_${kind}`,
    res.kind === "block_all" && res.reason === expectedReason,
    JSON.stringify(res),
  );
}

// 7. Answer-like + addressed_fields=[] → permissive allow.
{
  const res = decideSlotApplyGate({
    tiKind: "answered_partial",
    tiConfidence: "high",
    tiAddressedFields: [],
    proposalSource: "llm",
    patch: { sender_phone: "55512345" },
  });
  check(
    "answered_empty_addressed_permissive",
    res.kind === "allow" && res.reason === "addressed_fields_empty_permissive",
    JSON.stringify(res),
  );
}

// 8. Answer-like + addressed_fields covers every field → all_fields_addressed.
{
  const res = decideSlotApplyGate({
    tiKind: "answered_full",
    tiConfidence: "high",
    tiAddressedFields: ["sender_name", "sender_phone"],
    proposalSource: "llm",
    patch: { sender_name: "Ahmad", sender_phone: "55512345" },
  });
  check(
    "answered_all_fields_addressed",
    res.kind === "allow" && res.reason === "all_fields_addressed",
    JSON.stringify(res),
  );
}

// 9. Answer-like with addressed_fields missing a patch field → block_partial.
{
  const res = decideSlotApplyGate({
    tiKind: "answered_partial",
    tiConfidence: "high",
    tiAddressedFields: ["sender_name"],
    proposalSource: "llm",
    patch: { sender_name: "Ahmad", recipient_phone: "55512345" },
  });
  check(
    "answered_partial_blocks_unrelated_field",
    res.kind === "block_partial" &&
      res.reason === "field_not_in_addressed" &&
      Array.isArray(res.blockedFields) &&
      res.blockedFields.includes("recipient_phone") &&
      res.allowedFields.includes("sender_name"),
    JSON.stringify(res),
  );
}

// 10. Address-role mapping.
{
  check(
    "address_block_pickup_maps_to_pickup_address",
    patchFieldToAddressedToken("address_block", "pickup") === "pickup_address",
  );
  check(
    "address_street_delivery_maps_to_delivery_address",
    patchFieldToAddressedToken("address_street", "delivery") ===
      "delivery_address",
  );
  check(
    "address_house_no_role_is_ungateable",
    patchFieldToAddressedToken("address_house", null) === null,
  );
}

// 11. phone_decision maps to sender_phone.
{
  check(
    "phone_decision_maps_to_sender_phone",
    patchFieldToAddressedToken("phone_decision", null) === "sender_phone",
  );
  const res = decideSlotApplyGate({
    tiKind: "answered_partial",
    tiConfidence: "high",
    tiAddressedFields: ["sender_phone"],
    proposalSource: "llm",
    patch: { phone_decision: "use_whatsapp" },
  });
  check(
    "phone_decision_allowed_when_sender_phone_addressed",
    res.kind === "allow" && res.reason === "all_fields_addressed",
    JSON.stringify(res),
  );
}

// 12. "route" expands to pickup_area / dropoff_area. We don't have area
// fields in BookingFieldPatch today, but the expansion is still
// testable via the decideSlotApplyGate path — it's a no-op here (no
// fields present), but the set expansion itself is exercised in case
// we extend the patch later. Cover instead with a direct patch whose
// address fields are tagged pickup (so the token is pickup_address,
// which is distinct from pickup_area — the expansion should NOT treat
// pickup_address as addressed just because route is present).
{
  const res = decideSlotApplyGate({
    tiKind: "answered_partial",
    tiConfidence: "high",
    tiAddressedFields: ["route"],
    proposalSource: "llm",
    patch: { address_block: "5", address_role: "pickup" },
  });
  check(
    "route_does_not_cover_pickup_address",
    res.kind === "block_partial" &&
      res.blockedFields.includes("address_block"),
    JSON.stringify(res),
  );
}

// 13. Empty patch (only address_role).
{
  const res = decideSlotApplyGate({
    tiKind: "answered_partial",
    tiConfidence: "high",
    tiAddressedFields: ["pickup_address"],
    proposalSource: "llm",
    patch: { address_role: "pickup" },
  });
  check(
    "empty_patch_after_meta_filter",
    res.kind === "allow" && res.reason === "empty_patch_after_meta_filter",
    JSON.stringify(res),
  );
}

// 14. Regression: pasted operational text with unclear classification
//     blocks the phone extraction that lifted "20260422" from a timestamp.
{
  const res = decideSlotApplyGate({
    tiKind: "unclear",
    tiConfidence: "high",
    tiAddressedFields: [],
    proposalSource: "llm",
    patch: { sender_phone: "20260422" },
  });
  check(
    "pasted_operational_text_blocked_unclear",
    res.kind === "block_all" && res.reason === "ti_kind_unclear",
    JSON.stringify(res),
  );
}

// Also via fast_path source — the fast-path extractor, if gated later,
// would see the same block.
{
  const res = decideSlotApplyGate({
    tiKind: "unclear",
    tiConfidence: "high",
    tiAddressedFields: [],
    proposalSource: "fast_path",
    patch: { sender_phone: "20260422" },
  });
  check(
    "pasted_operational_text_blocked_unclear_fast_path",
    res.kind === "block_all" && res.reason === "ti_kind_unclear",
    JSON.stringify(res),
  );
}

// 15. Format token shape.
{
  const line = formatSlotApplyGateShadowLog({
    conversation_id: "conv1",
    turn_id: "t-7",
    proposal_source: "llm",
    ti_kind: "answered_partial",
    ti_confidence: "high",
    ti_addressed_fields_count: 1,
    patch_data_fields_count: 2,
    ungateable_fields_count: 0,
    decision_kind: "block_partial",
    decision_reason: "field_not_in_addressed",
    blocked_fields: ["recipient_phone"],
    allowed_fields: ["sender_name"],
  });
  const expected = [
    "[slot-apply-gate/shadow]",
    "conversation=conv1",
    "turn_id=t-7",
    "source=llm",
    "ti_kind=answered_partial",
    "ti_confidence=high",
    "ti_addressed_count=1",
    "patch_fields_count=2",
    "ungateable_count=0",
    "decision=block_partial",
    "reason=field_not_in_addressed",
    "blocked=[recipient_phone]",
    "allowed=[sender_name]",
  ];
  for (const tok of expected) {
    check(
      `shadow_log_contains_${tok.replace(/\W+/g, "_")}`,
      line.includes(tok),
      `missing "${tok}" in line: ${line}`,
    );
  }
}

// 2. Exhaustive policy (deferred to last so the rest runs first). Every
//    TurnIntentKind must produce a non-undefined decision for a
//    representative patch + source combo.
for (const kind of TURN_INTENT_KINDS) {
  const res = decideSlotApplyGate({
    tiKind: kind,
    tiConfidence: "high",
    tiAddressedFields: ["sender_phone"],
    proposalSource: "llm",
    patch: { sender_phone: "55512345" },
  });
  check(
    `policy_returns_decision_${kind}`,
    res && (res.kind === "allow" || res.kind === "block_all" || res.kind === "block_partial"),
    `got ${JSON.stringify(res)}`,
  );
}

// Extraction + counter sanity.
{
  const dataFields = extractDataFieldsFromPatch({
    sender_name: "Ahmad",
    address_role: "pickup",
    recipient_phone: null,
  });
  check(
    "extractDataFieldsFromPatch_skips_meta_and_null",
    Array.isArray(dataFields) &&
      dataFields.length === 1 &&
      dataFields[0] === "sender_name",
    JSON.stringify(dataFields),
  );
}

{
  const ungateable = countUngateablePatchFields({
    address_block: "5",
    address_role: null,
  });
  check(
    "countUngateablePatchFields_counts_missing_role",
    ungateable === 1,
    `got ${ungateable}`,
  );
}

if (failures.length > 0) {
  console.error(
    `[smoke-test-slot-apply-gate] FAIL (${failures.length} failures):\n  - ${failures.join("\n  - ")}`,
  );
  process.exit(1);
}

console.log(
  `[smoke-test-slot-apply-gate] OK — policy covers ${TURN_INTENT_KINDS.length} kinds, block / partial / allow branches verified, pasted-text regression case blocks as ti_kind_unclear, log token shape verified.`,
);
process.exit(0);
