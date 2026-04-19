#!/usr/bin/env node
/**
 * Smoke test: read-time sanitization of persisted booking state.
 *
 * Background — before this fix, any corrupted field that made it onto
 * disk (or into the conversation-controller cache) stayed there
 * forever. The 2026-04-19 15:28 incident is the canonical case: a
 * customer's saved profile contained
 * `sender.name = "Is this the cheapest option"` from a session before
 * the coherence fix landed; the write-side fix stopped new
 * corruption, but the old value kept surfacing every turn because the
 * read path trusted it.
 *
 * The principled fix is read-time sanitization at every load
 * boundary. This test pins:
 *
 *   1. `sanitizeBookingDraft` clears name fields that fail
 *      `validateName` (question-shape, too many words, artifact).
 *   2. `sanitizeBookingDraft` clears phone fields that fail
 *      `cleanPhone` (non-digits, too short/long).
 *   3. `sanitizeBookingDraft` clears address-part fields that fail
 *      `cleanAddressPart` (empty after trim, artifact, no alnum).
 *   4. Valid fields survive untouched.
 *   5. `sanitizeSavedOrder` runs per-field validation on the saved
 *      last-successful-order (sender / recipient / pickup / delivery).
 *   6. Poisoned-sender-name (the canonical 2026-04-19 case) is
 *      detected and cleared with reason `name_looks_like_question`.
 *   7. Drops are reported with field + reason + received so ops can
 *      grep for historical corruption.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { deliveryRoot, loadDeliveryTsModule } from "./_helpers/riders-plugin-loader.mjs";

async function main() {
  const sanitizerPath = path.join(deliveryRoot, "plugins/shared/persisted-state-sanitizer.ts");
  const mod = await loadDeliveryTsModule(import.meta.url, sanitizerPath);
  const { sanitizeBookingDraft, sanitizeSavedOrder, formatSanitizerDrops } = mod;

  // -------------------------------------------------------------------------
  // 1. sanitizeBookingDraft — name fields that fail validateName
  // -------------------------------------------------------------------------
  {
    const poisonedDraft = {
      senderName: "Is this the cheapest option",
      senderPhone: "99118375",
      recipientName: "aziz almulla",
      recipientPhone: "99338566",
      pickupBlock: "3",
      pickupStreet: "4",
      pickupHouse: "19",
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: "11",
      deliveryStreet: "7",
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: "apartment 11, floor 4, door 10",
      deliveryLocation: null,
      pendingLocation: null,
    };
    const res = sanitizeBookingDraft(poisonedDraft);
    assert.equal(res.value.senderName, null, "poisoned senderName must be cleared");
    assert.equal(res.value.recipientName, "aziz almulla", "valid recipientName must survive");
    assert.equal(res.value.senderPhone, "99118375", "valid sender phone must survive");
    assert.equal(res.value.recipientPhone, "99338566", "valid recipient phone must survive");
    assert.equal(res.value.pickupBlock, "3");
    assert.equal(res.value.deliveryExtra, "apartment 11, floor 4, door 10", "extra must be preserved untouched");
    assert.ok(res.drops.length >= 1, "must report at least one drop");
    const senderDrop = res.drops.find((d) => d.field === "senderName");
    assert.ok(senderDrop, "must report senderName drop");
    assert.equal(senderDrop.reason, "name_looks_like_question");
    assert.equal(senderDrop.source, "controller_entry");
    assert.ok(senderDrop.received.includes("cheapest"));
  }

  // -------------------------------------------------------------------------
  // 2. sanitizeBookingDraft — phone fields
  // -------------------------------------------------------------------------
  {
    const draft = {
      senderName: "Aziz",
      senderPhone: "not a phone",
      recipientName: "Ahmad",
      recipientPhone: "123",
      pickupBlock: null,
      pickupStreet: null,
      pickupHouse: null,
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: null,
      deliveryStreet: null,
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: null,
      deliveryLocation: null,
      pendingLocation: null,
    };
    const res = sanitizeBookingDraft(draft);
    assert.equal(res.value.senderPhone, null, "non-digit phone must be cleared");
    assert.equal(res.value.recipientPhone, null, "too-short phone must be cleared");
    assert.equal(res.value.senderName, "Aziz", "valid name survives");
    const phoneDrops = res.drops.filter((d) => d.field.includes("Phone"));
    assert.equal(phoneDrops.length, 2, `expected 2 phone drops, got ${phoneDrops.length}`);
  }

  // -------------------------------------------------------------------------
  // 3. sanitizeBookingDraft — address-part fields
  // -------------------------------------------------------------------------
  {
    const draft = {
      senderName: null,
      senderPhone: null,
      recipientName: null,
      recipientPhone: null,
      pickupBlock: "---",
      pickupStreet: "ok",
      pickupHouse: "   ",
      pickupAvenue: "11A",
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: null,
      deliveryStreet: null,
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: null,
      deliveryLocation: null,
      pendingLocation: null,
    };
    const res = sanitizeBookingDraft(draft);
    assert.equal(res.value.pickupBlock, null, "artifact block must be cleared");
    assert.equal(res.value.pickupStreet, null, "artifact street ('ok') must be cleared");
    assert.equal(res.value.pickupHouse, null, "whitespace-only house must be cleared/null");
    assert.equal(res.value.pickupAvenue, "11A", "valid avenue survives");
  }

  // -------------------------------------------------------------------------
  // 4. sanitizeBookingDraft — fully valid draft passes unchanged
  // -------------------------------------------------------------------------
  {
    const draft = {
      senderName: "Aziz Almulla",
      senderPhone: "99118375",
      recipientName: "Ahmad",
      recipientPhone: "99338566",
      pickupBlock: "3",
      pickupStreet: "4",
      pickupHouse: "19",
      pickupAvenue: null,
      pickupExtra: null,
      pickupLocation: null,
      deliveryBlock: "11",
      deliveryStreet: "7",
      deliveryHouse: null,
      deliveryAvenue: null,
      deliveryExtra: null,
      deliveryLocation: null,
      pendingLocation: null,
    };
    const res = sanitizeBookingDraft(draft);
    assert.equal(res.drops.length, 0, `valid draft must have zero drops, got ${JSON.stringify(res.drops)}`);
    assert.equal(res.value.senderName, "Aziz Almulla");
    assert.equal(res.value.pickupHouse, "19");
  }

  // -------------------------------------------------------------------------
  // 5. sanitizeBookingDraft — null input handling
  // -------------------------------------------------------------------------
  {
    const res = sanitizeBookingDraft(null);
    assert.equal(res.value, null);
    assert.equal(res.drops.length, 0);
  }

  // -------------------------------------------------------------------------
  // 6. sanitizeSavedOrder — the canonical 2026-04-19 profile
  // -------------------------------------------------------------------------
  {
    const poisonedOrder = {
      sender: { name: "Is this the cheapest option", phone: "99118375" },
      recipient: { name: "aziz almulla", phone: "99338566" },
      pickup: { area_en: "Shalehat Jlea'a", house: "19", avenue: null, block: "3", street: "4" },
      delivery: { area_en: "Wafra Residential", house: null, avenue: null, block: "11", street: "7" },
      payer: "sender",
      service: "standard_sedan",
    };
    const res = sanitizeSavedOrder(poisonedOrder);
    assert.equal(res.value.sender.name, null, "poisoned sender.name must be cleared");
    assert.equal(res.value.sender.phone, "99118375", "sender.phone survives");
    assert.equal(res.value.recipient.name, "aziz almulla", "recipient.name survives");
    assert.equal(res.value.pickup.house, "19", "valid pickup.house survives");
    // Non-validated fields are preserved verbatim.
    assert.equal(res.value.payer, "sender");
    assert.equal(res.value.service, "standard_sedan");
    assert.equal(res.value.pickup.area_en, "Shalehat Jlea'a");
    const drop = res.drops.find((d) => d.field === "last_successful_order.sender.name");
    assert.ok(drop, "must report sender.name drop");
    assert.equal(drop.reason, "name_looks_like_question");
    assert.equal(drop.source, "customer_profile");
  }

  // -------------------------------------------------------------------------
  // 7. sanitizeSavedOrder — absent sub-objects preserved
  // -------------------------------------------------------------------------
  {
    const partial = { sender: { name: "Aziz", phone: "99118375" } };
    const res = sanitizeSavedOrder(partial);
    assert.equal(res.drops.length, 0);
    assert.equal(res.value.sender.name, "Aziz");
    assert.equal(res.value.recipient, undefined, "absent recipient stays absent");
  }

  // -------------------------------------------------------------------------
  // 8. formatSanitizerDrops — structured single-line format
  // -------------------------------------------------------------------------
  {
    const drops = [
      { field: "senderName", reason: "name_looks_like_question", received: "Is this the cheapest option", source: "controller_entry" },
      { field: "senderPhone", reason: "phone_contains_non_digits", received: "abc", source: "controller_entry" },
    ];
    const formatted = formatSanitizerDrops(drops);
    assert.ok(formatted.includes("senderName=name_looks_like_question"));
    assert.ok(formatted.includes("senderPhone=phone_contains_non_digits"));
  }

  console.log("smoke-test-persisted-state-sanitizer: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
