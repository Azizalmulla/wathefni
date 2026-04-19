#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the Dialog State Tracking (DST) core module.
//
// Exercises the pure-function slot register:
//   1. createEmptyDialogState starts empty
//   2. updateSlot fills an unfilled slot (action "accepted")
//   3. Same value on a filled slot → "unchanged"
//   4. Different value on a filled slot → "conflict" (slot NOT overwritten)
//   5. Re-asserting the filled value resolves the conflict
//   6. Picking the conflictCandidate resolves the conflict to the new value
//   7. Null value on a filled slot clears it ("cleared")
//   8. setRequestedSlot / clearRequestedSlot round-trip
//   9. routeToRequested: LLM writes to slot X while we asked for Y → routed
//      with action "routed_to_requested" when the incoming value would have
//      filled Y anyway
//  10. Filling the requested slot auto-clears requestedSlot
//  11. mirrorDialogStateToDraft projects filled values onto the draft shape
//  12. seedDialogStateFromDraft reconstructs DST from a legacy draft
//  13. slotNameForBookingField translates booking-field+role → SlotName
//  14. deriveRequestedSlotFromMissing picks the first concrete missing marker
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

const dst = await loadTsModule("plugins/shared/dialog-state.ts");
const { createEmptyBookingDraft } = await loadTsModule("plugins/shared/conversation-policy.ts");

const {
  createEmptyDialogState,
  getSlot,
  setRequestedSlot,
  clearRequestedSlot,
  updateSlot,
  mirrorDialogStateToDraft,
  seedDialogStateFromDraft,
  slotNameForBookingField,
  deriveRequestedSlotFromMissing,
  ALL_SLOT_NAMES,
} = dst;

// --- 1: empty state ---------------------------------------------------------
{
  const s = createEmptyDialogState();
  assert(s.version === 1, "1: version is 1");
  assert(!s.requestedSlot, "1: requestedSlot starts null");
  assert(Object.keys(s.slots).length === 0, "1: slots starts empty");
  const slot = getSlot(s, "sender_name");
  assert(slot.status === "unfilled", "1: getSlot on empty returns unfilled");
  assert(slot.value === null, "1: getSlot on empty has null value");
}

// --- 2: fill unfilled slot --------------------------------------------------
{
  let s = createEmptyDialogState();
  const res = updateSlot(s, "sender_name", "Aziz", "llm_apply");
  assert(res.decision.action === "accepted", "2: action accepted");
  assert(res.decision.previousValue === null, "2: previousValue is null");
  assert(res.state.slots.sender_name.value === "Aziz", "2: value stored");
  assert(res.state.slots.sender_name.status === "filled", "2: status filled");
}

// --- 3: same value → unchanged ---------------------------------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_name", "Aziz", "llm_apply").state;
  const res = updateSlot(s, "sender_name", "Aziz", "llm_apply");
  assert(res.decision.action === "unchanged", "3: same value unchanged");
  assert(res.state.slots.sender_name.value === "Aziz", "3: value preserved");
  // Trim/case fold
  const res2 = updateSlot(s, "sender_name", " aziz ", "llm_apply");
  assert(res2.decision.action === "unchanged", "3: trim/case equal → unchanged");
}

// --- 4: different value → conflict (slot not overwritten) ------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_phone", "96597485757", "llm_apply").state;
  const res = updateSlot(s, "sender_phone", "96560000000", "llm_apply");
  assert(res.decision.action === "conflict", "4: conflict");
  assert(res.decision.filledValue === "96597485757", "4: filled preserved");
  assert(res.decision.incomingValue === "96560000000", "4: incoming reported");
  const slot = res.state.slots.sender_phone;
  assert(slot.status === "conflict", "4: status conflict");
  assert(slot.value === "96597485757", "4: value still old");
  assert(slot.conflictCandidate === "96560000000", "4: candidate recorded");
}

// --- 5: re-assert filled value resolves conflict ---------------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_phone", "96597485757", "llm_apply").state;
  s = updateSlot(s, "sender_phone", "96560000000", "llm_apply").state; // conflict
  const res = updateSlot(s, "sender_phone", "96597485757", "customer_fast_path");
  assert(res.decision.action === "accepted", "5: resolve to filled → accepted");
  const slot = res.state.slots.sender_phone;
  assert(slot.status === "filled", "5: status back to filled");
  assert(slot.value === "96597485757", "5: filled value kept");
  assert(!slot.conflictCandidate, "5: candidate cleared");
}

// --- 6: pick candidate resolves conflict to new value ----------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_phone", "96597485757", "llm_apply").state;
  s = updateSlot(s, "sender_phone", "96560000000", "llm_apply").state; // conflict
  const res = updateSlot(s, "sender_phone", "96560000000", "customer_fast_path");
  assert(res.decision.action === "accepted", "6: accept candidate");
  assert(res.state.slots.sender_phone.value === "96560000000", "6: candidate is now filled");
  assert(res.state.slots.sender_phone.status === "filled", "6: status filled");
}

// --- 7: null value clears filled slot --------------------------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_name", "Aziz", "llm_apply").state;
  const res = updateSlot(s, "sender_name", null, "llm_apply");
  assert(res.decision.action === "cleared", "7: cleared");
  assert(res.decision.previousValue === "Aziz", "7: previous reported");
  assert(!res.state.slots.sender_name, "7: slot removed");
}

// --- 8: requestedSlot set/clear --------------------------------------------
{
  const s = createEmptyDialogState();
  const s2 = setRequestedSlot(s, { name: "dropoff_area", options: ["Sabah Al-Salem"], askedTs: 123 });
  assert(s2.requestedSlot?.name === "dropoff_area", "8: requested set");
  const s3 = clearRequestedSlot(s2);
  assert(s3.requestedSlot === null, "8: requested cleared");
}

// --- 9: routeToRequested routes wrong-slot write to requested --------------
{
  let s = createEmptyDialogState();
  s = setRequestedSlot(s, { name: "dropoff_area", options: ["Sabah Al-Salem"], askedTs: Date.now() });
  // LLM writes pickup_area but we asked for dropoff_area; evidence (caller)
  // already decided it's valid for dropoff → pass routeToRequested: true.
  const res = updateSlot(s, "pickup_area", "Sabah Al-Salem", "llm_apply", { routeToRequested: true });
  assert(res.decision.action === "routed_to_requested", "9: routed_to_requested");
  assert(res.decision.intendedSlot === "pickup_area", "9: intended logged");
  assert(res.decision.requestedSlot === "dropoff_area", "9: requested logged");
  assert(res.state.slots.dropoff_area?.value === "Sabah Al-Salem", "9: filled dropoff");
  assert(!res.state.slots.pickup_area, "9: pickup untouched");
  assert(res.state.requestedSlot === null, "9: requested cleared");
}

// --- 10: filling requested slot auto-clears requestedSlot ------------------
{
  let s = createEmptyDialogState();
  s = setRequestedSlot(s, { name: "sender_phone", options: null, askedTs: Date.now() });
  const res = updateSlot(s, "sender_phone", "96597485757", "customer_fast_path");
  assert(res.decision.action === "accepted", "10: accepted");
  assert(res.state.requestedSlot === null, "10: requested cleared after fill");
}

// --- 11: mirrorDialogStateToDraft -----------------------------------------
{
  let s = createEmptyDialogState();
  s = updateSlot(s, "sender_name", "Aziz", "llm_apply").state;
  s = updateSlot(s, "sender_phone", "96597485757", "customer_fast_path").state;
  s = updateSlot(s, "pickup_block", "6", "llm_apply").state;
  // Introduce a conflict: pickup_street was filled then contested.
  s = updateSlot(s, "pickup_street", "9", "llm_apply").state;
  s = updateSlot(s, "pickup_street", "11", "llm_apply").state; // conflict

  const draft = createEmptyBookingDraft();
  draft.pickupLocation = { source: "location_pin", latitude: 29.3, longitude: 47.9, name: null, address: null, resolvedAreaName: null };

  const mirrored = mirrorDialogStateToDraft(s, draft);
  assert(mirrored.senderName === "Aziz", "11: mirror sender_name");
  assert(mirrored.senderPhone === "96597485757", "11: mirror sender_phone");
  assert(mirrored.pickupBlock === "6", "11: mirror pickup_block");
  assert(mirrored.pickupStreet === "9", "11: mirror conflict kept old value");
  assert(mirrored.pickupLocation?.source === "location_pin", "11: pickupLocation preserved");
}

// --- 12: seedDialogStateFromDraft -----------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.senderName = "Aziz";
  draft.senderPhone = "96597485757";
  draft.pickupBlock = "6";
  draft.pickupStreet = "9";
  draft.deliveryHouse = "11";
  const s = seedDialogStateFromDraft(draft);
  assert(s.slots.sender_name?.status === "filled", "12: sender_name filled");
  assert(s.slots.sender_name?.value === "Aziz", "12: sender_name value");
  assert(s.slots.pickup_block?.status === "filled", "12: pickup_block filled");
  assert(s.slots.delivery_house?.status === "filled", "12: delivery_house filled");
  assert(!s.slots.recipient_name, "12: unset field remains unset");
  assert(s.slots.sender_name?.lastSource === "legacy_mirror", "12: source legacy_mirror");
}

// --- 13: slotNameForBookingField -------------------------------------------
{
  assert(slotNameForBookingField("sender_name", null) === "sender_name", "13: sender_name");
  assert(slotNameForBookingField("address_block", "pickup") === "pickup_block", "13: pickup_block");
  assert(slotNameForBookingField("address_block", "delivery") === "delivery_block", "13: delivery_block");
  assert(slotNameForBookingField("address_block", null) === null, "13: null role → null slot");
  assert(slotNameForBookingField("phone_decision", null) === null, "13: phone_decision → null");
  assert(slotNameForBookingField("address_extra", "pickup") === "pickup_extra", "13: pickup_extra");
  assert(slotNameForBookingField("address_avenue", "delivery") === "delivery_avenue", "13: delivery_avenue");
}

// --- 14: deriveRequestedSlotFromMissing -----------------------------------
{
  assert(deriveRequestedSlotFromMissing([]) === null, "14: empty → null");
  assert(
    deriveRequestedSlotFromMissing(["sender.phone"]) === "sender_phone",
    "14: sender.phone → sender_phone",
  );
  // Sub-field preferred over coarse parent
  assert(
    deriveRequestedSlotFromMissing(["pickup.address", "pickup.block"]) === "pickup_block",
    "14: sub-field wins over coarse",
  );
  // First-match priority: sender_name comes before sender_phone in the prefs.
  assert(
    deriveRequestedSlotFromMissing(["sender.name", "sender.phone"]) === "sender_name",
    "14: sender_name priority",
  );
}

// --- final sanity: ALL_SLOT_NAMES unique ----------------------------------
{
  const set = new Set(ALL_SLOT_NAMES);
  assert(set.size === ALL_SLOT_NAMES.length, "all slot names unique");
}

// --- 15: env flag kill-switch ---------------------------------------------
{
  const { isDialogStateEnabled } = dst;
  const prev = process.env.RIDERS_DIALOG_STATE_ENABLED;
  try {
    delete process.env.RIDERS_DIALOG_STATE_ENABLED;
    assert(isDialogStateEnabled() === true, "15: default ON when unset");
    process.env.RIDERS_DIALOG_STATE_ENABLED = "1";
    assert(isDialogStateEnabled() === true, "15: '1' → on");
    for (const off of ["0", "false", "off", "no", "disabled", "FALSE", " 0 "]) {
      process.env.RIDERS_DIALOG_STATE_ENABLED = off;
      assert(isDialogStateEnabled() === false, `15: '${off}' → off`);
    }
  } finally {
    if (prev == null) delete process.env.RIDERS_DIALOG_STATE_ENABLED;
    else process.env.RIDERS_DIALOG_STATE_ENABLED = prev;
  }
}

console.log(`ok smoke-test-dialog-state (${ALL_SLOT_NAMES.length} slots exercised)`);
