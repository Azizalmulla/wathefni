#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: source-precedence override for identity tuples.
//
// Product rule (2026-04-19):
//   When the customer provides a FULL fresh identity tuple
//   (both `*_name` AND `*_phone` in the same patch) and the incumbent
//   value came from `carry_over_from_last_order` (`lastSource ===
//   "carryover"`), the new tuple silently overrides without raising a
//   conflict. Single-field corrections still flow through the conflict
//   path, which is correct — that's a real "you said X, now you're
//   saying Y" moment that deserves confirmation.
//
// Why it's at the patch layer, not a global source-ordering table:
//   tuple-atomicity is only visible to `applyBookingFieldPatch`, which
//   sees the whole turn. `updateSlot` operates one slot at a time and
//   can't tell whether the other half of the identity is coming in the
//   same patch.
//
// Cases covered:
//   T1  full sender tuple over carryover → silent override
//   T2  full recipient tuple over carryover → silent override
//   T3  only sender_name (no phone in same patch) → conflict (correct)
//   T4  only sender_phone (no name in same patch) → conflict (correct)
//   T5  full tuple where incumbent was NOT carryover → conflict (correct)
//   T6  full tuple but incoming source is `carryover` again → conflict
//       (a second carry-over can't overwrite an earlier carry-over
//       silently; that'd be nonsense)
//   T7  full tuple → legacy-draft mirror reflects the new values
//   T8  full tuple → DST slot's `lastSource` becomes the new source,
//       not "carryover"
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

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const dst = loadTs("plugins/shared/dialog-state.ts");
const booking = loadTs("plugins/shared/booking-draft.ts");

const {
  createEmptyDialogState,
  updateSlot,
  getSlot,
} = dst;
const {
  createEmptyBookingDraft,
  applyBookingFieldPatch,
} = booking;

function seedCarriedOverIdentity(draft, dialogState) {
  // Reproduce what the `carry_over_from_last_order` drain does: walk the
  // saved profile through `applyBookingFieldPatch` with
  // `dstSource: "carryover"`. We inline the equivalent via the patch
  // function so the test doesn't depend on the drain internals.
  const res = applyBookingFieldPatch({
    draft,
    patch: {
      sender_name: "Old Sender",
      sender_phone: "99118375",
      recipient_name: "Old Recipient",
      recipient_phone: "99112233",
    },
    dialogState,
    dstSource: "carryover",
  });
  assert(res.conflicts?.length === 0, `seed: no conflicts, got ${JSON.stringify(res.conflicts)}`);
  return { draft: res.draft, dialogState: res.dialogState };
}

// -----------------------------------------------------------------------
// T1: full sender tuple over carryover → silent override.
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: {
      sender_name: "Aziz Almulla",
      sender_phone: "92927173",
    },
    dialogState: seeded.dialogState,
    dstSource: "llm_apply",
  });
  assert(
    res.conflicts.length === 0,
    `T1: no conflicts, got ${JSON.stringify(res.conflicts)}`,
  );
  assert(
    res.draft.senderName === "Aziz Almulla",
    `T1: draft.senderName updated; got ${res.draft.senderName}`,
  );
  assert(
    res.draft.senderPhone === "92927173",
    `T1: draft.senderPhone updated; got ${res.draft.senderPhone}`,
  );
  const slot = getSlot(res.dialogState, "sender_name");
  assert(
    slot.status === "filled" && slot.value === "Aziz Almulla",
    `T1: DST sender_name filled with new value; got ${JSON.stringify(slot)}`,
  );
  assert(
    slot.lastSource === "llm_apply",
    `T1: DST sender_name.lastSource is the new source; got ${slot.lastSource}`,
  );
}

// -----------------------------------------------------------------------
// T2: full recipient tuple over carryover → silent override.
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: {
      recipient_name: "Ahmad Basha",
      recipient_phone: "72947291",
    },
    dialogState: seeded.dialogState,
    dstSource: "customer_fast_path",
  });
  assert(
    res.conflicts.length === 0,
    `T2: no conflicts, got ${JSON.stringify(res.conflicts)}`,
  );
  assert(
    res.draft.recipientName === "Ahmad Basha",
    `T2: recipientName updated; got ${res.draft.recipientName}`,
  );
  assert(
    res.draft.recipientPhone === "72947291",
    `T2: recipientPhone updated; got ${res.draft.recipientPhone}`,
  );
}

// -----------------------------------------------------------------------
// T3: only sender_name (no phone in same patch) → conflict (correct).
// This is a correction of ONE field, not a tuple replacement.
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: { sender_name: "Aziz Almulla" },
    dialogState: seeded.dialogState,
    dstSource: "llm_apply",
  });
  assert(
    res.conflicts.length === 1 && res.conflicts[0].slot === "sender_name",
    `T3: single-field sender_name must raise conflict; got ${JSON.stringify(res.conflicts)}`,
  );
  // The legacy draft must still show the carried-over value, not the new
  // one, because the conflict path holds the incumbent.
  assert(
    res.draft.senderName === "Old Sender",
    `T3: legacy draft reverts to incumbent on conflict; got ${res.draft.senderName}`,
  );
}

// -----------------------------------------------------------------------
// T4: only sender_phone (no name in same patch) → conflict (correct).
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: { sender_phone: "92927173" },
    dialogState: seeded.dialogState,
    dstSource: "llm_apply",
  });
  assert(
    res.conflicts.length === 1 && res.conflicts[0].slot === "sender_phone",
    `T4: single-field sender_phone must raise conflict; got ${JSON.stringify(res.conflicts)}`,
  );
}

// -----------------------------------------------------------------------
// T5: full tuple but incumbent was NOT carryover → still conflict.
// If the customer already typed a sender tuple earlier and now types a
// different one, that IS a real contradiction we need to resolve.
// -----------------------------------------------------------------------
{
  const draft0 = createEmptyBookingDraft();
  const dst0 = createEmptyDialogState();
  // Seed with customer-turn source, not carryover.
  const seeded = applyBookingFieldPatch({
    draft: draft0,
    patch: {
      sender_name: "First Sender",
      sender_phone: "50000001",
    },
    dialogState: dst0,
    dstSource: "llm_apply",
  });
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: {
      sender_name: "Second Sender",
      sender_phone: "60000002",
    },
    dialogState: seeded.dialogState,
    dstSource: "llm_apply",
  });
  assert(
    res.conflicts.length === 2,
    `T5: two-slot conflict for full tuple over customer-turn incumbent; got ${JSON.stringify(res.conflicts)}`,
  );
}

// -----------------------------------------------------------------------
// T6: full tuple where incoming source is carryover → still conflict.
// A second carry-over op can't silently overwrite an earlier carry-over
// because that'd mean the system is ping-ponging between two saved
// profiles without customer input. Not a real case, but cheap to assert.
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: {
      sender_name: "Other Saved Sender",
      sender_phone: "77777777",
    },
    dialogState: seeded.dialogState,
    dstSource: "carryover",
  });
  assert(
    res.conflicts.length === 2,
    `T6: carryover→carryover must conflict; got ${JSON.stringify(res.conflicts)}`,
  );
}

// -----------------------------------------------------------------------
// T7: full tuple → legacy-draft mirror reflects the new values (i.e.
// the summary renderer and context block will see the correct fields).
// -----------------------------------------------------------------------
{
  const seeded = seedCarriedOverIdentity(
    createEmptyBookingDraft(),
    createEmptyDialogState(),
  );
  const res = applyBookingFieldPatch({
    draft: seeded.draft,
    patch: {
      sender_name: "Aziz Almulla",
      sender_phone: "92927173",
    },
    dialogState: seeded.dialogState,
    dstSource: "llm_apply",
  });
  // After override, the mirror must carry the new values, not the
  // carried-over ones.
  assert(
    res.draft.senderName === "Aziz Almulla" &&
      res.draft.senderPhone === "92927173",
    `T7: draft mirror reflects override; got name=${res.draft.senderName} phone=${res.draft.senderPhone}`,
  );
  // Recipient (untouched) stays at the carried-over values.
  assert(
    res.draft.recipientName === "Old Recipient" &&
      res.draft.recipientPhone === "99112233",
    `T7: untouched recipient tuple preserved; got name=${res.draft.recipientName} phone=${res.draft.recipientPhone}`,
  );
}

// -----------------------------------------------------------------------
// T8: direct `updateSlot` API honors `overrideIfSourceWas` too (the
// patch-level rule is one caller, but the option is general).
// -----------------------------------------------------------------------
{
  let state = createEmptyDialogState();
  const r1 = updateSlot(state, "sender_name", "Old Sender", "carryover");
  state = r1.state;
  const r2 = updateSlot(state, "sender_name", "New Sender", "llm_apply", {
    overrideIfSourceWas: "carryover",
  });
  assert(
    r2.decision.action === "overridden_by_source_precedence",
    `T8: direct updateSlot override decision; got ${JSON.stringify(r2.decision)}`,
  );
  const slot = getSlot(r2.state, "sender_name");
  assert(
    slot.value === "New Sender" && slot.lastSource === "llm_apply",
    `T8: direct updateSlot override result; got ${JSON.stringify(slot)}`,
  );
}

console.log("smoke-test-carryover-source-precedence: OK");
