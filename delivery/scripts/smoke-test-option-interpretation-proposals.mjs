#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 1 — structured option interpretation contract
// (2026-04-20 "one source of truth for option resolution").
//
// Product rule:
//   Option resolution on a quoted route is driven by TWO proposals:
//     - Layer 1: deterministic raw-text matcher (class+tier tokens over the
//       customer's inbound text)
//     - Layer 2: the LLM's structured interpretation, carried on a new
//       responder op `propose_option_interpretation` ({class, tier,
//       qualifiers, source_quote, confidence})
//   A single reconciler (`resolveOptionFromProposals`) combines the two
//   outcomes and returns `commit` / `clarify` / `none`. Neither source is
//   allowed to silently commit a wrong option; ambiguity or disagreement
//   always falls to the clarify gate.
//
// This smoke covers:
//   V1-V8  validator shape rules on `propose_option_interpretation` ops
//          (class/tier enums, source-quote required, confidence enum,
//          class+tier not both null, qualifier cleanup)
//   R1     LLM-only commit: raw text underspecified, LLM high-confidence
//          unique → commit_llm
//   R2     Fast-path-only commit: LLM absent → commit_fast_path
//   R3     Both agree → commit_both_agree
//   R4     Disagreement: both unique to different options → clarify_disagreement
//   R5     Fast match but LLM ambiguous → clarify_ambiguous (conservative)
//   R6     LLM low-confidence alone → none (never committed solo)
//   R7     Both null/underspecified → none
//   R8     Fast match + LLM null (no proposal) → commit_fast_path
//   R9     Fast ambiguous + LLM ambiguous → clarify_ambiguous
//   L1     matchLlmOptionInterpretation: class+tier unique
//   L2     matchLlmOptionInterpretation: class-only single-tier class
//   L3     matchLlmOptionInterpretation: class-only ambiguous across tiers
//   L4     matchLlmOptionInterpretation: low-confidence → none
//   L5     matchLlmOptionInterpretation: tier-only → underspecified
//   L6     matchLlmOptionInterpretation: unknown class → underspecified
//   B1     Backward-compat: no propose_option_interpretation op →
//          pre-existing matcher + pre-dispatch commit path unaffected
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

const policy = loadTs("plugins/shared/conversation-policy.ts");
const ops = loadTs("plugins/shared/responder-state-ops.ts");
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");

const { normalizeIntentText } = policy;
const { validateOptionInterpretationOp } = ops;
const {
  matchQuotedOptionDiscriminated,
  matchLlmOptionInterpretation,
  resolveOptionFromProposals,
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
  opt("sedan_normal", "Standard sedan", "سيارة عاديه", 1.25, "verified"),
  opt("sedan_fast", "Express sedan", "سيارة عاديه + توصيل سريع", 1.75, "verified"),
  opt("van_normal", "Standard box van", "بوكس مقفل", 1.75, "verified"),
  opt("van_fast", "Express box van", "بوكس مقفل + مستعجل", 2.25, "verified"),
  opt("cooled_van_normal", "Standard refrigerated van", "سيارة مبردة", 1.75, "manual_confirmation_required"),
  opt("cooled_van_fast", "Express refrigerated van", "سيارة مبردة سريع", 2.25, "manual_confirmation_required"),
  opt("helper_standard", "Helper service", "مع مساعد (عادي)", 3.25, "manual_confirmation_required"),
];

// ---------------------------------------------------------------------------
// V1-V8: validator shape rules
// ---------------------------------------------------------------------------

// V1: minimal valid proposal
{
  const { cleaned, errors } = validateOptionInterpretationOp({
    class: "cooled_van",
    tier: "fast",
    source_quote: "express ref van",
    confidence: "high",
    turn_id: "t1",
  });
  assert.deepEqual(errors, [], `V1: no errors; got ${JSON.stringify(errors)}`);
  assert.equal(cleaned.class, "cooled_van");
  assert.equal(cleaned.tier, "fast");
  assert.equal(cleaned.source_quote, "express ref van");
  assert.equal(cleaned.confidence, "high");
  assert.equal(cleaned.op, "propose_option_interpretation");
}

// V2: unknown class rejected
{
  const { errors } = validateOptionInterpretationOp({
    class: "spaceship",
    tier: "fast",
    source_quote: "warp drive",
    confidence: "high",
    turn_id: "t1",
  });
  assert.ok(errors.some((e) => e.field === "class" && e.reason === "class_unknown"), "V2");
}

// V3: unknown tier rejected
{
  const { errors } = validateOptionInterpretationOp({
    class: "sedan",
    tier: "ludicrous",
    source_quote: "plaid mode",
    confidence: "high",
    turn_id: "t1",
  });
  assert.ok(errors.some((e) => e.field === "tier" && e.reason === "tier_unknown"), "V3");
}

// V4: both class and tier null rejected (op carries no signal)
{
  const { errors } = validateOptionInterpretationOp({
    class: null,
    tier: null,
    source_quote: "something",
    confidence: "high",
    turn_id: "t1",
  });
  assert.ok(
    errors.some((e) => e.reason === "class_and_tier_both_null"),
    `V4: want class_and_tier_both_null; got ${JSON.stringify(errors)}`,
  );
}

// V5: missing source_quote rejected
{
  const { errors } = validateOptionInterpretationOp({
    class: "sedan",
    tier: "normal",
    source_quote: "",
    confidence: "high",
    turn_id: "t1",
  });
  assert.ok(
    errors.some((e) => e.field === "source_quote" && e.reason === "source_quote_empty"),
    "V5",
  );
}

// V6: invalid confidence rejected
{
  const { errors } = validateOptionInterpretationOp({
    class: "sedan",
    tier: "normal",
    source_quote: "standard sedan",
    confidence: "medium",
    turn_id: "t1",
  });
  assert.ok(
    errors.some((e) => e.field === "confidence" && e.reason === "confidence_unknown"),
    "V6",
  );
}

// V7: tier-only (class=null) is valid; validator doesn't reject — resolver
// handles the underspecified outcome.
{
  const { cleaned, errors } = validateOptionInterpretationOp({
    class: null,
    tier: "fast",
    source_quote: "express",
    confidence: "high",
    turn_id: "t1",
  });
  assert.deepEqual(errors, [], `V7: no errors; got ${JSON.stringify(errors)}`);
  assert.equal(cleaned.class, null);
  assert.equal(cleaned.tier, "fast");
}

// V8: qualifiers are trimmed / capped / empty-strings dropped
{
  const { cleaned } = validateOptionInterpretationOp({
    class: "cooled_van",
    tier: "fast",
    qualifiers: ["  refrigerated  ", "", "ref van", "cold one"],
    source_quote: "express ref van",
    confidence: "high",
    turn_id: "t1",
  });
  assert.deepEqual(cleaned.qualifiers, ["refrigerated", "ref van", "cold one"], "V8");
}

// ---------------------------------------------------------------------------
// L1-L6: matchLlmOptionInterpretation
// ---------------------------------------------------------------------------

// L1: class+tier unique
{
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: "cooled_van",
      tier: "fast",
      source_quote: "ref van express",
      confidence: "high",
    },
    options: FULL_CATALOG,
  });
  assert.equal(res.kind, "match", "L1 kind");
  assert.equal(res.option.delivery_type, "cooled_van_fast", "L1 option");
  assert.equal(res.reason, "class_and_tier", "L1 reason");
}

// L2: single-tier class resolves without tier
{
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: "helper",
      tier: null,
      source_quote: "helper please",
      confidence: "high",
    },
    options: FULL_CATALOG,
  });
  assert.equal(res.kind, "match", "L2 kind");
  assert.equal(res.option.delivery_type, "helper_standard", "L2 option");
}

// L3: class-only on multi-tier class → ambiguous
{
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: "cooled_van",
      tier: null,
      source_quote: "the cool one",
      confidence: "high",
    },
    options: FULL_CATALOG,
  });
  assert.equal(res.kind, "ambiguous", `L3 kind; got ${JSON.stringify(res)}`);
  const types = res.candidates.map((o) => o.delivery_type).sort();
  assert.deepEqual(types, ["cooled_van_fast", "cooled_van_normal"], "L3 candidates");
}

// L4: low-confidence → none
{
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: "cooled_van",
      tier: "fast",
      source_quote: "not sure maybe that one",
      confidence: "low",
    },
    options: FULL_CATALOG,
  });
  assert.equal(res.kind, "none", `L4 kind; got ${JSON.stringify(res)}`);
}

// L5: tier-only → underspecified
{
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: null,
      tier: "fast",
      source_quote: "express",
      confidence: "high",
    },
    options: FULL_CATALOG,
  });
  assert.equal(res.kind, "underspecified", "L5 kind");
  assert.equal(res.hasTier, true);
  assert.equal(res.hasClass, false);
}

// L6: class whose catalog has zero priced options → underspecified
{
  const cataloglessOfVan = [
    opt("sedan_normal", "Standard sedan", "عادي", 1.25),
    opt("helper_standard", "Helper service", "مع مساعد", 3.25, "manual_confirmation_required"),
  ];
  const res = matchLlmOptionInterpretation({
    interpretation: {
      class: "cooled_van",
      tier: "fast",
      source_quote: "ref van",
      confidence: "high",
    },
    options: cataloglessOfVan,
  });
  assert.equal(res.kind, "underspecified", `L6 kind; got ${JSON.stringify(res)}`);
}

// ---------------------------------------------------------------------------
// R1-R9: resolveOptionFromProposals ladder
// ---------------------------------------------------------------------------

function rawTextOutcomeFor(text) {
  return matchQuotedOptionDiscriminated({
    normalizedText: normalizeIntentText(text),
    options: FULL_CATALOG,
  });
}

function llmOutcomeFor(interp) {
  return matchLlmOptionInterpretation({
    interpretation: interp,
    options: FULL_CATALOG,
  });
}

// R1: LLM disambiguates ambiguous/underspecified raw text
{
  const rawTextOutcome = rawTextOutcomeFor("the cold one please"); // no tokens match → none
  const llmOutcome = llmOutcomeFor({
    class: "cooled_van",
    tier: "fast",
    source_quote: "the cold one please",
    confidence: "high",
  });
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "commit", `R1 kind; got ${JSON.stringify(res)}`);
  assert.equal(res.source, "commit_llm", "R1 source");
  assert.equal(res.option.delivery_type, "cooled_van_fast", "R1 option");
}

// R2: raw text alone, LLM absent
{
  const rawTextOutcome = rawTextOutcomeFor("express ref van");
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome: { kind: "none" } });
  assert.equal(res.kind, "commit", "R2 kind");
  assert.equal(res.source, "commit_fast_path", "R2 source");
  assert.equal(res.option.delivery_type, "cooled_van_fast", "R2 option");
}

// R3: both agree
{
  const rawTextOutcome = rawTextOutcomeFor("express ref van");
  const llmOutcome = llmOutcomeFor({
    class: "cooled_van",
    tier: "fast",
    source_quote: "express ref van",
    confidence: "high",
  });
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "commit", "R3 kind");
  assert.equal(res.source, "commit_both_agree", "R3 source");
  assert.equal(res.option.delivery_type, "cooled_van_fast", "R3 option");
}

// R4: disagreement — different unique options
{
  // Raw text: "standard sedan" resolves to sedan_normal uniquely.
  // LLM claims cooled_van_fast (contradictory).
  const rawTextOutcome = rawTextOutcomeFor("standard sedan");
  const llmOutcome = llmOutcomeFor({
    class: "cooled_van",
    tier: "fast",
    source_quote: "standard sedan",
    confidence: "high",
  });
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "clarify", `R4 kind; got ${JSON.stringify(res)}`);
  assert.equal(res.source, "clarify_disagreement", "R4 source");
  assert.equal(res.fastPathCandidate.delivery_type, "sedan_normal", "R4 fast");
  assert.equal(res.llmCandidate.delivery_type, "cooled_van_fast", "R4 llm");
}

// R5: fast match + LLM ambiguous → clarify (conservative — LLM thinks the
// customer was ambiguous, so don't commit the regex's guess)
{
  const rawTextOutcome = rawTextOutcomeFor("standard sedan");
  const llmOutcome = llmOutcomeFor({
    class: "cooled_van",
    tier: null,
    source_quote: "standard sedan",
    confidence: "high",
  }); // ambiguous across cooled_van tiers
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "clarify", `R5 kind; got ${JSON.stringify(res)}`);
  assert.equal(res.source, "clarify_ambiguous", "R5 source");
  assert.equal(res.fastPathCandidate.delivery_type, "sedan_normal", "R5 fast preserved");
}

// R6: LLM low-confidence alone → none
{
  const rawTextOutcome = { kind: "none" };
  const llmOutcome = llmOutcomeFor({
    class: "cooled_van",
    tier: "fast",
    source_quote: "maybe",
    confidence: "low",
  }); // low-confidence returns { kind: "none" }
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "none", `R6 kind; got ${JSON.stringify(res)}`);
}

// R7: both underspecified
{
  const rawTextOutcome = rawTextOutcomeFor("express"); // tier-only
  const llmOutcome = llmOutcomeFor({
    class: null,
    tier: "fast",
    source_quote: "express",
    confidence: "high",
  });
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "none", `R7 kind; got ${JSON.stringify(res)}`);
}

// R8: fast match, LLM null (no op emitted)
{
  const rawTextOutcome = rawTextOutcomeFor("express ref van");
  const llmOutcome = { kind: "none" };
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "commit", "R8 kind");
  assert.equal(res.source, "commit_fast_path", "R8 source");
}

// R9: fast ambiguous + LLM ambiguous → clarify_ambiguous
{
  const rawTextOutcome = rawTextOutcomeFor("sedan"); // ambiguous sedan_normal vs sedan_fast
  const llmOutcome = llmOutcomeFor({
    class: "sedan",
    tier: null,
    source_quote: "sedan",
    confidence: "high",
  });
  const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome });
  assert.equal(res.kind, "clarify", "R9 kind");
  assert.equal(res.source, "clarify_ambiguous", "R9 source");
}

// ---------------------------------------------------------------------------
// B1: backward-compat sanity — resolver with llmOutcome={kind:"none"} is
// behaviorally identical to today's pre-dispatch matcher for the commit
// decision. Every combination where llm is absent should match raw-text
// alone.
// ---------------------------------------------------------------------------
{
  const cases = [
    { text: "express ref van", expectKind: "commit", expectSource: "commit_fast_path", expectType: "cooled_van_fast" },
    { text: "standard sedan", expectKind: "commit", expectSource: "commit_fast_path", expectType: "sedan_normal" },
    { text: "helper", expectKind: "commit", expectSource: "commit_fast_path", expectType: "helper_standard" },
    { text: "sedan", expectKind: "clarify", expectSource: "clarify_ambiguous" },
    { text: "express", expectKind: "none" },
    { text: "hello there", expectKind: "none" },
  ];
  for (const c of cases) {
    const rawTextOutcome = rawTextOutcomeFor(c.text);
    const res = resolveOptionFromProposals({ rawTextOutcome, llmOutcome: { kind: "none" } });
    assert.equal(res.kind, c.expectKind, `B1 kind for "${c.text}"`);
    if (c.expectSource) assert.equal(res.source, c.expectSource, `B1 source for "${c.text}"`);
    if (c.expectType) assert.equal(res.option.delivery_type, c.expectType, `B1 type for "${c.text}"`);
  }
}

console.log("smoke-test-option-interpretation-proposals: OK");
