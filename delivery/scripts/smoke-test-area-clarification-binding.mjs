#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: area-clarification state binding (2026-04-21 regression).
//
// Background
// ----------
// Customer sent `delivery salmiya to kuwait city pls`. The pricing tool
// resolved Salmiya, flagged Kuwait City as an `ambiguity_group` (sub-areas:
// Sharq, Mirqab, Qibla, Bnaid Al-Qar, Dasman), and pushed:
//   - `set_pending_area(pickup_area=Salmiya)`
//   - `set_requested_slot(dropoff_area, options=[…])`
// + returned an ambiguity result. BUT because no `apply_booking_field`
// patch fired on the same turn, `applyBookingDraftProgress` was not
// invoked during the drain, so controller `stage` stayed at `idle`.
// `computeOneBrainNextRequiredAction` only dispatches `ASK_PICKUP_AREA` /
// `ASK_DELIVERY_AREA` when `stage ∈ {collecting_booking_details,
// quoted}`, so the directive dispatcher never fired; the LLM free-composed
// the clarification question itself.
//
// On the next turn, the customer answered "mirqab". The LLM, seeing
// `stage=idle` context with no `pending_*_area` hint, called
// `get_price(pickup=Mirqab, dropoff=Mirqab)` symmetrically. The server
// had no evidence to reject the symmetric binding and produced a
// zero-distance route ("Mirqab → Mirqab, 1.250 KWD (standard sedan)").
// The outbound verify layer detected the shape but was log-only.
//
// Fix — layered, scope-tight
// --------------------------
//   1. Drain loop in `plugins/octopus-channel/index.ts` promotes
//      controller stage from `idle` → `collecting_booking_details`
//      when any `set_pending_area` op fires. That makes the directive
//      dispatcher take over for the clarification turn itself.
//   2. `renderAskPickupArea` / `renderAskDeliveryArea` in the directive
//      registry now recap the preserved side plus the `requestedSlot`
//      options, so the server-composed reply is at least as
//      informative as the LLM's was.
//   3. Pricing tool symmetric-rebind guard: when the LLM echoes
//      `pickup_area == dropoff_area` on a turn where `requestedSlot`
//      is a `*_area` slot and the controller has the OPPOSITE side
//      pinned as `pending*AreaNameEn`, override the non-requested leg
//      to the pinned value. This cuts off the symmetric rebind.
//   4. `one-brain-context.ts` surfaces the pinned area(s) and a
//      `pending_area_rule` hard rule explicitly forbidding symmetric
//      `get_price` calls.
//   5. `outbound-verify.ts` adds a `route_zero_distance` shape
//      (triggered when `quotePickupAreaNameEn == quoteDropoffAreaNameEn`)
//      and actively substitutes a recovery ask — belt-and-braces for
//      when all upstream guards have somehow missed.
//
// This test covers assertions for each layer.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const policy = await loadTsModule("plugins/shared/conversation-policy.ts");
const registry = await loadTsModule(
  "plugins/octopus-channel/lib/directive-reply-registry.ts",
);
const outboundVerify = await loadTsModule(
  "plugins/shared/outbound-verify.ts",
);
const oneBrain = await loadTsModule(
  "plugins/octopus-channel/lib/one-brain-context.ts",
);

const { createEmptyBookingDraft } = policy;
const { renderDirectiveReply } = registry;
const { classifyOutboundReplyShape, verifyAndRepairOutbound } = outboundVerify;
const { computeOneBrainNextRequiredAction, formatOneBrainLiveChannelContext } =
  oneBrain;

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
    dialogState: null,
    ...overrides,
  };
}

function makeDialogStateWithRequestedSlot(slotName, options) {
  return {
    slots: {},
    requestedSlot: {
      name: slotName,
      options: options ?? null,
      askedTs: 1730000000000,
    },
  };
}

// ---------------------------------------------------------------------------
// R1: ASK_DELIVERY_AREA with preserved pickup + ambiguity options (EN).
// The common "salmiya to kuwait city" case — pickup pinned, dropoff
// ambiguous with Kuwait City sub-area list.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Salmiya",
    pendingPickupAreaNameAr: "السالمية",
    dialogState: makeDialogStateWithRequestedSlot("dropoff_area", [
      "Sharq",
      "Mirqab",
      "Qibla",
      "Bnaid Al-Qar",
      "Dasman",
    ]),
  });
  const result = renderDirectiveReply("ASK_DELIVERY_AREA", {
    language: "en",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t-1",
  });
  assert.equal(result.kind, "render", "R1: renderer must produce a reply");
  assert.ok(
    /Pickup from Salmiya/.test(result.text),
    `R1: reply must recap preserved pickup, got ${JSON.stringify(result.text)}`,
  );
  assert.ok(
    /Sharq/.test(result.text) &&
      /Mirqab/.test(result.text) &&
      /Bnaid Al-Qar/.test(result.text),
    `R1: reply must list ambiguity options, got ${JSON.stringify(result.text)}`,
  );
  assert.ok(
    /delivery area/i.test(result.text),
    `R1: reply must ask for delivery area, got ${JSON.stringify(result.text)}`,
  );
}

// ---------------------------------------------------------------------------
// R2: ASK_DELIVERY_AREA — Arabic variant recaps pickup in Arabic.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Salmiya",
    pendingPickupAreaNameAr: "السالمية",
    dialogState: makeDialogStateWithRequestedSlot("dropoff_area", [
      "Sharq",
      "Mirqab",
    ]),
  });
  const result = renderDirectiveReply("ASK_DELIVERY_AREA", {
    language: "ar",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t-2",
  });
  assert.equal(result.kind, "render");
  assert.ok(
    /السالمية/.test(result.text),
    `R2: Arabic reply must recap السالمية, got ${JSON.stringify(result.text)}`,
  );
  assert.ok(
    /Sharq/.test(result.text) && /Mirqab/.test(result.text),
    `R2: Arabic reply must list options, got ${JSON.stringify(result.text)}`,
  );
}

// ---------------------------------------------------------------------------
// R3: ASK_PICKUP_AREA with preserved delivery — symmetric behaviour.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    pendingDropoffAreaNameEn: "Salwa",
    dialogState: makeDialogStateWithRequestedSlot("pickup_area", [
      "Jabriya",
      "Hawalli",
    ]),
  });
  const result = renderDirectiveReply("ASK_PICKUP_AREA", {
    language: "en",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t-3",
  });
  assert.equal(result.kind, "render");
  assert.ok(
    /Delivery to Salwa/.test(result.text),
    `R3: reply must recap preserved delivery, got ${JSON.stringify(result.text)}`,
  );
  assert.ok(
    /Jabriya/.test(result.text) && /Hawalli/.test(result.text),
    `R3: reply must list ambiguity options, got ${JSON.stringify(result.text)}`,
  );
}

// ---------------------------------------------------------------------------
// R4: ASK_DELIVERY_AREA with no preserved side and no options — falls
// back to the generic phrasing pool (regression-safe).
// ---------------------------------------------------------------------------
{
  const entry = makeEntry();
  const result = renderDirectiveReply("ASK_DELIVERY_AREA", {
    language: "en",
    draft: entry.bookingDraft,
    entry,
    route: null,
    turnSeed: "t-4",
  });
  assert.equal(result.kind, "render");
  assert.ok(
    /delivery area/i.test(result.text),
    `R4: fallback reply still asks for delivery area, got ${JSON.stringify(result.text)}`,
  );
  assert.ok(
    !/Pickup from/.test(result.text) && !/Delivery to/.test(result.text),
    `R4: fallback must not claim a preserved side, got ${JSON.stringify(result.text)}`,
  );
}

// ---------------------------------------------------------------------------
// V1: outbound-verify detects `route_zero_distance` when pickup == dropoff.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    quotePickupAreaNameEn: "Mirqab",
    quoteDropoffAreaNameEn: "Mirqab",
    quotedPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
  });
  const shape = classifyOutboundReplyShape({
    replyText: "Delivery from Mirqab to Mirqab. Price: 1.250 KWD (standard sedan)",
    entry,
    missingFields: ["sender.name", "sender.phone"],
    language: "en",
  });
  assert.equal(
    shape,
    "route_zero_distance",
    `V1: classifier must flag zero-distance route, got ${shape}`,
  );
}

// ---------------------------------------------------------------------------
// V2: verifyAndRepairOutbound substitutes the zero-distance reply
// with the recovery ask, sets `replaced=true`, and shape survives.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    quotePickupAreaNameEn: "Mirqab",
    quoteDropoffAreaNameEn: "Mirqab",
    quotedPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
  });
  const result = verifyAndRepairOutbound({
    replyText: "Delivery from Mirqab to Mirqab. Price: 1.250 KWD (standard sedan)",
    entry,
    missingFields: ["sender.name", "sender.phone"],
    language: "en",
  });
  assert.equal(result.replaced, true, "V2: must replace zero-distance reply");
  assert.equal(result.shape, "route_zero_distance");
  assert.equal(result.reason, "substituted_zero_distance_route_recovery");
  assert.ok(
    /pickup and delivery areas got mixed up/i.test(result.replyText),
    `V2: substitute must be recovery ask, got ${JSON.stringify(result.replyText)}`,
  );
}

// ---------------------------------------------------------------------------
// V3: Arabic zero-distance recovery.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    quotePickupAreaNameEn: "Mirqab",
    quoteDropoffAreaNameEn: "Mirqab",
    quotedPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
  });
  const result = verifyAndRepairOutbound({
    replyText: "التوصيل من المرقاب إلى المرقاب. السعر 1.250 د.ك",
    entry,
    missingFields: [],
    language: "ar",
  });
  assert.equal(result.replaced, true);
  assert.ok(
    /التباس في المناطق/.test(result.replyText),
    `V3: Arabic recovery text expected, got ${JSON.stringify(result.replyText)}`,
  );
}

// ---------------------------------------------------------------------------
// V4: Non-symmetric quote must NOT trip the zero-distance shape.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    quotePickupAreaNameEn: "Salmiya",
    quoteDropoffAreaNameEn: "Mirqab",
    quotedPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
  });
  const shape = classifyOutboundReplyShape({
    replyText: "Delivery from Salmiya to Mirqab. Price: 1.250 KWD (standard sedan)",
    entry,
    missingFields: ["sender.name"],
    language: "en",
  });
  assert.notEqual(
    shape,
    "route_zero_distance",
    "V4: non-symmetric quote must not flag zero-distance",
  );
}

// ---------------------------------------------------------------------------
// C1: one-brain-context surfaces `pending_pickup_area` + enforcement rule
// whenever `pendingPickupAreaNameEn` is set on the entry.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    pendingPickupAreaNameEn: "Salmiya",
    dialogState: makeDialogStateWithRequestedSlot("dropoff_area", [
      "Sharq",
      "Mirqab",
    ]),
  });
  const ctxBlock = formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "+96599338566",
    preferredReplyLanguage: "en",
    customerScriptMode: "latin",
    controllerEntry: entry,
    quotedRoute: null,
  });
  assert.ok(
    /pending_pickup_area:\s*Salmiya/.test(ctxBlock),
    "C1: context must surface pending_pickup_area",
  );
  assert.ok(
    /pending_area_rule:/.test(ctxBlock),
    "C1: context must surface pending_area_rule",
  );
  assert.ok(
    /Symmetric `get_price\(pickup=X, dropoff=X\)` calls are always wrong/.test(
      ctxBlock,
    ),
    "C1: pending_area_rule must forbid symmetric get_price",
  );
}

// ---------------------------------------------------------------------------
// C2: computeOneBrainNextRequiredAction returns ASK_DELIVERY_AREA for the
// post-stage-promotion state (collecting_booking_details + pickup pinned
// + dropoff missing). This is the directive the dispatcher substitutes.
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    stage: "collecting_booking_details",
    pendingPickupAreaNameEn: "Salmiya",
  });
  const missing = [
    "pickup.block",
    "pickup.street_or_avenue",
    "pickup.house_or_unit",
    "delivery.area",
    "service_type",
    "quoted_price",
  ];
  const directive = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing,
  });
  assert.ok(directive, "C2: directive must be returned");
  assert.equal(
    directive.action,
    "ASK_DELIVERY_AREA",
    `C2: expected ASK_DELIVERY_AREA, got ${directive.action}`,
  );
  assert.ok(
    Array.isArray(directive.forbiddenShapes) &&
      directive.forbiddenShapes.includes(
        "route_price_recap_with_symmetric_areas",
      ) &&
      directive.forbiddenShapes.includes("get_price_with_symmetric_areas"),
    "C2: forbidden shapes must include the symmetric-rebind entries",
  );
}

// ---------------------------------------------------------------------------
// C3: forbidden shapes do NOT include the symmetric-area entries on
// non-area directives (scoping check — don't leak these rules into
// collection turns where they'd be irrelevant).
// ---------------------------------------------------------------------------
{
  const entry = makeEntry({
    stage: "collecting_booking_details",
    quotePickupAreaNameEn: "Salmiya",
    quoteDropoffAreaNameEn: "Mirqab",
    quotedPrice: 1.25,
    selectedDeliveryType: "sedan_normal",
  });
  const missing = ["sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing,
  });
  assert.ok(directive, "C3: directive must be returned");
  assert.notEqual(
    directive.action,
    "ASK_DELIVERY_AREA",
    "C3: area directive must not fire when both legs resolved",
  );
}

// ---------------------------------------------------------------------------
// S1: source-level invariant — drain loop in octopus-channel/index.ts
// promotes stage to `collecting_booking_details` when a
// `set_pending_area` op fires at `idle`. Guards against a future refactor
// silently removing this promotion and re-introducing the regression.
// ---------------------------------------------------------------------------
{
  const source = fs.readFileSync(
    path.resolve(
      path.dirname(new URL(import.meta.url).pathname),
      "..",
      "plugins/octopus-channel/index.ts",
    ),
    "utf8",
  );
  assert.ok(
    /appliedPendingArea\s*&&\s*nextEntry\.stage\s*===\s*"idle"/.test(source) &&
      /stage:\s*"collecting_booking_details"/.test(source),
    "S1: drain loop must promote stage to collecting_booking_details when set_pending_area fires at idle",
  );
}

// ---------------------------------------------------------------------------
// S2: source-level invariant — pricing tool contains the symmetric-rebind
// guard that overrides the non-requested leg to the pending value.
// ---------------------------------------------------------------------------
{
  const source = fs.readFileSync(
    path.resolve(
      path.dirname(new URL(import.meta.url).pathname),
      "..",
      "plugins/riders-tools/tools/pricing.ts",
    ),
    "utf8",
  );
  assert.ok(
    /\[area-symmetric-rebind\]/.test(source),
    "S2: pricing tool must log [area-symmetric-rebind] overrides",
  );
  assert.ok(
    /pendingPickup\s*&&[\s\S]{0,200}pendingPickup\.toLowerCase\(\)\s*!==/.test(
      source,
    ),
    "S2: symmetric-rebind guard must compare pending pickup against params",
  );
}

console.log("smoke-test-area-clarification-binding.mjs OK");
