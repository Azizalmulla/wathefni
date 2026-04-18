#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the Kuwaiti-address completeness rule added after the
// 2026-04-17 hallucination incident. Verifies that:
//
//   1. Strict villa-style addresses (block + street + house) remain complete.
//   2. Apartment-style addresses (block + street + substantive extra, no
//      house) are now accepted as complete.
//   3. Trivial / junk extras ("thanks", "ok", single chars) do NOT complete
//      an address that lacks a house number.
//   4. Avenue substitutes for street (block + avenue + house).
//   5. diagnoseTextAddress returns specific sub-field markers the LLM can
//      ask about ("block", "street_or_avenue", "house_or_unit").
//   6. computeOneBrainMissingFields emits both the aggregate marker AND
//      granular sub-fields so downstream control flow keeps working while
//      the LLM gets a precise ask.
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

const { hasCompleteTextAddress, diagnoseTextAddress, hasSubstantiveAddressExtra, diagnoseBookingAddressMissing } =
  await loadTsModule("plugins/octopus-channel/lib/booking-flow.ts");
const { computeOneBrainMissingFields } =
  await loadTsModule("plugins/octopus-channel/lib/one-brain-context.ts");
const { createEmptyBookingDraft } =
  await loadTsModule("plugins/shared/conversation-policy.ts");

// -----------------------------------------------------------------------
// Case 1: villa-style full address → complete
// -----------------------------------------------------------------------
assert(
  hasCompleteTextAddress({ block: "6", street: "9", house: "17" }),
  "case1: villa block+street+house must be complete",
);

// -----------------------------------------------------------------------
// Case 2: yesterday's incident — apartment address that was wrongly rejected
// -----------------------------------------------------------------------
assert(
  hasCompleteTextAddress({
    block: "2",
    street: "9",
    house: null,
    extra: "Apartment 19, floor 8, door 11",
  }),
  "case2: apartment address with substantive extra must be complete (incident 2026-04-17)",
);

// -----------------------------------------------------------------------
// Case 3: garbage extra does NOT complete the address
// -----------------------------------------------------------------------
assert(
  !hasCompleteTextAddress({
    block: "2",
    street: "9",
    house: null,
    extra: "thanks",
  }),
  "case3: 'thanks' is not a locator — must stay incomplete",
);
assert(
  !hasCompleteTextAddress({
    block: "2",
    street: "9",
    house: null,
    extra: "ok",
  }),
  "case3b: 'ok' is not a locator — must stay incomplete",
);

// -----------------------------------------------------------------------
// Case 4: avenue substitutes for street
// -----------------------------------------------------------------------
assert(
  hasCompleteTextAddress({
    block: "6",
    street: null,
    house: "17",
    avenue: "9",
  }),
  "case4: block + avenue + house must be complete",
);
assert(
  hasCompleteTextAddress({
    block: "6",
    street: null,
    house: null,
    avenue: "9",
    extra: "tower 3 apt 5",
  }),
  "case4b: block + avenue + substantive extra must be complete",
);

// -----------------------------------------------------------------------
// Case 5: missing block is always fatal
// -----------------------------------------------------------------------
{
  const d = diagnoseTextAddress({
    block: null,
    street: "9",
    house: "17",
  });
  assert(!d.complete, "case5: missing block must be incomplete");
  assert(d.missing.includes("block"), "case5: 'block' must appear in missing[]");
}

// -----------------------------------------------------------------------
// Case 6: missing street AND missing avenue → street_or_avenue missing
// -----------------------------------------------------------------------
{
  const d = diagnoseTextAddress({
    block: "6",
    street: null,
    house: "17",
  });
  assert(!d.complete, "case6: missing street+avenue must be incomplete");
  assert(
    d.missing.includes("street_or_avenue"),
    "case6: 'street_or_avenue' must appear in missing[]",
  );
}

// -----------------------------------------------------------------------
// Case 7: missing house + missing substantive extra → house_or_unit missing
// -----------------------------------------------------------------------
{
  const d = diagnoseTextAddress({
    block: "6",
    street: "9",
    house: null,
    extra: null,
  });
  assert(!d.complete, "case7: missing house+extra must be incomplete");
  assert(
    d.missing.includes("house_or_unit"),
    "case7: 'house_or_unit' must appear in missing[]",
  );
}

// -----------------------------------------------------------------------
// Case 8: Arabic locators — "شقة 5 دور 3" should be substantive
// -----------------------------------------------------------------------
assert(
  hasSubstantiveAddressExtra("شقة 5 دور 3"),
  "case8: Arabic apartment/floor text must count as substantive",
);
assert(
  hasSubstantiveAddressExtra("برج الخليج طابق ٧"),
  "case8b: 'Gulf tower floor 7' (Arabic) must count as substantive",
);
assert(
  !hasSubstantiveAddressExtra("شكرا"),
  "case8c: 'thanks' in Arabic must NOT count as substantive",
);

// -----------------------------------------------------------------------
// Case 9: digits-only extra ("3") — passes digit check but only 1 char
// (min length 3) so should NOT be substantive
// -----------------------------------------------------------------------
assert(
  !hasSubstantiveAddressExtra("3"),
  "case9: too-short extra must NOT count as substantive even if digit",
);
assert(
  hasSubstantiveAddressExtra("apt 5"),
  "case9b: 'apt 5' (has digit AND keyword) must count as substantive",
);

// -----------------------------------------------------------------------
// Case 10: computeOneBrainMissingFields emits aggregate + granular
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.senderName = "Test";
  draft.senderPhone = "96550000000";
  draft.recipientName = "Friend";
  draft.recipientPhone = "96551111111";
  // pickup: full apartment address → should NOT be in missing
  draft.pickupBlock = "6";
  draft.pickupStreet = "9";
  draft.pickupHouse = "17";
  // delivery: missing house AND no substantive extra
  draft.deliveryBlock = "2";
  draft.deliveryStreet = "9";
  draft.deliveryHouse = null;
  draft.deliveryExtra = null;

  const entry = {
    quotePickupAreaNameEn: "Hawalli",
    quoteDropoffAreaNameEn: "Salmiya",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.5,
  };

  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    missing.includes("delivery.address"),
    "case10: aggregate 'delivery.address' marker must still be emitted (downstream control flow)",
  );
  assert(
    missing.includes("delivery.house_or_unit"),
    "case10: granular 'delivery.house_or_unit' marker must be emitted (LLM targeting)",
  );
  assert(
    !missing.includes("pickup.address"),
    "case10: complete pickup must NOT appear in missing",
  );
  assert(
    !missing.includes("pickup.house_or_unit"),
    "case10: complete pickup must NOT have granular markers either",
  );
}

// -----------------------------------------------------------------------
// Case 11: the exact incident payload — now complete
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.senderName = "Aziz";
  draft.senderPhone = "96550000000";
  draft.recipientName = "Ahmed";
  draft.recipientPhone = "96551111111";
  draft.pickupBlock = "6";
  draft.pickupStreet = "9";
  draft.pickupHouse = "17";
  draft.deliveryBlock = "2";
  draft.deliveryStreet = "9";
  draft.deliveryHouse = null;
  draft.deliveryExtra = "Apartment 19, floor 8, door 11";

  const missing = diagnoseBookingAddressMissing(draft, "delivery");
  assert(
    missing.length === 0,
    `case11: incident payload must now be complete — got missing=${JSON.stringify(missing)}`,
  );
}

console.log("ok: all 11 address-completeness smoke cases passed");
