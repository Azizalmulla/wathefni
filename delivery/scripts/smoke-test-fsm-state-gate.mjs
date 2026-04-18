#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the FSM state gate wired into the riders-tools before_tool_
// call hook. The gate refuses tool calls that are incoherent with the current
// booking stage, returning an error to the LLM that names the correct tool
// for that state. This shrinks the LLM's decision surface and eliminates a
// class of "LLM calls wrong tool + gets confused response + hallucinates"
// incidents.
//
// Scope of this test: the post-order gate (stage === "order_submitted") —
// the highest-value state boundary, since calling booking-collection tools
// after an order is submitted is always nonsensical and historically
// responsible for a meaningful slice of hallucinated post-order chatter.
//
// Cases:
//   1. Post-order blocks apply_booking_field.
//   2. Post-order blocks create_simple_order.
//   3. Post-order blocks start_booking.
//   4. Post-order blocks get_price.
//   5. Post-order does NOT block track_order (legitimate post-order tool).
//      [track_order has its own order_id gate, which we satisfy here.]
//   6. Pre-order state (collecting_booking_details) does NOT trigger the
//      FSM gate — apply_booking_field passes through.
//   7. Quoted state (stage === "quoted") does NOT trigger the FSM gate —
//      apply_booking_field passes through.
//   8. Non-customer contexts (e.g. admin) are not subject to the gate.
//   9. Block messages name the correct replacement tool(s).
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

async function loadTsModule(relativePath) {
  const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
  const jitiFactory = require(
    path.join(root, "plugins/riders-tools/node_modules/jiti/lib/jiti.cjs"),
  );
  const jiti = jitiFactory(pathToFileURL(import.meta.url).href, { interopDefault: true });
  return await jiti(path.join(root, relativePath));
}

const { createGuardModule } = await loadTsModule("plugins/riders-tools/tools/guards.ts");

const moduleDeps = {
  buildRouteKey: (_pickup, _dropoff) => "test",
  buildBookableQuoteMapFromGetPricePayload: () => ({}),
};

const guard = createGuardModule(moduleDeps);
const { beforeToolCall } = guard.helpers;

// ---- Context factory ----
//
// The guard's `isCustomerOctopusContext` keys off ctx.channel === "octopus"
// and ctx.isOperator === false. `getNormalizedBookingAuthority` reads from
// ctx.conversationStageHint (direct) or from the mirrored controller entry
// stored at ctx.mirroredConversationControllerEntry.
//
// We simulate the exact shape by providing the stage+bookingStep hints
// directly — that path is checked first and short-circuits the controller
// mirror lookup.
function buildCtx(overrides = {}) {
  // Matches what the guard actually reads: Surface / ConversationLabel /
  // From + the capitalized Hint fields populated by the channel plugin.
  return {
    Surface: "octopus",
    ConversationLabel: "customer:9647XXXXXXX",
    From: "octopus:ingress/default",
    BodyForAgent: "",
    CustomerIntentHint: "unknown",
    CustomerTurnActionHint: "unknown",
    ConversationStageHint: "collecting_booking_details",
    BookingStepHint: "sender",
    ...overrides,
  };
}

function tryBeforeToolCall(event, ctx) {
  try {
    beforeToolCall(event, ctx);
    return { blocked: false, reason: null };
  } catch (err) {
    return { blocked: true, reason: err instanceof Error ? err.message : String(err) };
  }
}

// -----------------------------------------------------------------------
// Case 1: post-order blocks apply_booking_field
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "order_submitted",
    BookingStepHint: "completed",
  });
  const res = tryBeforeToolCall({ toolName: "apply_booking_field", params: {} }, ctx);
  assert(res.blocked, `case1: apply_booking_field must be blocked post-order, got ${JSON.stringify(res)}`);
  assert(
    /already submitted/i.test(res.reason),
    `case1: block reason must mention already submitted, got: ${res.reason}`,
  );
  assert(
    /track_order|cancel_order|request_handoff/i.test(res.reason),
    `case1: block reason must point to correct replacement tool(s), got: ${res.reason}`,
  );
}

// -----------------------------------------------------------------------
// Case 2: post-order blocks create_simple_order
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "order_submitted",
    BookingStepHint: "completed",
  });
  const res = tryBeforeToolCall({ toolName: "create_simple_order", params: {} }, ctx);
  assert(res.blocked, "case2: create_simple_order must be blocked post-order");
  assert(/already submitted/i.test(res.reason), "case2: reason must mention already submitted");
}

// -----------------------------------------------------------------------
// Case 3: post-order blocks start_booking
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "order_submitted",
    BookingStepHint: "completed",
  });
  const res = tryBeforeToolCall({ toolName: "start_booking", params: {} }, ctx);
  assert(res.blocked, "case3: start_booking must be blocked post-order");
}

// -----------------------------------------------------------------------
// Case 4: post-order blocks get_price
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "order_submitted",
    BookingStepHint: "completed",
    BodyForAgent: "How much is a new delivery?",
  });
  const res = tryBeforeToolCall({ toolName: "get_price", params: {} }, ctx);
  assert(res.blocked, "case4: get_price must be blocked post-order");
  assert(
    /track_order|cancel_order|request_handoff/i.test(res.reason),
    `case4: reason must name post-order tools, got: ${res.reason}`,
  );
}

// -----------------------------------------------------------------------
// Case 5: post-order does NOT block track_order when order_id is valid
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "order_submitted",
    BookingStepHint: "completed",
    BodyForAgent: "Where is ORDER-123456?",
  });
  const res = tryBeforeToolCall(
    { toolName: "track_order", params: { order_id: "ORDER-123456" } },
    ctx,
  );
  assert(!res.blocked, `case5: track_order must pass post-order with valid id, got: ${res.reason}`);
}

// -----------------------------------------------------------------------
// Case 6: pre-order (collecting_booking_details) does NOT trigger FSM gate
// for apply_booking_field
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "collecting_booking_details",
    BookingStepHint: "sender",
  });
  const res = tryBeforeToolCall({ toolName: "apply_booking_field", params: {} }, ctx);
  // Not blocked by anything in current guard for apply_booking_field in
  // collecting state. (apply_booking_field has no other guard.)
  assert(
    !res.blocked,
    `case6: apply_booking_field must pass during collection, got: ${res.reason}`,
  );
}

// -----------------------------------------------------------------------
// Case 7: quoted state does NOT trigger FSM gate for apply_booking_field
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    ConversationStageHint: "quoted",
    BookingStepHint: "idle",
  });
  const res = tryBeforeToolCall({ toolName: "apply_booking_field", params: {} }, ctx);
  assert(!res.blocked, `case7: apply_booking_field must pass in quoted state, got: ${res.reason}`);
}

// -----------------------------------------------------------------------
// Case 8: non-customer context (admin / staff WhatsApp) is NOT subject
// to the FSM gate. Guard distinguishes customer-Octopus from everything
// else by requiring Surface===octopus AND ConversationLabel starts with
// "customer:". An admin WhatsApp shell chat fails both.
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({
    Surface: "whatsapp",
    From: "whatsapp:+965-admin",
    ConversationLabel: "staff:admin",
    ConversationStageHint: "order_submitted",
  });
  const res = tryBeforeToolCall({ toolName: "apply_booking_field", params: {} }, ctx);
  assert(!res.blocked, `case8: admin context must not be gated, got: ${res.reason}`);
}

// -----------------------------------------------------------------------
// Case 9: block-message correctness — spot check the full messages
// -----------------------------------------------------------------------
{
  const ctx = buildCtx({ ConversationStageHint: "order_submitted" });
  const res1 = tryBeforeToolCall({ toolName: "apply_booking_field" }, ctx);
  assert(
    res1.reason.includes("apply_booking_field cannot save"),
    "case9a: apply_booking_field block must explain why it cannot save",
  );

  const res2 = tryBeforeToolCall({ toolName: "get_price" }, ctx);
  assert(
    res2.reason.includes("re-quote"),
    "case9b: get_price block must discourage re-quoting",
  );

  const res3 = tryBeforeToolCall({ toolName: "create_simple_order" }, ctx);
  assert(
    res3.reason.includes("already submitted"),
    "case9c: create_simple_order block must reference already submitted",
  );
}

console.log("ok: all 9 FSM state-gate smoke cases passed");
