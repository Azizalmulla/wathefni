#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — Phase 2 Milestone 1 ack-aware reply compose (SHADOW).
//
// DEPLOY_CANARY_REPLY_COMPOSE_MODULE_MARKER expected to appear in the
// compiled module header. The test loads the TS source via tsx or falls
// back to the compiled bundle path.
//
// Coverage:
//
//   1. Registry exhaustiveness: every TurnIntentKind has a choice for both
//      `en` and `ar`. Driven off the exported `TURN_INTENT_KINDS` array, so
//      adding a new kind without a registry row fails loudly.
//   2. Per-kind English + Arabic prefixes match the documented intent.
//   3. Summary directive always skips regardless of tiKind.
//   4. ASK_SENDER_PHONE with a known senderName skips
//      (directive_has_builtin_ack).
//   5. ASK_SENDER_PHONE without senderName falls through to the kind-based
//      prefix.
//   6. Low-confidence turn_intent always skips (low_confidence).
//   7. Missing turn_intent always skips (turn_intent_missing).
//   8. acknowledgement + clarifying_question always skip (ack-of-ack +
//      customer_asked_question respectively).
//   9. composeAckAwareReply concatenates with \n when prefix present, and
//      returns the ask verbatim when skip.
//  10. formatReplyComposeShadowLog produces the expected token shape.
//
// Run from repo root:
//   node delivery/scripts/smoke-test-reply-compose.mjs
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const MODULE_REL = "plugins/shared/reply-compose.ts";
const PROPOSER_SCHEMA_REL = "plugins/shared/proposer-schema.ts";

// ---------------------------------------------------------------------------
// Minimal TS loader: run tsx --no-cache once via a spawned subprocess to
// transpile + import both modules, then exec the tests below in that
// subprocess. This avoids adding a runtime dep to the package and mirrors
// the pattern used by the other smoke-test-*.mjs scripts.
//
// Simpler alternative: exec `node --experimental-loader tsx/esm` if
// available. Fallback: read-module-only and assert on source heuristics.
// ---------------------------------------------------------------------------

const modulePath = path.join(repoRoot, MODULE_REL);
const schemaPath = path.join(repoRoot, PROPOSER_SCHEMA_REL);

const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
  cwd: repoRoot,
  stdio: "ignore",
});
const hasTsx = tsxCheck.status === 0;

if (!hasTsx) {
  // Fallback: source-level smoke. Asserts the registry rows are present
  // for every kind and the canary marker is in place. Not as strong as a
  // real import but enough to catch "someone deleted a kind".
  const fs = await import("node:fs/promises");
  const [moduleSource, schemaSource] = await Promise.all([
    fs.readFile(modulePath, "utf8"),
    fs.readFile(schemaPath, "utf8"),
  ]);
  const canary = "DEPLOY_CANARY_REPLY_COMPOSE_MODULE_MARKER";
  if (!moduleSource.includes(canary)) {
    console.error(`FAIL: missing ${canary} in ${MODULE_REL}`);
    process.exit(1);
  }
  const kindMatches = Array.from(
    schemaSource.matchAll(/"(answered_full|answered_partial|answered_unasked|corrected_prior|clarifying_question|acknowledgement|refused_or_stuck|unclear)"/g),
  ).map((m) => m[1]);
  const uniqueKinds = Array.from(new Set(kindMatches));
  const missing = [];
  for (const k of uniqueKinds) {
    // Each kind must appear as a top-level key in ACK_PREFIX_REGISTRY.
    const pattern = new RegExp(`^\\s*${k}\\s*:`, "m");
    if (!pattern.test(moduleSource)) {
      missing.push(k);
    }
  }
  if (missing.length > 0) {
    console.error(
      `FAIL: registry missing rows for kinds: ${missing.join(", ")}`,
    );
    process.exit(1);
  }
  console.log(
    `[smoke-test-reply-compose] OK (source-only mode; tsx not installed). Canary present, registry covers ${uniqueKinds.length} kinds.`,
  );
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Full-import path: tsx is available, re-exec ourselves under tsx so TS
// imports resolve.
// ---------------------------------------------------------------------------

if (!process.env.__REPLY_COMPOSE_SMOKE_TSX__) {
  const child = spawnSync(
    "node",
    ["--import", "tsx", fileURLToPath(import.meta.url)],
    {
      cwd: repoRoot,
      stdio: "inherit",
      env: { ...process.env, __REPLY_COMPOSE_SMOKE_TSX__: "1" },
    },
  );
  process.exit(child.status ?? 1);
}

const replyCompose = await import(pathToFileURL(modulePath).href);
const proposerSchema = await import(pathToFileURL(schemaPath).href);

const {
  ACK_PREFIX_REGISTRY,
  chooseAckPrefix,
  composeAckAwareReply,
  formatReplyComposeShadowLog,
} = replyCompose;
const { TURN_INTENT_KINDS } = proposerSchema;

const failures = [];
function check(name, cond, detail) {
  if (!cond) {
    failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
  }
}

// ---------------------------------------------------------------------------
// 1. Registry exhaustiveness.
// ---------------------------------------------------------------------------

for (const kind of TURN_INTENT_KINDS) {
  const row = ACK_PREFIX_REGISTRY[kind];
  check(
    `registry_row_present_${kind}`,
    row && typeof row === "object",
    `missing row for kind=${kind}`,
  );
  if (!row) continue;
  for (const lang of ["en", "ar"]) {
    const entry = row[lang];
    check(
      `registry_entry_present_${kind}_${lang}`,
      entry && (entry.kind === "prefix" || entry.kind === "skip"),
      `invalid entry kind=${kind} lang=${lang}`,
    );
    if (entry && entry.kind === "prefix") {
      check(
        `registry_prefix_nonempty_${kind}_${lang}`,
        typeof entry.text === "string" && entry.text.trim().length > 0,
        `empty prefix text kind=${kind} lang=${lang}`,
      );
    }
    if (entry && entry.kind === "skip") {
      check(
        `registry_skip_reason_${kind}_${lang}`,
        typeof entry.reason === "string" && entry.reason.length > 0,
        `empty skip reason kind=${kind} lang=${lang}`,
      );
    }
  }
}

// ---------------------------------------------------------------------------
// 2. Per-kind expected shapes.
// ---------------------------------------------------------------------------

const EXPECTED = {
  answered_full: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  answered_partial: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  answered_unasked: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  corrected_prior: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  refused_or_stuck: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  unclear: { en: { kind: "prefix" }, ar: { kind: "prefix" } },
  clarifying_question: {
    en: { kind: "skip", reason: "customer_asked_question" },
    ar: { kind: "skip", reason: "customer_asked_question" },
  },
  acknowledgement: {
    en: { kind: "skip", reason: "ack_of_ack" },
    ar: { kind: "skip", reason: "ack_of_ack" },
  },
};

for (const kind of Object.keys(EXPECTED)) {
  for (const lang of ["en", "ar"]) {
    const actual = ACK_PREFIX_REGISTRY[kind][lang];
    const expected = EXPECTED[kind][lang];
    check(
      `expected_kind_${kind}_${lang}`,
      actual.kind === expected.kind,
      `got kind=${actual.kind}, want kind=${expected.kind}`,
    );
    if (expected.reason) {
      check(
        `expected_reason_${kind}_${lang}`,
        actual.reason === expected.reason,
        `got reason=${actual.reason}, want reason=${expected.reason}`,
      );
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Summary directive always skips.
// ---------------------------------------------------------------------------

const emptyDraft = {};

{
  const res = chooseAckPrefix({
    tiKind: "answered_full",
    tiConfidence: "high",
    directiveAction: "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
    language: "en",
    draft: emptyDraft,
  });
  check(
    "summary_directive_skips",
    res.kind === "skip" && res.reason === "summary_directive_self_ack",
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 4. ASK_SENDER_PHONE with senderName → skip (builtin ack).
// ---------------------------------------------------------------------------

{
  const res = chooseAckPrefix({
    tiKind: "answered_partial",
    tiConfidence: "high",
    directiveAction: "ASK_SENDER_PHONE",
    language: "en",
    draft: { senderName: "Ahmad" },
  });
  check(
    "ask_sender_phone_with_name_skips",
    res.kind === "skip" && res.reason === "directive_has_builtin_ack",
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 5. ASK_SENDER_PHONE without senderName → fall through to kind.
// ---------------------------------------------------------------------------

{
  const res = chooseAckPrefix({
    tiKind: "answered_partial",
    tiConfidence: "high",
    directiveAction: "ASK_SENDER_PHONE",
    language: "en",
    draft: { senderName: "" },
  });
  check(
    "ask_sender_phone_without_name_prefixes",
    res.kind === "prefix" && res.text === "Got it.",
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 6. Low confidence → skip.
// ---------------------------------------------------------------------------

{
  const res = chooseAckPrefix({
    tiKind: "answered_full",
    tiConfidence: "low",
    directiveAction: "ASK_RECIPIENT_NAME_AND_PHONE",
    language: "en",
    draft: emptyDraft,
  });
  check(
    "low_confidence_skips",
    res.kind === "skip" && res.reason === "low_confidence",
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 7. Missing turn_intent → skip.
// ---------------------------------------------------------------------------

{
  const res = chooseAckPrefix({
    tiKind: null,
    tiConfidence: null,
    directiveAction: "ASK_RECIPIENT_NAME_AND_PHONE",
    language: "en",
    draft: emptyDraft,
  });
  check(
    "missing_turn_intent_skips",
    res.kind === "skip" && res.reason === "turn_intent_missing",
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 8. Unclear + pasted-text scenario → meaningful prefix (the regression
//    target from the 2026-04-22 paste incident).
// ---------------------------------------------------------------------------

{
  const res = chooseAckPrefix({
    tiKind: "unclear",
    tiConfidence: "high",
    directiveAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    language: "en",
    draft: emptyDraft,
  });
  check(
    "unclear_pastes_get_recovery_prefix",
    res.kind === "prefix" && /didn't come through clearly/.test(res.text),
    `got ${JSON.stringify(res)}`,
  );
}

{
  const res = chooseAckPrefix({
    tiKind: "unclear",
    tiConfidence: "high",
    directiveAction: "ASK_SENDER_NAME_AND_PHONE_DECISION",
    language: "ar",
    draft: emptyDraft,
  });
  check(
    "unclear_pastes_get_recovery_prefix_ar",
    res.kind === "prefix" && res.text.length > 0,
    `got ${JSON.stringify(res)}`,
  );
}

// ---------------------------------------------------------------------------
// 9. composeAckAwareReply shapes.
// ---------------------------------------------------------------------------

{
  const final = composeAckAwareReply({
    choice: { kind: "prefix", text: "Got it." },
    renderedAskText: "Sender's phone number?",
  });
  check(
    "compose_prefix_concatenates_newline",
    final === "Got it.\nSender's phone number?",
    `got ${JSON.stringify(final)}`,
  );
}

{
  const final = composeAckAwareReply({
    choice: { kind: "skip", reason: "ack_of_ack" },
    renderedAskText: "Sender's phone number?",
  });
  check(
    "compose_skip_returns_ask_only",
    final === "Sender's phone number?",
    `got ${JSON.stringify(final)}`,
  );
}

{
  const final = composeAckAwareReply({
    choice: { kind: "prefix", text: "  Got it.  " },
    renderedAskText: "  Sender's phone number?  ",
  });
  check(
    "compose_trims_both_sides",
    final === "Got it.\nSender's phone number?",
    `got ${JSON.stringify(final)}`,
  );
}

// ---------------------------------------------------------------------------
// 10. formatReplyComposeShadowLog token shape.
// ---------------------------------------------------------------------------

{
  const line = formatReplyComposeShadowLog({
    conversation_id: "conv123",
    session_key: "sess/abc",
    directive_action: "ASK_SENDER_PHONE",
    language: "en",
    ti_kind: "answered_partial",
    ti_confidence: "high",
    choice_kind: "prefix",
    choice_reason: "selected",
    prefix_chars: 7,
  });
  const expectedTokens = [
    "[reply-compose/shadow]",
    "conversation=conv123",
    "sessionKey=sess/abc",
    "directive=ASK_SENDER_PHONE",
    "lang=en",
    "ti_kind=answered_partial",
    "ti_confidence=high",
    "choice=prefix",
    "reason=selected",
    "prefix_chars=7",
  ];
  for (const tok of expectedTokens) {
    check(
      `shadow_log_contains_${tok.replace(/\W+/g, "_")}`,
      line.includes(tok),
      `missing token "${tok}" in line: ${line}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Summary.
// ---------------------------------------------------------------------------

if (failures.length > 0) {
  console.error(
    `[smoke-test-reply-compose] FAIL (${failures.length} failures):\n  - ${failures.join("\n  - ")}`,
  );
  process.exit(1);
}

console.log(
  `[smoke-test-reply-compose] OK — registry covers ${TURN_INTENT_KINDS.length} kinds × 2 languages, skip branches verified, compose + shadow-log shape verified.`,
);
process.exit(0);
