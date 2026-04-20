#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: clarify-before-proceed gate (Bug 1, 2026-04-20).
//
// Product rule:
//   On `stage=quoted` with a mixed-bookability option catalog (at least
//   one `manual_confirmation_required` option AND >= 2 priced options),
//   a vague proceed signal ("go ahead", "let's do it", "اكمل", "نعم")
//   from the customer — when they did NOT name a specific option —
//   must emit the `CLARIFY_OPTION_BEFORE_PROCEED` directive so the
//   server-composed clarify reply wins at Region A of the outbound
//   decision. The customer must never be advanced into sender
//   collection on an ambiguous "proceed" where a manual-confirm option
//   is in play.
//
// Cases covered:
//   T1  vague proceed + manual-confirm in catalog + no option named
//       → CLARIFY_OPTION_BEFORE_PROCEED
//   T2  explicit option named in text ("go ahead with helper") → gate
//       does NOT fire (normal route-selected flow takes over)
//   T3  catalog has NO manual-confirm option → gate does NOT fire
//       (all options are direct-bookable; vague proceed is safe)
//   T4  stage !== "quoted" → gate does NOT fire
//   T5  missing `currentCustomerText` / `activeQuotedRoute` args
//       → gate does NOT fire (backward-compat: old callers stay green)
//   T6  forbidden shapes block the known drift patterns
//   T7  deterministic reply builder lists every priced option and flags
//       manual-confirm ones, in EN and AR
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
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");
const { createEmptyBookingDraft } = policy;
const { computeOneBrainNextRequiredAction } = oneBrain;
const {
  detectVagueProceedSignal,
  detectExplicitOptionMention,
  routeHasManualConfirmOption,
  buildDeterministicClarifyOptionBeforeProceedReply,
} = quotedOptions;

function makeRoute(overrides = {}) {
  const base = {
    routeKey: "jabriya->salmiya",
    pickupAreaNameAr: "الجابرية",
    pickupAreaNameEn: "Jabriya",
    dropoffAreaNameAr: "السالمية",
    dropoffAreaNameEn: "Salmiya",
    pricesByType: { sedan_normal: 2.5, helper_standard: 3.25 },
    optionCatalog: [
      {
        delivery_type: "sedan_normal",
        label_ar: "عادي",
        label_en: "Standard",
        quoted_price: 2.5,
        formatted_price: "2.500 KWD",
        visibility: "visible",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
      {
        delivery_type: "helper_standard",
        label_ar: "مع مساعد",
        label_en: "Helper service",
        quoted_price: 3.25,
        formatted_price: "3.250 KWD",
        visibility: "visible",
        direct_chat_booking_status: "manual_confirmation_required",
        direct_chat_booking_note: null,
      },
    ],
    serviceDiscovery: null,
  };
  return { ...base, ...overrides };
}

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
    stage: "quoted",
    bookingDraft: createEmptyBookingDraft(),
    ...overrides,
  };
}

// -----------------------------------------------------------------------
// Unit-ish checks for the helpers first so any regression is localised.
// -----------------------------------------------------------------------
{
  assert(detectVagueProceedSignal("can we go ahead with it or?"), "vague: go ahead");
  assert(detectVagueProceedSignal("let's do it"), "vague: let's do it");
  assert(detectVagueProceedSignal("proceed"), "vague: proceed");
  assert(detectVagueProceedSignal("نعم"), "vague: Arabic نعم");
  assert(detectVagueProceedSignal("تمام"), "vague: Arabic تمام");
  assert(detectVagueProceedSignal("اكمل"), "vague: Arabic اكمل");
  // `detectVagueProceedSignal` is the text-shape half; the gate pairs it
  // with `detectExplicitOptionMention` to decide whether clarification
  // is required. "go ahead with helper" IS a proceed signal — the
  // option-mention check is what neutralises it downstream.
  assert(detectVagueProceedSignal("go ahead with helper"), "vague shape: go ahead with helper");
  assert(!detectVagueProceedSignal("actually no"), "not vague: cancel-ish");
  assert(!detectVagueProceedSignal(""), "not vague: empty");
  assert(!detectVagueProceedSignal(null), "not vague: null");
  const long = "a ".repeat(70) + " go ahead";
  assert(!detectVagueProceedSignal(long), "not vague: >120 chars");
}

{
  const route = makeRoute();
  assert(
    detectExplicitOptionMention({ text: "go ahead with helper", route })?.delivery_type ===
      "helper_standard",
    "explicit: helper matches",
  );
  assert(
    detectExplicitOptionMention({ text: "standard please", route })?.delivery_type === "sedan_normal",
    "explicit: standard matches",
  );
  assert(
    detectExplicitOptionMention({ text: "can we go ahead with it or?", route }) === null,
    "explicit: vague does not match",
  );
}

{
  assert(routeHasManualConfirmOption(makeRoute()) === true, "mixed catalog has manual-confirm");
  const singleOption = makeRoute({
    optionCatalog: [
      {
        delivery_type: "helper_standard",
        label_ar: "مع مساعد",
        label_en: "Helper service",
        quoted_price: 3.25,
        formatted_price: "3.250 KWD",
        visibility: "visible",
        direct_chat_booking_status: "manual_confirmation_required",
        direct_chat_booking_note: null,
      },
    ],
  });
  assert(
    routeHasManualConfirmOption(singleOption) === false,
    "single-option catalog does NOT trigger (vague proceed is unambiguous)",
  );
  const noManualConfirm = makeRoute({
    optionCatalog: [
      {
        delivery_type: "sedan_normal",
        label_ar: "عادي",
        label_en: "Standard",
        quoted_price: 2.5,
        formatted_price: "2.500 KWD",
        visibility: "visible",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
      {
        delivery_type: "sedan_fast",
        label_ar: "سريع",
        label_en: "Express",
        quoted_price: 3.0,
        formatted_price: "3.000 KWD",
        visibility: "visible",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
    ],
  });
  assert(routeHasManualConfirmOption(noManualConfirm) === false, "no manual-confirm options");
}

// -----------------------------------------------------------------------
// T1: the canonical bug transcript. Vague proceed, manual-confirm exists,
// option not named → CLARIFY_OPTION_BEFORE_PROCEED.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const entry = makeEntry();
  const draft = entry.bookingDraft;
  const missing = [
    "sender.name",
    "sender.phone",
    "recipient.name",
    "recipient.phone",
    "pickup.address",
    "delivery.address",
  ];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "can we go ahead with it or?",
    activeQuotedRoute: route,
  });
  assert(
    directive?.action === "CLARIFY_OPTION_BEFORE_PROCEED",
    `T1: want CLARIFY_OPTION_BEFORE_PROCEED; got ${JSON.stringify(directive)}`,
  );
  assert(directive.field === "selected_option", `T1: field=${directive?.field}`);
}

// -----------------------------------------------------------------------
// T2: customer names the option explicitly → gate does NOT fire.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const entry = makeEntry();
  const draft = entry.bookingDraft;
  const missing = ["sender.name", "sender.phone", "recipient.name", "recipient.phone"];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "go ahead with helper please",
    activeQuotedRoute: route,
  });
  assert(
    directive?.action !== "CLARIFY_OPTION_BEFORE_PROCEED",
    `T2: explicit option must skip clarify gate; got ${JSON.stringify(directive)}`,
  );
}

// -----------------------------------------------------------------------
// T3: catalog has no manual-confirm option → gate does NOT fire. Vague
// proceed here is safe because every option is instant-bookable.
// -----------------------------------------------------------------------
{
  const route = makeRoute({
    optionCatalog: [
      {
        delivery_type: "sedan_normal",
        label_ar: "عادي",
        label_en: "Standard",
        quoted_price: 2.5,
        formatted_price: "2.500 KWD",
        visibility: "visible",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
      {
        delivery_type: "sedan_fast",
        label_ar: "سريع",
        label_en: "Express",
        quoted_price: 3.0,
        formatted_price: "3.000 KWD",
        visibility: "visible",
        direct_chat_booking_status: "verified",
        direct_chat_booking_note: null,
      },
    ],
  });
  const entry = makeEntry();
  const draft = entry.bookingDraft;
  const missing = ["sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "let's do it",
    activeQuotedRoute: route,
  });
  assert(
    directive?.action !== "CLARIFY_OPTION_BEFORE_PROCEED",
    `T3: no manual-confirm option must skip clarify gate; got ${JSON.stringify(directive)}`,
  );
}

// -----------------------------------------------------------------------
// T4: stage !== "quoted" → gate does NOT fire. Post-price collection or
// other stages have their own invariants.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const entry = makeEntry({ stage: "collecting_booking_details" });
  const draft = entry.bookingDraft;
  const missing = ["sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "go ahead",
    activeQuotedRoute: route,
  });
  assert(
    directive?.action !== "CLARIFY_OPTION_BEFORE_PROCEED",
    `T4: non-quoted stage must skip clarify gate; got ${JSON.stringify(directive)}`,
  );
}

// -----------------------------------------------------------------------
// T5: missing `currentCustomerText` or `activeQuotedRoute` → gate does
// NOT fire. Backward compat for callers (e.g. post-drain recomputation)
// that cannot supply the args.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const entry = makeEntry();
  const draft = entry.bookingDraft;
  const missing = ["sender.name", "sender.phone"];
  const noText = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    activeQuotedRoute: route,
  });
  assert(
    noText?.action !== "CLARIFY_OPTION_BEFORE_PROCEED",
    `T5a: missing text must skip gate; got ${JSON.stringify(noText)}`,
  );
  const noRoute = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "go ahead",
  });
  assert(
    noRoute?.action !== "CLARIFY_OPTION_BEFORE_PROCEED",
    `T5b: missing route must skip gate; got ${JSON.stringify(noRoute)}`,
  );
}

// -----------------------------------------------------------------------
// T6: forbidden shapes cover the known drift patterns.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const entry = makeEntry();
  const draft = entry.bookingDraft;
  const missing = ["sender.name", "sender.phone"];
  const directive = computeOneBrainNextRequiredAction({
    draft,
    entry,
    missing,
    currentCustomerText: "go ahead",
    activeQuotedRoute: route,
  });
  const expected = [
    "ask_sender_before_option_confirmed",
    "ask_recipient_before_option_confirmed",
    "start_booking_with_default_option",
    "call_create_simple_order_before_option_confirmed",
  ];
  for (const shape of expected) {
    assert(
      directive.forbiddenShapes.includes(shape),
      `T6: forbiddenShapes includes ${shape}; got ${JSON.stringify(directive.forbiddenShapes)}`,
    );
  }
}

// -----------------------------------------------------------------------
// T7: deterministic clarify reply. Lists every priced option and tags
// manual-confirm ones explicitly in both EN and AR.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const en = buildDeterministicClarifyOptionBeforeProceedReply({ language: "en", route });
  assert(en.includes("Which option would you like to go ahead with?"), `T7 en: header missing: ${en}`);
  assert(en.includes("Standard"), "T7 en: lists standard");
  assert(en.includes("Helper service"), "T7 en: lists helper");
  assert(
    en.includes("(needs manual confirmation)"),
    `T7 en: flags manual-confirm; got ${en}`,
  );
  const ar = buildDeterministicClarifyOptionBeforeProceedReply({ language: "ar", route });
  assert(ar.includes("أي خيار تفضل نكمل فيه؟"), `T7 ar: header missing: ${ar}`);
  assert(ar.includes("مع مساعد"), "T7 ar: lists helper");
  assert(ar.includes("(يحتاج تأكيد يدوي)"), `T7 ar: flags manual-confirm: ${ar}`);
}

console.log("smoke-test-clarify-option-before-proceed: OK");
