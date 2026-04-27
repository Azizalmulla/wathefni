#!/usr/bin/env node
/**
 * Smoke test: name-field shape validation at the apply boundary.
 *
 * Background — on 2026-04-19 13:42 (live) the LLM mis-attributed the
 * customer's question "Is this the cheapest option" as the sender's
 * name. The string passed the existing shape regex
 * (`^[\p{L}][\p{L}\s'\-.]*$`) because it's pure letters+spaces. The
 * draft was corrupted from that point on.
 *
 * Two hardening rules added to `validateName`:
 *
 *   - `name_looks_like_question`: rejects strings starting with English
 *     or Arabic interrogatives (is, are, do, what, when, why, how, هل,
 *     شو, شنو, وين, كيف, كم, ليش, etc.) AND any string containing `?`
 *     or `؟`.
 *
 *   - `name_too_many_words`: rejects strings with > 4 whitespace-
 *     separated tokens. Real Kuwaiti names rarely exceed 4 tokens;
 *     "Is this the cheapest option" has 5.
 *
 * Both rules are evaluated AFTER the existing shape/digits/artifact
 * checks so we don't change the rejection-reason precedence for legacy
 * cases. Each rejection produces a `field_rejection` op which the LLM
 * receives as a re-ask signal — the same defense-in-depth pattern as
 * `verifyAreaEvidence` for area smuggles.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

function makeOp(fields) {
  return {
    op: "apply_booking_field",
    sender_name: null,
    sender_phone: null,
    phone_decision: null,
    recipient_name: null,
    recipient_phone: null,
    address_block: null,
    address_street: null,
    address_house: null,
    address_avenue: null,
    address_extra: null,
    address_role: null,
    source_quote: null,
    turn_id: "test-turn",
    ...fields,
  };
}

async function main() {
  const opsPath = path.join(deliveryRoot, "plugins/shared/responder-state-ops.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, opsPath);
  const { validateApplyBookingFieldOp } = mod;
  assert.equal(typeof validateApplyBookingFieldOp, "function", "missing validateApplyBookingFieldOp");

  // --- Live regression: "Is this the cheapest option" must be rejected
  // for both the question-shape rule AND the word-count rule. The first
  // reason wins because checks run in declaration order; the test pins
  // the contract.
  {
    const result = validateApplyBookingFieldOp(
      makeOp({ sender_name: "Is this the cheapest option" }),
    );
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, "expected sender_name to be rejected");
    assert(
      err.reason === "name_looks_like_question" || err.reason === "name_too_many_words",
      `unexpected rejection reason: ${err.reason}`,
    );
    assert.equal(result.cleaned.sender_name, null, "rejected field must be nulled in cleaned op");
  }

  // --- English interrogative variants — each must be rejected.
  for (const value of [
    "Is the order ready",
    "Are you available",
    "Do you deliver",
    "Does this work",
    "Can I pay cash",
    "What is the price",
    "When will it arrive",
    "Where is the driver",
    "Why is it expensive",
    "Who is the driver",
    "Which option is cheaper",
    "How long does it take",
    "How much",
    "Will you arrive soon",
  ]) {
    const result = validateApplyBookingFieldOp(makeOp({ sender_name: value }));
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, `expected rejection for ${JSON.stringify(value)}`);
    assert(
      err.reason === "name_looks_like_question" || err.reason === "name_too_many_words",
      `unexpected reason for ${JSON.stringify(value)}: ${err.reason}`,
    );
  }

  // --- Question-mark anywhere in the value triggers the question rule.
  for (const value of ["Aziz?", "Mohammed Hamad?", "هل تستلمون"]) {
    const result = validateApplyBookingFieldOp(makeOp({ sender_name: value }));
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, `expected rejection for ${JSON.stringify(value)}`);
  }

  // --- Arabic-script interrogatives.
  for (const value of [
    "هل الطلب جاهز",
    "شو الموضوع",
    "وين السائق",
    "كيف ادفع",
    "كم السعر",
    "ليش غالي",
  ]) {
    const result = validateApplyBookingFieldOp(makeOp({ sender_name: value }));
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, `expected rejection for ${JSON.stringify(value)}`);
  }

  // --- Arabizi interrogatives (customers often type questions in Latin).
  for (const value of [
    "Shlonk il yom",
    "Shnu el price",
    "Wain el driver",
    "Kam el delivery",
    "Kef adfa3",
    "Laish ghali",
  ]) {
    const result = validateApplyBookingFieldOp(makeOp({ sender_name: value }));
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, `expected rejection for arabizi question ${JSON.stringify(value)}`);
  }

  // --- Word-count cap: 5+ token names are rejected even without
  // interrogative markers (catches arbitrary conversation snippets).
  {
    const result = validateApplyBookingFieldOp(
      makeOp({ sender_name: "this is a very long name string indeed" }),
    );
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(err, "expected rejection for 8-token string");
    assert.equal(err.reason, "name_too_many_words");
  }

  // --- Recipient_name uses the same validator — confirm coverage.
  {
    const result = validateApplyBookingFieldOp(
      makeOp({ recipient_name: "Is this the cheapest option" }),
    );
    const err = result.errors.find((e) => e.field === "recipient_name");
    assert(err, "recipient_name must use the same shape rules as sender_name");
  }

  // --- Happy path: real Kuwaiti names must still pass cleanly.
  for (const value of [
    "Aziz",
    "Aziz Al Mulla",
    "Mohammed Hamad",
    "Mohammed Hamad Al Sabah",
    "Sara",
    "Yousef Al-Sabah",
    "Abdulaziz",
    "عزيز",
    "عزيز الملا",
    "محمد حمد الصباح",
    "Fatima Al-Otaibi",
    "John Smith",
  ]) {
    const result = validateApplyBookingFieldOp(makeOp({ sender_name: value }));
    const err = result.errors.find((e) => e.field === "sender_name");
    assert(!err, `name ${JSON.stringify(value)} must NOT be rejected; got reason=${err?.reason}`);
    assert.equal(
      result.cleaned.sender_name,
      value,
      `valid name must survive cleaning unchanged: ${JSON.stringify(value)}`,
    );
  }

  // --- Existing rules still hold (regression guard for the older
  // artifact/digits/empty checks).
  {
    const r = validateApplyBookingFieldOp(makeOp({ sender_name: "12345" }));
    assert.equal(
      r.errors.find((e) => e.field === "sender_name")?.reason,
      "name_is_digits",
    );
  }
  {
    const r = validateApplyBookingFieldOp(makeOp({ sender_name: "ok" }));
    assert.equal(
      r.errors.find((e) => e.field === "sender_name")?.reason,
      "name_is_artifact",
    );
  }
  {
    const r = validateApplyBookingFieldOp(makeOp({ sender_name: "A" }));
    assert.equal(
      r.errors.find((e) => e.field === "sender_name")?.reason,
      "name_too_short",
    );
  }

  // --- Boundary: exactly 4 words is the max-allowed.
  {
    const r = validateApplyBookingFieldOp(makeOp({ sender_name: "One Two Three Four" }));
    const err = r.errors.find((e) => e.field === "sender_name");
    assert(!err, "exactly 4 words must be allowed");
  }
  {
    const r = validateApplyBookingFieldOp(makeOp({ sender_name: "One Two Three Four Five" }));
    const err = r.errors.find((e) => e.field === "sender_name");
    assert.equal(err?.reason, "name_too_many_words", "5 words must be rejected");
  }

  // --- Pre-LLM fast-path parity: the deterministic fast-path extractor
  // must reject the same shapes the apply-boundary validator rejects.
  // This closes the architectural gap that let "Is this the cheapest
  // option" be written to sender_name BEFORE the LLM ever ran on
  // 2026-04-19 13:42 (live). The fast-path used its own weaker
  // `looksLikeValidName`; we now route both through `validateName`.
  const fastPathPath = path.join(deliveryRoot, "plugins/shared/fast-path-extractor.ts");
  const fastPath = await loadDeliveryTsModule(import.meta.url, fastPathPath);
  const { extractForNextAction, extractSenderNameAndDecision, extractRecipientNameAndPhone } = fastPath;
  assert.equal(typeof extractForNextAction, "function", "missing extractForNextAction");

  // The exact live-incident input. Before the fix the fast-path emitted
  // a high-confidence patch with sender_name set; after the fix it must
  // emit no patch (so the LLM gets to handle the message naturally).
  {
    const r = extractSenderNameAndDecision({ text: "Is this the cheapest option" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `fast-path must NOT extract sender_name from a question; got ${JSON.stringify(r)}`,
    );
  }
  // Same defense for the recipient combined extractor.
  {
    const r = extractRecipientNameAndPhone({ text: "Is this the cheapest option" });
    assert.equal(
      r.patch?.recipient_name ?? null,
      null,
      `fast-path recipient extractor must NOT accept a question as a name; got ${JSON.stringify(r)}`,
    );
  }
  // English interrogative variants must all be rejected by the fast-path.
  for (const value of [
    "What is the price",
    "Are you available",
    "How long does it take",
    "Why is it expensive",
  ]) {
    const r = extractSenderNameAndDecision({ text: value });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `fast-path must reject interrogative ${JSON.stringify(value)}`,
    );
  }
  // Identity authority cut: the fast-path no longer writes names or
  // phones at all. The LLM's `apply_booking_field` tool op owns identity
  // extraction and still runs through the apply-boundary validation we
  // exercised above.
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Al Mulla" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      "Phase 1: fast-path must not write sender_name for plain name input",
    );
    assert.equal(r.confidence, "none");
  }
  {
    const r = extractSenderNameAndDecision({ text: "Aziz Al Mulla, use my whatsapp" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      "Phase 1: fast-path must not write sender_name alongside use_whatsapp",
    );
    assert.equal(r.patch, null, "identity phone decision must also be LLM/tool-owned");
    assert.equal(r.confidence, "none");
  }
  {
    const r = extractRecipientNameAndPhone({ text: "Mohammed Hamad 99887766" });
    assert.equal(
      r.patch,
      null,
      "Phase 1: recipient combined fast-path must be disabled",
    );
    assert.equal(r.confidence, "none");
  }
  // Top-level dispatcher exercises the same gating end-to-end (this is
  // what the orchestrator actually calls before the LLM turn).
  {
    const r = extractForNextAction({
      text: "Is this the cheapest option",
      action: "ASK_SENDER_NAME_AND_PHONE_DECISION",
      whatsappNumber: "96599338566",
    });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      "extractForNextAction must inherit the rejection",
    );
  }

  console.log("smoke-test-name-shape-validation: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
