#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: carry_over_from_last_order end-to-end.
//
// Covers the three-layer fix for the "same names and number as last order"
// transcript bug (2026-04-19):
//
//   1. PROVENANCE — `dstSource: "carryover"` survives through
//      `applyBookingFieldPatch` and lands on the DST slot's `lastSource`.
//      This is what the summary renderer reads to mark carried-over lines.
//   2. CARRY-OVER PRIMITIVES — the building blocks (`applyBookingFieldPatch`
//      with `dstSource: "carryover"`) that the live `applyCarryOverOp` drain
//      uses:
//         a. fills sender+recipient from a saved profile,
//         b. skips stale/corrupt saved values (every field re-validated),
//         c. no-ops when there is no saved order.
//      Live-drain end-to-end coverage lives in
//      `smoke-test-carry-over-live-drain.mjs`.
//   3. ROUTE-RESET PARTITION — `createRouteResetDraft` preserves identity
//      fields and wipes route-scoped fields. `createRouteResetDialogState`
//      preserves identity slots and wipes route-scoped slots.
//
// Each test exits with a non-zero code on failure.
// ---------------------------------------------------------------------------

import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const {
  applyBookingFieldPatch,
  createEmptyBookingDraft,
  createRouteResetDraft,
  ROUTE_SCOPED_DRAFT_FIELDS,
} = await loadTsModule("plugins/shared/booking-draft.ts");

const {
  createEmptyDialogState,
  createRouteResetDialogState,
  IDENTITY_SLOT_NAMES,
  ROUTE_SCOPED_SLOT_NAMES,
} = await loadTsModule("plugins/shared/dialog-state.ts");

// -----------------------------
// 1. Provenance survives apply_booking_field with dstSource: "carryover"
// -----------------------------
{
  const draft = createEmptyBookingDraft();
  const dst = createEmptyDialogState();
  const result = applyBookingFieldPatch({
    draft,
    patch: { sender_name: "Aziz Almulla", sender_phone: "99118375" },
    whatsappNumber: "96599338566",
    dialogState: dst,
    dstSource: "carryover",
  });
  assert(result.draft.senderName === "Aziz Almulla", "T1 sender name not applied");
  assert(result.draft.senderPhone === "99118375", "T1 sender phone not applied");
  assert(result.dialogState, "T1 dialog state not returned");
  const slotName = result.dialogState.slots.sender_name;
  const slotPhone = result.dialogState.slots.sender_phone;
  assert(slotName?.lastSource === "carryover", `T1 sender_name lastSource=${slotName?.lastSource} (expected carryover)`);
  assert(slotPhone?.lastSource === "carryover", `T1 sender_phone lastSource=${slotPhone?.lastSource} (expected carryover)`);
  console.log("PASS T1 provenance: lastSource=carryover lands on DST slot records");
}

// -----------------------------
// 2. Stale saved phone is rejected by the clean helpers (the drain gate).
//    This confirms that if a saved number gets corrupted/shape-changed,
//    carry-over silently skips it rather than writing garbage.
// -----------------------------
{
  const draft = createEmptyBookingDraft();
  const dst = createEmptyDialogState();
  // Simulating a stale saved phone with letters (shouldn't exist, but
  // defensively tested). Running through applyBookingFieldPatch with the
  // corrupt value: `cleanPhone` will reject, so it should NOT land.
  const result = applyBookingFieldPatch({
    draft,
    patch: { sender_name: "Aziz", sender_phone: "not-a-phone-999" },
    whatsappNumber: "96599338566",
    dialogState: dst,
    dstSource: "carryover",
  });
  assert(result.draft.senderName === "Aziz", "T2 name should still apply");
  assert(result.draft.senderPhone == null, "T2 corrupt phone should NOT apply");
  assert(
    result.rejected.some((r) => r.field === "sender_phone"),
    "T2 rejection for sender_phone expected",
  );
  console.log("PASS T2 stale-field rejection: carryover phone with invalid shape skipped");
}

// -----------------------------
// 3. Route-reset partition: identity preserved, route scrubbed
// -----------------------------
{
  const filled = {
    ...createEmptyBookingDraft(),
    senderName: "Aziz Almulla",
    senderPhone: "99118375",
    recipientName: "Ahmad",
    recipientPhone: "59384581",
    pickupBlock: "5",
    pickupStreet: "7",
    pickupHouse: "19",
    pickupAvenue: "9",
    pickupExtra: "floor 2",
    deliveryBlock: "11",
    deliveryStreet: "7",
    deliveryHouse: "11",
    deliveryAvenue: null,
    deliveryExtra: null,
  };
  const reset = createRouteResetDraft(filled);
  assert(reset.senderName === "Aziz Almulla", "T3 senderName preserved");
  assert(reset.senderPhone === "99118375", "T3 senderPhone preserved");
  assert(reset.recipientName === "Ahmad", "T3 recipientName preserved");
  assert(reset.recipientPhone === "59384581", "T3 recipientPhone preserved");
  for (const f of ROUTE_SCOPED_DRAFT_FIELDS) {
    assert(reset[f] == null, `T3 route-scoped field ${f} should be null, got=${JSON.stringify(reset[f])}`);
  }
  console.log("PASS T3 route-reset draft: identity kept, route-scoped wiped");
}

// -----------------------------
// 4. Route-reset dialog state: identity slots preserved, route-scoped cleared
// -----------------------------
{
  // Build a DST with every slot filled.
  const now = Date.now();
  const slots = {};
  for (const n of [...IDENTITY_SLOT_NAMES, ...ROUTE_SCOPED_SLOT_NAMES]) {
    slots[n] = {
      value: `v-${n}`,
      status: "filled",
      lastSetTs: now,
      lastSource: n.startsWith("pickup") || n.startsWith("delivery") || n.endsWith("_area") ? "customer_fast_path" : "carryover",
    };
  }
  const before = { slots, requestedSlot: null, version: 1 };
  const after = createRouteResetDialogState(before);
  for (const n of IDENTITY_SLOT_NAMES) {
    assert(after.slots[n], `T4 identity slot ${n} should be preserved`);
    assert(after.slots[n]?.value === `v-${n}`, `T4 value of identity slot ${n} changed`);
  }
  for (const n of ROUTE_SCOPED_SLOT_NAMES) {
    assert(!after.slots[n], `T4 route-scoped slot ${n} should be cleared, got=${JSON.stringify(after.slots[n])}`);
  }
  assert(after.requestedSlot == null, "T4 requestedSlot should be null after reset");
  console.log("PASS T4 route-reset DST: identity slots kept, route-scoped cleared");
}

// -----------------------------
// 5. Reuse-intent classifier covers the transcript phrase
// -----------------------------
{
  const { classifyReuseIntent } = await loadTsModule("plugins/shared/reuse-intent.ts");
  const cases = [
    { text: "same names and number as last order", expect: ["sender_identity", "recipient_identity"], reason: "en_same_as_last" },
    { text: "Same Sender and recipient", expect: ["sender_identity", "recipient_identity"], reason: "en_same_sender_and_recipient" },
    { text: "use my last order", expect: ["sender_identity", "recipient_identity"], reason: "en_use_my_last" },
    { text: "same sender", expect: ["sender_identity"], reason: "en_same_sender" },
    { text: "same recipient", expect: ["recipient_identity"], reason: "en_same_recipient" },
    { text: "نفس الأسماء والأرقام", expect: ["sender_identity", "recipient_identity"], reason: "ar_same_names_and_numbers" },
    { text: "نفس المرسل", expect: ["sender_identity"], reason: "ar_same_sender" },
  ];
  for (const c of cases) {
    const r = classifyReuseIntent({ text: c.text, hasSavedOrder: true });
    assert(r.kind === "carry_over", `T5 expected carry_over for "${c.text}", got ${r.kind} (${r.reason})`);
    assert(
      JSON.stringify(r.buckets) === JSON.stringify(c.expect),
      `T5 expected buckets=${JSON.stringify(c.expect)} for "${c.text}", got ${JSON.stringify(r.buckets)}`,
    );
  }
  // No saved order → never fire.
  const none = classifyReuseIntent({ text: "same names and number as last order", hasSavedOrder: false });
  assert(none.kind === "none" && none.reason === "no_saved_order", "T5 hasSavedOrder=false should short-circuit");
  // Unrelated text → never fire.
  const unrelated = classifyReuseIntent({ text: "salwa to massayel", hasSavedOrder: true });
  assert(unrelated.kind === "none", `T5 unrelated text should return none, got ${unrelated.kind}`);
  console.log("PASS T5 reuse-intent classifier: EN + AR phrasings + negative cases");
}

console.log("ALL carry-over-from-last-order smoke tests passed.");
