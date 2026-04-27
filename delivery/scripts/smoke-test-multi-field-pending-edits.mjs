#!/usr/bin/env node
// Regression coverage for summary-stage multi-field edits.
//
// A bot that asks for multiple updated values must persist those expected
// fields. The next message should then apply those values as intentional edits,
// not as filled-slot conflicts.

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

const {
  createEmptyBookingDraft,
} = await loadTsModule("plugins/shared/conversation-policy.ts");
const {
  seedDialogStateFromDraft,
} = await loadTsModule("plugins/shared/dialog-state.ts");
const {
  applyProposals,
  llmProposal,
} = await loadTsModule("plugins/shared/apply-boundary.ts");
const {
  applySelectedQuotedOptionToController,
  matchQuotedOptionDiscriminated,
  matchLlmOptionInterpretation,
  resolveOptionFromProposals,
} = await loadTsModule("plugins/octopus-channel/lib/quoted-options.ts");
const {
  decidePostStateOutbound,
} = await loadTsModule("plugins/octopus-channel/lib/outbound-decision.ts");

function option(delivery_type, label_en, price) {
  return {
    delivery_type,
    label_en,
    label_ar: label_en,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "public",
    direct_chat_booking_status: "verified",
    direct_chat_booking_note: null,
  };
}

function buildDraft() {
  const d = createEmptyBookingDraft();
  d.senderName = "Abdulaziz almulla";
  d.senderPhone = "96599338566";
  d.recipientName = "Ahamad basha";
  d.recipientPhone = "99278765";
  d.pickupBlock = "1";
  d.pickupStreet = "7";
  d.pickupHouse = "19";
  d.deliveryBlock = "1";
  d.deliveryStreet = "8";
  d.deliveryExtra = "apart 19, floor 1, door 9";
  return d;
}

function buildEntry(draft) {
  return {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "awaiting_confirmation",
    bookingStep: "awaiting_summary_confirmation",
    conversationId: "test",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: "northwest_sulaibikhat:zahra",
    quoteTs: Date.now(),
    quotePickupAreaNameEn: "Northwest Sulaibikhat",
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: "Zahra",
    quoteDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: "Standard sedan",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    bookingDraft: draft,
    pendingReplyText: null,
    quotePresentedToCustomer: true,
    submittedOrderUid: null,
    dialogState: seedDialogStateFromDraft(draft),
    pendingOrderEdits: {
      fields: ["sender_name", "service"],
      askedTs: Date.now(),
      sourceQuote: "can i change the sender name and the service",
    },
  };
}

const route = {
  routeKey: "northwest_sulaibikhat:zahra",
  pickupAreaNameEn: "Northwest Sulaibikhat",
  pickupAreaNameAr: null,
  dropoffAreaNameEn: "Zahra",
  dropoffAreaNameAr: null,
  pricesByType: {
    sedan_normal: 1.25,
    sedan_fast: 1.75,
  },
  optionCatalog: [
    option("sedan_normal", "Standard sedan", 1.25),
    option("sedan_fast", "Express sedan", 1.75),
  ],
};

// Pending sender_name edit overwrites the filled slot without conflict.
{
  const draft = buildDraft();
  const entry = buildEntry(draft);
  const result = applyProposals(
    [
      llmProposal({
        op: {
          sender_name: "Rawan al ajmi",
          sender_phone: null,
          phone_decision: null,
          recipient_name: null,
          recipient_phone: null,
          address_block: null,
          address_street: null,
          address_house: null,
          address_avenue: null,
          address_extra: null,
          address_role: null,
          source_quote: "rawan al ajmi express sedan",
          turn_id: "t1",
        },
      }),
    ],
    {
      draft,
      dialogState: entry.dialogState,
      whatsappNumber: "96599338566",
      stage: entry.stage,
      pendingEditSlots: ["sender_name"],
    },
  );
  assert(result.draft.senderName === "Rawan al ajmi", "sender name should update");
  assert(result.rejections.length === 0, `sender edit should not reject: ${JSON.stringify(result.rejections)}`);
  assert(result.conflicts.length === 0, `sender edit should not conflict: ${JSON.stringify(result.conflicts)}`);
}

// Pending service edit resolves against the quoted catalog at confirmation stage.
{
  const draft = buildDraft();
  let entry = buildEntry(draft);
  const rawTextOutcome = matchQuotedOptionDiscriminated({
    normalizedText: "rawan al ajmi express sedan",
    options: route.optionCatalog,
  });
  const llmOutcome = matchLlmOptionInterpretation({
    interpretation: {
      class: "sedan",
      tier: "fast",
      source_quote: "express sedan",
      confidence: "high",
    },
    options: route.optionCatalog,
  });
  const reconciled = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert(reconciled.kind === "commit", `service should resolve, got ${reconciled.kind}`);
  entry = applySelectedQuotedOptionToController(entry, reconciled.option);
  assert(entry.selectedDeliveryType === "sedan_fast", "service should update to sedan_fast");
  assert(entry.quotedPrice === 1.75, "price should update to express sedan price");
}

// Untracked multi-edit asks are blocked instead of creating invisible state.
{
  const draft = buildDraft();
  const entry = buildEntry(draft);
  entry.pendingOrderEdits = null;
  const decision = decidePostStateOutbound({
    replyText:
      "Yes. Send me the new sender name and the service you want, and we’ll update it.",
    conversationControllerEntry: entry,
    controllerTransitionHint: null,
    conversationId: "test",
    sessionKeyForLogs: "test",
    preferredLanguage: "en",
    stageAtTurnStart: "awaiting_confirmation",
    missingFields: [],
    hallucinationGuardEnabled: false,
    hallucinationGuardRejections: [],
    nextRequiredAction: null,
    activeQuotedPrices: [1.25, 1.75],
    buildProviderIssueFallbackReply: () => "Provider issue.",
    buildDeterministicGraceWindowReply: () => "Grace.",
  });
  assert(decision.reason === "replace_untracked_multi_edit_ask", `unexpected reason ${decision.reason}`);
  assert(!/send me the new sender name and the service/i.test(decision.replyText), "untracked ask should be replaced");
}

console.log("smoke-test-multi-field-pending-edits: OK");
