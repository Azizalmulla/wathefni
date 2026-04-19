#!/usr/bin/env node
/**
 * Smoke test: slot-response coherence rejects acknowledgments for name
 * slots.
 *
 * Background — 2026-04-19 22:08 live transcript:
 *
 *   Bot:      "Delivery from Salmiya to Salwa — Price: 1.250 KWD …"
 *   Customer: "alright"
 *   Bot:      "Send me the sender phone number."   ← skipped the name!
 *
 * The fast-path extractor's name gate used `isAcceptableSlotResponse`
 * which had no `acknowledgment` branch. `alright` passed letters-only
 * shape and carried no foreign-domain vocabulary, so the classifier
 * returned `answer`. The pre-applier wrote `sender_name = "alright"`,
 * the draft advanced, and the real name step was silently skipped.
 *
 * The fix adds an `acknowledgment` branch to `classifyResponseForSlot`
 * that fires BEFORE question/topic-change classification — symmetric
 * with the existing `greeting` branch. This test pins:
 *
 *   1. English acks (`ok`, `okay`, `alright`, `sure`, `yes`, `yeah`,
 *      `fine`, `cool`, `great`, `perfect`, `got it`, `sounds good`,
 *      `noted`, `done`) classify as `acknowledgment` for name slots
 *      with high confidence.
 *   2. Arabizi / Kuwaiti acks (`tamam`, `mashi`, `zain`, `yalla`,
 *      `akeed`, `tayeb`, `inshallah`) classify as `acknowledgment`.
 *   3. Arabic-script acks (`تمام`, `طيب`, `زين`, `ماشي`, `اوكي`,
 *      `اكيد`, `ان شاء الله`, `يلا`) classify as `acknowledgment`.
 *   4. `alright, I'm Aziz` does NOT classify as acknowledgment — it's
 *      an acknowledgment PLUS content, which is still a legitimate
 *      answer and should flow through to the name validator.
 *   5. `isAcceptableSlotResponse` rejects acknowledgment decisions for
 *      name slots (write-path gate).
 *   6. Acknowledgment classification applies uniformly — bare `ok` is
 *      not a coherent answer to phones, addresses, or areas either.
 *   7. Greeting and acknowledgment are distinct kinds — a greeting
 *      stays `greeting`, not `acknowledgment`.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const coherencePath = path.join(deliveryRoot, "plugins/shared/slot-response-coherence.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, coherencePath);
  const { classifyResponseForSlot, isAcceptableSlotResponse } = mod;

  // -------------------------------------------------------------------------
  // 1. English acknowledgments for name slots
  // -------------------------------------------------------------------------
  const englishAcks = [
    "ok",
    "Ok",
    "OK",
    "okay",
    "okey",
    "alright",
    "Alright",
    "alrighty",
    "sure",
    "Sure",
    "fine",
    "cool",
    "nice",
    "great",
    "perfect",
    "awesome",
    "excellent",
    "yes",
    "Yes",
    "yeah",
    "yep",
    "yup",
    "done",
    "noted",
    "got it",
    "Got it",
    "sounds good",
    "Sounds good",
    "go ahead",
    "do it",
    "proceed",
    // trailing punctuation
    "ok.",
    "alright!",
    "yes!!",
    "sure,",
  ];
  for (const text of englishAcks) {
    for (const slot of ["sender_name", "recipient_name"]) {
      const d = classifyResponseForSlot({ text, slot });
      assert.equal(
        d.kind,
        "acknowledgment",
        `expected acknowledgment for ${JSON.stringify(text)} on ${slot}, got ${d.kind} (${d.reason})`,
      );
      assert.equal(d.confidence, "high");
    }
  }

  // -------------------------------------------------------------------------
  // 2. Arabizi / Kuwaiti acknowledgments
  // -------------------------------------------------------------------------
  const arabiziAcks = [
    "tamam",
    "Tamam",
    "tmam",
    "mashi",
    "maashi",
    "zain",
    "Zain",
    "zein",
    "yalla",
    "yallah",
    "akeed",
    "akid",
    "tayeb",
    "inshallah",
    "isa",
  ];
  for (const text of arabiziAcks) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(
      d.kind,
      "acknowledgment",
      `expected acknowledgment for ${JSON.stringify(text)}, got ${d.kind} (${d.reason})`,
    );
  }

  // -------------------------------------------------------------------------
  // 3. Arabic-script acknowledgments
  // -------------------------------------------------------------------------
  const arabicAcks = [
    "تمام",
    "تم",
    "طيب",
    "ماشي",
    "زين",
    "اوكي",
    "أوكي",
    "اوك",
    "نعم",
    "أكيد",
    "اكيد",
    "ان شاء الله",
    "إن شاء الله",
    "يلا",
    "يلله",
  ];
  for (const text of arabicAcks) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(
      d.kind,
      "acknowledgment",
      `expected acknowledgment for ${JSON.stringify(text)}, got ${d.kind} (${d.reason})`,
    );
  }

  // -------------------------------------------------------------------------
  // 4. Acknowledgment + content is NOT an acknowledgment
  //
  // The whole-message anchor on the patterns means these fall through
  // to the normal slot-shape path. Exact kind depends on shape/coherence
  // — the important thing is they're NOT tagged acknowledgment.
  // -------------------------------------------------------------------------
  const notAcks = [
    "alright, I'm Aziz",
    "ok my name is Ahmed",
    "yes Aziz Almulla",
    "Sure, Ahmed Basha",
    "تمام اسمي عزيز",
  ];
  for (const text of notAcks) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.notEqual(
      d.kind,
      "acknowledgment",
      `${JSON.stringify(text)} must NOT be classified as acknowledgment, got ${d.kind}`,
    );
  }

  // -------------------------------------------------------------------------
  // 5. Write-path gate — `isAcceptableSlotResponse` rejects acks
  //    for name slots (strict slots).
  // -------------------------------------------------------------------------
  for (const text of ["alright", "ok", "yes", "تمام", "zain"]) {
    const res = isAcceptableSlotResponse({ text, slot: "sender_name" });
    assert.equal(
      res.acceptable,
      false,
      `${JSON.stringify(text)} must NOT be acceptable as sender_name`,
    );
    assert.equal(res.decision.kind, "acknowledgment");
  }
  for (const text of ["alright", "ok", "yes", "تمام"]) {
    const res = isAcceptableSlotResponse({ text, slot: "recipient_name" });
    assert.equal(
      res.acceptable,
      false,
      `${JSON.stringify(text)} must NOT be acceptable as recipient_name`,
    );
    assert.equal(res.decision.kind, "acknowledgment");
  }

  // -------------------------------------------------------------------------
  // 6. Uniform across slots — bare `ok` is not a coherent answer to
  //    phones, addresses, or areas either.
  // -------------------------------------------------------------------------
  const nonNameSlots = [
    "sender_phone",
    "recipient_phone",
    "pickup_area",
    "dropoff_area",
    "pickup_block",
    "delivery_block",
  ];
  for (const slot of nonNameSlots) {
    const d = classifyResponseForSlot({ text: "ok", slot });
    assert.equal(
      d.kind,
      "acknowledgment",
      `"ok" must be acknowledgment on ${slot}, got ${d.kind}`,
    );
  }

  // -------------------------------------------------------------------------
  // 7. Greeting and acknowledgment are distinct — `hi` stays greeting.
  // -------------------------------------------------------------------------
  {
    const hi = classifyResponseForSlot({ text: "hi", slot: "sender_name" });
    assert.equal(hi.kind, "greeting", `"hi" must stay greeting, got ${hi.kind}`);
    const ok = classifyResponseForSlot({ text: "ok", slot: "sender_name" });
    assert.equal(ok.kind, "acknowledgment", `"ok" must be acknowledgment, got ${ok.kind}`);
  }

  // -------------------------------------------------------------------------
  // 8. Regression anchor for the 2026-04-19 22:08 incident.
  // -------------------------------------------------------------------------
  {
    const d = classifyResponseForSlot({ text: "alright", slot: "sender_name" });
    assert.equal(d.kind, "acknowledgment");
    assert.equal(d.confidence, "high");
    const res = isAcceptableSlotResponse({ text: "alright", slot: "sender_name" });
    assert.equal(res.acceptable, false);
    assert.equal(res.decision.reason, "acknowledgment");
  }

  console.log("smoke-test-coherence-acknowledgment: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
