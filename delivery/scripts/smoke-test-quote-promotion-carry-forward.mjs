#!/usr/bin/env node
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

const octopus = loadTs("plugins/octopus-channel/index.ts");
const shared = loadTs("plugins/shared/conversation-policy.ts");
const dialog = loadTs("plugins/shared/dialog-state.ts");

const { promoteQuotedRouteState } = octopus.__testables;
assert(promoteQuotedRouteState, "missing promoteQuotedRouteState test hook");

function option(deliveryType, labelEn, labelAr, price) {
  return {
    delivery_type: deliveryType,
    label_ar: labelAr,
    label_en: labelEn,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "visible",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

const route = {
  routeKey: "Sulaibikhat::Zahra",
  pickupAreaNameAr: "الصليبيخات",
  pickupAreaNameEn: "Sulaibikhat",
  dropoffAreaNameAr: "الزهراء",
  dropoffAreaNameEn: "Zahra",
  optionCatalog: [
    option("sedan_normal", "Standard sedan", "سيارة عاديه + توصيل عادي", 1.25),
    option("sedan_fast", "Express sedan", "سيارة عاديه + توصيل سريع", 1.75),
  ],
};

function baseEntry(draft = shared.createEmptyBookingDraft()) {
  return {
    conversationId: "20848",
    replyTarget: "96599338566",
    accountId: "default",
    lastActivityTs: Date.now(),
    language: "ar",
    stage: "summary_shown",
    bookingStep: "summary_pending",
    quoteTs: null,
    quoteRouteKey: null,
    quotePickupAreaNameEn: null,
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: null,
    quoteDropoffAreaNameAr: null,
    pendingPickupAreaNameEn: "Sulaibikhat",
    pendingPickupAreaNameAr: "الصليبيخات",
    pendingDropoffAreaNameEn: "Zahra",
    pendingDropoffAreaNameAr: "الزهراء",
    selectedQuoteOptionType: null,
    selectedQuoteOptionLabelAr: null,
    selectedQuoteOptionLabelEn: null,
    selectedQuoteOptionPrice: null,
    selectedQuoteOptionDirectChatBookingStatus: null,
    selectedDeliveryType: null,
    quotedPrice: null,
    quotePresentedToCustomer: false,
    bookingDraft: draft,
    dialogState: dialog.setRequestedSlot(dialog.createEmptyDialogState(), {
      name: "dropoff_area",
      options: null,
      askedTs: Date.now(),
    }),
    pendingReplyText: null,
    submittedOrderUid: null,
    pendingOrderEdits: null,
  };
}

function completeDraft() {
  const draft = shared.createEmptyBookingDraft();
  draft.senderName = "عبدالعزيز الملا";
  draft.senderPhone = "96599338566";
  draft.recipientName = "أحمد باشا";
  draft.recipientPhone = "99278765";
  draft.pickupBlock = "2";
  draft.pickupStreet = "7";
  draft.pickupHouse = "19";
  draft.deliveryBlock = "2";
  draft.deliveryStreet = "9";
  draft.deliveryExtra = "شقة ١١، الدور الرابع، باب ٢";
  return draft;
}

{
  const promoted = promoteQuotedRouteState({
    controllerEntry: baseEntry(completeDraft()),
    route,
    quoteTs: 12345,
    language: "ar",
    quotePresentedToCustomer: true,
    preserveBookingDraft: true,
    visibleText:
      "ابي دليفري من الصليبيخات لي الزهراء، اكسبرس سيدان. اسمي عبدالعزيز الملا واستخدم رقم الواتساب.",
    sameTurnOptionInterpretation: {
      class: "sedan",
      tier: "fast",
      source_quote: "اكسبرس سيدان",
      confidence: "high",
    },
  });
  const entry = promoted.entry;
  assert.equal(entry.quotePickupAreaNameEn, "Sulaibikhat");
  assert.equal(entry.quoteDropoffAreaNameEn, "Zahra");
  assert.equal(entry.selectedDeliveryType, "sedan_fast");
  assert.equal(entry.quotedPrice, 1.75);
  assert.equal(entry.bookingDraft.senderName, "عبدالعزيز الملا");
  assert.equal(entry.bookingDraft.senderPhone, "96599338566");
  assert.equal(entry.bookingDraft.recipientName, "أحمد باشا");
  assert.equal(entry.bookingDraft.recipientPhone, "99278765");
  assert.equal(entry.bookingDraft.pickupBlock, "2");
  assert.equal(entry.bookingDraft.pickupStreet, "7");
  assert.equal(entry.bookingDraft.pickupHouse, "19");
  assert.equal(entry.bookingDraft.deliveryBlock, "2");
  assert.equal(entry.bookingDraft.deliveryStreet, "9");
  assert.equal(entry.bookingDraft.deliveryExtra, "شقة ١١، الدور الرابع، باب ٢");
  assert.equal(entry.stage, "summary_shown");
  assert.equal(entry.bookingStep, "summary_pending");
  assert.equal(entry.dialogState.requestedSlot, null);
  assert.equal(promoted.selectedOptionSource, "same_turn_option_intent");
  console.log("ok - quote promotion preserves same-turn all-in-one draft and express option");
}

{
  const staleDraft = completeDraft();
  const promoted = promoteQuotedRouteState({
    controllerEntry: baseEntry(staleDraft),
    route,
    quoteTs: 12346,
    language: "ar",
    quotePresentedToCustomer: true,
    preserveBookingDraft: false,
    visibleText: "ابي دليفري من الصليبيخات لي الزهراء",
    sameTurnOptionInterpretation: null,
  });
  const entry = promoted.entry;
  assert.equal(entry.selectedDeliveryType, "sedan_normal");
  assert.equal(entry.bookingDraft.senderName, null);
  assert.equal(entry.bookingDraft.recipientName, null);
  assert.equal(entry.bookingDraft.pickupBlock, null);
  assert.equal(entry.stage, "quoted");
  assert.equal(entry.bookingStep, "none");
  assert.equal(promoted.selectedOptionSource, "default");
  console.log("ok - quote promotion resets stale draft when no same-turn booking progress applied");
}

{
  const promoted = promoteQuotedRouteState({
    controllerEntry: baseEntry(completeDraft()),
    route,
    quoteTs: 12347,
    language: "ar",
    quotePresentedToCustomer: true,
    preserveBookingDraft: true,
    visibleText: "ابي دليفري من الصليبيخات لي الزهراء",
    sameTurnOptionInterpretation: {
      class: "sedan",
      tier: "fast",
      source_quote: "اكسبرس سيدان",
      confidence: "high",
    },
  });
  assert.equal(promoted.entry.selectedDeliveryType, "sedan_normal");
  assert.equal(promoted.selectedOptionSource, "default");
  console.log("ok - ungrounded same-turn option intent does not override default");
}

console.log("\nQuote-promotion carry-forward smoke passed.");
