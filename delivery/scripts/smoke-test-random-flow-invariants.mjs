#!/usr/bin/env node
// Random-flow architecture smoke suite.
//
// This is not an end-to-end WhatsApp simulator. It is a compact invariant
// suite for the random-flow bug classes that have repeatedly escaped live:
// all-in-one collection, summary corrections, multi-edit intent, stale
// clarification state, option rejection/selection, pins, coverage-only turns,
// and partial field application.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

async function loadTsModule(relativePath) {
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
  setRequestedSlot,
} = await loadTsModule("plugins/shared/dialog-state.ts");
const {
  applyProposals,
  llmProposal,
} = await loadTsModule("plugins/shared/apply-boundary.ts");
const {
  applyBookingFieldPatch,
} = await loadTsModule("plugins/shared/booking-draft.ts");
const {
  computeOneBrainMissingFields,
  formatOneBrainLiveChannelContext,
} = await loadTsModule("plugins/octopus-channel/lib/one-brain-context.ts");
const {
  bindNativeLocationToAddressStep,
} = await loadTsModule("plugins/octopus-channel/lib/booking-flow.ts");
const {
  applySelectedQuotedOptionToController,
  matchQuotedOptionDiscriminated,
  matchLlmOptionInterpretation,
  resolveOptionFromProposals,
  resolveSameRouteQuoteFollowupAction,
} = await loadTsModule("plugins/octopus-channel/lib/quoted-options.ts");
const {
  decideFastPathDispositionGate,
} = await loadTsModule("plugins/shared/fast-path-extractor.ts");
const {
  guardCreateSimpleOrder,
} = await loadTsModule("plugins/shared/order-guard.ts");

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

function buildCompleteDraft(overrides = {}) {
  const draft = createEmptyBookingDraft();
  Object.assign(draft, {
    senderName: "Abdulaziz almulla",
    senderPhone: "96599338566",
    recipientName: "Ahmad basha",
    recipientPhone: "99278765",
    pickupBlock: "2",
    pickupStreet: "7",
    pickupHouse: "19",
    pickupAvenue: null,
    pickupExtra: null,
    deliveryBlock: "2",
    deliveryStreet: "9",
    deliveryHouse: null,
    deliveryAvenue: null,
    deliveryExtra: "apartment 11, floor 4, door 2",
    ...overrides,
  });
  return draft;
}

function buildEntry(draft = buildCompleteDraft(), overrides = {}) {
  const entry = {
    lastActivityTs: Date.now(),
    language: "en",
    explicitLanguage: null,
    stage: "awaiting_confirmation",
    bookingStep: "awaiting_summary_confirmation",
    conversationId: "flow-smoke",
    replyTarget: "96599338566",
    accountId: "default",
    quoteRouteKey: route.routeKey,
    quoteTs: Date.now(),
    quotePickupAreaNameEn: route.pickupAreaNameEn,
    quotePickupAreaNameAr: null,
    quoteDropoffAreaNameEn: route.dropoffAreaNameEn,
    quoteDropoffAreaNameAr: null,
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
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
    pendingOrderEdits: null,
    ...overrides,
  };
  return entry;
}

function bookingProposalFromPatch(patch, sourceQuote = "all details") {
  return llmProposal({
    op: {
      sender_name: patch.sender_name ?? null,
      sender_phone: patch.sender_phone ?? null,
      phone_decision: patch.phone_decision ?? null,
      recipient_name: patch.recipient_name ?? null,
      recipient_phone: patch.recipient_phone ?? null,
      address_block: patch.address_block ?? null,
      address_street: patch.address_street ?? null,
      address_house: patch.address_house ?? null,
      address_avenue: patch.address_avenue ?? null,
      address_extra: patch.address_extra ?? null,
      address_role: patch.address_role ?? null,
      source_quote: sourceQuote,
      turn_id: "flow-smoke-turn",
    },
  });
}

function applyService(entry, text, interpretation) {
  const rawTextOutcome = matchQuotedOptionDiscriminated({
    normalizedText: text,
    options: route.optionCatalog,
  });
  const llmOutcome = matchLlmOptionInterpretation({
    interpretation,
    options: route.optionCatalog,
  });
  const resolved = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert(resolved.kind === "commit", `service should resolve from ${text}, got ${resolved.kind}`);
  return applySelectedQuotedOptionToController(entry, resolved.option);
}

// 1. All-in-one booking: many fields apply in one proposal without fake conflict.
{
  const draft = createEmptyBookingDraft();
  const entry = buildEntry(draft, {
    stage: "quoted",
    bookingStep: "none",
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
    selectedQuoteOptionType: "sedan_fast",
    selectedQuoteOptionPrice: 1.75,
    dialogState: seedDialogStateFromDraft(draft),
  });
  const result = applyProposals(
    [
      bookingProposalFromPatch(
        {
          sender_name: "Rawan al ajmi",
          sender_phone: "96599338566",
          recipient_name: "Ahmad basha",
          recipient_phone: "99278765",
          address_block: "2",
          address_street: "7",
          address_house: "19",
          address_role: "pickup",
        },
        "Sender Rawan al ajmi 96599338566 recipient Ahmad basha 99278765 pickup block 2 street 7 house 19",
      ),
      bookingProposalFromPatch(
        {
          address_block: "2",
          address_street: "9",
          address_extra: "apartment 11, floor 4, door 2",
          address_role: "delivery",
        },
        "delivery address block 2 street 9 apartment 11 floor 4 door 2",
      ),
    ],
    {
      draft,
      dialogState: entry.dialogState,
      whatsappNumber: "96599338566",
      stage: "quoted",
    },
  );
  const nextEntry = buildEntry(result.draft, {
    selectedDeliveryType: "sedan_fast",
    quotedPrice: 1.75,
  });
  assert(result.rejections.length === 0, `all-in-one should not reject: ${JSON.stringify(result.rejections)}`);
  assert(result.conflicts.length === 0, `all-in-one should not conflict: ${JSON.stringify(result.conflicts)}`);
  assert(computeOneBrainMissingFields(result.draft, nextEntry).length === 0, "all-in-one should complete missing fields");
}

// 2. Correction at summary: explicit edit source overwrites a filled slot.
{
  const draft = buildCompleteDraft();
  const entry = buildEntry(draft);
  const result = applyProposals(
    [
      bookingProposalFromPatch(
        { sender_name: "Rawan al ajmi" },
        "change the sender name to Rawan al ajmi",
      ),
    ],
    {
      draft,
      dialogState: entry.dialogState,
      whatsappNumber: "96599338566",
      stage: "awaiting_confirmation",
    },
  );
  assert(result.draft.senderName === "Rawan al ajmi", "summary correction should overwrite sender name");
  assert(result.conflicts.length === 0, "summary correction should not become conflict");
}

// 3. Multiple edits in one turn: pending edit state scopes both name and service.
{
  const draft = buildCompleteDraft();
  let entry = buildEntry(draft, {
    pendingOrderEdits: {
      fields: ["sender_name", "service"],
      askedTs: Date.now(),
      sourceQuote: "change sender name and service",
    },
  });
  const result = applyProposals(
    [
      bookingProposalFromPatch(
        { sender_name: "Rawan al ajmi" },
        "rawan al ajmi express sedan",
      ),
    ],
    {
      draft,
      dialogState: entry.dialogState,
      whatsappNumber: "96599338566",
      stage: "awaiting_confirmation",
      pendingEditSlots: ["sender_name"],
    },
  );
  entry = { ...entry, bookingDraft: result.draft, dialogState: result.dialogState };
  entry = applyService(entry, "rawan al ajmi express sedan", {
    class: "sedan",
    tier: "fast",
    confidence: "high",
    source_quote: "express sedan",
  });
  assert(entry.bookingDraft.senderName === "Rawan al ajmi", "pending multi-edit should update sender");
  assert(entry.selectedDeliveryType === "sedan_fast", "pending multi-edit should update service");
  assert(entry.quotedPrice === 1.75, "pending multi-edit should update selected price");
}

// 4. Cancel/reset lifecycle: source contains reset branches that clear edit and DST state.
{
  const indexSrc = fs.readFileSync(path.join(root, "plugins/octopus-channel/index.ts"), "utf8");
  assert(/pendingOrderEdits:\s*null/.test(indexSrc), "reset paths must clear pendingOrderEdits");
  assert(/greeting reset[\s\S]*dialogState:[\s\S]*createEmptyDialogState/.test(indexSrc), "greeting reset must reset DST");
  assert(/create_simple_order[\s\S]*pendingOrderEdits:\s*null/.test(indexSrc), "order submit must clear pendingOrderEdits");
}

// 5. Coverage then booking: coverage tool remains read-only with respect to controller booking state.
{
  const coverageSrc = fs.readFileSync(path.join(root, "plugins/riders-tools/tools/coverage.ts"), "utf8");
  assert(!/pushResponderStateOp/.test(coverageSrc), "coverage tool must not write responder state");
  assert(/Does NOT advance booking state or set requested slots/.test(coverageSrc), "coverage tool contract should stay explicit");
}

// 6. Ambiguous area then short reply: post-drain derivation carries current text/route context, and unknown fast-path disposition skips writes.
{
  const indexSrc = fs.readFileSync(path.join(root, "plugins/octopus-channel/index.ts"), "utf8");
  assert(/currentCustomerText:\s*rawBody/.test(indexSrc), "requestedSlot derivation must use current customer text");
  assert(/activeQuotedRoute/.test(indexSrc), "requestedSlot derivation must include active quote context");
  const gate = decideFastPathDispositionGate({ disposition: null, mode: "on" });
  assert(gate.action === "skip", `unknown disposition should fail closed, got ${gate.action}`);
}

// 7. Pin then address: native location pin binds to the active address step and clears requestedSlot.
{
  const draft = createEmptyBookingDraft();
  const entry = buildEntry(draft, {
    stage: "collecting_booking_details",
    bookingStep: "pickup_address",
    quotePickupAreaNameEn: null,
    dialogState: setRequestedSlot(seedDialogStateFromDraft(draft), {
      name: "pickup_area",
      options: null,
      askedTs: Date.now(),
    }),
  });
  const result = bindNativeLocationToAddressStep({
    entry,
    location: {
      source: "location_pin",
      latitude: 29.37,
      longitude: 47.98,
      name: "Pinned place",
      address: "Mirqab",
      resolvedAreaName: "Mirqab",
    },
  });
  assert(result && result.role === "pickup", "pin should bind to pickup address step");
  assert(result.entry.bookingDraft.pickupLocation?.resolvedAreaName === "Mirqab", "pin area should be saved");
  assert(result.entry.dialogState?.requestedSlot === null, "pin binding should clear requestedSlot");
  assert(result.entry.pendingPickupAreaNameEn === "Mirqab", "pin resolved area should become pending pickup area");
}

// 8. Option rejection then selection: rejecting current option shows alternatives; later selection commits.
{
  const draft = buildCompleteDraft();
  const quotedEntry = buildEntry(draft, {
    stage: "quoted",
    selectedDeliveryType: "sedan_fast",
    selectedQuoteOptionType: "sedan_fast",
    quotedPrice: 1.75,
    selectedQuoteOptionPrice: 1.75,
  });
  const reject = resolveSameRouteQuoteFollowupAction({
    visibleText: "not express sedan",
    controllerEntry: quotedEntry,
    route,
  });
  assert(reject?.kind === "show_other_options", `rejecting current option should show alternatives, got ${reject?.kind}`);
  const select = resolveSameRouteQuoteFollowupAction({
    visibleText: "standard sedan",
    controllerEntry: quotedEntry,
    route,
  });
  assert(select?.kind === "switch_option", `selecting another option should switch, got ${select?.kind}`);
}

// 9. Unsupported area then nearby question: coverage pending supports nearby follow-ups without route state writes.
{
  const coverageSrc = fs.readFileSync(path.join(root, "plugins/riders-tools/tools/coverage.ts"), "utf8");
  assert(/status:\s*"nearby_suggestions"/.test(coverageSrc), "coverage should support nearby suggestions");
  assert(/isNearbyFollowup/.test(coverageSrc), "coverage should recognize short nearby follow-ups");
  assert(/setCoveragePending/.test(coverageSrc), "coverage should persist coverage-specific pending context");
}

// Fuzz: roleless address parts must not silently disappear; they become explicit rejections.
{
  const values = ["2", "street 9", "house 11", "avenue 4", "apartment 3 floor 2"];
  for (let i = 0; i < 200; i += 1) {
    const draft = createEmptyBookingDraft();
    const field = ["address_block", "address_street", "address_house", "address_avenue", "address_extra"][i % 5];
    const patch = { address_role: null, [field]: values[i % values.length] };
    const result = applyBookingFieldPatch({
      draft,
      patch,
      whatsappNumber: "96599338566",
      dialogState: seedDialogStateFromDraft(draft),
      dstSource: "llm_apply",
    });
    assert(result.applied.length === 0, `roleless ${field} should not apply`);
    assert(
      result.rejected.some((r) => r.reason === "address_role_required" || r.field === "address_house"),
      `roleless ${field} should produce explicit rejection, got ${JSON.stringify(result.rejected)}`,
    );
  }
}

// Fuzz: complete randomized identity/address payloads should not produce conflicts on empty drafts.
{
  const names = ["Aziz Al Mulla", "Rawan Al Ajmi", "Ahmad Basha", "Sara Al Sabah"];
  for (let i = 0; i < 80; i += 1) {
    const draft = createEmptyBookingDraft();
    const sender = names[i % names.length];
    const recipient = names[(i + 1) % names.length];
    const result = applyProposals(
      [
        bookingProposalFromPatch(
          {
            sender_name: sender,
            sender_phone: `965${90000000 + i}`,
            recipient_name: recipient,
            recipient_phone: `965${60000000 + i}`,
            address_block: String((i % 9) + 1),
            address_street: String((i % 20) + 1),
            address_house: String((i % 30) + 1),
            address_role: "pickup",
          },
          `${sender} ${recipient} block street house ${i}`,
        ),
      ],
      {
        draft,
        dialogState: seedDialogStateFromDraft(draft),
        whatsappNumber: "96599338566",
        stage: "collecting_booking_details",
      },
    );
    assert(result.conflicts.length === 0, `empty draft fuzz should not conflict: ${JSON.stringify(result.conflicts)}`);
  }
}

// Raw nulls can still appear, but satisfaction/missing truth must be present beside them.
{
  const draft = buildCompleteDraft({ deliveryHouse: null });
  const entry = buildEntry(draft);
  const context = formatOneBrainLiveChannelContext({
    normalizedReplyTarget: "96599338566",
    preferredReplyLanguage: "en",
    customerScriptMode: "english",
    controllerEntry: entry,
  });
  assert(/delivery_address_satisfied=true/.test(context), "context must expose delivery address satisfaction");
  assert(/missing_fields:\s*\[\]/.test(context), "context must expose authoritative empty missing fields");
}

// Invalid draft state should surface as invalid even when missing fields also exist.
{
  const draft = buildCompleteDraft({
    senderPhone: "abc",
    recipientName: null,
  });
  const result = guardCreateSimpleOrder({
    draft,
    pickupAreaNameEn: "Northwest Sulaibikhat",
    dropoffAreaNameEn: "Zahra",
    deliveryType: "sedan_normal",
    quotedPrice: 1.25,
    visibleCustomerText: "yes",
    lastQuotedRoute: {
      routeKey: route.routeKey,
      pickupAreaNameEn: route.pickupAreaNameEn,
      pickupAreaNameAr: null,
      dropoffAreaNameEn: route.dropoffAreaNameEn,
      dropoffAreaNameAr: null,
      pricesByType: route.pricesByType,
      optionCatalog: route.optionCatalog,
    },
  });
  assert(result.ok === false && result.code === "draft_invalid", `invalid+missing should report invalid, got ${JSON.stringify(result)}`);
}

console.log("smoke-test-random-flow-invariants: OK");
