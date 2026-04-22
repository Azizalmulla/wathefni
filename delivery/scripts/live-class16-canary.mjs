#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Live canary: Class-16 (single-token clarification misattribution).
//
// Primary blocker transcript: `delivery hawalli to doha pls` -> `mina doha`.
//
// Invariant chain:
//   1. Turn 1 MUST be server-owned. Preferred path is tool-owned clarify:
//      `get_price` fires, resolver flags the Doha ambiguity group, server
//      pushes `set_pending_area(pickup_area=Hawalli)` +
//      `set_requested_slot(dropoff_area, options=[Doha Residential, Shalehat
//      Doha, Mina Doha])`, and the directive dispatcher renders an
//      ASK_DELIVERY_AREA recap that enumerates those members.
//      Fallback path is Class-15 repair — valid but terminates this canary
//      early because no clarification state survives, so Class-16 binding
//      cannot be exercised.
//   2. Turn 2 (`mina doha`, single token) MUST bind to the `requestedSlot`
//      (dropoff_area) and NOT collapse into a symmetric route. The tool
//      must quote Hawalli -> Mina Doha with a KWD price.
//
// Fails loudly if:
//   - turn 2 reply is the "mixed up / resend both areas" recovery shape,
//   - turn 2 quote collapses into `pickup == dropoff`,
//   - turn 2 reply still asks for the delivery area (state was lost).
// ---------------------------------------------------------------------------

import {
  compactWhitespace,
  createRunContext,
  ensureLiveGatewayReady,
  fetchGatewayLogs,
  getLiveSmokeConfig,
  postTextTurn,
  resetLiveConversationState,
  sleep,
  waitForGatewayReplyLog,
} from "./live-riders-harness.mjs";

if (!process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS) {
  process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS = "120000";
}

const DOHA_MEMBERS = ["Doha Residential", "Shalehat Doha", "Mina Doha"];

const MIXED_UP_RECOVERY =
  /(got mixed up|resend the pickup area and the delivery area|send the pickup and dropoff areas?)/i;

const CLASS15_REPAIR_EN =
  /send the pickup area and the delivery area together/i;

const ASK_DELIVERY_AREA_SHAPE =
  /(what'?s the delivery area|which part of|where in|which area)/i;

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function waitForOutbound(config, run, acceptedAtMs, label) {
  const outbound = await waitForGatewayReplyLog(
    config,
    run,
    acceptedAtMs,
    "outbound reply sent",
    label,
  );
  return outbound.reply;
}

async function gatherAllLogs(config, run, afterMs) {
  const lines = await fetchGatewayLogs(config, run, afterMs, "");
  return Array.isArray(lines) ? lines : [];
}

async function runTurn1(config, run) {
  const text = "delivery hawalli to doha pls";
  console.log(`\n[turn1] customer: ${text}`);
  const ack = await postTextTurn(config, run, text);
  const reply = await waitForOutbound(config, run, ack.acceptedAtMs, "class16 turn1");
  const replyText = compactWhitespace(reply.text || "");
  console.log(`[turn1] assistant: ${replyText}`);

  assert(
    !MIXED_UP_RECOVERY.test(replyText),
    `CLASS-9 REGRESSION: turn1 produced the mixed-up recovery reply. Raw: ${replyText}`,
  );
  assert(
    !/\bhawalli\s+to\s+hawalli\b/i.test(replyText) &&
      !/\bdoha\s+to\s+doha\b/i.test(replyText),
    `CLASS-9 REGRESSION: turn1 collapsed into a symmetric route. Raw: ${replyText}`,
  );

  await sleep(1_500);
  const logLines = await gatherAllLogs(config, run, ack.acceptedAtMs - 5_000);

  const class15BypassFired = logLines.some((line) =>
    line.includes("[class-15/bypass] route_intent_turn_bypassed_get_price"),
  );
  const clarifyCommitLogged = logLines.some((line) =>
    line.includes("[one-brain/clarify-commit]"),
  );
  const getPriceCalled = logLines.some((line) =>
    /\[responder-ops\/push\] op=(set_pending_area|set_requested_slot)/.test(line),
  );
  const pendingPickupHawalli = logLines.some((line) =>
    /\[responder-ops\/push\] op=set_pending_area[^\n]*area_en="Hawalli"/i.test(line),
  );
  const dropoffRequested = logLines.some((line) =>
    /\[responder-ops\/push\] op=set_requested_slot[^\n]*slot=dropoff_area/.test(line),
  );
  const dohaOptionsEnumerated = logLines.some((line) =>
    /options=\[[^\]]*Mina Doha[^\]]*\]/i.test(line),
  );
  const replyAuthorServer = logLines.some((line) =>
    /\[one-brain\/reply-attribution\][^\n]*reply_author=server[^\n]*reason=replace_directive_ask/.test(
      line,
    ),
  );

  const mentionsMember = DOHA_MEMBERS.some((name) =>
    new RegExp(`\\b${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}\\b`, "i").test(replyText),
  );
  const mentionsHawalli = /\bhawalli\b/i.test(replyText);

  console.log(
    `[turn1] diag: class15BypassFired=${class15BypassFired} clarifyCommitLogged=${clarifyCommitLogged} ` +
      `getPriceCalled=${getPriceCalled} pendingPickupHawalli=${pendingPickupHawalli} ` +
      `dropoffRequested=${dropoffRequested} dohaOptionsEnumerated=${dohaOptionsEnumerated} ` +
      `replyAuthorServer=${replyAuthorServer} mentionsHawalli=${mentionsHawalli} ` +
      `mentionsMember=${mentionsMember}`,
  );

  if (class15BypassFired && CLASS15_REPAIR_EN.test(replyText)) {
    console.log(
      "[turn1] Class-15 repair fired. This terminates the Class-16 canary early " +
        "because no clarification state carries into turn 2. Not a failure, but " +
        "the LLM skipped get_price on this run — prompt-drift signal to watch.",
    );
    return { path: "class15_bypass_repair", acceptedAtMs: ack.acceptedAtMs };
  }

  const toolOwnedClarify =
    getPriceCalled &&
    clarifyCommitLogged &&
    replyAuthorServer &&
    pendingPickupHawalli &&
    dropoffRequested &&
    dohaOptionsEnumerated &&
    mentionsHawalli &&
    mentionsMember;

  if (toolOwnedClarify) {
    console.log("[turn1] PASS path=tool_owned_clarify");
    return { path: "tool_owned_clarify", acceptedAtMs: ack.acceptedAtMs };
  }

  const diag = {
    class15BypassFired,
    clarifyCommitLogged,
    getPriceCalled,
    pendingPickupHawalli,
    dropoffRequested,
    dohaOptionsEnumerated,
    replyAuthorServer,
    mentionsHawalli,
    mentionsMember,
    replyText,
    logTail: logLines.slice(-25),
  };
  throw new Error(
    `CLASS-16 TURN-1 FAIL: neither tool-owned clarify nor class-15 repair produced a clean state.\n${JSON.stringify(diag, null, 2)}`,
  );
}

async function runTurn2(config, run, turn1Path) {
  const text = "mina doha";
  console.log(`\n[turn2] customer: ${text}`);
  const ack = await postTextTurn(config, run, text);
  const reply = await waitForOutbound(config, run, ack.acceptedAtMs, "class16 turn2");
  const replyText = compactWhitespace(reply.text || "");
  console.log(`[turn2] assistant: ${replyText}`);

  assert(
    !MIXED_UP_RECOVERY.test(replyText),
    `CLASS-9 REGRESSION: turn2 produced the mixed-up recovery reply. Raw: ${replyText}`,
  );
  assert(
    !/\bhawalli\s+to\s+hawalli\b/i.test(replyText) &&
      !/\bmina\s+doha\s+to\s+mina\s+doha\b/i.test(replyText),
    `CLASS-16 REGRESSION: turn2 collapsed into a symmetric route. Raw: ${replyText}`,
  );

  if (turn1Path === "class15_bypass_repair") {
    // Turn 2 started with no state after the Class-15 repair, so the correct
    // behaviour here is a clean full-route ask — NOT a silent symmetric
    // quote. The assertion above already covers the hard invariants; do
    // not require a route binding because there is no state to bind to.
    console.log(
      "[turn2] skipping route-binding assertion — turn1 was a Class-15 repair.",
    );
    return;
  }

  // Tool-owned clarify path: turn 2 MUST bind Mina Doha as the dropoff
  // and quote Hawalli -> Mina Doha with a KWD price. This is the Class-16
  // invariant we explicitly patched `alignAreaTokensToRequestedSlot` for.
  assert(
    /\bhawalli\b/i.test(replyText) && /\bmina\s+doha\b/i.test(replyText),
    `CLASS-16 REGRESSION: turn2 should quote Hawalli -> Mina Doha. Raw: ${replyText}`,
  );
  // Additional sanity: reply must NOT still be asking for the delivery
  // area — that would mean the single-token answer was dropped.
  assert(
    !ASK_DELIVERY_AREA_SHAPE.test(replyText),
    `CLASS-16 REGRESSION: turn2 still asked for the delivery area instead of binding. Raw: ${replyText}`,
  );
  assert(
    /\d+(?:\.\d{1,3})?\s*kwd/i.test(replyText),
    `CLASS-16 REGRESSION: turn2 should contain a KWD price after binding. Raw: ${replyText}`,
  );

  console.log("[turn2] PASS path=tool_owned_quote");
}

async function main() {
  const config = getLiveSmokeConfig();
  await ensureLiveGatewayReady(config);
  const run = await createRunContext(config);
  console.log(
    `[canary] scenario=class16 replyTarget=${run.replyTarget} conversationId=${run.conversationId} runId=${run.runId}`,
  );

  console.log("[canary] resetting live conversation + guard state...");
  await resetLiveConversationState(config, run);

  const turn1Result = await runTurn1(config, run);
  await runTurn2(config, run, turn1Result.path);

  console.log("\n[canary] ALL GREEN — class16 live invariants hold.");
}

main().catch((error) => {
  console.error(`\n[canary] FAIL: ${error?.message || error}`);
  if (error?.stack) console.error(error.stack);
  process.exit(1);
});
