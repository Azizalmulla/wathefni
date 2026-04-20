#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: server-composed manual-confirm replies (Bug 4, 2026-04-20).
//
// Product rule:
//   On a quoted route where the customer has selected an option flagged
//   `manual_confirmation_required`, the server OWNS the customer-facing
//   reply text for the rest of the flow. Every reply must explicitly name
//   the option, its price, AND the "needs manual confirmation by our
//   team" signal. The LLM's draft text is discarded by the Region-A
//   substitute in `decidePreStateOutbound`.
//
// Covered:
//   S1  pickup address missing → replace_manual_confirm_address_ask +
//       reply contains the option label, price, manual-confirm signal,
//       and a pickup-address prompt (EN)
//   S2  same shape in Arabic (AR)
//   S3  delivery address missing (pickup satisfied) → delivery prompt
//   S4  both addresses present → replace_manual_confirm_handoff + reply
//       carries manual-confirm signal and the "team will reach out"
//       message
//   S5  direct-book option (`verified`) with same state must NOT trigger
//       the substitution (caller passes null flags)
//   S6  forbidden_reply_shapes on the ASK directives include the new
//       `ask_<side>_address_without_manual_confirm_signal` shapes so
//       upstream LLM drift is also steered
//   S7  REQUEST_HANDOFF directive includes
//       `request_handoff_without_manual_confirm_signal`
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const outboundDecision = loadTs("plugins/octopus-channel/lib/outbound-decision.ts");
const oneBrain = loadTs("plugins/octopus-channel/lib/one-brain-context.ts");
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");
const policy = loadTs("plugins/shared/conversation-policy.ts");

const { decidePreStateOutbound } = outboundDecision;
const { computeOneBrainNextRequiredAction } = oneBrain;
const {
  buildDeterministicSelectedQuotedOptionReply,
  buildDeterministicClarifyOptionBeforeProceedReply,
  buildDeterministicManualConfirmAddressAskReply,
  buildDeterministicManualConfirmHandoffReply,
} = quotedOptions;
const { createEmptyBookingDraft } = policy;

function opt(deliveryType, labelEn, labelAr, price, status = "manual_confirmation_required") {
  return {
    delivery_type: deliveryType,
    label_ar: labelAr,
    label_en: labelEn,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "visible",
    direct_chat_booking_status: status,
    direct_chat_booking_note: null,
  };
}

const ROUTE = {
  routeKey: "salmiya__jabriya",
  pickupAreaNameAr: "السالمية",
  pickupAreaNameEn: "Salmiya",
  dropoffAreaNameAr: "الجابرية",
  dropoffAreaNameEn: "Jabriya",
  pricesByType: {
    sedan_normal: 1.25,
    cooled_van_fast: 2.25,
  },
  optionCatalog: [
    opt("sedan_normal", "Standard sedan", "سيارة عاديه", 1.25, "verified"),
    opt("cooled_van_fast", "Express refrigerated van", "سيارة مبردة سريع", 2.25, "manual_confirmation_required"),
  ],
  serviceDiscovery: null,
};

const COOLED_VAN_FAST = ROUTE.optionCatalog.find((o) => o.delivery_type === "cooled_van_fast");
const SEDAN_NORMAL = ROUTE.optionCatalog.find((o) => o.delivery_type === "sedan_normal");

const PRICE_EXTRACTOR = (text) => {
  const out = [];
  const re = /\b(\d+\.\d{3})\b/g;
  let m;
  while ((m = re.exec(text)) !== null) out.push(m[1]);
  return out;
};

const noopBuilders = {
  buildDeterministicSelectedQuotedOptionReply,
  buildDeterministicClarifyOptionBeforeProceedReply,
  buildDeterministicManualConfirmAddressAskReply,
  buildDeterministicManualConfirmHandoffReply,
};

function baseInput(overrides = {}) {
  return {
    replyText: "Sure — send the pickup address first.",
    preferredLanguage: "en",
    sessionGuard: {
      allValidPrices: new Set(["2.250"]),
      lastToolTs: Date.now(),
      lastToolName: "get_price",
    },
    sessionIsRecent: true,
    preferredCanonicalText: null,
    guardToolAgeMs: 1000,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: PRICE_EXTRACTOR,
    activeQuotedRoute: ROUTE,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c-mc-1",
    sessionKeyForLogs: "s-mc-1",
    controllerStage: "quoted",
    manualConfirmAddressAsk: null,
    manualConfirmHandoff: null,
    ...overrides,
  };
}

// -------------------------------------------------------------------------
// S1: pickup address missing → substitute with EN manual-confirm ask
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      manualConfirmAddressAsk: { side: "pickup", option: COOLED_VAN_FAST },
    }),
  );
  assert.equal(res.decision, "replace_authoritative", "S1: decision kind");
  assert.equal(res.reason, "replace_manual_confirm_address_ask", "S1: reason code");
  assert.ok(/Express refrigerated van/.test(res.replyText), `S1: names option label, got: ${res.replyText}`);
  assert.ok(/2\.250/.test(res.replyText), `S1: quotes price`);
  assert.ok(/manual confirmation/i.test(res.replyText), `S1: contains manual-confirm signal`);
  assert.ok(/pickup address/i.test(res.replyText), `S1: asks for pickup address`);
  assert.ok(
    res.logEntries.some((e) => e.level === "warn" && /manual-confirm pickup-address ask/.test(e.message)),
    "S1: warn log emitted",
  );
}

// -------------------------------------------------------------------------
// S2: same shape in Arabic
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      preferredLanguage: "ar",
      manualConfirmAddressAsk: { side: "pickup", option: COOLED_VAN_FAST },
    }),
  );
  assert.equal(res.reason, "replace_manual_confirm_address_ask");
  assert.ok(/تأكيد يدوي/.test(res.replyText), `S2: contains AR manual-confirm signal`);
  assert.ok(/عنوان الاستلام/.test(res.replyText), `S2: asks for pickup address in AR`);
  assert.ok(/2\.250/.test(res.replyText), `S2: quotes price`);
}

// -------------------------------------------------------------------------
// S3: delivery address missing → delivery ask
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      manualConfirmAddressAsk: { side: "delivery", option: COOLED_VAN_FAST },
    }),
  );
  assert.equal(res.reason, "replace_manual_confirm_address_ask");
  assert.ok(/delivery address/i.test(res.replyText), `S3: delivery prompt`);
  assert.ok(/manual confirmation/i.test(res.replyText), `S3: still carries manual-confirm signal`);
}

// -------------------------------------------------------------------------
// S4: both addresses present → handoff substitution
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      manualConfirmHandoff: { option: COOLED_VAN_FAST },
    }),
  );
  assert.equal(res.decision, "replace_authoritative", "S4: decision kind");
  assert.equal(res.reason, "replace_manual_confirm_handoff", "S4: reason code");
  assert.ok(/manual confirmation/i.test(res.replyText), `S4: manual-confirm signal`);
  assert.ok(/team/i.test(res.replyText), `S4: promises team follow-up`);
  assert.ok(/Express refrigerated van/.test(res.replyText), `S4: names option`);
}

// -------------------------------------------------------------------------
// S5: no manualConfirm flags → no substitution (passes through normal path)
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      replyText: "Sure, 2.250 KWD.",
      manualConfirmAddressAsk: null,
      manualConfirmHandoff: null,
    }),
  );
  assert.notEqual(res.reason, "replace_manual_confirm_address_ask", "S5: not substituted");
  assert.notEqual(res.reason, "replace_manual_confirm_handoff", "S5: not substituted");
}

// -------------------------------------------------------------------------
// S6 / S7: forbidden_reply_shapes surface the new shapes on each ASK /
// HANDOFF directive.
// -------------------------------------------------------------------------
function makeEntry(overrides = {}) {
  return {
    stage: "quoted",
    quoteTs: Date.now(),
    quoteRouteKey: ROUTE.routeKey,
    bookingStep: "none",
    quotePickupAreaNameEn: ROUTE.pickupAreaNameEn,
    quotePickupAreaNameAr: ROUTE.pickupAreaNameAr,
    quoteDropoffAreaNameEn: ROUTE.dropoffAreaNameEn,
    quoteDropoffAreaNameAr: ROUTE.dropoffAreaNameAr,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "cooled_van_fast",
    selectedQuoteOptionLabelAr: "سيارة مبردة سريع",
    selectedQuoteOptionLabelEn: "Express refrigerated van",
    selectedQuoteOptionPrice: 2.25,
    selectedQuoteOptionDirectChatBookingStatus: "manual_confirmation_required",
    selectedDeliveryType: "cooled_van_fast",
    quotedPrice: 2.25,
    bookingDraft: createEmptyBookingDraft(),
    ...overrides,
  };
}

{
  // Pickup missing
  const entry = makeEntry();
  const missing = ["pickup.address", "delivery.address"];
  const directive = computeOneBrainNextRequiredAction({
    draft: entry.bookingDraft,
    entry,
    missing,
  });
  assert.equal(directive?.action, "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM", "S6a: pickup action");
  assert.ok(
    directive.forbiddenShapes.includes("ask_pickup_address_without_manual_confirm_signal"),
    `S6a: forbidden shape present; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
}

{
  // Delivery missing only
  const draft = createEmptyBookingDraft();
  draft.pickupArea = "Salmiya";
  draft.pickupBlock = "6";
  draft.pickupStreet = "9";
  draft.pickupExtra = "Apartment 12";
  const entry = makeEntry({ bookingDraft: draft });
  const missing = ["delivery.address"];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
  });
  assert.equal(directive?.action, "ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM", "S6b: delivery action");
  assert.ok(
    directive.forbiddenShapes.includes("ask_delivery_address_without_manual_confirm_signal"),
    `S6b: forbidden shape present`,
  );
}

{
  // Both addresses satisfied → handoff directive
  const draft = createEmptyBookingDraft();
  draft.pickupArea = "Salmiya";
  draft.pickupBlock = "6";
  draft.pickupStreet = "9";
  draft.pickupExtra = "Apartment 12";
  draft.deliveryArea = "Jabriya";
  draft.deliveryBlock = "2";
  draft.deliveryStreet = "1";
  draft.deliveryExtra = "Villa 5";
  const entry = makeEntry({ bookingDraft: draft });
  const missing = [];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
  });
  assert.equal(directive?.action, "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM", "S7: handoff action");
  assert.ok(
    directive.forbiddenShapes.includes("request_handoff_without_manual_confirm_signal"),
    `S7: forbidden shape present; got ${JSON.stringify(directive.forbiddenShapes)}`,
  );
  assert.ok(
    directive.forbiddenShapes.includes("route_price_recap"),
    `S7: preserves existing route_price_recap forbid`,
  );
}

// -------------------------------------------------------------------------
// Sanity: the substitution is authoritative — it beats the price
// whitelist (so a reply that would otherwise be blocked for mismatched
// price is still cleanly replaced with the manual-confirm text).
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    baseInput({
      replyText: "This costs 0.500 KWD and I need the pickup address.",
      manualConfirmAddressAsk: { side: "pickup", option: COOLED_VAN_FAST },
    }),
  );
  assert.equal(res.reason, "replace_manual_confirm_address_ask", "ordering: manual-confirm outranks price whitelist");
}

console.log("smoke-test-manual-confirm-address-ask-substitution: OK");
