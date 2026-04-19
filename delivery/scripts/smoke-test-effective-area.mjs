#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: pin-resolved area counts as the pickup/delivery area across
// the whole system.
//
// Background (2026-04-19 live incident)
// -------------------------------------
// Customer shared a WhatsApp location pin. The nearest-area resolver
// correctly produced "Mirqab" and persisted the pin under
// `bookingDraft.pendingLocation` with `resolvedAreaName: "Mirqab"`. The
// agent then asked "pickup or delivery?", and the customer replied
// "pickup". The controller moved the pin into `bookingDraft.pickupLocation`
// — BUT `pendingPickupAreaNameEn` / `quotePickupAreaNameEn` were never
// set, so:
//
//   - `computeOneBrainMissingFields` still listed `pickup.area` (it only
//     checked `quotePickupAreaNameEn`).
//   - The LLM context block's pickup line rendered `area: null` even though
//     `pin: "Mirqab"` was right there.
//   - The LLM correctly followed its instructions and asked "which pickup
//     area is it from?", even though Mirqab had just been resolved.
//
// The fix lands in three places and this test covers all three:
//
//   1. `getEffectivePickupAreaName` / `getEffectiveDeliveryAreaName` in
//      `plugins/shared/conversation-policy.ts` — fallback chain
//      quote → pending → pin-resolved.
//   2. `computeOneBrainMissingFields` in
//      `plugins/octopus-channel/lib/one-brain-context.ts` — uses the
//      effective-area helper so a pin-only resolution satisfies the
//      area slot.
//   3. `buildOneBrainLiveContextBlock` — surfaces the effective area in
//      the pickup/delivery lines so the LLM reads `area: "Mirqab"`
//      instead of `area: null`.
//
// Priority order is invariant across the three call sites:
//   quote  >  pending  >  pin
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

const policy = await loadTsModule("plugins/shared/conversation-policy.ts");
const oneBrain = await loadTsModule("plugins/octopus-channel/lib/one-brain-context.ts");

const {
  createEmptyBookingDraft,
  getEffectivePickupAreaName,
  getEffectiveDeliveryAreaName,
} = policy;
const { computeOneBrainMissingFields, formatOneBrainLiveChannelContext } = oneBrain;

function renderContextBlock(entry) {
  return formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "+96599338566",
    preferredReplyLanguage: "en",
    customerScriptMode: "latin",
    controllerEntry: entry,
    quotedRoute: null,
  });
}

function makePin(resolvedAreaName) {
  return {
    source: "location_pin",
    latitude: 29.3,
    longitude: 48.05,
    name: null,
    address: null,
    resolvedAreaName,
  };
}

function makeEntry(overrides = {}) {
  return {
    bookingStep: "none",
    quotePickupAreaNameEn: null,
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: null,
    quoteDropoffAreaNameAr: null,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: null,
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: null,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: null,
    quotedPrice: null,
    stage: "collecting_booking_details",
    bookingDraft: createEmptyBookingDraft(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Helper 1: getEffectivePickupAreaName — quote → pending → pin.
// ---------------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry();
  assert(
    getEffectivePickupAreaName(draft, entry) === "Mirqab",
    "helper: pickup pin-only resolution must be effective area",
  );
}

{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry({ pendingPickupAreaNameEn: "Salmiya" });
  assert(
    getEffectivePickupAreaName(draft, entry) === "Salmiya",
    "helper: pending must beat pin-resolved area",
  );
}

{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Salmiya",
    quotePickupAreaNameEn: "Hawally",
  });
  assert(
    getEffectivePickupAreaName(draft, entry) === "Hawally",
    "helper: quote must beat pending and pin",
  );
}

{
  assert(
    getEffectivePickupAreaName(null, null) === null,
    "helper: all-null inputs must return null",
  );
  assert(
    getEffectivePickupAreaName(createEmptyBookingDraft(), makeEntry()) === null,
    "helper: empty draft+entry must return null (no area anywhere)",
  );
}

// ---------------------------------------------------------------------------
// Helper 2: getEffectiveDeliveryAreaName — symmetric behaviour.
// ---------------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.deliveryLocation = makePin("Jabriya");
  const entry = makeEntry();
  assert(
    getEffectiveDeliveryAreaName(draft, entry) === "Jabriya",
    "helper: delivery pin-only resolution must be effective area",
  );
}

{
  const draft = createEmptyBookingDraft();
  draft.deliveryLocation = makePin("Jabriya");
  const entry = makeEntry({
    pendingDropoffAreaNameEn: "Salwa",
    quoteDropoffAreaNameEn: "Al Masayel",
  });
  assert(
    getEffectiveDeliveryAreaName(draft, entry) === "Al Masayel",
    "helper: delivery quote must beat pending and pin",
  );
}

// ---------------------------------------------------------------------------
// Integration 1: computeOneBrainMissingFields honors pin-resolved area.
// Simulates the 2026-04-19 transcript after the user said "pickup": pin
// is on draft.pickupLocation, pending area is set from the pin lift,
// quote is still null (no get_price yet).
// ---------------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry({ pendingPickupAreaNameEn: "Mirqab" });
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    !missing.includes("pickup.area"),
    `incident: pickup.area must NOT appear in missing_fields when pin resolved + pending set; got ${JSON.stringify(missing)}`,
  );
}

// Belt-and-suspenders: even if only the pin is set (pending somehow
// missing, e.g. a pre-fix persisted entry), the pin-resolved area
// still satisfies the slot — this is the "read-time recovery" case.
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry();
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    !missing.includes("pickup.area"),
    `pin-only: pickup.area must NOT appear in missing_fields when pin has resolvedAreaName (pending=null); got ${JSON.stringify(missing)}`,
  );
}

// Negative case: a pin with NO resolvedAreaName (resolver failed)
// must still leave the slot open.
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin(null);
  const entry = makeEntry();
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    missing.includes("pickup.area"),
    "negative: pickup.area must appear when pin has no resolvedAreaName",
  );
}

// Delivery-side symmetry.
{
  const draft = createEmptyBookingDraft();
  draft.deliveryLocation = makePin("Jabriya");
  const entry = makeEntry({ pendingDropoffAreaNameEn: "Jabriya" });
  const missing = computeOneBrainMissingFields(draft, entry);
  assert(
    !missing.includes("delivery.area"),
    `delivery-integration: delivery.area must NOT appear when pin resolved + pending set; got ${JSON.stringify(missing)}`,
  );
}

// ---------------------------------------------------------------------------
// Integration 2: context-block pickup/delivery lines surface the
// effective area. The LLM reads these lines verbatim, so this is the
// string that drives "area: null" vs "area: Mirqab".
// ---------------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Mirqab",
    bookingDraft: draft,
  });
  const block = renderContextBlock(entry);
  assert(
    /pickup:\s*\{\s*area:\s*"Mirqab"/.test(block),
    `context-block: pickup line must read area: "Mirqab" when pin resolved; got:\n${block}`,
  );
}

{
  const draft = createEmptyBookingDraft();
  draft.deliveryLocation = makePin("Jabriya");
  const entry = makeEntry({
    pendingDropoffAreaNameEn: "Jabriya",
    bookingDraft: draft,
  });
  const block = renderContextBlock(entry);
  assert(
    /delivery:\s*\{\s*area:\s*"Jabriya"/.test(block),
    `context-block: delivery line must read area: "Jabriya" when pin resolved; got:\n${block}`,
  );
}

// ---------------------------------------------------------------------------
// Integration 3: quote still wins in the context block (we must not
// regress the ordering — a priced area is always authoritative).
// ---------------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  draft.pickupLocation = makePin("Mirqab");
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Salmiya",
    quotePickupAreaNameEn: "Hawally",
    bookingDraft: draft,
  });
  const block = renderContextBlock(entry);
  assert(
    /pickup:\s*\{\s*area:\s*"Hawally"/.test(block),
    `context-block: quote must beat pending and pin; got:\n${block}`,
  );
}

console.log("smoke-test-effective-area: OK");
