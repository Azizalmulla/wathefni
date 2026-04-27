#!/usr/bin/env node
// Guard-state contract for order submission:
// a failed create_simple_order attempt must never reuse a stale order UID or
// promote the controller to order_submitted.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

const guardSrc = fs.readFileSync(
  path.join(root, "plugins/riders-tools/tools/guards.ts"),
  "utf8",
);
const indexSrc = fs.readFileSync(
  path.join(root, "plugins/octopus-channel/index.ts"),
  "utf8",
);

{
  const clearIdx = guardSrc.indexOf("session.lastCreatedOrderUid = null;");
  const failedIdx = guardSrc.indexOf('if (!createdOrderUid)');
  const successIdx = guardSrc.indexOf("session.lastToolName = toolName;");
  assert.ok(clearIdx >= 0, "create_simple_order path must clear stale lastCreatedOrderUid");
  assert.ok(failedIdx > clearIdx, "stale order UID must be cleared before failure branch");
  assert.ok(successIdx > failedIdx, "failed create_simple_order must return before recording lastToolName");
  assert.match(
    guardSrc,
    /create_simple_order_not_submitted/,
    "failed create_simple_order attempts must emit a clear not-submitted marker",
  );
}

{
  assert.match(
    indexSrc,
    /sessionGuard\.lastToolName === "create_simple_order" &&\s*String\(sessionGuard\.lastCreatedOrderUid \|\| ""\)\.trim\(\)/,
    "controller promotion to order_submitted must require a same-session created order UID",
  );
  assert.match(
    indexSrc,
    /const createSimpleOrderFiredThisTurn =[\s\S]*lastCreatedOrderUid[\s\S]*sessionGuard\.lastToolTs >= turnStartMs;/,
    "post-order transaction invariant must only arm for successful create_simple_order results",
  );
  assert.doesNotMatch(
    indexSrc,
    /sessionGuard\.lastCreatedOrderUid[\s\S]{0,120}conversationControllerEntry\.submittedOrderUid/,
    "create_simple_order promotion must not fall back to a stale submittedOrderUid",
  );
}

console.log("ALL PASS smoke-test-post-order-submission-guard.mjs");
