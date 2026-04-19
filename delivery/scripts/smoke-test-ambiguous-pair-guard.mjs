#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: ambiguous unlabeled name+phone pair guard.
//
// Anchors the policy added 2026-04-19 after the incident where the LLM
// silently attributed "Aziz almulla 99338566" to the recipient even
// though the sender was still unresolved. The server-side guard lives
// in `plugins/shared/ambiguous-pair-guard.ts` and is consumed by the
// drain in `plugins/octopus-channel/index.ts`.
//
// The rule (state-derived, not phrasing-derived):
//   IF op writes recipient_name or recipient_phone
//   AND source_quote looks like a single unlabeled name+phone pair
//   AND sender is still unresolved in the draft
//   AND the op does NOT also write a sender field
//   THEN reject the recipient write and steer the next turn back to
//        ASK_SENDER_NAME_AND_PHONE_DECISION.
//
// Also verifies the SKILL.md + next_required_action companion anchors:
//   - SKILL.md forbids bundling recipient ask into the sender step.
//   - `computeOneBrainNextRequiredAction` adds `ask_recipient_with_sender`
//     to `forbiddenShapes` at the sender step.
// ---------------------------------------------------------------------------

import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

async function loadTsModule(relativePath) {
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const {
  evaluateAmbiguousPair,
  looksLikeSingleUnlabeledPair,
} = await loadTsModule("plugins/shared/ambiguous-pair-guard.ts");

const { computeOneBrainNextRequiredAction } = await loadTsModule(
  "plugins/octopus-channel/lib/one-brain-context.ts",
);
const { createEmptyBookingDraft } = await loadTsModule(
  "plugins/shared/conversation-policy.ts",
);

// ---------------------------------------------------------------------------
// (1) looksLikeSingleUnlabeledPair unit cases
// ---------------------------------------------------------------------------

// Positive: bare name + phone, no labels.
assert.equal(
  looksLikeSingleUnlabeledPair("Aziz almulla 99338566"),
  true,
  "P1: bare name + phone = ambiguous pair",
);
assert.equal(
  looksLikeSingleUnlabeledPair("99338566 Aziz almulla"),
  true,
  "P2: phone + name (order flipped) = ambiguous pair",
);
assert.equal(
  looksLikeSingleUnlabeledPair("أحمد 99338566"),
  true,
  "P3: Arabic-script name + phone = ambiguous pair",
);

// Negative: explicit role labels kill the ambiguity claim.
assert.equal(
  looksLikeSingleUnlabeledPair("sender Aziz 99338566"),
  false,
  "N1: explicit 'sender' label disambiguates",
);
assert.equal(
  looksLikeSingleUnlabeledPair("recipient Aziz 99338566"),
  false,
  "N2: explicit 'recipient' label disambiguates",
);
assert.equal(
  looksLikeSingleUnlabeledPair("to Aziz 99338566"),
  false,
  "N3: 'to' preposition disambiguates",
);
assert.equal(
  looksLikeSingleUnlabeledPair("from Aziz 99338566"),
  false,
  "N4: 'from' preposition disambiguates",
);
assert.equal(
  looksLikeSingleUnlabeledPair("المرسل أحمد 99338566"),
  false,
  "N5: Arabic 'المرسل' label disambiguates",
);
assert.equal(
  looksLikeSingleUnlabeledPair("المستلم أحمد 99338566"),
  false,
  "N6: Arabic 'المستلم' label disambiguates",
);

// Negative: missing one of the required pieces.
assert.equal(
  looksLikeSingleUnlabeledPair("99338566"),
  false,
  "N7: pure phone (no letters) not a pair",
);
assert.equal(
  looksLikeSingleUnlabeledPair("Aziz almulla"),
  false,
  "N8: pure name (no phone) not a pair",
);
assert.equal(
  looksLikeSingleUnlabeledPair("Aziz 99338566 and Ahmad 62844738"),
  false,
  "N9: two distinct pairs not ambiguous (labeled by count)",
);
assert.equal(
  looksLikeSingleUnlabeledPair(""),
  false,
  "N10: empty string",
);
assert.equal(
  looksLikeSingleUnlabeledPair(null),
  false,
  "N11: null input safe",
);

// ---------------------------------------------------------------------------
// (2) evaluateAmbiguousPair integration
// ---------------------------------------------------------------------------

// The canonical incident shape. MUST reject.
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      recipient_name: "Aziz almulla",
      recipient_phone: "99338566",
      source_quote: "Aziz almulla 99338566",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "reject_recipient_write", "R1: incident case must reject");
  assert.equal(res.reason, "ambiguous_unlabeled_pair_with_sender_unresolved");
  assert.deepEqual(
    [...res.dropFields].sort(),
    ["recipient_name", "recipient_phone"],
    "R1: both recipient fields dropped",
  );
  assert.equal(res.requestedSlot, "sender_name", "R1: next-turn slot steered to sender");
  assert.equal(res.rejections.length, 2, "R1: one rejection per dropped field");
}

// Sender already resolved → allow.
{
  const d = createEmptyBookingDraft();
  d.senderName = "Ali";
  d.senderPhone = "96512345678";
  const res = evaluateAmbiguousPair({
    op: {
      recipient_name: "Aziz almulla",
      recipient_phone: "99338566",
      source_quote: "Aziz almulla 99338566",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: null,
      recipientPhone: null,
    },
  });
  assert.equal(res.action, "allow", "A1: sender resolved → allow");
  assert.equal(res.reason, "sender_already_resolved");
}

// Op also writes a sender field → allow (LLM explicitly labeled both).
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      sender_name: "Ali",
      sender_phone: "96512345678",
      recipient_name: "Aziz almulla",
      recipient_phone: "99338566",
      source_quote: "sender Ali 96512345678, recipient Aziz almulla 99338566",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "allow", "A2: op disambiguates both parties");
  assert.equal(res.reason, "op_also_writes_sender");
}

// Op with phone_decision also counts as sender-touching.
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      phone_decision: "use_whatsapp",
      recipient_name: "Aziz",
      recipient_phone: "99338566",
      source_quote: "use whatsapp, and send to Aziz 99338566",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "allow", "A3: phone_decision signal counts as sender-touching");
  assert.equal(res.reason, "op_also_writes_sender");
}

// Op writes only recipient, but source_quote has an explicit "to" label
// → allow (labeled, not ambiguous).
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      recipient_name: "Aziz",
      recipient_phone: "99338566",
      source_quote: "send to Aziz 99338566",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "allow", "A4: labeled source_quote → allow");
  assert.equal(res.reason, "source_quote_not_single_pair");
}

// No source_quote → default to allow (guard is narrow; source_quote is
// required for the fire condition).
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      recipient_name: "Aziz",
      recipient_phone: "99338566",
      source_quote: null,
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "allow", "A5: missing source_quote → allow");
  assert.equal(res.reason, "no_source_quote");
}

// Op writes only address → irrelevant to this guard.
{
  const d = createEmptyBookingDraft();
  const res = evaluateAmbiguousPair({
    op: {
      source_quote: "block 6, street 9, house 17",
    },
    draft: {
      senderName: d.senderName,
      senderPhone: d.senderPhone,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
    },
  });
  assert.equal(res.action, "allow", "A6: address-only op not touched");
  assert.equal(res.reason, "no_recipient_write");
}

// ---------------------------------------------------------------------------
// (3) next_required_action companion anchor
// ---------------------------------------------------------------------------

// At the sender step, forbiddenShapes MUST include `ask_recipient_with_sender`.
{
  const draft = createEmptyBookingDraft();
  const entry = {
    stage: "quoted",
    bookingStep: "collecting_booking_details",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  };
  const missing = [
    "sender.name",
    "sender.phone",
    "recipient.name",
    "recipient.phone",
    "pickup.address",
    "delivery.address",
  ];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert.ok(directive, "S1: directive must fire at sender step");
  assert.equal(
    directive.action,
    "ASK_SENDER_NAME_AND_PHONE_DECISION",
    "S1: sender step action",
  );
  assert.ok(
    directive.forbiddenShapes.includes("ask_recipient_with_sender"),
    "S1: forbiddenShapes must include ask_recipient_with_sender at sender step",
  );
}

// At the recipient step (sender done), `ask_recipient_with_sender` must NOT be
// present — the step now allows asking for the recipient.
{
  const draft = createEmptyBookingDraft();
  draft.senderName = "Ali";
  draft.senderPhone = "96512345678";
  const entry = {
    stage: "quoted",
    bookingStep: "collecting_booking_details",
    bookingDraft: draft,
    quotePickupAreaNameEn: "Hawalli",
    quotePickupAreaNameAr: "حولي",
    quoteDropoffAreaNameEn: "Salmiya",
    quoteDropoffAreaNameAr: "السالمية",
    selectedDeliveryType: "sedan_normal",
    quotedPrice: 1.25,
  };
  const missing = [
    "recipient.name",
    "recipient.phone",
    "pickup.address",
    "delivery.address",
  ];
  const directive = computeOneBrainNextRequiredAction({ draft, entry, missing });
  assert.ok(directive, "S2: directive must fire at recipient step");
  assert.equal(
    directive.action,
    "ASK_RECIPIENT_NAME_AND_PHONE",
    "S2: recipient step action",
  );
  assert.ok(
    !directive.forbiddenShapes.includes("ask_recipient_with_sender"),
    "S2: ask_recipient_with_sender must NOT be present at recipient step",
  );
}

// ---------------------------------------------------------------------------
// (4) SKILL.md anchor — rule text present
// ---------------------------------------------------------------------------

const skillSrc = fs.readFileSync(
  path.join(root, "workspaces/riders/SKILL.md"),
  "utf8",
);
assert.ok(
  /ask_recipient_with_sender/.test(skillSrc),
  "SKILL.md must define ask_recipient_with_sender",
);
assert.ok(
  /sender and recipient are collected sequentially/i.test(skillSrc) ||
    /do not ask for the recipient in the same message/i.test(skillSrc),
  "SKILL.md must state the sequential sender-then-recipient rule",
);

console.log("ALL PASS smoke-test-ambiguous-pair-guard.mjs");
