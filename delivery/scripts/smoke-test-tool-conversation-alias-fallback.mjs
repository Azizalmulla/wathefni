#!/usr/bin/env node

import { strict as assert } from "node:assert";

const mod = await import("../plugins/riders-tools/lib/tool-conversation-ids.ts");
const {
  resolveToolConversationId,
  resolveToolConversationAliases,
  resolveToolTurnId,
} = mod;

assert.equal(
  typeof resolveToolConversationId,
  "function",
  "T0: resolveToolConversationId must be exported for regression coverage.",
);
assert.equal(
  typeof resolveToolConversationAliases,
  "function",
  "T0b: resolveToolConversationAliases must be exported for regression coverage.",
);
assert.equal(
  typeof resolveToolTurnId,
  "function",
  "T0c: resolveToolTurnId must be exported for regression coverage.",
);

// Class-11 / blocker regression:
// the pricing tool's clarify-turn ctx may lack ConversationId / SessionKey /
// To, yet still carry responder-op-routable identities via ControllerStateKey
// or replyTarget-like fields. If alias collection ignores those, the
// clarification state is never persisted and the next turn falls through to
// mixed-up recovery.

const controllerOnlyCtx = {
  ControllerStateKey: "default::19103",
};
assert.equal(
  resolveToolConversationId(controllerOnlyCtx),
  "19103",
  "T1: controllerStateKey must recover the bare conversation id.",
);
assert.deepEqual(
  resolveToolConversationAliases(controllerOnlyCtx),
  ["default::19103", "19103"],
  "T2: aliases must include both controllerStateKey and extracted conversation id.",
);

const replyTargetOnlyCtx = {
  replyTarget: "96599338566",
};
assert.equal(
  resolveToolConversationId(replyTargetOnlyCtx),
  "",
  "T3: replyTarget is an alias fallback, not the authoritative conversation id.",
);
assert.deepEqual(
  resolveToolConversationAliases(replyTargetOnlyCtx),
  ["96599338566"],
  "T4: replyTarget-only ctx must still produce a responder-op alias.",
);

const whatsappOnlyCtx = {
  current_customer_whatsapp: "96599338566",
};
assert.deepEqual(
  resolveToolConversationAliases(whatsappOnlyCtx),
  ["96599338566"],
  "T5: current_customer_whatsapp must act as a responder-op alias fallback.",
);

const sessionKeyCtx = {
  SessionKey: "agent:riders:octopus:direct:19103::prompt=f5e8a85dd957",
};
assert.equal(
  resolveToolConversationId(sessionKeyCtx),
  "19103",
  "T6: SessionKey parsing must keep working.",
);
assert.ok(
  resolveToolConversationAliases(sessionKeyCtx).includes("19103"),
  "T7: aliases must still include the conversation id extracted from SessionKey.",
);

const octopusToCtx = {
  To: "octopus:96599338566",
};
assert.equal(
  resolveToolConversationId(octopusToCtx),
  "96599338566",
  "T8: To=octopus:<replyTarget> fallback must remain intact.",
);
assert.ok(
  resolveToolConversationAliases(octopusToCtx).includes("96599338566"),
  "T9: aliases must still include the octopus replyTarget suffix.",
);

const explicitTurnCtx = { MessageId: "wamid.123" };
assert.equal(
  resolveToolTurnId(explicitTurnCtx),
  "wamid.123",
  "T10: turn-id fallback should remain stable.",
);

// Class-11 regression (2026-04-21):
// stripped_tool_ctx_loses_conversation_identity.
//
// On conv 19127 turn 1, pricing.ts logged `aliases=[]` with EVERY identity
// field null because openclaw's tool runtime hands `tool.execute(...)` a
// stripped ctx. The fix publishes the current turn's identity on a
// globalThis stash at Octopus ingress and the resolvers fall back to it.
//
// These assertions prove the fallback fires on an entirely empty ctx, and
// does NOT override a ctx that already carries a real id (to keep
// cross-conversation contamination impossible under interleaved load).

const { setCurrentTurnIdentity, clearCurrentTurnIdentity, peekCurrentTurnIdentity } = mod;

clearCurrentTurnIdentity();

const strippedCtx = {
  Body: "bnaid al gar",
  Provider: "octopus",
  Surface: "octopus",
};

assert.equal(
  resolveToolConversationId(strippedCtx),
  "",
  "T11a: with no ctx identity and no stash, primary id must be empty.",
);
assert.deepEqual(
  resolveToolConversationAliases(strippedCtx),
  [],
  "T11b: with no ctx identity and no stash, aliases must be empty.",
);

setCurrentTurnIdentity({
  conversationId: "19127",
  sessionKey: "agent:riders:octopus:direct:19127::prompt=abc123",
  controllerStateKey: "default::19127",
  replyTarget: "96599338566",
  senderId: "",
});

const stash = peekCurrentTurnIdentity();
assert.ok(stash && stash.conversationId === "19127", "T11c: stash round-trips.");

assert.equal(
  resolveToolConversationId(strippedCtx),
  "19127",
  "T12: stripped ctx + ingress stash must recover the primary conversation id.",
);

const aliasesFromStash = resolveToolConversationAliases(strippedCtx);
assert.ok(
  aliasesFromStash.includes("19127"),
  "T13a: aliases must include the stashed conversation id.",
);
assert.ok(
  aliasesFromStash.includes("default::19127"),
  "T13b: aliases must include the stashed controllerStateKey.",
);
assert.ok(
  aliasesFromStash.includes("96599338566"),
  "T13c: aliases must include the stashed replyTarget so legacy tool ctx shapes still drain.",
);

// Guard: if the ctx already carries a real id, we must prefer it and NOT
// bleed in the stash aliases. Two conversations interleaving inside the
// stash TTL must be isolated.
const realCtx = { ConversationId: "19000" };
assert.equal(
  resolveToolConversationId(realCtx),
  "19000",
  "T14: stash must not override a real ctx id.",
);
assert.deepEqual(
  resolveToolConversationAliases(realCtx),
  ["19000"],
  "T15: stash must stay idle when ctx carries any identity field at all.",
);

// Guard: TTL must expire. We simulate an ancient stash by stomping ts.
(globalThis).__ridersCurrentTurnIdentity__ = {
  conversationId: "19127",
  sessionKey: "",
  controllerStateKey: "default::19127",
  replyTarget: "",
  senderId: "",
  ts: Date.now() - 10 * 60_000,
};
assert.equal(
  resolveToolConversationId(strippedCtx),
  "",
  "T16: expired stash must not be used as an identity fallback.",
);

clearCurrentTurnIdentity();

// Runtime proof: push via the stripped ctx resolvers, drain via the primary
// id. This is the exact invariant the blocker path violated.
const {
  pushResponderStateOp,
  drainResponderStateOps,
  clearResponderStateOps,
} = await import("../plugins/shared/responder-state-ops.ts");

setCurrentTurnIdentity({
  conversationId: "19127",
  sessionKey: "agent:riders:octopus:direct:19127::prompt=abc123",
  controllerStateKey: "default::19127",
  replyTarget: "96599338566",
  senderId: "",
});

clearResponderStateOps("19127", ["default::19127", "19127"]);

const simulatedStrippedCtx = { Body: "kuwait city" };
const primary = resolveToolConversationId(simulatedStrippedCtx);
const aliases = resolveToolConversationAliases(simulatedStrippedCtx);
assert.equal(primary, "19127", "T17: end-to-end primary id recovery.");

pushResponderStateOp(
  primary,
  {
    op: "set_pending_area",
    field: "pickup_area",
    area_name_en: "Salmiya",
    area_name_ar: null,
    turn_id: "test-turn-11",
  },
  aliases,
);
pushResponderStateOp(
  primary,
  {
    op: "set_requested_slot",
    slot: "dropoff_area",
    options: null,
    turn_id: "test-turn-11",
  },
  aliases,
);

const drained = drainResponderStateOps("19127", ["default::19127", "19127"]);
assert.equal(
  drained.length,
  2,
  `T18: drain under the real conversation id must recover both stripped-ctx pushes; drained=${drained.length}.`,
);
assert.ok(
  drained.some(
    (op) => op.op === "set_pending_area" && op.area_name_en === "Salmiya",
  ),
  "T18a: set_pending_area for Salmiya must survive the ingress-stash roundtrip.",
);
assert.ok(
  drained.some(
    (op) => op.op === "set_requested_slot" && op.slot === "dropoff_area",
  ),
  "T18b: set_requested_slot for dropoff_area must survive the ingress-stash roundtrip.",
);

clearCurrentTurnIdentity();

// Source-level invariant: `octopus-channel/index.ts` must publish the stash
// at inbound ingress. If this block is ever deleted, the entire fallback
// silently becomes useless, so we anchor on the well-known globalThis key
// name.
const fs = await import("node:fs");
const octopusSrc = fs.readFileSync(
  new URL("../plugins/octopus-channel/index.ts", import.meta.url),
  "utf8",
);
assert.ok(
  octopusSrc.includes("__ridersCurrentTurnIdentity__"),
  "T19: octopus-channel must publish the identity stash at ingress.",
);
assert.ok(
  /__ridersCurrentTurnIdentity__[^;]*conversationId/s.test(octopusSrc),
  "T19a: octopus-channel stash must carry conversationId.",
);
assert.ok(
  /__ridersCurrentTurnIdentity__[^;]*controllerStateKey/s.test(octopusSrc),
  "T19b: octopus-channel stash must carry controllerStateKey.",
);

// Class-17 regression (2026-04-21):
// stripped_tool_ctx_loses_booking_authority.
//
// On the paired Hawalli → Doha → "mina doha" canary, the LLM called
// get_price(pickup=Mina Doha, dropoff=Mina Doha) on turn 2 but the pricing
// symmetric-rebind guard did not fire — because `getNormalizedBookingAuthority(
// ctx).controller` was null on the stripped ctx, so `controllerEntry?.
// pendingPickupAreaNameEn` was null and the guard had nothing to rebind
// against. The fix extends the Class-11 ingress stash with a minimal
// booking-authority snapshot that the pricing fallback reads when the
// ctx-derived authority is empty. These assertions pin that the stash
// round-trips the authority fields, that the getter fires only when
// bookingAuthority is present, and that `pricing.ts` actually reaches
// for the stashed authority via `getStashedBookingAuthority`.
const { setCurrentTurnBookingAuthority, getStashedBookingAuthority } = mod;

clearCurrentTurnIdentity();

assert.equal(
  getStashedBookingAuthority("c17-empty-test"),
  null,
  "T20: getStashedBookingAuthority must return null when no stash is present.",
);

setCurrentTurnIdentity({
  conversationId: "19200",
  sessionKey: "",
  controllerStateKey: "default::19200",
  replyTarget: "96599338566",
  senderId: "",
});

assert.equal(
  getStashedBookingAuthority("c17-identity-only-test"),
  null,
  "T21: getStashedBookingAuthority must return null when identity is set but authority hasn't been patched in.",
);

setCurrentTurnBookingAuthority({
  stage: "quoted",
  bookingStep: "none",
  pendingPickupAreaNameEn: "Hawalli",
  pendingPickupAreaNameAr: null,
  pendingDropoffAreaNameEn: null,
  pendingDropoffAreaNameAr: null,
  requestedSlot: {
    name: "dropoff_area",
    options: ["Doha Residential", "Shalehat Doha", "Mina Doha"],
  },
});

const stashedAuthority = getStashedBookingAuthority("c17-roundtrip-test");
assert.ok(stashedAuthority, "T22: booking authority must round-trip through the stash.");
assert.equal(
  stashedAuthority.pendingPickupAreaNameEn,
  "Hawalli",
  "T22a: stashed pendingPickupAreaNameEn must round-trip.",
);
assert.equal(
  stashedAuthority.requestedSlot && stashedAuthority.requestedSlot.name,
  "dropoff_area",
  "T22b: stashed requestedSlot.name must round-trip.",
);
assert.deepEqual(
  stashedAuthority.requestedSlot && stashedAuthority.requestedSlot.options,
  ["Doha Residential", "Shalehat Doha", "Mina Doha"],
  "T22c: stashed requestedSlot.options must round-trip verbatim.",
);

setCurrentTurnBookingAuthority(null);
assert.equal(
  getStashedBookingAuthority("c17-clear-authority-test"),
  null,
  "T23: setCurrentTurnBookingAuthority(null) must detach authority without clearing identity.",
);
// Identity must still be intact after clearing authority.
const stillIdentified = peekCurrentTurnIdentity();
assert.ok(
  stillIdentified && stillIdentified.conversationId === "19200",
  "T23a: clearing authority must not drop identity.",
);

clearCurrentTurnIdentity();

// Source-level invariants for the Class-17 fix. Two anchors:
//   * octopus-channel must publish the `bookingAuthority` snapshot alongside
//     identity, otherwise the stash silently degrades back to Class-11
//     identity-only and pricing has nothing to fall back on.
//   * pricing.ts must reach for `getStashedBookingAuthority` in the
//     symmetric-rebind / DST swap code path, not just import it.
assert.ok(
  octopusSrc.includes("bookingAuthority"),
  "T24: octopus-channel must publish bookingAuthority on the ingress stash.",
);
assert.ok(
  octopusSrc.includes("pendingPickupAreaNameEn") &&
    octopusSrc.includes("pendingDropoffAreaNameEn"),
  "T24a: octopus-channel stash payload must include both pending leg names.",
);
assert.ok(
  /bookingAuthority[\s\S]{0,1500}requestedSlot/.test(octopusSrc),
  "T24b: octopus-channel stash payload must include requestedSlot.",
);

const pricingSrc = fs.readFileSync(
  new URL("../plugins/riders-tools/tools/pricing.ts", import.meta.url),
  "utf8",
);
assert.ok(
  pricingSrc.includes("getStashedBookingAuthority"),
  "T25: pricing.ts must consult getStashedBookingAuthority for the Class-17 fallback path.",
);
assert.ok(
  /pricing_area_binding/.test(pricingSrc),
  "T25a: pricing.ts must tag the authority-fallback call with the expected reason string for log filtering.",
);

console.log("smoke-test-tool-conversation-alias-fallback: OK");
