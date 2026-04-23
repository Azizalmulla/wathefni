#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: server-synthesized request_handoff + toagent escalation
// (2026-04-20, narrowed 2026-04-23).
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
//        the handoff reply text ("one of our agents will reach out" /
//        "راح يتواصل معك أحد الموظفين").
//
// Authority-cutover Phase 6 (2026-04-23): the deterministic
// manual-confirm reply builders were deleted together with the A0a /
// A0b Region-A substitutions. The LLM now composes the handoff +
// address-ask replies natively (hard rule 8 + option catalog facts).
// The previous H1/H2/H3 + M1-M4 cases exercised the deleted builders
// directly and were dropped. What's still load-bearing:
//   * `shouldMoveToHumanAgent` — still gates the `toagent` call in
//     `sendOctopusTextReply` and must keep its preservation markers
//     working (support-tool stub, human-agent phrasing, etc.).
//   * The server-synthesis drain block in index.ts — still emits
//     `request_handoff` with a `manual_confirm_*` reason when the LLM
//     forgets to call the tool on a manual-confirm turn.
//
// Cases covered:
//   M5   shouldMoveToHumanAgent — pre-existing escalation markers
//        (support-tool stub + "human agent") keep working.
//   S1   Source-shape anchor: the server-synthesis drain block in
//        index.ts still fires on the right conditions.
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
const { shouldMoveToHumanAgent } = intentText;

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
// S1: source-shape anchor — the server-synthesis drain block in
// index.ts still exists and triggers on the right conditions. We grep
// the source to anchor the structural contract — if someone deletes or
// renames the synthesis block this test fails and forces a review.
// -------------------------------------------------------------------------
{
  const fs = await import("node:fs");
  const indexSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  assert.ok(
    /\[one-brain\/server-handoff\] synthesized/.test(indexSrc),
    "S1: synthesis audit log line must exist in index.ts",
  );
  assert.ok(
    /request_handoff:server_synthesized\(/.test(indexSrc),
    "S1: synthesis appliedOps tag must exist in index.ts",
  );
  // The block must only act when `!handoffRequested` — prevents double-
  // synthesis when the LLM already emitted the op. Grep for the guard
  // literal above the audit log.
  const withGuard = indexSrc.match(
    /!handoffRequested[\s\S]{0,2000}\[one-brain\/server-handoff\] synthesized/,
  );
  assert.ok(
    withGuard,
    "S1: synthesis must guard on !handoffRequested to stay idempotent with LLM-emitted op",
  );
}

console.log("smoke-test-server-synthesized-handoff: OK");
