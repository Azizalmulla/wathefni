#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: pre-pricing, the LLM must ask for a missing route area
// before any sender/recipient collection.
//
// Product rule (2026-04-19):
//   If pickup.area or delivery.area is missing while a booking is being
//   collected, the runtime's `next_required_action` directive must steer
//   the LLM to ASK_*_AREA (or ASK_MISSING_AREAS when both sides are
//   missing). No sender/recipient asks until the route resolves.
//
// Cases covered:
//   T1  both areas missing → ASK_MISSING_AREAS
//   T2  only pickup.area missing → ASK_PICKUP_AREA
//   T3  only delivery.area missing → ASK_DELIVERY_AREA
//   T4  both areas resolved → fall through to the post-pricing path
//       (which returns null pre-quote; the LLM reasons freely)
//   T5  stage !== collecting_booking_details / quoted → no pre-pricing
//       gate (pure chit-chat stays in SKILL.md's domain)
//   T6  forbiddenShapes include the new sequence anchors
//       (ask_sender_before_area / ask_recipient_before_area)
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
const { createEmptyBookingDraft } = policy;
const { computeOneBrainNextRequiredAction } = oneBrain;

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

// -----------------------------------------------------------------------
// T1: both areas missing → ASK_MISSING_AREAS.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry();
  const missing = ["pickup.area", "delivery.area", "sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(directive?.action === "ASK_MISSING_AREAS", `T1: ${JSON.stringify(directive)}`);
  assert(directive.field === "areas", `T1: field=${directive?.field}`);
}

// -----------------------------------------------------------------------
// T2: only pickup.area missing → ASK_PICKUP_AREA.
// This is the 2026-04-19 transcript case (pin set delivery via Qibla
// somehow resolved — or the symmetric version). We emit the specific
// side so the LLM asks the one question that matters.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({ quoteDropoffAreaNameEn: "Qibla" });
  const missing = ["pickup.area", "sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive?.action === "ASK_PICKUP_AREA",
    `T2: want ASK_PICKUP_AREA; got ${JSON.stringify(directive)}`,
  );
  assert(directive.field === "pickup.area", `T2: field=${directive?.field}`);
}

// -----------------------------------------------------------------------
// T3: only delivery.area missing → ASK_DELIVERY_AREA.
// Exactly the screenshot transcript: pin resolved pickup to Qibla; the
// LLM was asking for sender while delivery.area was still blank.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({ quotePickupAreaNameEn: "Qibla" });
  const missing = ["delivery.area", "sender.name", "sender.phone", "recipient.name"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive?.action === "ASK_DELIVERY_AREA",
    `T3: want ASK_DELIVERY_AREA; got ${JSON.stringify(directive)}`,
  );
  assert(directive.field === "delivery.area", `T3: field=${directive?.field}`);
}

// -----------------------------------------------------------------------
// T4: both areas resolved + no price yet → the pre-pricing gate falls
// through. The post-pricing path returns null because quotedPrice is
// still null, which is the correct intermediate "LLM reasons freely
// using SKILL.md" state between area resolution and get_price.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({
    quotePickupAreaNameEn: "Qibla",
    quoteDropoffAreaNameEn: "Salmiya",
  });
  const missing = ["sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(directive === null, `T4: expected null, got ${JSON.stringify(directive)}`);
}

// -----------------------------------------------------------------------
// T5: stage is not a booking-collection stage → the pre-pricing gate
// does NOT fire. Pure chit-chat or pre-quote states stay in SKILL.md's
// domain, as before.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({ stage: "greeting" });
  const missing = ["pickup.area", "delivery.area"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(directive === null, `T5: no gate pre-booking; got ${JSON.stringify(directive)}`);
}

// -----------------------------------------------------------------------
// T6: forbiddenShapes list the sequence-anchor markers the prompt
// enforcer keys on.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry();
  const missing = ["pickup.area", "delivery.area"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive?.forbiddenShapes?.includes("ask_sender_before_area"),
    `T6: forbiddenShapes includes ask_sender_before_area; got ${JSON.stringify(directive?.forbiddenShapes)}`,
  );
  assert(
    directive.forbiddenShapes.includes("ask_recipient_before_area"),
    `T6: forbiddenShapes includes ask_recipient_before_area; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
}

// -----------------------------------------------------------------------
// T7: stage "quoted" (post-price, pre-collection) with a missing area
// also fires the gate — this is the case where the price went stale
// and the customer has typed a new route partially.
// -----------------------------------------------------------------------
{
  const draft = createEmptyBookingDraft();
  const entry = makeEntry({ stage: "quoted", quotePickupAreaNameEn: "Qibla" });
  const missing = ["delivery.area"];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert(
    directive?.action === "ASK_DELIVERY_AREA",
    `T7: quoted+delivery-missing must ASK_DELIVERY_AREA; got ${JSON.stringify(directive)}`,
  );
}

console.log("smoke-test-area-before-identity: OK");
