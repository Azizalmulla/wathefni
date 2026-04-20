#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: class+tier discriminated option matcher (Bug 3, 2026-04-20).
//
// Product rule:
//   The server-side option matcher that commits `switch_option` on a quoted
//   route must resolve the customer's utterance through a class+tier model
//   (class ∈ {sedan, van, cooled_van, helper}; tier ∈ {normal, fast,
//   standard}). Tier-only signals ("express"), ambiguous class-only
//   signals on mixed-tier catalogs ("express van" — van_fast vs
//   cooled_van_fast both consistent), and abbreviated inputs ("ref",
//   "refrig") must EITHER resolve uniquely OR fall through to the
//   clarify-before-proceed gate. A tier-only hit ("express") must NEVER
//   silently commit to a specific option.
//
// Regression anchor:
//   Pre-fix, `"express ref van"` scored sedan_fast = 7 (alias "express")
//   and cooled_van_fast = 0 (no alias contained "ref"), so the matcher
//   committed sedan_fast. The customer then got "Express sedan, 1.750 KWD"
//   instead of "Express refrigerated van, 2.250 KWD".
//
// Cases covered:
//   M1  "express ref van"     → cooled_van_fast (class+tier unique)
//   M2  "ref van"             → cooled_van_normal via class-only rule when
//                               route has a single cooled_van option; or
//                               ambiguous across cooled_van_{normal,fast}
//                               when both are present
//   M3  "express van"         → ambiguous between van_fast and cooled_van_fast
//   M4  "express"             → underspecified (tier-only) → no commit
//   M5  "standard sedan"      → sedan_normal (class+tier unique)
//   M6  "box express"         → van_fast (class+tier unique)
//   M7  "helper"              → helper_standard (class-only, single-tier class)
//   M8  "Express refrigerated van" (full label) → cooled_van_fast
//   M9  "مبرد سريع"           → cooled_van_fast (AR class+tier)
//   M10 "ref" alone           → ambiguous when both cooled options present
//   M11 "sedan"               → ambiguous between sedan_normal and sedan_fast
//   M12 same-route resolver honours the new matcher and refuses to commit
//       on tier-only input (wires the controller-side invariant)
//   M13 `detectExplicitOptionMention` returns null on ambiguous/tier-only
//       input (wires the clarify-before-proceed invariant)
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
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");
const { normalizeIntentText } = policy;
const {
  matchQuotedOptionDiscriminated,
  getOptionClassification,
  resolveSameRouteQuoteFollowupAction,
  detectExplicitOptionMention,
} = quotedOptions;

function opt(deliveryType, labelEn, labelAr, price, status = "verified") {
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

const FULL_CATALOG = [
  opt("sedan_normal", "Standard sedan", "سيارة عاديه + توصيل عادي", 1.25, "verified"),
  opt("sedan_fast", "Express sedan", "سيارة عاديه + توصيل سريع", 1.75, "verified"),
  opt("van_normal", "Standard box van", "بوكس مقفل + توصيل عادي", 1.75, "verified"),
  opt("van_fast", "Express box van", "بوكس مقفل + توصيل مستعجل", 2.25, "verified"),
  opt("cooled_van_normal", "Standard refrigerated van", "سيارة مبردة + توصيل عادي", 1.75, "manual_confirmation_required"),
  opt("cooled_van_fast", "Express refrigerated van", "سيارة مبردة + توصيل سريع", 2.25, "manual_confirmation_required"),
  opt("helper_standard", "Helper service", "مع مساعد (عادي)", 3.25, "manual_confirmation_required"),
];

function makeRoute(catalog = FULL_CATALOG) {
  return {
    routeKey: "salwa__salmiya",
    pickupAreaNameAr: "السالمية",
    pickupAreaNameEn: "Salwa",
    dropoffAreaNameAr: "السالمية",
    dropoffAreaNameEn: "Salmiya",
    pricesByType: Object.fromEntries(catalog.map((o) => [o.delivery_type, o.quoted_price])),
    optionCatalog: catalog,
    serviceDiscovery: null,
  };
}

function matchByText(text, catalog = FULL_CATALOG) {
  const normalized = normalizeIntentText(text);
  return matchQuotedOptionDiscriminated({ normalizedText: normalized, options: catalog });
}

// -----------------------------------------------------------------------
// Sanity: classification table is complete for all canonical delivery types.
// -----------------------------------------------------------------------
{
  const expected = {
    sedan_normal: { class: "sedan", tier: "normal" },
    sedan_fast: { class: "sedan", tier: "fast" },
    van_normal: { class: "van", tier: "normal" },
    van_fast: { class: "van", tier: "fast" },
    cooled_van_normal: { class: "cooled_van", tier: "normal" },
    cooled_van_fast: { class: "cooled_van", tier: "fast" },
    helper_standard: { class: "helper", tier: "standard" },
  };
  for (const [type, want] of Object.entries(expected)) {
    const got = getOptionClassification(type);
    assert(
      got && got.class === want.class && got.tier === want.tier,
      `classification ${type} want ${JSON.stringify(want)} got ${JSON.stringify(got)}`,
    );
  }
  assert(getOptionClassification("unknown_type") === null, "unknown type → null");
  assert(getOptionClassification("") === null, "empty → null");
  assert(getOptionClassification(null) === null, "null → null");
}

// -----------------------------------------------------------------------
// M1: canonical regression — "express ref van" → cooled_van_fast.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("express ref van");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "cooled_van_fast",
    `M1: want cooled_van_fast; got ${JSON.stringify(outcome)}`,
  );
  assert(
    outcome.reason === "class_and_tier",
    `M1: reason should be class_and_tier; got ${outcome.reason}`,
  );
}

// -----------------------------------------------------------------------
// M2a: "ref van" on full catalog → ambiguous (cooled_van_normal and
// cooled_van_fast both consistent).
// -----------------------------------------------------------------------
{
  const outcome = matchByText("ref van");
  assert(
    outcome.kind === "ambiguous",
    `M2a: want ambiguous; got ${JSON.stringify(outcome)}`,
  );
  const types = outcome.candidates.map((o) => o.delivery_type).sort();
  assert(
    JSON.stringify(types) === JSON.stringify(["cooled_van_fast", "cooled_van_normal"]),
    `M2a: want cooled pair; got ${JSON.stringify(types)}`,
  );
}

// M2b: "ref van" on a catalog with only one cooled_van option → unique.
{
  const outcome = matchByText(
    "ref van",
    [
      opt("sedan_normal", "Standard sedan", "سيارة عاديه", 1.25),
      opt("cooled_van_normal", "Standard refrigerated van", "سيارة مبردة", 1.75, "manual_confirmation_required"),
    ],
  );
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "cooled_van_normal",
    `M2b: want cooled_van_normal unique; got ${JSON.stringify(outcome)}`,
  );
  assert(outcome.reason === "class_only_unique", `M2b: reason class_only_unique`);
}

// -----------------------------------------------------------------------
// M3: "express van" — bare "van" is INTENTIONALLY not a class token. It
// would otherwise be ambiguous between `van_*` (box van) and
// `cooled_van_*` (refrigerated van). The canonical English class marker
// for the box-van family is `"box"` / `"box van"`, so the matcher
// treats a bare "express van" as underspecified and hands off to the
// clarify gate. This is the same safe default as `"express"` alone.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("express van");
  assert(
    outcome.kind === "underspecified",
    `M3: want underspecified (bare "van" is ambiguous); got ${JSON.stringify(outcome)}`,
  );
}

// M3b: "express box van" is the unambiguous phrasing and MUST resolve.
{
  const outcome = matchByText("express box van");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "van_fast",
    `M3b: want van_fast via "box van"; got ${JSON.stringify(outcome)}`,
  );
}

// -----------------------------------------------------------------------
// M4: "express" alone → underspecified (tier-only, no class).
// -----------------------------------------------------------------------
{
  const outcome = matchByText("express");
  assert(outcome.kind === "underspecified", `M4: want underspecified; got ${JSON.stringify(outcome)}`);
  assert(outcome.hasTier === true && outcome.hasClass === false, `M4: dimensions flags`);
}

// -----------------------------------------------------------------------
// M5: "standard sedan" → sedan_normal.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("standard sedan");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "sedan_normal",
    `M5: want sedan_normal; got ${JSON.stringify(outcome)}`,
  );
}

// -----------------------------------------------------------------------
// M6: "box express" → van_fast.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("box express");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "van_fast",
    `M6: want van_fast; got ${JSON.stringify(outcome)}`,
  );
}

// -----------------------------------------------------------------------
// M7: "helper" → helper_standard (class-only, single-tier class always
// resolves uniquely).
// -----------------------------------------------------------------------
{
  const outcome = matchByText("helper");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "helper_standard",
    `M7: want helper_standard; got ${JSON.stringify(outcome)}`,
  );
  assert(outcome.reason === "class_only_unique", `M7: reason class_only_unique`);
}

// -----------------------------------------------------------------------
// M8: full label "Express refrigerated van" → cooled_van_fast via full-
// label path.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("i want express refrigerated van please");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "cooled_van_fast",
    `M8: want cooled_van_fast via label; got ${JSON.stringify(outcome)}`,
  );
  assert(outcome.reason === "full_label", `M8: reason full_label; got ${outcome.reason}`);
}

// -----------------------------------------------------------------------
// M9: AR "مبرد سريع" → cooled_van_fast.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("مبرد سريع");
  assert(
    outcome.kind === "match" && outcome.option.delivery_type === "cooled_van_fast",
    `M9: want cooled_van_fast; got ${JSON.stringify(outcome)}`,
  );
}

// -----------------------------------------------------------------------
// M10: "ref" alone → ambiguous when both cooled options present.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("ref");
  assert(
    outcome.kind === "ambiguous",
    `M10: want ambiguous; got ${JSON.stringify(outcome)}`,
  );
  const types = outcome.candidates.map((o) => o.delivery_type).sort();
  assert(
    JSON.stringify(types) === JSON.stringify(["cooled_van_fast", "cooled_van_normal"]),
    `M10: want both cooled options; got ${JSON.stringify(types)}`,
  );
}

// -----------------------------------------------------------------------
// M11: bare "sedan" → ambiguous between sedan_normal and sedan_fast.
// -----------------------------------------------------------------------
{
  const outcome = matchByText("sedan");
  assert(
    outcome.kind === "ambiguous",
    `M11: want ambiguous sedan; got ${JSON.stringify(outcome)}`,
  );
  const types = outcome.candidates.map((o) => o.delivery_type).sort();
  assert(
    JSON.stringify(types) === JSON.stringify(["sedan_fast", "sedan_normal"]),
    `M11: want sedan pair; got ${JSON.stringify(types)}`,
  );
}

// -----------------------------------------------------------------------
// M12: same-route resolver commits switch_option ONLY on unique match.
// Tier-only input must NOT commit a guess.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  const controllerEntry = {
    bookingStep: "none",
    quoteTs: Date.now(),
    quoteRouteKey: "salwa__salmiya",
    quotePickupAreaNameEn: "Salwa",
    quotePickupAreaNameAr: "السالمية",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    pendingPickupAreaNameEn: null,
    pendingPickupAreaNameAr: null,
    pendingDropoffAreaNameEn: null,
    pendingDropoffAreaNameAr: null,
    selectedQuoteOptionType: "sedan_normal",
    selectedQuoteOptionLabelAr: "سيارة عاديه",
    selectedQuoteOptionLabelEn: "Standard sedan",
    selectedQuoteOptionPrice: 1.25,
    selectedQuoteOptionDirectChatBookingStatus: "verified",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    stage: "quoted",
    bookingDraft: policy.createEmptyBookingDraft(),
  };

  const uniqueHit = resolveSameRouteQuoteFollowupAction({
    visibleText: "express ref van",
    controllerEntry,
    route,
  });
  assert(
    uniqueHit && uniqueHit.kind === "switch_option" && uniqueHit.option.delivery_type === "cooled_van_fast",
    `M12a: unique hit commits; got ${JSON.stringify(uniqueHit)}`,
  );

  const tierOnly = resolveSameRouteQuoteFollowupAction({
    visibleText: "express",
    controllerEntry,
    route,
  });
  assert(
    tierOnly === null,
    `M12b: tier-only must NOT commit; got ${JSON.stringify(tierOnly)}`,
  );

  const ambiguous = resolveSameRouteQuoteFollowupAction({
    visibleText: "ref van",
    controllerEntry,
    route,
  });
  assert(
    ambiguous === null,
    `M12c: ambiguous must NOT commit; got ${JSON.stringify(ambiguous)}`,
  );
}

// -----------------------------------------------------------------------
// M13: detectExplicitOptionMention mirrors the same behavior so the
// clarify-before-proceed gate sees consistent signals.
// -----------------------------------------------------------------------
{
  const route = makeRoute();
  assert(
    detectExplicitOptionMention({ text: "express ref van", route })?.delivery_type === "cooled_van_fast",
    "M13a: explicit mention on abbreviation",
  );
  assert(
    detectExplicitOptionMention({ text: "express", route }) === null,
    "M13b: tier-only explicit mention is null",
  );
  assert(
    detectExplicitOptionMention({ text: "ref van", route }) === null,
    "M13c: ambiguous explicit mention is null (clarify will engage)",
  );
  assert(
    detectExplicitOptionMention({ text: "helper", route })?.delivery_type === "helper_standard",
    "M13d: helper class-only resolves",
  );
}

console.log("smoke-test-option-matcher-class-discriminated: OK");
