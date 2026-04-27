#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: pending all-in-one intent preservation across route ambiguity.
//
// Invariant:
//   Route ambiguity may block quote creation, but it must not discard safe
//   non-route facts from the same customer message. In particular, a grounded
//   service intent captured before the route is canonical must be carried
//   forward and used when the delayed quote is promoted.
//
// Regression anchor:
//   Arabic all-in-one message contained "اكسبرس سيدان". The route needed local
//   clarification, and after clarification quote promotion fell back to
//   standard sedan. Expected: preserved pending service intent -> sedan_fast.
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

async function loadTs(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const shared = await loadTs("plugins/shared/conversation-policy.ts");
const { buildBookingTruthSnapshot } = await loadTs("plugins/shared/booking-truth-snapshot.ts");
const { __testables } = await loadTs("plugins/octopus-channel/index.ts");

function option(deliveryType, labelEn, labelAr, price) {
  return {
    delivery_type: deliveryType,
    label_en: labelEn,
    label_ar: labelAr,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "public",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

function canonicalArea(nameEn, nameAr, areaId) {
  return {
    status: "canonical",
    areaId,
    nameEn,
    nameAr,
    confirmedByUser: true,
    quoteBuiltFromAreaIds: true,
  };
}

function buildEntry(overrides = {}) {
  const draft = shared.createEmptyBookingDraft();
  Object.assign(draft, {
    senderName: "Abdulaziz Almulla",
    senderPhone: "96599338566",
    recipientName: "Ahmad Basha",
    recipientPhone: "99278765",
    pickupBlock: "2",
    pickupStreet: "7",
    pickupHouse: "19",
    deliveryBlock: "2",
    deliveryStreet: "9",
    deliveryHouse: null,
    deliveryExtra: "apartment 11, floor 4, door 2",
  });
  return {
    lastActivityTs: Date.now(),
    language: "ar",
    explicitLanguage: null,
    stage: "idle",
    bookingStep: "none",
    conversationId: "pending-intent-smoke",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: null,
    quoteTs: null,
    quotePickupAreaNameEn: null,
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: null,
    quoteDropoffAreaNameAr: null,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    pendingPickupAreaResolution: null,
    pendingDropoffAreaResolution: null,
    selectedQuoteOptionType: null,
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: null,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: null,
    quotedPrice: null,
    bookingDraft: draft,
    pendingReplyText: null,
    quotePresentedToCustomer: false,
    submittedOrderUid: null,
    dialogState: null,
    pendingOrderEdits: null,
    ...overrides,
  };
}

const catalog = [
  option("sedan_normal", "Standard sedan", "سيارة عادية", 1.25),
  option("sedan_fast", "Express sedan", "اكسبرس سيدان", 1.75),
];

const delayedQuote = {
  routeKey: "sulaibikhat__zahra",
  pickupAreaNameEn: "Sulaibikhat",
  pickupAreaNameAr: "الصليبخات",
  dropoffAreaNameEn: "Zahra",
  dropoffAreaNameAr: "الزهراء",
  pickupAreaResolution: canonicalArea("Sulaibikhat", "الصليبخات", 101),
  dropoffAreaResolution: canonicalArea("Zahra", "الزهراء", 202),
  pricesByType: {
    sedan_normal: 1.25,
    sedan_fast: 1.75,
  },
  optionCatalog: catalog,
  serviceDiscovery: null,
};

{
  const interpretation = {
    class: "sedan",
    tier: "fast",
    source_quote: "اكسبرس سيدان",
    confidence: "high",
    turn_id: "original-all-in-one",
  };
  const pendingType = __testables.optionInterpretationDeliveryType(interpretation);
  assert(pendingType === "sedan_fast", `expected pending sedan_fast, got ${pendingType}`);
}

{
  const originalAllInOne =
    "ابي دليفري من الصليبخات لي الزهراء، اكسبرس سيدان. اسمي عبدالعزيز الملا واستخدم رقم الواتساب. المستلم أحمد باشا ٩٩٢٧٨٧٦٥.";
  const entryWithPendingService = buildEntry({
    selectedDeliveryType: "sedan_fast",
  });
  const pendingSnapshot = buildBookingTruthSnapshot({
    timing: "post_drain",
    controllerState: entryWithPendingService,
    sessionGuard: null,
    dialogState: null,
  });
  assert(
    pendingSnapshot.quote.selectedService === "sedan_fast",
    `snapshot should expose pending selected service, got ${pendingSnapshot.quote.selectedService}`,
  );
  assert(
    !pendingSnapshot.missingFields.includes("service_type"),
    `snapshot should not ask for service_type when pending service exists: ${pendingSnapshot.missingFields.join(",")}`,
  );

  const promoted = __testables.promoteQuotedRouteState({
    controllerEntry: entryWithPendingService,
    route: delayedQuote,
    quoteTs: Date.now(),
    language: "ar",
    quotePresentedToCustomer: true,
    preserveBookingDraft: true,
    visibleText: originalAllInOne,
    sameTurnOptionInterpretation: null,
    sessionGuard: {
      lastToolName: "get_price",
      lastToolTs: Date.now(),
      lastQuotedRoute: delayedQuote,
    },
  });

  assert(promoted.promoted === true, "delayed quote should promote after route becomes canonical");
  assert(
    promoted.selectedOptionSource === "pending_service_intent",
    `expected pending_service_intent source, got ${promoted.selectedOptionSource}`,
  );
  assert(
    promoted.entry.selectedDeliveryType === "sedan_fast",
    `expected selectedDeliveryType sedan_fast, got ${promoted.entry.selectedDeliveryType}`,
  );
  assert(
    promoted.entry.selectedQuoteOptionType === "sedan_fast",
    `expected selectedQuoteOptionType sedan_fast, got ${promoted.entry.selectedQuoteOptionType}`,
  );
  assert(
    promoted.entry.quotedPrice === 1.75,
    `expected quotedPrice 1.75, got ${promoted.entry.quotedPrice}`,
  );
  assert(
    promoted.entry.bookingDraft.recipientPhone === "99278765",
    "preserved draft details should survive delayed quote promotion",
  );
}

console.log("smoke-test-pending-all-in-one-intent-carry-forward: OK");
