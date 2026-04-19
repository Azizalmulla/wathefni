#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: DST-aware hallucination guard behavior for slot conflicts.
//
// The DST layer tightens the field-rejection guard's evidence check. Before
// DST, the guard relied on `isValidPhone/isValidName` on the legacy draft to
// decide whether an "please re-send X" reply was grounded. That's fine when
// the draft was never contested — but it didn't know the difference between
// "value was accepted" and "value passed syntax". DST records explicit
// status transitions (unfilled → filled → conflict), so the guard can now
// ask: does the slot register show any core slot that is *not* currently
// `filled`?
//
// Cases:
//   1. All core slots `filled` in DST → field-rejection claim is
//      hallucinated and blocked, even when the legacy draft also looks
//      valid (regression ground for the 2026-04-17 incident).
//   2. DST has a `conflict` on sender_phone → field-rejection claim is
//      grounded (LLM is legitimately asking the customer to resolve).
//   3. DST has an `unfilled` core slot (phone missing) → claim grounded
//      (the LLM is preemptively asking, no hallucination).
//   4. Entry without `dialogState` at all → legacy path still works (falls
//      back to draft-level isValidPhone/isValidName checks).
//   5. DST present but non-core slot (pickup_block) is in conflict → the
//      core-slot check doesn't treat address-level conflicts as license to
//      re-send phones. Claim still blocked.
//   6. All core slots filled AND price_mismatch claim → different claim
//      path still fires.
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

const { runHallucinationGuard } = await loadTsModule(
  "plugins/shared/reply-hallucination-guard.ts",
);
const { createEmptyBookingDraft } = await loadTsModule("plugins/shared/conversation-policy.ts");
const {
  createEmptyDialogState,
  updateSlot,
  seedDialogStateFromDraft,
} = await loadTsModule("plugins/shared/dialog-state.ts");

function buildCompleteDraft() {
  const d = createEmptyBookingDraft();
  d.senderName = "Aziz";
  d.senderPhone = "96597485757";
  d.recipientName = "Ahmed";
  d.recipientPhone = "96562844738";
  d.pickupBlock = "6";
  d.pickupStreet = "9";
  d.pickupHouse = "17";
  d.deliveryBlock = "2";
  d.deliveryStreet = "9";
  d.deliveryExtra = "Apartment 19, floor 8, door 11";
  return d;
}

function buildEntry(draft, dialogState, overrides = {}) {
  return {
    stage: "collecting_booking_details",
    bookingStep: "summary_pending",
    bookingDraft: draft,
    dialogState: dialogState ?? null,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    ...overrides,
  };
}

const RESEND_REPLY =
  "The phone numbers need to be resent in a valid format. Send the sender and recipient phone numbers again, digits only.";

// --- Case 1: DST all core filled → claim blocked --------------------------
{
  const draft = buildCompleteDraft();
  const dialogState = seedDialogStateFromDraft(draft);
  const entry = buildEntry(draft, dialogState);
  const decision = runHallucinationGuard({
    replyText: RESEND_REPLY,
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(decision.blocked, "case1: DST all-filled must block hallucinated resend");
  assert(
    decision.claims.includes("field_rejection_hallucination"),
    "case1: must flag field_rejection_hallucination",
  );
}

// --- Case 2: DST with conflict on sender_phone → claim grounded -----------
{
  const draft = buildCompleteDraft();
  let dialogState = seedDialogStateFromDraft(draft);
  dialogState = updateSlot(dialogState, "sender_phone", "96512345678", "llm_apply").state;
  assert(
    dialogState.slots.sender_phone.status === "conflict",
    "case2: sender_phone must be in conflict before guard runs",
  );
  const entry = buildEntry(draft, dialogState);
  const decision = runHallucinationGuard({
    replyText: "The sender phone conflicts with what we had — please resend it, digits only.",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_SENDER_PHONE",
  });
  assert(
    !decision.blocked,
    "case2: DST conflict on core slot means LLM legitimately asks for resend",
  );
}

// --- Case 3: DST with an unfilled core slot → claim grounded --------------
{
  const draft = buildCompleteDraft();
  draft.recipientPhone = null;
  const dialogState = seedDialogStateFromDraft(draft);
  assert(
    !dialogState.slots.recipient_phone,
    "case3: recipient_phone should not be in DST",
  );
  const entry = buildEntry(draft, dialogState);
  const decision = runHallucinationGuard({
    replyText: "Please send the recipient phone number again, digits only.",
    entry,
    missingFields: ["recipient.phone"],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "ASK_RECIPIENT_NAME_AND_PHONE",
  });
  assert(
    !decision.blocked,
    "case3: unfilled core slot means ask is legitimate",
  );
}

// --- Case 4: Entry without dialogState → legacy path still works ---------
{
  const draft = buildCompleteDraft();
  const entry = buildEntry(draft, null); // no DST
  const decision = runHallucinationGuard({
    replyText: RESEND_REPLY,
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(
    decision.blocked,
    "case4: legacy path (no DST) still blocks hallucinated resend when draft is valid",
  );
}

// --- Case 5: non-core conflict (pickup_block) → still blocks phone claim -
{
  const draft = buildCompleteDraft();
  let dialogState = seedDialogStateFromDraft(draft);
  dialogState = updateSlot(dialogState, "pickup_block", "9", "llm_apply").state; // different from "6"
  assert(
    dialogState.slots.pickup_block.status === "conflict",
    "case5: pickup_block must be in conflict for setup",
  );
  // Core slots (name/phone) all filled → resend claim is still ungrounded.
  const entry = buildEntry(draft, dialogState);
  const decision = runHallucinationGuard({
    replyText: RESEND_REPLY,
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(
    decision.blocked,
    "case5: pickup_block conflict is not license to ask for phone resend",
  );
  assert(
    decision.claims.includes("field_rejection_hallucination"),
    "case5: must still flag field_rejection_hallucination",
  );
}

// --- Case 6: all filled + price mismatch → other claim path still fires ---
{
  const draft = buildCompleteDraft();
  const dialogState = seedDialogStateFromDraft(draft);
  const entry = buildEntry(draft, dialogState);
  const decision = runHallucinationGuard({
    replyText: "Your delivery is 5 KWD, shall we confirm?",
    entry,
    missingFields: [],
    rejectionsThisTurn: [],
    stageAtTurnStart: "collecting_booking_details",
    language: "en",
    nextRequiredAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
  });
  assert(
    decision.claims.includes("price_mismatch"),
    "case6: price mismatch still detected even when DST is clean",
  );
}

// --- Case 7: RIDERS_DIALOG_STATE_ENABLED=0 → applyBookingFieldPatch
//             returns null dialogState → guard falls back to legacy path ---
{
  const bd = await loadTsModule("plugins/shared/booking-draft.ts");
  const { applyBookingFieldPatch } = bd;
  const ds = await loadTsModule("plugins/shared/dialog-state.ts");
  const { createEmptyDialogState } = ds;

  const prev = process.env.RIDERS_DIALOG_STATE_ENABLED;
  process.env.RIDERS_DIALOG_STATE_ENABLED = "0";
  try {
    const state = createEmptyDialogState();
    const res = applyBookingFieldPatch({
      draft: createEmptyBookingDraft(),
      patch: { sender_name: "Aziz" },
      dialogState: state,
      dstSource: "llm_apply",
    });
    assert(res.dialogState === null, "case7: DST disabled → dialogState returned null");
    assert(res.draft.senderName === "Aziz", "case7: legacy draft write still happens");
  } finally {
    if (prev == null) delete process.env.RIDERS_DIALOG_STATE_ENABLED;
    else process.env.RIDERS_DIALOG_STATE_ENABLED = prev;
  }
}

console.log("ok smoke-test-slot-conflict-guard (7 cases)");
