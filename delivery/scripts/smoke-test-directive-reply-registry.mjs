#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 2 — directive-to-reply registry (2026-04-20).
//
// Product rule:
//   Collection-flow field asks are server-composed. On turns where the
//   directive is ASK_SENDER_* / ASK_RECIPIENT_* / ASK_PICKUP_ADDRESS /
//   ASK_DELIVERY_ADDRESS / CONFIRM_SLOT_CONFLICT, Region A of the
//   outbound decision substitutes the LLM's draft with a
//   server-rendered ask. The registry is compile-time exhaustive — every
//   `OneBrainNextRequiredAction.action` value must have an entry.
//
// Cases covered:
//   E1   Exhaustiveness: every action string the directive computer can
//        emit is present in `DIRECTIVE_REPLY_RENDERERS`.
//   E2   Every registry entry has a known `kind` (server /
//        server_existing / llm_owned).
//   C1-C6 Contract: each server-composed directive produces a reply
//         that (a) references the correct field, (b) is non-empty, (c)
//         differs by language.
//   V1   Variability: different turn seeds produce different phrasings
//         for the same directive state (when pool > 1).
//   V2   Determinism: same turn seed always produces the same phrasing.
//   W1-W4 Wiring: decidePreStateOutbound substitutes when the directive
//         is server-composed, and passes through when it is
//         llm_owned / server_existing / unknown.
//   W5   skipDirectiveDispatchForSameRouteSwitch: directive dispatch
//         defers to A4 when a switch_option is active.
//   B1   Backward-compat: with directiveAction=null, the outbound
//         decision behaves exactly as it did before Phase 2 (same as
//         passing renderDirectiveReply=undefined).
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function loadTs(relativePath) {
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const policy = loadTs("plugins/shared/conversation-policy.ts");
const registry = loadTs("plugins/octopus-channel/lib/directive-reply-registry.ts");
const outboundDecision = loadTs("plugins/octopus-channel/lib/outbound-decision.ts");

const {
  DIRECTIVE_REPLY_RENDERERS,
  renderDirectiveReply,
  isRegisteredDirectiveAction,
  directiveHasServerRenderer,
  pickPhrasingIndex,
} = registry;
const { decidePreStateOutbound } = outboundDecision;
const { createEmptyBookingDraft } = policy;

// ---------------------------------------------------------------------------
// E1: exhaustiveness — every action string emitted by the directive
// computer must appear in the registry. We grep the one-brain-context
// source for `action: "X"` literals and verify coverage.
// ---------------------------------------------------------------------------
{
  const src = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/lib/one-brain-context.ts"),
    "utf8",
  );
  const emittedActions = new Set();
  // Matches both object-literal form (`action: "X"`) and variable-
  // assignment form (`action = "X"`) so conditional branches that set
  // action before returning are caught too.
  const re = /\baction\s*[:=]\s*"([A-Z_]+)"/g;
  let m;
  while ((m = re.exec(src)) !== null) emittedActions.add(m[1]);
  const registered = new Set(Object.keys(DIRECTIVE_REPLY_RENDERERS));
  const missing = [...emittedActions].filter((a) => !registered.has(a));
  assert.deepEqual(
    missing,
    [],
    `E1: emitted actions missing from registry: ${missing.join(", ")}`,
  );
  // Also: the registry must not carry any action that is never emitted
  // (stale entries). If this fires, prune the registry.
  const orphans = [...registered].filter((a) => !emittedActions.has(a));
  assert.deepEqual(
    orphans,
    [],
    `E1: orphan registry entries (no emitting call site): ${orphans.join(", ")}`,
  );
}

// ---------------------------------------------------------------------------
// E2: every registry entry has a known `kind`.
// ---------------------------------------------------------------------------
{
  const valid = new Set(["server", "server_existing", "llm_owned"]);
  for (const [action, spec] of Object.entries(DIRECTIVE_REPLY_RENDERERS)) {
    assert.ok(
      valid.has(spec.kind),
      `E2: ${action} has unknown kind=${spec.kind}`,
    );
    if (spec.kind === "server") {
      assert.equal(typeof spec.render, "function", `E2: ${action} missing render`);
    } else if (spec.kind === "server_existing") {
      assert.equal(typeof spec.via, "string", `E2: ${action} missing via`);
    } else if (spec.kind === "llm_owned") {
      assert.equal(
        typeof spec.rationale,
        "string",
        `E2: ${action} missing rationale`,
      );
    }
  }
}

// ---------------------------------------------------------------------------
// C1-C6: contract — server-rendered asks produce grounded text in each
// language and reference the correct field.
// ---------------------------------------------------------------------------

function baseCtx({
  language = "en",
  draftOverrides = {},
  entryOverrides = {},
  conflictingSlot = null,
  conflictValues = null,
  turnSeed = "t1::conv1",
} = {}) {
  const draft = { ...createEmptyBookingDraft(), ...draftOverrides };
  const entry = {
    stage: "collecting_booking_details",
    bookingStep: "sender",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
    ...entryOverrides,
  };
  return {
    language,
    draft,
    entry,
    route: null,
    conflictingSlot,
    conflictValues,
    turnSeed,
  };
}

// C1: ASK_SENDER_NAME_AND_PHONE_DECISION — references "sender" + phone
{
  for (const language of ["en", "ar"]) {
    const ctx = baseCtx({ language });
    const res = renderDirectiveReply("ASK_SENDER_NAME_AND_PHONE_DECISION", ctx);
    assert.equal(res.kind, "render", `C1 ${language} kind`);
    assert.ok(res.text.length > 0, `C1 ${language} nonempty`);
    if (language === "en") {
      assert.ok(/sender/i.test(res.text), `C1 en sender: ${res.text}`);
      assert.ok(/phone|number|whatsapp/i.test(res.text), `C1 en phone: ${res.text}`);
    } else {
      assert.ok(/مرسل/.test(res.text), `C1 ar sender: ${res.text}`);
      assert.ok(/رقم/.test(res.text), `C1 ar phone: ${res.text}`);
    }
  }
}

// C2: ASK_SENDER_PHONE — references sender phone + name when known
{
  const ctx = baseCtx({ draftOverrides: { senderName: "Aziz" } });
  const res = renderDirectiveReply("ASK_SENDER_PHONE", ctx);
  assert.equal(res.kind, "render", "C2 kind");
  assert.ok(/Aziz/.test(res.text), `C2: references name; got ${res.text}`);
  assert.ok(/phone|number/i.test(res.text), `C2: asks phone; got ${res.text}`);
}

// C3: ASK_RECIPIENT_NAME_AND_PHONE — references recipient
{
  for (const language of ["en", "ar"]) {
    const ctx = baseCtx({ language });
    const res = renderDirectiveReply("ASK_RECIPIENT_NAME_AND_PHONE", ctx);
    assert.equal(res.kind, "render", `C3 ${language} kind`);
    if (language === "en") {
      assert.ok(/recipient/i.test(res.text), `C3 en: ${res.text}`);
    } else {
      assert.ok(/مستلم/.test(res.text), `C3 ar: ${res.text}`);
    }
  }
}

// C4: ASK_PICKUP_ADDRESS — names pickup + area
{
  const ctx = baseCtx({ language: "en" });
  const res = renderDirectiveReply("ASK_PICKUP_ADDRESS", ctx);
  assert.equal(res.kind, "render", "C4 kind");
  assert.ok(/pickup/i.test(res.text), `C4 pickup: ${res.text}`);
  assert.ok(/Hawalli/.test(res.text), `C4 area: ${res.text}`);
  assert.ok(/block|street|building|apartment/i.test(res.text), `C4 parts: ${res.text}`);
}

// C5: ASK_DELIVERY_ADDRESS — names delivery + area (AR variant)
{
  const ctx = baseCtx({ language: "ar" });
  const res = renderDirectiveReply("ASK_DELIVERY_ADDRESS", ctx);
  assert.equal(res.kind, "render", "C5 kind");
  assert.ok(/التوصيل/.test(res.text), `C5 delivery AR: ${res.text}`);
  assert.ok(/السالمية/.test(res.text), `C5 area AR: ${res.text}`);
}

// C6: CONFIRM_SLOT_CONFLICT — names the slot + both values
{
  const ctx = baseCtx({
    language: "en",
    conflictingSlot: "pickup_extra",
    conflictValues: {
      existing: "Apartment 12, floor 3",
      incoming: "apt 12 floor 3",
    },
  });
  const res = renderDirectiveReply("CONFIRM_SLOT_CONFLICT", ctx);
  assert.equal(res.kind, "render", "C6 kind");
  assert.ok(/pickup extra/i.test(res.text), `C6 slot: ${res.text}`);
  assert.ok(res.text.includes("Apartment 12, floor 3"), `C6 existing: ${res.text}`);
  assert.ok(res.text.includes("apt 12 floor 3"), `C6 incoming: ${res.text}`);
}

// ---------------------------------------------------------------------------
// V1: Variability — different seeds yield at least one pair that differs.
// Over the 5 server-rendered directives with phrasing pools of size ≥ 2,
// there must exist a pair of seeds that produces a different string.
// ---------------------------------------------------------------------------
{
  const actions = [
    "ASK_SENDER_NAME_AND_PHONE_DECISION",
    "ASK_SENDER_PHONE",
    "ASK_RECIPIENT_NAME_AND_PHONE",
    "ASK_PICKUP_ADDRESS",
    "ASK_DELIVERY_ADDRESS",
  ];
  for (const action of actions) {
    const outputs = new Set();
    for (let i = 0; i < 12; i++) {
      const ctx = baseCtx({
        draftOverrides: { senderName: "Aziz" },
        turnSeed: `seed-${i}`,
      });
      const res = renderDirectiveReply(action, ctx);
      outputs.add(res.text);
    }
    assert.ok(
      outputs.size >= 2,
      `V1: ${action} should vary across seeds; got ${outputs.size} unique outputs`,
    );
  }
}

// V2: Determinism — same seed yields same text every call, same hash
// pick too. pickPhrasingIndex is a pure function of seed + count.
{
  const ctx = baseCtx({ language: "en", turnSeed: "fixed-seed" });
  const a = renderDirectiveReply("ASK_PICKUP_ADDRESS", ctx);
  const b = renderDirectiveReply("ASK_PICKUP_ADDRESS", ctx);
  assert.equal(a.text, b.text, "V2: deterministic for same seed");
  assert.equal(
    pickPhrasingIndex("fixed-seed", 3),
    pickPhrasingIndex("fixed-seed", 3),
    "V2b: pickPhrasingIndex stable for identical seeds",
  );
  // Empty seed is deterministic and in-range; exact index depends on the
  // hash. We just care that it doesn't throw and stays bounded.
  const emptyIdx = pickPhrasingIndex("", 5);
  assert.ok(emptyIdx >= 0 && emptyIdx < 5, `V2c: empty seed in-range; got ${emptyIdx}`);
  assert.equal(pickPhrasingIndex("anything", 1), 0, "V2d: count=1 always 0");
  assert.equal(pickPhrasingIndex("anything", 0), 0, "V2e: count=0 defensive 0");
}

// ---------------------------------------------------------------------------
// W1-W5: decidePreStateOutbound wiring
// ---------------------------------------------------------------------------

const noopBuilders = {
  buildDeterministicSelectedQuotedOptionReply: ({ language }) =>
    language === "ar" ? "خيار موثق" : "Selected",
  buildDeterministicGraceWindowReply: (l) =>
    l === "ar" ? "نافذة سماح" : "Grace",
  buildProviderIssueFallbackReply: (l) =>
    l === "ar" ? "خلل فني" : "Technical issue",
};

function preInput(overrides = {}) {
  return {
    replyText: "Sure, sending you to the next step.",
    preferredLanguage: "en",
    sessionGuard: null,
    sessionIsRecent: false,
    preferredCanonicalText: null,
    guardToolAgeMs: Number.POSITIVE_INFINITY,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: () => [],
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: "collecting_booking_details",
    directiveAction: null,
    directiveRenderContext: null,
    renderDirectiveReply,
    ...overrides,
  };
}

// W1: directive present + server renderer → substituted
{
  const ctx = baseCtx({ draftOverrides: { senderName: "Aziz" } });
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Sure, I'll continue.",
      directiveAction: "ASK_SENDER_PHONE",
      directiveRenderContext: ctx,
    }),
  );
  assert.equal(res.decision, "replace_authoritative", "W1 decision");
  assert.equal(res.reason, "replace_directive_ask", "W1 reason");
  assert.ok(/phone|number/i.test(res.replyText), `W1 substituted text: ${res.replyText}`);
}

// W2: directive is server_existing → not substituted here (delegated)
{
  const ctx = baseCtx();
  const res = decidePreStateOutbound(
    preInput({
      replyText: "LLM drafted text survives",
      directiveAction: "ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM",
      directiveRenderContext: ctx,
    }),
  );
  // No manualConfirmAddressAsk flag set, so the dedicated branch also
  // doesn't fire. LLM reply should pass through via the `existing` no-op
  // fallthrough.
  assert.equal(res.decision, "allow", "W2 decision");
  assert.equal(res.replyText, "LLM drafted text survives", "W2 passthrough");
}

// W3: directive is llm_owned → not substituted, LLM draft preserved
{
  const ctx = baseCtx();
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Your order is on its way; track: https://...",
      directiveAction: "POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF",
      directiveRenderContext: ctx,
    }),
  );
  assert.equal(res.decision, "allow", "W3 decision");
  assert.equal(res.reason, "allow", "W3 reason");
}

// W4: directive is unknown string → passthrough
{
  const ctx = baseCtx();
  const res = decidePreStateOutbound(
    preInput({
      replyText: "LLM draft",
      directiveAction: "MADE_UP_DIRECTIVE_NAME",
      directiveRenderContext: ctx,
    }),
  );
  assert.equal(res.decision, "allow", "W4 decision");
  assert.equal(res.replyText, "LLM draft", "W4 passthrough");
}

// W5: switch_option active → directive dispatch SKIPPED so A4 owns the
// post-switch recap/ask composition.
{
  const ctx = baseCtx({ draftOverrides: { senderName: "Aziz" } });
  // Manufacture a minimal switch_option to flip the guard.
  const sameRouteQuoteAction = {
    kind: "switch_option",
    option: {
      delivery_type: "cooled_van_fast",
      label_en: "Express refrigerated van",
      label_ar: "سيارة مبردة سريع",
      quoted_price: 2.25,
      formatted_price: "2.250 KWD",
      visibility: "visible",
      direct_chat_booking_status: "manual_confirmation_required",
      direct_chat_booking_note: null,
    },
  };
  const activeQuotedRoute = {
    routeKey: "hawalli__salmiya",
    pickupAreaNameEn: "Hawalli",
    pickupAreaNameAr: "حولي",
    dropoffAreaNameEn: "Salmiya",
    dropoffAreaNameAr: "السالمية",
    pricesByType: { cooled_van_fast: 2.25 },
    optionCatalog: [sameRouteQuoteAction.option],
    serviceDiscovery: null,
  };
  // Reply contains a WRONG price (0.999) — A4's missingExpectedPrice
  // check fires because the expected 2.250 isn't present. That substitutes
  // with the deterministic selected-option reply and is tagged
  // replace_price_mismatch.
  const res = decidePreStateOutbound(
    preInput({
      replyText: "The price is 0.999 KWD and we'll proceed.",
      directiveAction: "ASK_SENDER_PHONE",
      directiveRenderContext: ctx,
      sameRouteQuoteAction,
      activeQuotedRoute,
      extractPricesFromText: (text) => {
        const out = [];
        const re = /\b(\d+\.\d{3})\b/g;
        let m;
        while ((m = re.exec(text)) !== null) out.push(m[1]);
        return out;
      },
    }),
  );
  assert.notEqual(
    res.reason,
    "replace_directive_ask",
    `W5: directive dispatch must defer to A4 on switch_option; got ${res.reason}`,
  );
  assert.equal(res.reason, "replace_price_mismatch", `W5 A4 owns recap; got ${res.reason}`);
}

// ---------------------------------------------------------------------------
// B1: backward-compat — with directiveAction=null, outbound-decision
// behaves identically to pre-Phase-2.
// ---------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(
    preInput({
      replyText: "Healthy LLM reply that should survive",
      directiveAction: null,
      directiveRenderContext: null,
    }),
  );
  assert.equal(res.decision, "allow", "B1 decision");
  assert.equal(res.reason, "allow", "B1 reason");
  assert.equal(res.replyText, "Healthy LLM reply that should survive");
}

// Additionally: if the caller omits the directive fields entirely, the
// decision must still work (no runtime errors).
{
  const input = preInput({});
  delete input.directiveAction;
  delete input.directiveRenderContext;
  delete input.renderDirectiveReply;
  const res = decidePreStateOutbound(input);
  assert.equal(res.decision, "allow", "B1b decision");
}

// ---------------------------------------------------------------------------
// isRegisteredDirectiveAction / directiveHasServerRenderer — sanity
// ---------------------------------------------------------------------------
{
  assert.ok(isRegisteredDirectiveAction("ASK_PICKUP_ADDRESS"));
  assert.ok(!isRegisteredDirectiveAction("SOMETHING_ELSE"));
  assert.ok(directiveHasServerRenderer("ASK_PICKUP_ADDRESS"));
  assert.ok(!directiveHasServerRenderer("POST_ORDER_ONLY_TRACK_CANCEL_RECREATE_OR_HANDOFF"));
  assert.ok(!directiveHasServerRenderer("ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM"));
  assert.ok(!directiveHasServerRenderer("MADE_UP"));
}

console.log("smoke-test-directive-reply-registry: OK");
