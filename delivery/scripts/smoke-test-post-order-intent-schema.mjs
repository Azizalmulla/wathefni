#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test — Phase 3c: post_order_intent schema + emit anchors.
//
// DEPLOY_CANARY_POST_ORDER_INTENT_* markers expected across schema / prompt
// rule / emit sites. Source-only fallback when tsx is not installed; full
// import mode when tsx is present.
//
// Coverage:
//   1. Module canary: `POST_ORDER_INTENT_KINDS` exported with exactly 6
//      expected values.
//   2. Schema: `schema_version` union now includes `"1.3"`.
//   3. Schema: `ProposedTurnDecision` accepts an optional
//      `post_order_intent` field.
//   4. Validator:
//        a) v1.3 payload WITHOUT post_order_intent → accepted
//           (no validator error — conformance miss is the emit's job).
//        b) v1.3 payload WITH valid post_order_intent → accepted, round-
//           trips the kind + reason.
//        c) v1.3 payload with unknown post_order_intent.kind → rejected.
//        d) v1.3 payload with post_order_intent missing reason → rejected.
//        e) v1.3 payload with post_order_intent not object (string) → rejected.
//   5. Tool schema: `PROPOSE_TURN_DECISION_TOOL_SCHEMA.properties.post_order_intent`
//      is present, has required kind+reason, enum covers all 6 kinds.
//   6. Prompt rule literal: rule 14 canary marker present in one-brain-context.ts.
//   7. Emit literal: the po_classification canary is wired in index.ts.
// ---------------------------------------------------------------------------

import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const SCHEMA_REL = "plugins/shared/proposer-schema.ts";
const PROMPT_REL = "plugins/octopus-channel/lib/one-brain-context.ts";
const INDEX_REL = "plugins/octopus-channel/index.ts";

const EXPECTED_KINDS = [
  "track",
  "cancel_this_order",
  "recreate_same",
  "recreate_modified",
  "customer_support",
  "unclear",
];

const schemaPath = path.join(repoRoot, SCHEMA_REL);
const promptPath = path.join(repoRoot, PROMPT_REL);
const indexPath = path.join(repoRoot, INDEX_REL);

const tsxCheck = spawnSync("node", ["-e", "require.resolve('tsx')"], {
  cwd: repoRoot,
  stdio: "ignore",
});
const hasTsx = tsxCheck.status === 0;

if (!hasTsx) {
  const fs = await import("node:fs/promises");
  const [schemaSrc, promptSrc, indexSrc] = await Promise.all([
    fs.readFile(schemaPath, "utf8"),
    fs.readFile(promptPath, "utf8"),
    fs.readFile(indexPath, "utf8"),
  ]);

  const fails = [];

  // 1. Module canary + kinds present.
  if (!schemaSrc.includes("POST_ORDER_INTENT_KINDS")) {
    fails.push("schema: POST_ORDER_INTENT_KINDS export not found");
  }
  for (const k of EXPECTED_KINDS) {
    if (!new RegExp(`"${k}"`).test(schemaSrc)) {
      fails.push(`schema: kind literal "${k}" not found`);
    }
  }

  // 2. Schema version bumped.
  if (!schemaSrc.includes('"1.3"')) {
    fails.push("schema: version \"1.3\" not present in PROPOSER_SCHEMA_VERSIONS");
  }

  // 3. Field on interface.
  if (!/post_order_intent\??:/.test(schemaSrc)) {
    fails.push("schema: post_order_intent field not declared on ProposedTurnDecision");
  }

  // 5. Tool schema entry.
  if (!/post_order_intent:\s*\{[\s\S]*?enum:\s*\[\.\.\.POST_ORDER_INTENT_KINDS\]/.test(schemaSrc)) {
    fails.push("schema: PROPOSE_TURN_DECISION_TOOL_SCHEMA missing post_order_intent entry");
  }

  // 6. Prompt rule canary.
  if (!promptSrc.includes("DEPLOY_CANARY_POST_ORDER_INTENT_PROMPT_MARKER")) {
    fails.push("prompt: DEPLOY_CANARY_POST_ORDER_INTENT_PROMPT_MARKER missing from one-brain-context.ts");
  }
  if (!promptSrc.includes("post_order_intent classification (v1.3)")) {
    fails.push("prompt: rule 14 text not found");
  }

  // 7. Emit canary.
  if (!indexSrc.includes("DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER")) {
    fails.push("emit: DEPLOY_CANARY_POST_ORDER_INTENT_EMIT_MARKER missing from index.ts");
  }
  if (!indexSrc.includes("po_classification=")) {
    fails.push("emit: po_classification= not found in structured-output/proposer emit");
  }

  if (fails.length > 0) {
    console.error(
      `[smoke-test-post-order-intent-schema] FAIL (source-only mode):\n  - ${fails.join("\n  - ")}`,
    );
    process.exit(1);
  }

  console.log(
    `[smoke-test-post-order-intent-schema] OK (source-only mode; tsx not installed). Canaries + 6 kinds + schema v1.3 + field + tool-schema entry + prompt rule 14 + emit marker all present.`,
  );
  process.exit(0);
}

if (!process.env.__POST_ORDER_INTENT_SMOKE_TSX__) {
  const child = spawnSync(
    "node",
    ["--import", "tsx", fileURLToPath(import.meta.url)],
    {
      cwd: repoRoot,
      stdio: "inherit",
      env: { ...process.env, __POST_ORDER_INTENT_SMOKE_TSX__: "1" },
    },
  );
  process.exit(child.status ?? 1);
}

const schemaMod = await import(pathToFileURL(schemaPath).href);
const {
  POST_ORDER_INTENT_KINDS,
  PROPOSER_SCHEMA_VERSIONS,
  validateProposedTurnDecision,
  PROPOSE_TURN_DECISION_TOOL_SCHEMA,
} = schemaMod;

const fails = [];
function check(name, cond, detail) {
  if (!cond) fails.push(`${name}${detail ? ` — ${detail}` : ""}`);
}

// 1. Kinds.
check(
  "kinds_exact_set",
  Array.isArray(POST_ORDER_INTENT_KINDS) &&
    POST_ORDER_INTENT_KINDS.length === EXPECTED_KINDS.length &&
    EXPECTED_KINDS.every((k) => POST_ORDER_INTENT_KINDS.includes(k)),
  `got ${JSON.stringify(POST_ORDER_INTENT_KINDS)}`,
);

// 2. Schema version.
check(
  "schema_version_1_3",
  Array.isArray(PROPOSER_SCHEMA_VERSIONS) &&
    PROPOSER_SCHEMA_VERSIONS.includes("1.3"),
);

// 4a. v1.3 without post_order_intent → accepted.
{
  const res = validateProposedTurnDecision({
    schema_version: "1.3",
    turn_kind: "post_order_chat",
    pricing_decision: { action: "none", reason: "post order" },
    planned_tool_calls: [],
    customer_reply_draft: "ok",
  });
  check(
    "v1_3_without_post_order_intent_ok",
    res.ok === true && !("post_order_intent" in (res.value || {})),
    JSON.stringify(res),
  );
}

// 4b. Valid post_order_intent.
{
  const res = validateProposedTurnDecision({
    schema_version: "1.3",
    turn_kind: "post_order_chat",
    pricing_decision: { action: "none", reason: "track" },
    planned_tool_calls: [],
    customer_reply_draft: "tracking",
    post_order_intent: { kind: "track", reason: "asking about driver ETA" },
  });
  check(
    "valid_post_order_intent_round_trips",
    res.ok === true &&
      res.value.post_order_intent &&
      res.value.post_order_intent.kind === "track" &&
      res.value.post_order_intent.reason === "asking about driver ETA",
    JSON.stringify(res),
  );
}

// 4c. Unknown kind.
{
  const res = validateProposedTurnDecision({
    schema_version: "1.3",
    turn_kind: "post_order_chat",
    pricing_decision: { action: "none", reason: "x" },
    planned_tool_calls: [],
    customer_reply_draft: "x",
    post_order_intent: { kind: "bogus", reason: "y" },
  });
  check(
    "unknown_kind_rejected",
    res.ok === false &&
      res.errors.some((e) => e.startsWith("post_order_intent.kind_invalid")),
    JSON.stringify(res),
  );
}

// 4d. Missing reason.
{
  const res = validateProposedTurnDecision({
    schema_version: "1.3",
    turn_kind: "post_order_chat",
    pricing_decision: { action: "none", reason: "x" },
    planned_tool_calls: [],
    customer_reply_draft: "x",
    post_order_intent: { kind: "track" },
  });
  check(
    "missing_reason_rejected",
    res.ok === false &&
      res.errors.some((e) => e === "post_order_intent.reason_not_string"),
    JSON.stringify(res),
  );
}

// 4e. Non-object.
{
  const res = validateProposedTurnDecision({
    schema_version: "1.3",
    turn_kind: "post_order_chat",
    pricing_decision: { action: "none", reason: "x" },
    planned_tool_calls: [],
    customer_reply_draft: "x",
    post_order_intent: "track",
  });
  check(
    "non_object_rejected",
    res.ok === false &&
      res.errors.some((e) => e === "post_order_intent_not_object"),
    JSON.stringify(res),
  );
}

// 5. Tool schema.
{
  const prop = PROPOSE_TURN_DECISION_TOOL_SCHEMA?.properties?.post_order_intent;
  check("tool_schema_field_present", !!prop);
  if (prop) {
    check(
      "tool_schema_required_kind_reason",
      Array.isArray(prop.required) &&
        prop.required.includes("kind") &&
        prop.required.includes("reason"),
      JSON.stringify(prop.required),
    );
    const kindEnum = prop.properties?.kind?.enum || [];
    check(
      "tool_schema_kind_enum_complete",
      EXPECTED_KINDS.every((k) => kindEnum.includes(k)),
      JSON.stringify(kindEnum),
    );
  }
}

if (fails.length > 0) {
  console.error(
    `[smoke-test-post-order-intent-schema] FAIL (${fails.length} failures):\n  - ${fails.join("\n  - ")}`,
  );
  process.exit(1);
}

console.log(
  `[smoke-test-post-order-intent-schema] OK — 6 kinds, v1.3 version, optional field, validator branches, tool-schema enum all verified.`,
);
process.exit(0);
