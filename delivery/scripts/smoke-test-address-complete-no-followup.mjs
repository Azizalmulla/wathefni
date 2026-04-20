#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: when an address side is already satisfied under
// `hasSatisfiedBookingAddress`, the directive must forbid the LLM from
// asking for any more sub-fields of that side (Bug 2, 2026-04-20).
//
// Product rule:
//   The server's address completeness predicate accepts a substantive
//   `address_extra` (apartment/floor/door + digit or locator keyword) in
//   place of `address_house`. When the server judges a side complete,
//   `missing_fields` omits it and the LLM must not ask for the house /
//   building number in a follow-up reply.
//
// Cases covered:
//   T1  pickup complete via `address_house` → forbidden shapes include
//       `ask_for_satisfied_pickup_address_field`; the house-specific
//       shape does NOT fire (house is present, not extra).
//   T2  delivery complete via `address_extra` (apartment-style) → both
//       `ask_for_satisfied_delivery_address_field` AND
//       `ask_for_delivery_house_when_extra_satisfies_completeness` fire.
//   T3  pickup incomplete, delivery complete → only the delivery shapes
//       are added. Pickup's sub-field ask stays allowed.
//   T4  both sides complete, no collection missing → summary directive
//       still inherits the per-side forbidden shapes.
//   T5  apartment-style text "block 11, street 8, apartment 11, floor 11,
//       door 14" after extraction → side is complete under the server
//       predicate (reproduces the reported transcript shape).
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

const policy = loadTs("plugins/shared/conversation-policy.ts");
const oneBrain = loadTs("plugins/octopus-channel/lib/one-brain-context.ts");
const bookingFlow = loadTs("plugins/octopus-channel/lib/booking-flow.ts");
const { createEmptyBookingDraft } = policy;
const { computeOneBrainNextRequiredAction, computeOneBrainMissingFields } = oneBrain;
const { hasSatisfiedBookingAddress } = bookingFlow;

function makeEntry(overrides = {}) {
  return {
    bookingStep: "none",
    quotePickupAreaNameEn: "Jabriya",
    quotePickupAreaNameAr: "الجابرية",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: "عادي",
    selectedQuoteOptionLabelEn: "Standard",
    selectedQuoteOptionPrice: 2.5,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 2.5,
    stage: "collecting_booking_details",
    ...overrides,
  };
}

// -----------------------------------------------------------------------
// T1: pickup complete via address_house; extra-specific shape MUST NOT
// fire (there is no `address_extra` in play on pickup).
// -----------------------------------------------------------------------
{
  const draft = {
    ...createEmptyBookingDraft(),
    senderName: null,
    senderPhone: null,
    pickupBlock: "6",
    pickupStreet: "9",
    pickupHouse: "17",
    pickupExtra: null,
  };
  const entry = makeEntry({ bookingDraft: draft });
  assert(hasSatisfiedBookingAddress(draft, "pickup"), "T1: pickup must be satisfied via house");
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(!missing.includes("pickup.address"), `T1: pickup.address not missing; got ${missing}`);
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive.forbiddenShapes.includes("ask_for_satisfied_pickup_address_field"),
    `T1: forbidden shapes include pickup-satisfied; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert(
    !directive.forbiddenShapes.includes("ask_for_pickup_house_when_extra_satisfies_completeness"),
    `T1: extra-specific shape must NOT fire when house present; got ${JSON.stringify(
      directive.forbiddenShapes,
    )}`,
  );
}

// -----------------------------------------------------------------------
// T2: delivery complete via apartment-style address_extra — the exact
// transcript shape ("block 11, street 8, apartment 11, floor 11, door 14").
// Both the generic and the house-specific shapes fire.
// -----------------------------------------------------------------------
{
  const draft = {
    ...createEmptyBookingDraft(),
    senderName: "Aziz",
    senderPhone: "96599338566",
    recipientName: "Ahmad",
    recipientPhone: "96550001111",
    pickupBlock: "6",
    pickupStreet: "9",
    pickupHouse: "17",
    deliveryBlock: "11",
    deliveryStreet: "8",
    deliveryHouse: null,
    deliveryExtra: "apartment 11, floor 11, door 14",
  };
  const entry = makeEntry({ bookingDraft: draft });
  assert(
    hasSatisfiedBookingAddress(draft, "delivery"),
    "T2: delivery must be satisfied by substantive extra",
  );
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    !missing.includes("delivery.address"),
    `T2: delivery.address not missing; got ${JSON.stringify(missing)}`,
  );
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive.forbiddenShapes.includes("ask_for_satisfied_delivery_address_field"),
    `T2: forbidden shapes include delivery-satisfied; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert(
    directive.forbiddenShapes.includes(
      "ask_for_delivery_house_when_extra_satisfies_completeness",
    ),
    `T2: forbidden shapes include delivery-house-when-extra-completes; got ${JSON.stringify(
      directive.forbiddenShapes,
    )}`,
  );
}

// -----------------------------------------------------------------------
// T3: pickup incomplete, delivery complete. Only delivery shapes land
// in forbiddenShapes; pickup can still be asked.
// -----------------------------------------------------------------------
{
  const draft = {
    ...createEmptyBookingDraft(),
    senderName: "Aziz",
    senderPhone: "96599338566",
    recipientName: "Ahmad",
    recipientPhone: "96550001111",
    pickupBlock: null,
    pickupStreet: null,
    pickupHouse: null,
    pickupExtra: null,
    deliveryBlock: "11",
    deliveryStreet: "8",
    deliveryHouse: null,
    deliveryExtra: "apartment 11, floor 11, door 14",
  };
  const entry = makeEntry({ bookingDraft: draft });
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(missing.includes("pickup.address"), `T3: pickup.address MUST be missing; got ${missing}`);
  assert(
    !missing.includes("delivery.address"),
    `T3: delivery.address not missing; got ${JSON.stringify(missing)}`,
  );
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive.action === "ASK_PICKUP_ADDRESS",
    `T3: action=ASK_PICKUP_ADDRESS; got ${JSON.stringify(directive)}`,
  );
  assert(
    directive.forbiddenShapes.includes("ask_for_satisfied_delivery_address_field"),
    `T3: delivery-satisfied shape included; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert(
    !directive.forbiddenShapes.includes("ask_for_satisfied_pickup_address_field"),
    `T3: pickup-satisfied must NOT fire; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
}

// -----------------------------------------------------------------------
// T4: every collection slot filled → summary directive still carries
// the per-side forbidden shapes.
// -----------------------------------------------------------------------
{
  const draft = {
    ...createEmptyBookingDraft(),
    senderName: "Aziz",
    senderPhone: "96599338566",
    recipientName: "Ahmad",
    recipientPhone: "96550001111",
    pickupBlock: "6",
    pickupStreet: "9",
    pickupHouse: "17",
    deliveryBlock: "11",
    deliveryStreet: "8",
    deliveryHouse: null,
    deliveryExtra: "apartment 11, floor 11, door 14",
  };
  const entry = makeEntry({ bookingDraft: draft });
  const missing = computeOneBrainMissingFields(draft, entry);
  const collectionMarkers = [
    "sender.name",
    "sender.phone",
    "recipient.name",
    "recipient.phone",
    "pickup.address",
    "delivery.address",
  ];
  assert(
    !collectionMarkers.some((m) => missing.includes(m)),
    `T4: no collection fields missing; got ${JSON.stringify(missing)}`,
  );
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive.action === "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    `T4: summary directive; got ${JSON.stringify(directive)}`,
  );
  assert(
    directive.forbiddenShapes.includes("ask_for_satisfied_pickup_address_field"),
    `T4: pickup-satisfied on summary; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert(
    directive.forbiddenShapes.includes("ask_for_satisfied_delivery_address_field"),
    `T4: delivery-satisfied on summary; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert(
    directive.forbiddenShapes.includes(
      "ask_for_delivery_house_when_extra_satisfies_completeness",
    ),
    `T4: delivery-house-when-extra on summary; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
}

// -----------------------------------------------------------------------
// T5: neither side fully satisfied yet → no per-side forbidden shapes,
// but the normal sender ask fires cleanly.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({ bookingDraft: draft });
  const missing = computeOneBrainMissingFields(draft, entry);
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive.action === "ASK_SENDER_NAME_AND_PHONE_DECISION",
    `T5: sender ask; got ${JSON.stringify(directive)}`,
  );
  assert(
    !directive.forbiddenShapes.some((s) => s.startsWith("ask_for_satisfied_")),
    `T5: no per-side satisfied shape when nothing satisfied; got ${JSON.stringify(
      directive.forbiddenShapes,
    )}`,
  );
}

console.log("smoke-test-address-complete-no-followup: OK");
