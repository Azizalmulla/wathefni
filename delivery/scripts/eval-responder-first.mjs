#!/usr/bin/env node
/**
 * Eval harness for the responder-first orchestration path.
 *
 * Exercises the `applyResponderStateOps` pipeline with representative
 * fixtures so we can verify that tool-emitted state ops produce the
 * expected controller state and deterministic-summary trigger before
 * flipping RIDERS_RESPONDER_FIRST=1 in production.
 *
 * Run: node delivery/scripts/eval-responder-first.mjs
 */
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

function makeDraft(shared, overrides = {}) {
  return {
    ...shared.createEmptyBookingDraft(),
    ...overrides,
  };
}

function makeEntry(shared, overrides = {}) {
  return {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "collecting_booking_details",
    bookingStep: "sender",
    conversationId: "eval-conversation",
    replyTarget: "96599999999",
    accountId: "eval-account",
    quoteRouteKey: null,
    quoteTs: null,
    quotePickupAreaNameEn: "Salwa",
    quotePickupAreaNameAr: "سلوى",
    quoteDropoffAreaNameEn: "The Sea Front Hawalli",
    quoteDropoffAreaNameAr: "السي فرونت حولي",
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: 2.25,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 2.25,
    bookingDraft: makeDraft(shared),
    pendingReplyText: null,
    ...overrides,
  };
}

function ok(label) {
  console.log(`PASS ${label}`);
}
function bad(label, detail) {
  console.error(`FAIL ${label} :: ${detail}`);
  process.exitCode = 1;
}

async function main() {
  const octopus = loadTs("plugins/octopus-channel/index.ts");
  const shared = loadTs("plugins/shared/conversation-policy.ts");
  const t = octopus.__testables;
  if (!t?.applyResponderStateOps) {
    throw new Error("applyResponderStateOps is not exported via __testables");
  }

  // Fixture 1: sender name + phone_decision=use_whatsapp advances to recipient
  {
    const entry = makeEntry(shared);
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "my name is aziz use my whatsapp",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          sender_name: "Aziz",
          phone_decision: "use_whatsapp",
          turn_id: "t1",
        },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (!nextEntry) return bad("F1_sender_use_whatsapp", "no entry returned");
    if (nextEntry.bookingDraft.senderName !== "Aziz") return bad("F1_sender_use_whatsapp", `senderName=${nextEntry.bookingDraft.senderName}`);
    if (!nextEntry.bookingDraft.senderPhone || !nextEntry.bookingDraft.senderPhone.endsWith("99338566")) return bad("F1_sender_use_whatsapp", `senderPhone=${nextEntry.bookingDraft.senderPhone}`);
    if (nextEntry.bookingStep !== "recipient") return bad("F1_sender_use_whatsapp", `expected step=recipient got=${nextEntry.bookingStep}`);
    if (result.summaryReady) return bad("F1_sender_use_whatsapp", "summaryReady should be false");
    ok("F1 sender+use_whatsapp advances to recipient");
  }

  // Fixture 2: recipient name + phone advances to pickup_address
  {
    const entry = makeEntry(shared, {
      bookingStep: "recipient",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "ahamad and 59384581",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          recipient_name: "Ahamad",
          recipient_phone: "59384581",
          turn_id: "t2",
        },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (nextEntry.bookingStep !== "pickup_address") return bad("F2_recipient", `got step=${nextEntry.bookingStep}`);
    ok("F2 recipient name+phone advances to pickup_address");
  }

  // Fixture 3: pickup address block/street/house with explicit role
  {
    const entry = makeEntry(shared, {
      bookingStep: "pickup_address",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
        recipientName: "Ahamad",
        recipientPhone: "59384581",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "block 1 street 5 house 23",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          address_block: "1",
          address_street: "5",
          address_house: "23",
          address_role: "pickup",
          turn_id: "t3",
        },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (nextEntry.bookingDraft.pickupBlock !== "1" || nextEntry.bookingDraft.pickupStreet !== "5" || nextEntry.bookingDraft.pickupHouse !== "23") {
      return bad("F3_pickup_address", `got pickup=${JSON.stringify({b: nextEntry.bookingDraft.pickupBlock, s: nextEntry.bookingDraft.pickupStreet, h: nextEntry.bookingDraft.pickupHouse})}`);
    }
    if (nextEntry.bookingStep !== "delivery_address") return bad("F3_pickup_address", `expected delivery_address got=${nextEntry.bookingStep}`);
    ok("F3 pickup address advances to delivery_address");
  }

  // Fixture 4: delivery address completes → summary_ready
  {
    const entry = makeEntry(shared, {
      bookingStep: "delivery_address",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
        recipientName: "Ahamad",
        recipientPhone: "59384581",
        pickupBlock: "1",
        pickupStreet: "5",
        pickupHouse: "23",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "1 3 11",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          address_block: "1",
          address_street: "3",
          address_house: "11",
          address_role: "delivery",
          turn_id: "t4",
        },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (!result.summaryReady) return bad("F4_summary_ready", "summaryReady should be true");
    if (nextEntry.stage !== "awaiting_confirmation") return bad("F4_summary_ready", `expected stage=awaiting_confirmation got=${nextEntry.stage}`);
    ok("F4 delivery address triggers summary_ready");
  }

  // Fixture 5: post-summary edit with no role declared & both addresses satisfied → ambiguous
  {
    const entry = makeEntry(shared, {
      stage: "awaiting_confirmation",
      bookingStep: "awaiting_summary_confirmation",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
        recipientName: "Ahamad",
        recipientPhone: "59384581",
        pickupBlock: "1",
        pickupStreet: "5",
        pickupHouse: "23",
        deliveryBlock: "1",
        deliveryStreet: "3",
        deliveryHouse: "11",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "change block to 2",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          address_block: "2",
          address_role: null,
          turn_id: "t5",
        },
      ],
    });
    if (result.corrections.ambiguous !== 1) return bad("F5_ambiguous", `corrections.ambiguous=${result.corrections.ambiguous}`);
    if (result.summaryReady) return bad("F5_ambiguous", "summaryReady should be false");
    ok("F5 ambiguous post-summary edit reported, not applied");
  }

  // Fixture 6: cancel_booking resets controller in calling path (flag set)
  {
    const entry = makeEntry(shared);
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "nvm",
      replyTarget: "96599338566",
      ops: [{ op: "cancel_booking", turn_id: "t6" }],
    });
    if (!result.cancelled) return bad("F6_cancel", "cancelled flag not set");
    ok("F6 cancel_booking op reported");
  }

  // Fixture 7: confirm_summary only accepted when stage is awaiting_confirmation
  {
    const entryCollecting = makeEntry(shared, { stage: "collecting_booking_details", bookingStep: "sender" });
    const r1 = t.applyResponderStateOps({
      controllerEntry: entryCollecting,
      visibleText: "yes",
      replyTarget: "96599338566",
      ops: [{ op: "confirm_summary", turn_id: "t7a" }],
    });
    if (r1.confirmSummary) return bad("F7_confirm_gated", "confirmSummary accepted during collecting stage");

    const entryAwaiting = makeEntry(shared, { stage: "awaiting_confirmation", bookingStep: "awaiting_summary_confirmation" });
    const r2 = t.applyResponderStateOps({
      controllerEntry: entryAwaiting,
      visibleText: "yes go ahead",
      replyTarget: "96599338566",
      ops: [{ op: "confirm_summary", turn_id: "t7b" }],
    });
    if (!r2.confirmSummary) return bad("F7_confirm_gated", "confirmSummary should be accepted during awaiting_confirmation");
    ok("F7 confirm_summary is stage-gated");
  }

  // Fixture 8: multi-op turn: recipient provided full AND pickup address role=pickup
  {
    const entry = makeEntry(shared, {
      bookingStep: "recipient",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "recipient ahmad 59384581, pickup block 1 street 5 house 23",
      replyTarget: "96599338566",
      ops: [
        { op: "apply_booking_field", recipient_name: "Ahmad", recipient_phone: "59384581", turn_id: "t8a" },
        { op: "apply_booking_field", address_block: "1", address_street: "5", address_house: "23", address_role: "pickup", turn_id: "t8b" },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (nextEntry.bookingDraft.recipientName !== "Ahmad") return bad("F8_multi_op", `recipientName=${nextEntry.bookingDraft.recipientName}`);
    if (nextEntry.bookingDraft.pickupBlock !== "1") return bad("F8_multi_op", `pickupBlock=${nextEntry.bookingDraft.pickupBlock}`);
    if (nextEntry.bookingStep !== "delivery_address") return bad("F8_multi_op", `expected delivery_address got=${nextEntry.bookingStep}`);
    ok("F8 multi-op turn applies both in order");
  }

  // Fixture 9: empty op (LLM called tool with no fields) → no-op
  {
    const entry = makeEntry(shared);
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "ok",
      replyTarget: "96599338566",
      ops: [{ op: "apply_booking_field", turn_id: "t9" }],
    });
    if (result.corrections.noop !== 1) return bad("F9_empty", `noop count=${result.corrections.noop}`);
    if (result.summaryReady) return bad("F9_empty", "summaryReady should be false");
    ok("F9 empty apply_booking_field is a no-op");
  }

  // Fixture 10: request_handoff flag propagates
  {
    const entry = makeEntry(shared);
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "i want to speak to a human",
      replyTarget: "96599338566",
      ops: [{ op: "request_handoff", reason: "refund dispute", turn_id: "t10" }],
    });
    if (!result.handoffRequested) return bad("F10_handoff", "handoffRequested flag missing");
    ok("F10 request_handoff op reported");
  }

  // ---- Validation & sanity fixtures (Fix C1/C2) ----
  const stateOps = loadTs("plugins/shared/responder-state-ops.ts");

  // Fixture 11: validate — phone with label "thenumber is 94728472" rejected
  {
    const v = stateOps.validateApplyBookingFieldOp({
      op: "apply_booking_field",
      sender_phone: "thenumber is 94728472",
      turn_id: "v1",
    });
    const err = v.errors.find((e) => e.field === "sender_phone");
    if (!err) return bad("F11_phone_label", "expected sender_phone rejection");
    if (v.cleaned.sender_phone !== null) return bad("F11_phone_label", "cleaned sender_phone should be null");
    ok("F11 phone with label is rejected");
  }

  // Fixture 12: validate — name that is "Ok" (an artifact) is rejected
  {
    const v = stateOps.validateApplyBookingFieldOp({
      op: "apply_booking_field",
      sender_name: "Ok",
      turn_id: "v2",
    });
    const err = v.errors.find((e) => e.field === "sender_name");
    if (!err) return bad("F12_name_artifact", "expected sender_name rejection");
    if (v.cleaned.sender_name !== null) return bad("F12_name_artifact", "cleaned sender_name should be null");
    ok("F12 name 'Ok' is rejected as artifact");
  }

  // Fixture 13: validate — mixed good+bad fields: good preserved, bad nulled
  {
    const v = stateOps.validateApplyBookingFieldOp({
      op: "apply_booking_field",
      sender_name: "Aziz",
      sender_phone: "not a phone",
      recipient_name: "Ahamad",
      recipient_phone: "59384581",
      turn_id: "v3",
    });
    if (v.cleaned.sender_name !== "Aziz") return bad("F13_partial", "sender_name should be preserved");
    if (v.cleaned.sender_phone !== null) return bad("F13_partial", "sender_phone should be nulled");
    if (v.cleaned.recipient_phone !== "59384581") return bad("F13_partial", "recipient_phone should be preserved");
    if (!v.hasAnyValidField) return bad("F13_partial", "hasAnyValidField should be true");
    if (v.errors.length !== 1) return bad("F13_partial", `expected exactly 1 error, got ${v.errors.length}`);
    ok("F13 partial validation preserves good fields, nulls bad ones");
  }

  // Fixture 14: drain validation — defense-in-depth: apply op gets re-validated
  {
    const entry = makeEntry(shared, {
      bookingStep: "sender",
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "my name is ok",
      replyTarget: "96599338566",
      ops: [
        {
          op: "apply_booking_field",
          sender_name: "Ok",
          sender_phone: "97395739",
          turn_id: "v4",
        },
      ],
    });
    const nextEntry = result.controllerEntry;
    if (nextEntry.bookingDraft.senderName === "Ok") return bad("F14_drain_validation", "senderName=Ok leaked into draft");
    if (!result.validationRejections.find((r) => r.field === "sender_name")) return bad("F14_drain_validation", "expected sender_name rejection in result");
    ok("F14 drain re-validation nullifies bad fields before applying");
  }

  // Fixture 15: pre-confirm sanity — confirm_summary rejected when draft has bad phone
  {
    const entry = makeEntry(shared, {
      stage: "awaiting_confirmation",
      bookingStep: "awaiting_summary_confirmation",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "thenumber is 94728472",
        recipientName: "Ahamad",
        recipientPhone: "59384581",
        pickupBlock: "1",
        pickupStreet: "5",
        pickupHouse: "23",
        deliveryBlock: "1",
        deliveryStreet: "3",
        deliveryHouse: "11",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "yes confirm",
      replyTarget: "96599338566",
      ops: [{ op: "confirm_summary", turn_id: "v5" }],
    });
    if (result.confirmSummary) return bad("F15_sanity_block", "confirmSummary should be false when draft has bad phone");
    if (result.draftSanityProblems.length === 0) return bad("F15_sanity_block", "expected draftSanityProblems to be populated");
    const senderPhoneProblem = result.draftSanityProblems.find((p) => p.field === "sender_phone");
    if (!senderPhoneProblem) return bad("F15_sanity_block", "expected sender_phone problem");
    ok("F15 confirm_summary rejected by pre-confirm sanity check");
  }

  // Fixture 16: clean draft passes sanity and confirmSummary accepted
  {
    const entry = makeEntry(shared, {
      stage: "awaiting_confirmation",
      bookingStep: "awaiting_summary_confirmation",
      bookingDraft: makeDraft(shared, {
        senderName: "Aziz",
        senderPhone: "97395739",
        recipientName: "Ahamad",
        recipientPhone: "59384581",
        pickupBlock: "1",
        pickupStreet: "5",
        pickupHouse: "23",
        deliveryBlock: "1",
        deliveryStreet: "3",
        deliveryHouse: "11",
      }),
    });
    const result = t.applyResponderStateOps({
      controllerEntry: entry,
      visibleText: "yes confirm",
      replyTarget: "96599338566",
      ops: [{ op: "confirm_summary", turn_id: "v6" }],
    });
    if (!result.confirmSummary) return bad("F16_clean_confirm", "confirmSummary should be true with clean draft");
    if (result.draftSanityProblems.length !== 0) return bad("F16_clean_confirm", `expected no draft problems got=${JSON.stringify(result.draftSanityProblems)}`);
    ok("F16 clean draft allows confirm_summary");
  }

  // Fixture 17: extracted digits pass validation
  {
    const v = stateOps.validateApplyBookingFieldOp({
      op: "apply_booking_field",
      sender_phone: "+965 9472 8472",
      turn_id: "v7",
    });
    if (v.errors.length !== 0) return bad("F17_phone_formatted", `expected no errors, got ${JSON.stringify(v.errors)}`);
    ok("F17 +965 9472 8472 phone format validates ok");
  }

  // Fixture 18: numeric-only name rejected
  {
    const v = stateOps.validateApplyBookingFieldOp({
      op: "apply_booking_field",
      recipient_name: "59384581",
      turn_id: "v8",
    });
    const err = v.errors.find((e) => e.field === "recipient_name");
    if (!err) return bad("F18_name_digits", "expected recipient_name rejection");
    ok("F18 numeric-only name is rejected");
  }

  // Fixture 19: sanityCheckBookingDraft catches multiple problems
  {
    const problems = stateOps.sanityCheckBookingDraft({
      senderName: "Ok",
      senderPhone: "thenumber is 94728472",
      recipientName: "Ahamad",
      recipientPhone: "59384581",
      pickupAddressBlock: "1",
      pickupAddressStreet: "5",
      pickupAddressHouse: "23",
      deliveryAddressBlock: "1",
      deliveryAddressStreet: "3",
      deliveryAddressHouse: "11",
    });
    const fields = problems.map((p) => p.field);
    if (!fields.includes("sender_name")) return bad("F19_sanity_multi", "missing sender_name problem");
    if (!fields.includes("sender_phone")) return bad("F19_sanity_multi", "missing sender_phone problem");
    ok("F19 sanityCheckBookingDraft catches multi-field problems");
  }

  if (process.exitCode === 1) {
    console.error("\nSome fixtures failed.");
    process.exit(1);
  }
  console.log("\nAll responder-first fixtures passed.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
