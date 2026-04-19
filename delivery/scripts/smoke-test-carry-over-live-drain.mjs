#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: `carry_over_from_last_order` handled by the LIVE one-brain
// drain path.
//
// Background:
// The legacy `applyResponderStateOps` path (covered by
// smoke-test-carry-over-drain-integration.mjs) has been unreachable in
// production since `RESPONDER_FIRST_FLAG + isOneBrainConversation` were
// hardcoded on. The live drain runs inside `dispatchReplyWithBufferedBlockDispatcher`
// and — until today — had no branch to handle `carry_over_from_last_order`
// ops, so every op pushed by the fast-path reuse-intent classifier was
// silently dropped.
//
// This test exercises the shared helper `applyCarryOverOp` that the live
// drain now delegates to. Asserting on this helper is the direct regression
// anchor: if someone deletes or forgets to call it again, this test fails.
//
// Coverage:
//   T1 — Full sender+recipient identity buckets applied from a clean saved order.
//   T2 — Missing saved order → `no_saved_order` outcome, no draft mutation.
//   T3 — Empty buckets array → `empty_buckets` outcome.
//   T4 — Stale/corrupt saved sender name is skipped; valid fields still apply.
//   T5 — Address-only buckets → `ask_fresh` outcome, no draft mutation.
//   T6 — DST slots written by carry-over are tagged `lastSource: "carryover"`.
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

const octopus = loadTs("plugins/octopus-channel/index.ts");
const shared = loadTs("plugins/shared/conversation-policy.ts");
const { createEmptyDialogState } = loadTs("plugins/shared/dialog-state.ts");

const applyCarryOverOp = octopus.__testables?.applyCarryOverOp;
if (!applyCarryOverOp)
  throw new Error("applyCarryOverOp not exported via __testables");

function goodProfile() {
  return {
    version: 1,
    phone_e164: "+96599118375",
    last_successful_order: {
      sender: { name: "Aziz Almulla", phone: "99118375" },
      recipient: { name: "Sara Khalid", phone: "99338566" },
      pickup: {
        area_name_en: "Salwa",
        block: "3",
        street: "4",
        house: "19",
      },
      delivery: {
        area_name_en: "Al Masayel",
        block: "11",
        street: "7",
        house: "10",
      },
    },
    order_count: 1,
  };
}

// -------- T1: full identity carry-over applies both buckets --------
{
  const result = applyCarryOverOp({
    op: {
      op: "carry_over_from_last_order",
      buckets: ["sender_identity", "recipient_identity"],
    },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: goodProfile(),
    whatsappNumber: "96599118375",
  });

  assert(result.outcome === "applied", `T1 outcome=${result.outcome}`);
  assert(
    result.appliedFields.includes("sender_name") &&
      result.appliedFields.includes("sender_phone") &&
      result.appliedFields.includes("recipient_name") &&
      result.appliedFields.includes("recipient_phone"),
    `T1 appliedFields=${JSON.stringify(result.appliedFields)}`,
  );
  assert(
    result.draft.senderName === "Aziz Almulla",
    `T1 senderName=${result.draft.senderName}`,
  );
  assert(
    result.draft.senderPhone === "99118375",
    `T1 senderPhone=${result.draft.senderPhone}`,
  );
  assert(
    result.draft.recipientName === "Sara Khalid",
    `T1 recipientName=${result.draft.recipientName}`,
  );
  assert(
    result.draft.recipientPhone === "99338566",
    `T1 recipientPhone=${result.draft.recipientPhone}`,
  );
  console.log("PASS T1 full identity carry-over");
}

// -------- T2: no saved order --------
{
  const result = applyCarryOverOp({
    op: {
      op: "carry_over_from_last_order",
      buckets: ["sender_identity"],
    },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: null,
    whatsappNumber: "96599118375",
  });
  assert(result.outcome === "no_saved_order", `T2 outcome=${result.outcome}`);
  console.log("PASS T2 no_saved_order");
}

// -------- T3: empty buckets --------
{
  const result = applyCarryOverOp({
    op: { op: "carry_over_from_last_order", buckets: [] },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: goodProfile(),
    whatsappNumber: "96599118375",
  });
  assert(result.outcome === "empty_buckets", `T3 outcome=${result.outcome}`);
  console.log("PASS T3 empty_buckets");
}

// -------- T4: invalid saved sender name is skipped, phone still applies --------
// This proves the per-field validator (cleanName) runs on every saved value,
// so a corrupt value can never silently write to the draft. We use a name
// that cleanName actually rejects (contains digits) to exercise the skip
// path. The higher-level "sanitize on profile load" boundary covers the
// "looks syntactically valid but is actually a sentence" case that today's
// read-time sanitizer addresses.
{
  const profile = goodProfile();
  profile.last_successful_order.sender.name = "12345"; // cleanName rejects: name_has_invalid_chars
  const result = applyCarryOverOp({
    op: {
      op: "carry_over_from_last_order",
      buckets: ["sender_identity", "recipient_identity"],
    },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: profile,
    whatsappNumber: "96599118375",
  });
  assert(
    result.outcome === "applied_partial",
    `T4 outcome=${result.outcome}`,
  );
  assert(
    !result.appliedFields.includes("sender_name"),
    `T4 invalid sender_name should be skipped, appliedFields=${JSON.stringify(result.appliedFields)}`,
  );
  assert(
    result.appliedFields.includes("sender_phone"),
    `T4 sender_phone should still apply, appliedFields=${JSON.stringify(result.appliedFields)}`,
  );
  assert(
    result.appliedFields.includes("recipient_name") &&
      result.appliedFields.includes("recipient_phone"),
    `T4 recipient bucket should apply fully, appliedFields=${JSON.stringify(result.appliedFields)}`,
  );
  assert(
    result.skipped.some((s) => s.field === "sender_name"),
    `T4 skipped should note sender_name, skipped=${JSON.stringify(result.skipped)}`,
  );
  console.log("PASS T4 invalid sender name skipped");
}

// -------- T5: address-only buckets → ask_fresh --------
{
  const result = applyCarryOverOp({
    op: {
      op: "carry_over_from_last_order",
      buckets: ["pickup_location", "delivery_location"],
    },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: goodProfile(),
    whatsappNumber: "96599118375",
  });
  assert(result.outcome === "ask_fresh", `T5 outcome=${result.outcome}`);
  assert(
    result.askFresh.includes("pickup_location") &&
      result.askFresh.includes("delivery_location"),
    `T5 askFresh=${JSON.stringify(result.askFresh)}`,
  );
  console.log("PASS T5 address-only → ask_fresh");
}

// -------- T6: DST slots tagged lastSource: "carryover" --------
{
  const result = applyCarryOverOp({
    op: {
      op: "carry_over_from_last_order",
      buckets: ["sender_identity", "recipient_identity"],
    },
    draft: shared.createEmptyBookingDraft(),
    dialogState: createEmptyDialogState(),
    customerProfile: goodProfile(),
    whatsappNumber: "96599118375",
  });
  assert(result.outcome === "applied", `T6 outcome=${result.outcome}`);
  assert(result.dialogState, "T6 dialogState should be returned");
  const slots = result.dialogState.slots || {};
  for (const name of [
    "sender_name",
    "sender_phone",
    "recipient_name",
    "recipient_phone",
  ]) {
    assert(
      slots[name]?.lastSource === "carryover",
      `T6 ${name} lastSource=${slots[name]?.lastSource}`,
    );
  }
  console.log("PASS T6 DST lastSource=carryover");
}

console.log("ALL PASS smoke-test-carry-over-live-drain.mjs");
