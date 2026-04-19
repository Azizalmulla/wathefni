#!/usr/bin/env node
/**
 * Smoke test: slot-response coherence rejects greetings for name slots.
 *
 * Background — before this fix, a bare "hello" or "hala" passed name
 * shape (pure letters, short) and carried no foreign-domain
 * vocabulary, so it classified as `answer` for `sender_name` /
 * `recipient_name`. On 2026-04-19 the customer said "hello" while a
 * complete (but corrupted) draft was active; "hello" was considered
 * a sender-name candidate and created a slot conflict against the
 * stored `"Is this the cheapest option"`.
 *
 * The fix adds a `greeting` intent to the coherence classifier. This
 * test pins:
 *
 *   1. English greetings ("hi", "hello", "hey") classify as greeting
 *      for name slots with high confidence.
 *   2. Arabizi / Kuwaiti greetings ("hala", "halla wallah", "marhaba",
 *      "salam alaikum") classify as greeting.
 *   3. Arabic-script greetings ("السلام عليكم", "مرحبا", "أهلا")
 *      classify as greeting.
 *   4. "hello?" (with question mark) still classifies as greeting
 *      (greeting wins over question for these exact forms).
 *   5. "hi, I'm Aziz" does NOT classify as greeting — it's a greeting
 *      PLUS name content, which is still a legitimate answer and
 *      should pass through to the name validator.
 *   6. `isAcceptableSlotResponse` rejects greeting decisions for name
 *      slots (write-path gate).
 *   7. Greeting classification applies uniformly to all slots —
 *      phones, addresses, areas — since a bare greeting isn't a
 *      coherent answer to any slot.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const coherencePath = path.join(deliveryRoot, "plugins/shared/slot-response-coherence.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, coherencePath);
  const { classifyResponseForSlot, isAcceptableSlotResponse } = mod;

  // -------------------------------------------------------------------------
  // 1. English greetings for name slots
  // -------------------------------------------------------------------------
  const englishGreetings = [
    "hi",
    "Hello",
    "HEY",
    "howdy",
    "greetings",
    "yo",
    "good morning",
    "Good evening",
    "good afternoon!",
  ];
  for (const text of englishGreetings) {
    for (const slot of ["sender_name", "recipient_name"]) {
      const d = classifyResponseForSlot({ text, slot });
      assert.equal(
        d.kind,
        "greeting",
        `expected greeting for ${JSON.stringify(text)} on ${slot}, got ${d.kind} (${d.reason})`,
      );
      assert.equal(d.confidence, "high");
    }
  }

  // -------------------------------------------------------------------------
  // 2. Arabizi / Kuwaiti greetings
  // -------------------------------------------------------------------------
  const arabiziGreetings = [
    "hala",
    "halla",
    "Hala wallah",
    "halla wallah",
    "marhaba",
    "Sabah el kheir",
    "sabah al khair",
    "masa el kheir",
    "salam",
    "salaam",
    "salamu alaikum",
    "assalamu alaikum",
  ];
  for (const text of arabiziGreetings) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(
      d.kind,
      "greeting",
      `expected greeting for ${JSON.stringify(text)}, got ${d.kind} (${d.reason})`,
    );
  }

  // -------------------------------------------------------------------------
  // 3. Arabic-script greetings
  // -------------------------------------------------------------------------
  const arabicGreetings = [
    "السلام عليكم",
    "وعليكم السلام",
    "مرحبا",
    "أهلا",
    "اهلا",
    "أهلين",
    "صباح الخير",
    "مساء الخير",
    "هلا",
  ];
  for (const text of arabicGreetings) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(
      d.kind,
      "greeting",
      `expected greeting for ${JSON.stringify(text)}, got ${d.kind} (${d.reason})`,
    );
  }

  // -------------------------------------------------------------------------
  // 4. Greetings with trailing "?" still classify as greeting.
  //    This is the canonical 2026-04-19 case: the customer typed
  //    "hello?" after waiting for the order confirmation.
  // -------------------------------------------------------------------------
  for (const text of ["hello?", "hi?", "hala?"]) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.equal(d.kind, "greeting", `expected greeting for ${JSON.stringify(text)}, got ${d.kind}`);
  }

  // -------------------------------------------------------------------------
  // 5. "hi, I'm Aziz" is NOT a pure greeting — it has name content.
  //    Current classifier treats the whole message shape; downstream
  //    validators decide whether to accept the leading "hi," fragment.
  //    We pin that it does NOT get tagged as `greeting`, so the name
  //    path doesn't short-circuit.
  // -------------------------------------------------------------------------
  for (const text of ["hi, I'm Aziz", "Hello, Aziz", "hala, ana Aziz"]) {
    const d = classifyResponseForSlot({ text, slot: "sender_name" });
    assert.notEqual(
      d.kind,
      "greeting",
      `greeting+content should not short-circuit, got greeting for ${JSON.stringify(text)}`,
    );
  }

  // -------------------------------------------------------------------------
  // 6. isAcceptableSlotResponse rejects greetings for name slots.
  //    This is the write-path gate: the fast-path and apply-boundary
  //    both read `acceptable` and skip the write when false.
  // -------------------------------------------------------------------------
  for (const text of ["hello", "hala", "مرحبا"]) {
    for (const slot of ["sender_name", "recipient_name"]) {
      const res = isAcceptableSlotResponse({ text, slot });
      assert.equal(
        res.acceptable,
        false,
        `greeting ${JSON.stringify(text)} must not be acceptable for ${slot}`,
      );
      assert.equal(res.decision.kind, "greeting");
    }
  }

  // -------------------------------------------------------------------------
  // 7. Greeting rejection applies to other strict slots too.
  //    Addresses should never accept a bare greeting.
  // -------------------------------------------------------------------------
  for (const slot of ["pickup_block", "pickup_street", "pickup_house", "delivery_block"]) {
    const res = isAcceptableSlotResponse({ text: "hello", slot });
    assert.equal(res.acceptable, false, `greeting must not be acceptable for ${slot}`);
  }

  console.log("smoke-test-coherence-greeting: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
