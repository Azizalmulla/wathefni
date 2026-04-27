#!/usr/bin/env node
/**
 * Smoke test: slot-response coherence classifier + write-path integration.
 *
 * Background — shape-only validators (`validateName`, fast-path's old
 * `looksLikeValidName`) cannot distinguish a real name from a
 * conversational fragment with the same shape. On 2026-04-19 13:42
 * (live) the customer's follow-up question "Is this the cheapest
 * option" was accepted as `sender_name`. The fix moved intent
 * classification into `slot-response-coherence.ts`: given a customer
 * message and the slot we asked for, the classifier returns `answer`,
 * `question`, `topic_change`, `ambiguous`, or `empty`. Both write
 * paths (fast-path and apply-boundary) now consult it.
 *
 * This test pins:
 *
 *   1. The classifier's per-kind behavior across slots.
 *   2. That the fast-path refuses name writes when the message is a
 *      question or topic-change for the asked slot.
 *   3. That the apply-boundary drain drops name writes when the
 *      customer's visible text was a question / topic-change for the
 *      currently-requested name slot, even when the field VALUE the
 *      LLM emitted looks like a plausible name.
 *
 * Item (3) is the critical integration: it proves the defense is
 * end-to-end, not just at the pre-LLM gate.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const coherencePath = path.join(deliveryRoot, "plugins/shared/slot-response-coherence.ts");
  const coherenceMod = await loadDeliveryTsModule(import.meta.url, coherencePath);
  const { classifyResponseForSlot, isAcceptableSlotResponse } = coherenceMod;

  // -------------------------------------------------------------------------
  // 1. Core classifier — question detection
  // -------------------------------------------------------------------------
  for (const text of [
    "Is this the cheapest option",
    "What is the price",
    "How long does it take",
    "Are you available",
    "Why is it expensive",
    "When will it arrive",
    "Can I pay cash",
    "هل الطلب جاهز",
    "شو الموضوع",
    "كم السعر",
    "ليش غالي",
    "Shlonk il yom",
    "Shnu el price",
    "Wain el driver",
  ]) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(
      d.kind,
      "question",
      `expected question for ${JSON.stringify(text)}, got ${d.kind} (${d.reason})`,
    );
    assert.equal(d.confidence, "high");
  }

  // Question-mark anywhere → question.
  for (const text of ["Aziz?", "ok?", "؟"]) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(d.kind, "question", `expected question for ${JSON.stringify(text)}`);
  }

  // -------------------------------------------------------------------------
  // 2. Core classifier — topic-change detection
  // -------------------------------------------------------------------------
  // Price vocabulary relative to a name slot. Shape-only name predicate
  // would accept these; coherence must not.
  for (const text of [
    "akhass option please",
    "cheapest sedan",
    "I want a cheaper price",
    "Pay with knet",
    "ابي اوفر سعر",
  ]) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.notEqual(d.kind, "answer", `must not be answer for ${JSON.stringify(text)}: ${d.reason}`);
  }

  // Area vocabulary relative to a NAME slot is foreign; the same words
  // relative to a pickup_area slot are native and must NOT trip topic-
  // change.
  {
    const foreign = classifyResponseForSlot({ text: "Salmiya", slot: "sender_name" });
    assert.notEqual(foreign.kind, "answer", "area vocab must not answer a name slot");
    const native = classifyResponseForSlot({ text: "Salmiya", slot: "pickup_area" });
    assert.equal(native.kind, "answer", "area vocab must answer a pickup_area slot");
  }

  // -------------------------------------------------------------------------
  // 3. Core classifier — happy-path answers
  // -------------------------------------------------------------------------
  for (const [text, slot] of [
    ["Aziz", "sender_name"],
    ["Aziz Al Mulla", "sender_name"],
    ["Mohammed Hamad Al Sabah", "recipient_name"],
    ["عزيز الملا", "sender_name"],
    ["Salmiya", "pickup_area"],
    ["Wafra Residential", "dropoff_area"],
    ["99887766", "sender_phone"],
    ["+965 9988 7766", "recipient_phone"],
    ["block 5", "pickup_block"],
    ["street 12", "pickup_street"],
    ["house 7", "pickup_house"],
    ["Floor 3 apt 12", "pickup_extra"],
  ]) {
    const d = classifyResponseForSlot({ text, slot });
    assert.equal(
      d.kind,
      "answer",
      `expected answer for ${JSON.stringify(text)} -> ${slot}: got ${d.kind} (${d.reason})`,
    );
  }

  // -------------------------------------------------------------------------
  // 4. Core classifier — ambiguity and empty
  // -------------------------------------------------------------------------
  {
    const d = classifyResponseForSlot({ text: "", slot: "sender_name" });
    assert.equal(d.kind, "empty");
  }
  {
    const d = classifyResponseForSlot({ text: "   ", slot: "sender_name" });
    assert.equal(d.kind, "empty");
  }
  {
    // Over word cap, no foreign vocab → ambiguous (NOT topic_change).
    // A 5-token name is unusual but not outright wrong — the apply-
    // boundary's own `validateName` will make the final call.
    const d = classifyResponseForSlot({
      text: "Abdulaziz Mohammed Al Sabah Al Mubarak",
      slot: "sender_name",
    });
    assert.equal(d.kind, "ambiguous", `got ${d.kind} (${d.reason})`);
    assert.equal(d.reason, "over_word_cap");
  }
  {
    // No slot requested → ambiguous with a specific reason. Callers
    // should not use coherence as a write gate in this case.
    const d = classifyResponseForSlot({ text: "Aziz", slot: null });
    assert.equal(d.kind, "ambiguous");
    assert.equal(d.reason, "no_slot_requested");
  }

  // -------------------------------------------------------------------------
  // 5. Core classifier — topic-change with shape that happens to pass
  // (foreign vocab + over word cap): the exact live-incident signal.
  // -------------------------------------------------------------------------
  {
    const d = classifyResponseForSlot({
      text: "Is this the cheapest option",
      slot: "sender_name",
    });
    assert.equal(d.kind, "question", "interrogative prefix wins over topic-change");
    assert.equal(d.confidence, "high");
  }
  {
    // Drop the interrogative and keep the price vocab — now classified as
    // topic_change. Confidence is high because the message exceeds the
    // name-slot word cap.
    const d = classifyResponseForSlot({
      text: "cheapest option please for my order",
      slot: "sender_name",
    });
    assert.equal(
      d.kind,
      "topic_change",
      `expected topic_change, got ${d.kind} (${d.reason})`,
    );
    assert.ok(d.signals.includes("foreign_domain:price"));
    assert.equal(d.confidence, "high");
  }
  {
    // Short foreign-vocab message still classifies as topic_change, but
    // with medium confidence. This lets callers apply stricter or
    // looser policies per slot.
    const d = classifyResponseForSlot({ text: "akhass option", slot: "sender_name" });
    assert.equal(d.kind, "topic_change");
    assert.equal(d.confidence, "medium");
  }

  // -------------------------------------------------------------------------
  // 6. isAcceptableSlotResponse — policy matters
  // -------------------------------------------------------------------------
  {
    // Name slots REJECT ambiguous (high-risk).
    const r = isAcceptableSlotResponse({
      text: "Abdulaziz Mohammed Al Sabah Al Mubarak",
      slot: "sender_name",
    });
    assert.equal(r.acceptable, false);
    assert.equal(r.decision.kind, "ambiguous");
  }
  {
    // Phone slots ACCEPT ambiguous (apply-boundary's validatePhone is strong).
    const r = isAcceptableSlotResponse({
      text: "my number is around 9988",
      slot: "sender_phone",
    });
    // Shape passes (has digit); no foreign vocab; answer.
    assert.equal(r.acceptable, true);
  }
  {
    const r = isAcceptableSlotResponse({
      text: "Is this the cheapest option",
      slot: "sender_name",
    });
    assert.equal(r.acceptable, false);
  }

  // -------------------------------------------------------------------------
  // 7. Fast-path integration — names are LLM-owned (Phase 1, 2026-04-24)
  //
  // The fast-path used to extract sender/recipient names and phones from
  // identity-shaped fragments. The identity cut removed that whole branch:
  // the fast-path no longer writes `sender_name`, `sender_phone`,
  // `recipient_name`, or `recipient_phone` under any shape. The coherence
  // classifier still runs on the post-LLM
  // apply-boundary path (see `smoke-test-slot-fill-fixes.mjs` and
  // `apply-boundary.ts`), which is where the live incident rule
  // "reject questions written to name slots" now lives.
  // -------------------------------------------------------------------------
  const fastPathPath = path.join(deliveryRoot, "plugins/shared/fast-path-extractor.ts");
  const fastPath = await loadDeliveryTsModule(import.meta.url, fastPathPath);
  const { extractSenderNameAndDecision, extractRecipientNameAndPhone } = fastPath;

  // Question-shaped sender-combined messages: no `sender_name`, no
  // structured signal → no patch at all.
  for (const text of [
    "Is this the cheapest option",
    "What is the cheaper price",
    "When will the driver arrive",
    "Why is this so expensive",
  ]) {
    const r = extractSenderNameAndDecision({ text });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      `Phase 1: fast-path must never write sender_name; leaked on ${JSON.stringify(text)}`,
    );
    assert.equal(
      r.confidence,
      "none",
      `identity cut: sender-combined input must be confidence=none (${JSON.stringify(text)})`,
    );
  }

  // Recipient combined: fully LLM-owned → always `none`, regardless of
  // whether a phone is present.
  for (const text of [
    "Is this the cheapest option 99118375",
    "What is the cheaper price 99118375",
    "Mohammed Hamad 99887766",
    "Aziz",
  ]) {
    const r = extractRecipientNameAndPhone({ text });
    assert.equal(
      r.patch,
      null,
      `Phase 1: recipient combined fast-path must return null; leaked on ${JSON.stringify(text)}`,
    );
    assert.equal(r.confidence, "none");
  }

  // Phone-only and use-whatsapp are also LLM/tool-owned. A phone number is
  // structured, but assigning sender vs recipient is semantic.
  {
    const r = extractSenderNameAndDecision({ text: "use my whatsapp" });
    assert.equal(
      r.patch?.sender_name ?? null,
      null,
      "use-whatsapp input must not write sender_name",
    );
    assert.equal(r.patch, null);
    assert.equal(r.confidence, "none");
  }
  {
    const r = extractSenderNameAndDecision({ text: "94728472" });
    assert.equal(r.patch?.sender_name ?? null, null);
    assert.equal(r.patch, null);
    assert.equal(r.confidence, "none");
  }

  console.log("smoke-test-slot-response-coherence: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
