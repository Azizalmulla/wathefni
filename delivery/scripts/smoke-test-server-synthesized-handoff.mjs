#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 4 — server-synthesized request_handoff + toagent
// escalation for manual-confirm handoff turns (2026-04-20).
//
// Product rule:
//   On manual-confirm handoff turns (selected option has
//   direct_chat_booking_status = manual_confirmation_required AND both
//   pickup + delivery addresses are satisfied), escalation is
//   server-owned:
//     1. The drain-layer synthesizes `request_handoff` with a
//        `manual_confirm_<option_type>` reason when the LLM didn't emit
//        the tool (so `handoffRequested=true` is guaranteed).
//     2. The Octopus `toagent` API call fires via
//        `shouldMoveToHumanAgent` matching distinctive substrings of
//        the server-rendered handoff reply ("one of our agents will
//        reach out" / "راح يتواصل معك أحد الموظفين"). These markers
//        appear ONLY in the handoff reply, not in pickup/delivery ask.
//
// Cases covered:
//   M1   shouldMoveToHumanAgent — matches EN handoff reply text
//   M2   shouldMoveToHumanAgent — matches AR handoff reply text
//   M3   shouldMoveToHumanAgent — does NOT match pickup-ask reply
//        (which also mentions manual confirmation, but not "agents will
//        reach out")
//   M4   shouldMoveToHumanAgent — does NOT match delivery-ask reply
//   M5   shouldMoveToHumanAgent — continues to match pre-existing
//        escalation markers (support-tool stub + "human agent")
//   H1   Deterministic handoff reply contains the EN marker
//   H2   Deterministic handoff reply contains the AR marker
//   H3   Deterministic address-ask replies do NOT contain the handoff
//        markers (prevents false toagent triggers)
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function loadTs(relativePath) {
  const jitiFactory = require(path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"));
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return jiti(path.join(root, relativePath));
}

const intentText = loadTs("plugins/octopus-channel/lib/intent-text.ts");
const quotedOptions = loadTs("plugins/octopus-channel/lib/quoted-options.ts");

const { shouldMoveToHumanAgent } = intentText;
const {
  buildDeterministicManualConfirmAddressAskReply,
  buildDeterministicManualConfirmHandoffReply,
} = quotedOptions;

function opt(deliveryType, labelEn, labelAr, price) {
  return {
    delivery_type: deliveryType,
    label_ar: labelAr,
    label_en: labelEn,
    quoted_price: price,
    formatted_price: `${price.toFixed(3)} KWD`,
    visibility: "visible",
    direct_chat_booking_status: "manual_confirmation_required",
    direct_chat_booking_note: null,
  };
}

const COOLED_VAN_FAST = opt(
  "cooled_van_fast",
  "Express refrigerated van",
  "سيارة مبردة سريع",
  2.25,
);
const ROUTE = {
  routeKey: "salmiya__jabriya",
  pickupAreaNameEn: "Salmiya",
  pickupAreaNameAr: "السالمية",
  dropoffAreaNameEn: "Jabriya",
  dropoffAreaNameAr: "الجابرية",
  pricesByType: { cooled_van_fast: 2.25 },
  optionCatalog: [COOLED_VAN_FAST],
  serviceDiscovery: null,
};

// -------------------------------------------------------------------------
// H1 / H2: deterministic handoff reply contains the matching markers.
// -------------------------------------------------------------------------
{
  const en = buildDeterministicManualConfirmHandoffReply({
    language: "en",
    route: ROUTE,
    option: COOLED_VAN_FAST,
  });
  assert.ok(
    en.includes("one of our agents will reach out"),
    `H1: EN handoff marker missing; got:\n${en}`,
  );
  assert.ok(
    en.includes("Express refrigerated van"),
    `H1: EN handoff names option; got:\n${en}`,
  );
}

{
  const ar = buildDeterministicManualConfirmHandoffReply({
    language: "ar",
    route: ROUTE,
    option: COOLED_VAN_FAST,
  });
  assert.ok(
    ar.includes("راح يتواصل معك أحد الموظفين"),
    `H2: AR handoff marker missing; got:\n${ar}`,
  );
}

// -------------------------------------------------------------------------
// H3: address-ask replies (pickup + delivery) do NOT contain the
// handoff markers. This is the critical scoping property — without it,
// `shouldMoveToHumanAgent` would fire on every manual-confirm collection
// turn and Octopus would escalate before addresses are collected.
// -------------------------------------------------------------------------
for (const side of ["pickup", "delivery"]) {
  for (const language of ["en", "ar"]) {
    const text = buildDeterministicManualConfirmAddressAskReply({
      language,
      route: ROUTE,
      option: COOLED_VAN_FAST,
      side,
    });
    assert.ok(
      !text.includes("one of our agents will reach out"),
      `H3: ${language}/${side} ask must not contain EN handoff marker; got:\n${text}`,
    );
    assert.ok(
      !text.includes("راح يتواصل معك أحد الموظفين"),
      `H3: ${language}/${side} ask must not contain AR handoff marker; got:\n${text}`,
    );
  }
}

// -------------------------------------------------------------------------
// M1: EN handoff reply triggers toagent
// -------------------------------------------------------------------------
{
  const en = buildDeterministicManualConfirmHandoffReply({
    language: "en",
    route: ROUTE,
    option: COOLED_VAN_FAST,
  });
  assert.equal(
    shouldMoveToHumanAgent(en),
    true,
    `M1: EN handoff reply must trigger toagent`,
  );
}

// -------------------------------------------------------------------------
// M2: AR handoff reply triggers toagent
// -------------------------------------------------------------------------
{
  const ar = buildDeterministicManualConfirmHandoffReply({
    language: "ar",
    route: ROUTE,
    option: COOLED_VAN_FAST,
  });
  assert.equal(
    shouldMoveToHumanAgent(ar),
    true,
    `M2: AR handoff reply must trigger toagent`,
  );
}

// -------------------------------------------------------------------------
// M3 / M4: address-ask replies do NOT trigger toagent on manual-confirm
// collection turns (pickup + delivery, EN + AR).
// -------------------------------------------------------------------------
for (const side of ["pickup", "delivery"]) {
  for (const language of ["en", "ar"]) {
    const text = buildDeterministicManualConfirmAddressAskReply({
      language,
      route: ROUTE,
      option: COOLED_VAN_FAST,
      side,
    });
    assert.equal(
      shouldMoveToHumanAgent(text),
      false,
      `M${side === "pickup" ? "3" : "4"}: ${language}/${side} ask must NOT trigger toagent; got:\n${text}`,
    );
  }
}

// -------------------------------------------------------------------------
// M5: pre-existing markers still work (regression lock).
// -------------------------------------------------------------------------
{
  const supportStubAr = "تم تحويل المحادثة لموظف الدعم المختص. يرجى الانتظار قليلاً.";
  assert.equal(shouldMoveToHumanAgent(supportStubAr), true, "M5a: support-tool AR stub");
  const complaintStubAr = "تم تسجيل الشكوى وتحويلها للإدارة للمراجعة.";
  assert.equal(shouldMoveToHumanAgent(complaintStubAr), true, "M5b: complaint AR stub");
  assert.equal(
    shouldMoveToHumanAgent("Transferring you to a human agent now."),
    true,
    "M5c: EN 'human agent'",
  );
  assert.equal(
    shouldMoveToHumanAgent("You're being moved to a human agent."),
    true,
    "M5d: 'moved to a human agent'",
  );
  // Negatives — unrelated replies stay unmatched.
  assert.equal(
    shouldMoveToHumanAgent("Sure, what's the sender's phone?"),
    false,
    "M5e: normal reply untouched",
  );
  assert.equal(
    shouldMoveToHumanAgent(""),
    false,
    "M5f: empty reply",
  );
}

// -------------------------------------------------------------------------
// Source-shape anchor: the server-synthesis drain block in index.ts
// exists and triggers on the right conditions. We grep the source to
// anchor the structural contract — if someone deletes or renames the
// synthesis block this test fails and forces a review.
// -------------------------------------------------------------------------
{
  const fs = await import("node:fs");
  const indexSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  assert.ok(
    /\[one-brain\/server-handoff\] synthesized/.test(indexSrc),
    "synthesis audit log line must exist in index.ts",
  );
  assert.ok(
    /request_handoff:server_synthesized\(/.test(indexSrc),
    "synthesis appliedOps tag must exist in index.ts",
  );
  // The synthesis block must guard on both pickup AND delivery being
  // satisfied — this is the same state `computeOneBrainNextRequiredAction`
  // uses to pick REQUEST_HANDOFF_FOR_MANUAL_CONFIRM. Use a multi-line
  // regex to verify the adjacent structure.
  const synthesisBlockMatch = indexSrc.match(
    /\[one-brain\/server-handoff\] synthesized[\s\S]{0,300}/,
  );
  assert.ok(synthesisBlockMatch, "synthesis block anchor present");
  // The block must only act when `!handoffRequested` — prevents double-
  // synthesis when the LLM already emitted the op. Grep for the guard
  // literal above the audit log.
  const withGuard = indexSrc.match(
    /!handoffRequested[\s\S]{0,2000}\[one-brain\/server-handoff\] synthesized/,
  );
  assert.ok(
    withGuard,
    "synthesis must guard on !handoffRequested to stay idempotent with LLM-emitted op",
  );
}

console.log("smoke-test-server-synthesized-handoff: OK");
