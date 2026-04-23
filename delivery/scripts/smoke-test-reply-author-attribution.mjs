#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test: Phase 5 — reply-author attribution contract (2026-04-20).
//
// Product rule:
//   Every `OutboundDecisionResult` carries a `replyAuthor:
//   "server" | "llm" | "fallback"` tag, derived from the decision kind
//   via `classifyReplyAuthor`. This is the observability tripwire that
//   enables per-turn "who actually composed this reply" analysis — the
//   whole Phase 2/3 architecture investment is only measurable when we
//   can count attributions.
//
// Cases covered:
//   A1-A5 classifyReplyAuthor ↔ OutboundDecisionKind mapping is
//         exhaustive: allow / allow_sanitized → llm;
//         replace_authoritative → server; replace_fallback /
//         block_retry → fallback.
//   R1-R4 Every return path from decidePreStateOutbound /
//         decidePostStateOutbound carries a replyAuthor consistent
//         with its decision kind. Exercises representative branches:
//         allow-through, clarify substitution, manual-confirm
//         substitution, directive-ask substitution, price whitelist
//         fallback, empty-reply fallback.
//   U1    Unknown-op logging guard — the drain loop's fallthrough
//         emits a warn line for unknown op kinds. Source-grep anchor.
//   L1    Attribution log emitter exists and includes reply_author.
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

const outboundDecision = loadTs("plugins/octopus-channel/lib/outbound-decision.ts");
const policy = loadTs("plugins/shared/conversation-policy.ts");

const {
  classifyReplyAuthor,
  decidePreStateOutbound,
  decidePostStateOutbound,
} = outboundDecision;
const { createEmptyBookingDraft } = policy;

// -------------------------------------------------------------------------
// A1–A5: classifyReplyAuthor mapping.
// -------------------------------------------------------------------------
assert.equal(classifyReplyAuthor("allow"), "llm", "A1: allow → llm");
assert.equal(classifyReplyAuthor("allow_sanitized"), "llm", "A2: allow_sanitized → llm");
assert.equal(
  classifyReplyAuthor("replace_authoritative"),
  "server",
  "A3: replace_authoritative → server",
);
assert.equal(
  classifyReplyAuthor("replace_fallback"),
  "fallback",
  "A4: replace_fallback → fallback",
);
assert.equal(
  classifyReplyAuthor("block_retry"),
  "fallback",
  "A5: block_retry → fallback",
);

// -------------------------------------------------------------------------
// Fixtures for decision tests.
// -------------------------------------------------------------------------

function priceExtractor(text) {
  const out = [];
  const re = /\b(\d+\.\d{3})\b/g;
  let m;
  while ((m = re.exec(text)) !== null) out.push(m[1]);
  return out;
}

const noopBuilders = {
  buildDeterministicSelectedQuotedOptionReply: ({ language }) =>
    language === "ar" ? "خيار موثق" : "Selected option",
  buildDeterministicGraceWindowReply: (l) => (l === "ar" ? "نافذة" : "grace"),
  buildProviderIssueFallbackReply: (l) =>
    l === "ar" ? "خلل فني" : "Technical issue",
};

function prePassthrough(replyText) {
  return {
    replyText,
    preferredLanguage: "en",
    sessionGuard: null,
    sessionIsRecent: false,
    preferredCanonicalText: null,
    guardToolAgeMs: Number.POSITIVE_INFINITY,
    canonicalOverwriteAllowed: false,
    canonicalOverwriteSkipReason: null,
    extractPricesFromText: priceExtractor,
    activeQuotedRoute: null,
    sameRouteQuoteAction: null,
    ...noopBuilders,
    conversationId: "c1",
    sessionKeyForLogs: "s1",
    controllerStage: null,
  };
}

// -------------------------------------------------------------------------
// R1: allow-through — healthy LLM reply, nothing substitutes. Expect
// replyAuthor="llm".
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound(prePassthrough("Hello, how can I help?"));
  assert.equal(res.decision, "allow", "R1 decision");
  assert.equal(res.replyAuthor, "llm", "R1 attribution");
}

// -------------------------------------------------------------------------
// R2: price whitelist → replace_fallback / replace_price_mismatch →
// replyAuthor="fallback".
// -------------------------------------------------------------------------
{
  const res = decidePreStateOutbound({
    ...prePassthrough("Great news, 0.750 KWD only."),
    sessionGuard: {
      allValidPrices: new Set(["1.250"]),
      lastToolTs: Date.now(),
      lastToolName: "get_price",
    },
    sessionIsRecent: true,
  });
  assert.equal(res.reason, "replace_price_mismatch", "R2 reason");
  assert.equal(res.decision, "replace_fallback", "R2 decision");
  assert.equal(res.replyAuthor, "fallback", "R2 attribution");
}

// R3 removed in authority-cutover phase 3 (2026-04-23): the
// clarify-before-proceed substitution branch was deleted from
// decidePreStateOutbound. The LLM composes option / manual-confirm
// questions itself from prompt facts.

// -------------------------------------------------------------------------
// R4: directive-ask substitution (Phase 2) → replace_authoritative →
// replyAuthor="server".
// -------------------------------------------------------------------------
{
  const ctx = {
    language: "en",
    draft: createEmptyBookingDraft(),
    entry: {
      stage: "collecting_booking_details",
      bookingStep: "sender",
      bookingDraft: createEmptyBookingDraft(),
      quotePickupAreaNameEn: "Hawalli",
      quotePickupAreaNameAr: "حولي",
      quoteDropoffAreaNameEn: "Salmiya",
      quoteDropoffAreaNameAr: "السالمية",
      selectedDeliveryType: "sedan_normal",
      quotedPrice: 1.25,
    },
    route: null,
    turnSeed: "t1::c1",
  };
  const res = decidePreStateOutbound({
    ...prePassthrough("LLM draft that gets replaced."),
    directiveAction: "ASK_PICKUP_ADDRESS",
    directiveRenderContext: ctx,
    renderDirectiveReply: (action, c) => ({
      kind: "render",
      text: `Please share the pickup address in ${c.entry.quotePickupAreaNameEn}.`,
    }),
  });
  assert.equal(res.reason, "replace_directive_ask", "R4 reason");
  assert.equal(res.decision, "replace_authoritative", "R4 decision");
  assert.equal(res.replyAuthor, "server", "R4 attribution");
}

// -------------------------------------------------------------------------
// Post-state: empty reply + no controller → replace_fallback /
// fallback_empty_reply → replyAuthor="fallback".
// -------------------------------------------------------------------------
{
  const res = decidePostStateOutbound({
    replyText: "",
    preferredLanguage: "en",
    conversationControllerEntry: null,
    missingFields: [],
    hallucinationGuardRejections: [],
    stageAtTurnStart: null,
    hallucinationGuardEnabled: false,
    nextRequiredAction: null,
    controllerTransitionHint: null,
    buildDeterministicGraceWindowReply: noopBuilders.buildDeterministicGraceWindowReply,
    buildProviderIssueFallbackReply: noopBuilders.buildProviderIssueFallbackReply,
    conversationId: "c1",
  });
  assert.equal(res.reason, "fallback_empty_reply", "post R1 reason");
  assert.equal(res.decision, "replace_fallback", "post R1 decision");
  assert.equal(res.replyAuthor, "fallback", "post R1 attribution");
}

// -------------------------------------------------------------------------
// U1: unknown-op drain fallthrough. Structural anchor: the else-branch
// must exist in index.ts and emit a warn log. If removed or renamed,
// this test catches it so the unknown-op contract is preserved.
// -------------------------------------------------------------------------
{
  const indexSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  assert.ok(
    /\[one-brain\/drain\] unknown_op/.test(indexSrc),
    "U1: drain-layer unknown_op warn log must exist",
  );
  assert.ok(
    /appliedOps\.push\(`unknown_op:\$\{unknownKind\}`\)/.test(indexSrc),
    "U1: unknown_op appears in appliedOps audit",
  );
}

// -------------------------------------------------------------------------
// L1: attribution log emitter in index.ts.
// -------------------------------------------------------------------------
{
  const indexSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/index.ts"),
    "utf8",
  );
  assert.ok(
    /\[one-brain\/reply-attribution\]/.test(indexSrc),
    "L1: attribution log line must exist",
  );
  assert.ok(
    /reply_author=\$\{turnReplyAuthor\}/.test(indexSrc),
    "L1: attribution line carries reply_author",
  );
  assert.ok(
    /reason=\$\{turnReplyReason\}/.test(indexSrc),
    "L1: attribution line carries reason",
  );
  assert.ok(
    /directive=\$\{turnReplyDirective/.test(indexSrc),
    "L1: attribution line carries directive",
  );
}

// -------------------------------------------------------------------------
// Source-shape anchor: the outbound-decision result type must
// require `replyAuthor` so no caller can silently fall back to
// attribution-less decisions.
// -------------------------------------------------------------------------
{
  const moduleSrc = fs.readFileSync(
    path.join(root, "plugins/octopus-channel/lib/outbound-decision.ts"),
    "utf8",
  );
  assert.ok(
    /replyAuthor:\s*ReplyAuthor/.test(moduleSrc),
    "result type must declare replyAuthor: ReplyAuthor",
  );
  assert.ok(
    /finalizeOutboundDecision/.test(moduleSrc),
    "finalizeOutboundDecision wrapper must exist",
  );
  // Both entry points must delegate through the finalizer so attribution
  // is guaranteed end-to-end.
  assert.ok(
    /decidePreStateOutbound[\s\S]{0,200}finalizeOutboundDecision\(decidePreStateOutboundImpl/.test(
      moduleSrc,
    ),
    "decidePreStateOutbound must wrap through finalizeOutboundDecision",
  );
  assert.ok(
    /decidePostStateOutbound[\s\S]{0,200}finalizeOutboundDecision\(decidePostStateOutboundImpl/.test(
      moduleSrc,
    ),
    "decidePostStateOutbound must wrap through finalizeOutboundDecision",
  );
}

console.log("smoke-test-reply-author-attribution: OK");
