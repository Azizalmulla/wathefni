#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Live canary: Class-15 (route-intent turn bypasses get_price) + Class-16
// (single-token clarification misattribution).
//
// Primary blocker transcript: `delivery salmiya to kuwait city pls`.
// Invariant (Class-15): the first outbound reply must be server-owned —
// either a tool-driven clarify that enumerates the Kuwait City options OR
// the deterministic Class-15 bypass repair reply. A free-composed LLM
// clarification with no `get_price` tool call is forbidden.
//
// Invariant (Class-16): a single-token follow-up answer (`Bnaid Al-Qar`)
// must bind to the `requestedSlot`, never collapse into a symmetric route.
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

// Turn 1 for `delivery salmiya to kuwait city pls` includes a full
// `get_price` round-trip; end-to-end latency comfortably exceeds the
// 45s harness default on first cold turn. Bump the class-15 canary
// timeout to 120s so we never fall back to the stale session snapshot.
if (!process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS) {
  process.env.RIDERS_LIVE_SMOKE_TIMEOUT_MS = "120000";
}

const TURN_LABELS = {
  turn1: "class15 turn1 (salmiya -> kuwait city)",
  turn2: "class15 turn2 (clarify -> bnaid al-qar)",
};

const FREE_COMPOSED_EN = [
  /which (part|area) of kuwait city/i,
  /where in kuwait city/i,
  /what'?s the (delivery|drop[- ]?off) area/i,
  /which area do you want (us )?to deliver/i,
];

const MIXED_UP_RECOVERY = /(got mixed up|resend the pickup area and the delivery area|send the pickup and dropoff areas?)/i;

const KUWAIT_CITY_MEMBERS = ["Sharq", "Mirqab", "Qibla", "Bnaid Al-Qar", "Dasman"];

const CLASS15_REPAIR_EN = /send the pickup area and the delivery area together/i;

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function gatherAllLogs(config, run, afterMs) {
  const lines = await fetchGatewayLogs(config, run, afterMs, "");
  return Array.isArray(lines) ? lines : [];
}

async function waitForOutbound(config, run, acceptedAtMs, label) {
  // We intentionally do NOT fall back to the session-snapshot helper here:
  // session files lag the outbound gateway log and on a fresh conversation
  // the snapshot will return a *stale* assistant event from a prior run,
  // producing false-fail diagnostics. If the gateway log marker never
  // arrives in the canary window, that is the real failure we want to see.
  const outbound = await waitForGatewayReplyLog(
    config,
    run,
    acceptedAtMs,
    "outbound reply sent",
    label,
  );
  return outbound.reply;
}

async function runTurn1(config, run) {
  const text = "delivery salmiya to kuwait city pls";
  console.log(`\n[turn1] customer: ${text}`);
  const ack = await postTextTurn(config, run, text);
  const reply = await waitForOutbound(config, run, ack.acceptedAtMs, TURN_LABELS.turn1);
  const replyText = compactWhitespace(reply.text || "");
  console.log(`[turn1] assistant: ${replyText}`);

  // Hard invariant: no symmetric / recovery shape allowed.
  assert(
    !MIXED_UP_RECOVERY.test(replyText),
    `CLASS-9 REGRESSION: turn1 produced the "mixed up / resend both areas" recovery reply. Raw: ${replyText}`,
  );
  assert(
    !/\bdelivery from\s+salmiya\s+to\s+salmiya\b/i.test(replyText) &&
      !/\bdelivery from\s+kuwait city\s+to\s+kuwait city\b/i.test(replyText),
    `CLASS-9 REGRESSION: turn1 collapsed into a symmetric route. Raw: ${replyText}`,
  );

  // Give the log tail a beat to settle, then inspect which server branch fired.
  await sleep(1_500);
  const logLines = await gatherAllLogs(config, run, ack.acceptedAtMs - 5_000);

  const class15BypassFired = logLines.some((line) =>
    line.includes("[class-15/bypass] route_intent_turn_bypassed_get_price"),
  );
  const clarifyCommitLogged = logLines.some((line) =>
    line.includes("[one-brain/clarify-commit]"),
  );
  // `set_pending_area` + `set_requested_slot` responder ops are ONLY emitted
  // from inside the `get_price` tool's markPendingArea / markRequestedSlot
  // helpers, so the push log is the authoritative "tool fired" signal.
  const getPriceCalled = logLines.some((line) =>
    /\[responder-ops\/push\] op=(set_pending_area|set_requested_slot)/.test(line),
  );
  const replyAuthorServer = logLines.some((line) =>
    /\[one-brain\/reply-attribution\][^\n]*reply_author=server[^\n]*reason=replace_directive_ask/.test(
      line,
    ),
  );

  const mentionsMember = KUWAIT_CITY_MEMBERS.some((name) =>
    new RegExp(`\\b${name.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}\\b`, "i").test(replyText),
  );
  const matchesClass15Repair = CLASS15_REPAIR_EN.test(replyText);
  const matchesFreeComposed = FREE_COMPOSED_EN.some((re) => re.test(replyText));

  console.log(
    `[turn1] diag: class15BypassFired=${class15BypassFired} clarifyCommitLogged=${clarifyCommitLogged} ` +
      `getPriceCalled=${getPriceCalled} replyAuthorServer=${replyAuthorServer} ` +
      `mentionsMember=${mentionsMember} matchesClass15Repair=${matchesClass15Repair} ` +
      `matchesFreeComposed=${matchesFreeComposed}`,
  );

  // Acceptance: exactly one of two server-owned paths must have produced
  // turn 1. Either the tool-driven clarify that enumerates Kuwait City
  // members, OR the Class-15 bypass repair substitution. A free-composed
  // LLM clarification with no matching substitution is a FAIL.
  const toolOwnedClarify =
    getPriceCalled && clarifyCommitLogged && replyAuthorServer && mentionsMember;
  if (toolOwnedClarify) {
    console.log("[turn1] PASS path=tool_owned_clarify");
    return { reply, replyText, path: "tool_owned_clarify", acceptedAtMs: ack.acceptedAtMs };
  }
  if (class15BypassFired && matchesClass15Repair) {
    console.log("[turn1] PASS path=class15_bypass_repair");
    return { reply, replyText, path: "class15_bypass_repair", acceptedAtMs: ack.acceptedAtMs };
  }

  const diag = {
    class15BypassFired,
    clarifyCommitLogged,
    getPriceCalled,
    replyAuthorServer,
    mentionsMember,
    matchesClass15Repair,
    matchesFreeComposed,
    replyText,
    logTail: logLines.slice(-20),
  };
  throw new Error(
    `CLASS-15 BLOCKER STILL OPEN: turn1 is not server-owned.\n${JSON.stringify(diag, null, 2)}`,
  );
}

async function runTurn2(config, run, turn1Path) {
  const text = "Bnaid Al-Qar";
  console.log(`\n[turn2] customer: ${text}`);
  const ack = await postTextTurn(config, run, text);
  const reply = await waitForOutbound(config, run, ack.acceptedAtMs, TURN_LABELS.turn2);
  const replyText = compactWhitespace(reply.text || "");
  console.log(`[turn2] assistant: ${replyText}`);

  // Class-9 / Class-16 hard invariants apply regardless of which turn-1 path
  // fired.
  assert(
    !MIXED_UP_RECOVERY.test(replyText),
    `CLASS-9 REGRESSION: turn2 produced the mixed-up recovery reply. Raw: ${replyText}`,
  );
  assert(
    !/\bbnaid\s+al[- ]?qar\s+to\s+bnaid\s+al[- ]?qar\b/i.test(replyText) &&
      !/\bsalmiya\s+to\s+salmiya\b/i.test(replyText),
    `CLASS-16 REGRESSION: turn2 collapsed into a symmetric route. Raw: ${replyText}`,
  );

  if (turn1Path === "class15_bypass_repair") {
    console.log("[turn2] skipping route-binding assertion — turn1 was a Class-15 repair.");
    return;
  }

  // Tool-owned clarify path: turn 2 MUST resolve to Salmiya -> Bnaid Al-Qar.
  assert(
    /salmiya/i.test(replyText) && /bnaid\s+al[- ]?qar/i.test(replyText),
    `CLASS-16 REGRESSION: turn2 should quote Salmiya -> Bnaid Al-Qar. Raw: ${replyText}`,
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
    `[canary] scenario=class15 replyTarget=${run.replyTarget} conversationId=${run.conversationId} runId=${run.runId}`,
  );

  console.log("[canary] resetting live conversation + guard state...");
  await resetLiveConversationState(config, run);

  const turn1Result = await runTurn1(config, run);
  await runTurn2(config, run, turn1Result.path);

  console.log("\n[canary] ALL GREEN — class15 + class16 live invariants hold.");
}

main().catch((error) => {
  console.error(`\n[canary] FAIL: ${error?.message || error}`);
  if (error?.stack) console.error(error.stack);
  process.exit(1);
});
