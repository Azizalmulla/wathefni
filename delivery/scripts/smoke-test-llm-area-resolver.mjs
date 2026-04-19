#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Smoke test for the LLM area-resolver fallback (Option B).
//
// Uses an injected mock `fetchImpl` instead of calling real OpenAI so the
// test is fast, deterministic, and free to run in CI. Real OpenAI integration
// is validated manually once after deploy.
//
// Cases:
//   1. Disabled flag → returns unresolved without calling fetch
//   2. High-confidence valid response → status=resolved, should_learn=true
//   3. Medium-confidence response → status=suggested, should_learn=false
//   4. Low-confidence response → status=unresolved, area_id=null
//   5. Hallucinated area_id (not in candidates) → rejected as unresolved
//   6. Invalid JSON response → rejected as unresolved
//   7. Missing confidence field → rejected as unresolved
//   8. Cross-governorate high-confidence → downgraded to suggested
//   9. Budget exhaustion: per-conversation cap honored
//  10. Empty candidates list → unresolved without calling fetch
//  11. appendLearnedAlias: idempotent (second write is a no-op)
//  12. appendLearnedAlias: collision on same alias→different area rejected
// ---------------------------------------------------------------------------

import path from "node:path";
import os from "node:os";
import { promises as fs } from "node:fs";
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

const resolverMod = await loadTsModule("plugins/riders-tools/lib/llm-area-resolver.ts");
const learnedIoMod = await loadTsModule("plugins/riders-tools/lib/learned-aliases-io.ts");

const {
  isLlmAreaResolverEnabled,
  resolveAreaWithLlm,
  parseAndValidateModelOutput,
  buildSystemPrompt,
  buildUserPrompt,
  llmAreaResolverBudget,
} = resolverMod;

const { appendLearnedAlias, loadLearnedAliasesFile } = learnedIoMod;

const JLAIA_AREA = {
  id: 194,
  name_en: "Shalehat Jlea'a",
  name_ar: "شاليهات الجليعة",
  governorate: "Ahmadi",
};
const OTHER_AREA = {
  id: 10,
  name_en: "Jahra",
  name_ar: "الجهراء",
  governorate: "Jahra",
};
const SALMIYA_AREA = {
  id: 50,
  name_en: "Salmiya",
  name_ar: "السالمية",
  governorate: "Hawalli",
};

function makeCandidates() {
  return [
    { area: JLAIA_AREA, similarity: 0.62 },
    { area: OTHER_AREA, similarity: 0.41 },
    { area: SALMIYA_AREA, similarity: 0.33 },
  ];
}

function makeMockFetch(responseBody, options = {}) {
  return async (_url, _init) => {
    return {
      ok: options.ok !== false,
      status: options.status || 200,
      async text() {
        return typeof responseBody === "string"
          ? responseBody
          : JSON.stringify(responseBody);
      },
      async json() {
        if (typeof responseBody === "string") {
          return JSON.parse(responseBody);
        }
        return responseBody;
      },
    };
  };
}

function chatCompletionResponse(contentJsonString, usage = { prompt_tokens: 200, completion_tokens: 40 }) {
  return {
    choices: [{ message: { content: contentJsonString } }],
    usage,
  };
}

// -------- Case 1: disabled flag --------
{
  delete process.env.RIDERS_LLM_AREA_RESOLVER_ENABLED;
  assert(!isLlmAreaResolverEnabled(), "case1a: default should be disabled");
  let fetchCalled = false;
  const result = await resolveAreaWithLlm(
    { query: "Jlai3a", candidates: makeCandidates(), trigger: "not_found" },
    {
      openaiApiKey: "sk-test",
      fetchImpl: async () => {
        fetchCalled = true;
        return { ok: true, status: 200, async text() { return "{}"; }, async json() { return {}; } };
      },
    },
  );
  assert(result.status === "unresolved", "case1b: disabled returns unresolved");
  assert(!fetchCalled, "case1c: disabled must NOT call fetch");
}

// Enable the flag for the rest of the cases.
process.env.RIDERS_LLM_AREA_RESOLVER_ENABLED = "1";
assert(isLlmAreaResolverEnabled(), "flag enable sanity");

// -------- Case 2: high-confidence valid response --------
{
  const body = chatCompletionResponse(
    JSON.stringify({
      area_id: 194,
      confidence: "high",
      reasoning: "Jlai3a is Arabizi form of Jlea'a, 3 stands for the ع.",
    }),
  );
  const result = await resolveAreaWithLlm(
    { query: "Jlai3a", candidates: makeCandidates(), trigger: "not_found", conversationId: "c2" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(result.status === "resolved", `case2a: status resolved, got ${result.status}`);
  assert(result.area_id === 194, `case2b: area_id 194, got ${result.area_id}`);
  assert(result.confidence === "high", "case2c: confidence high");
  assert(result.should_learn === true, "case2d: should_learn true");
  assert(result.diagnostics.prompt_tokens === 200, "case2e: prompt_tokens populated");
  assert(
    typeof result.diagnostics.estimated_cost_usd === "number",
    "case2f: cost estimate present",
  );
}

// -------- Case 3: medium-confidence response --------
{
  const body = chatCompletionResponse(
    JSON.stringify({
      area_id: 194,
      confidence: "medium",
      reasoning: "plausible but similar to other form",
    }),
  );
  const result = await resolveAreaWithLlm(
    { query: "Jleia", candidates: makeCandidates(), trigger: "not_found", conversationId: "c3" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(result.status === "suggested", "case3a: status suggested");
  assert(result.should_learn === false, "case3b: medium does NOT learn");
}

// -------- Case 4: low-confidence response --------
{
  const body = chatCompletionResponse(
    JSON.stringify({ area_id: null, confidence: "low", reasoning: "no plausible match" }),
  );
  const result = await resolveAreaWithLlm(
    { query: "gibberishplace", candidates: makeCandidates(), trigger: "not_found", conversationId: "c4" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(result.status === "unresolved", "case4a: low → unresolved");
  assert(result.area_id === null, "case4b: area_id null");
  assert(result.should_learn === false, "case4c: should_learn false");
}

// -------- Case 5: hallucinated area_id --------
{
  const body = chatCompletionResponse(
    JSON.stringify({
      area_id: 999999,
      confidence: "high",
      reasoning: "fictional area",
    }),
  );
  const result = await resolveAreaWithLlm(
    { query: "mystery", candidates: makeCandidates(), trigger: "not_found", conversationId: "c5" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(
    result.status === "unresolved",
    `case5a: hallucinated area_id must be rejected (status=${result.status})`,
  );
  assert(result.diagnostics.fallback_used === true, "case5b: fallback marker set");
  assert(
    String(result.reasoning).includes("area_id_not_in_candidates"),
    "case5c: reason should cite area_id_not_in_candidates",
  );
}

// -------- Case 6: invalid JSON --------
{
  const body = chatCompletionResponse("this is not json at all");
  const result = await resolveAreaWithLlm(
    { query: "x", candidates: makeCandidates(), trigger: "not_found", conversationId: "c6" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(result.status === "unresolved", "case6a: invalid JSON → unresolved");
  assert(String(result.reasoning).includes("not_json"), "case6b: reason cites not_json");
}

// -------- Case 7: missing confidence --------
{
  const body = chatCompletionResponse(JSON.stringify({ area_id: 194, reasoning: "no conf" }));
  const result = await resolveAreaWithLlm(
    { query: "x", candidates: makeCandidates(), trigger: "not_found", conversationId: "c7" },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(result.status === "unresolved", "case7a: missing confidence → unresolved");
  assert(
    String(result.reasoning).includes("invalid_confidence"),
    "case7b: reason cites invalid_confidence",
  );
}

// -------- Case 8: cross-governorate high-confidence → downgraded --------
{
  const body = chatCompletionResponse(
    JSON.stringify({
      area_id: 194,
      confidence: "high",
      reasoning: "high match even though different gov",
    }),
  );
  const result = await resolveAreaWithLlm(
    {
      query: "Jlai3a",
      candidates: makeCandidates(),
      governorateHint: "Hawalli",
      trigger: "not_found",
      conversationId: "c8",
    },
    { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
  );
  assert(
    result.status === "suggested",
    `case8a: cross-gov high should downgrade to suggested, got ${result.status}`,
  );
  assert(result.confidence === "medium", "case8b: effective confidence medium");
  assert(result.should_learn === false, "case8c: cross-gov must not learn");
}

// -------- Case 9: per-conversation budget cap --------
{
  const body = chatCompletionResponse(
    JSON.stringify({ area_id: 194, confidence: "low", reasoning: "test" }),
  );
  // Default cap is 3 per conversation. Make 4 calls with same conversation id.
  for (let i = 0; i < 3; i++) {
    const res = await resolveAreaWithLlm(
      { query: `try${i}`, candidates: makeCandidates(), trigger: "not_found", conversationId: "c9" },
      { openaiApiKey: "sk-test", fetchImpl: makeMockFetch(body) },
    );
    assert(res.status === "unresolved", `case9.${i}: low conf unresolved`);
  }
  // 4th call must be budget-capped (fallback_used=true with budget reason)
  let fetchCalled = false;
  const capped = await resolveAreaWithLlm(
    { query: "try4", candidates: makeCandidates(), trigger: "not_found", conversationId: "c9" },
    {
      openaiApiKey: "sk-test",
      fetchImpl: async () => {
        fetchCalled = true;
        return { ok: true, status: 200, async text() { return "{}"; }, async json() { return chatCompletionResponse("{}"); } };
      },
    },
  );
  assert(
    capped.status === "unresolved" && !fetchCalled,
    "case9.4: 4th call must be short-circuited by budget without calling fetch",
  );
  assert(
    String(capped.reasoning).includes("per_conversation_cap_reached"),
    "case9.5: reason cites per_conversation_cap_reached",
  );
}

// -------- Case 10: empty candidates --------
{
  let fetchCalled = false;
  const result = await resolveAreaWithLlm(
    { query: "x", candidates: [], trigger: "not_found", conversationId: "c10" },
    {
      openaiApiKey: "sk-test",
      fetchImpl: async () => {
        fetchCalled = true;
        return { ok: true, status: 200, async text() { return ""; }, async json() { return {}; } };
      },
    },
  );
  assert(result.status === "unresolved", "case10a: empty candidates → unresolved");
  assert(!fetchCalled, "case10b: no fetch call when candidates empty");
  assert(String(result.reasoning).includes("no_candidates"), "case10c: reason cites no_candidates");
}

// -------- Cases 11 & 12: learned-aliases-io --------
{
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "riders-learned-"));
  const filePath = path.join(tmpDir, "pricing.resolver.learned-aliases.json");

  // First write: should succeed.
  const r1 = await appendLearnedAlias(
    {
      alias: "Jlai3a",
      area_id: 194,
      model: "gpt-4o-mini",
      confidence: "high",
      conversation_id: "c11",
      reasoning: "Arabizi form",
    },
    filePath,
  );
  assert(r1.written === true, "case11a: first write succeeds");

  // Same write again: idempotent skip.
  const r2 = await appendLearnedAlias(
    {
      alias: "Jlai3a",
      area_id: 194,
      model: "gpt-4o-mini",
      confidence: "high",
      conversation_id: "c11b",
      reasoning: "repeat",
    },
    filePath,
  );
  assert(r2.written === false, "case11b: duplicate is skipped");
  assert(
    r2.reason === "already_learned",
    `case11c: reason already_learned, got ${r2.reason}`,
  );

  // Same alias, different area → collision rejected.
  const r3 = await appendLearnedAlias(
    {
      alias: "Jlai3a",
      area_id: 200,
      model: "gpt-4o-mini",
      confidence: "high",
      conversation_id: "c12",
      reasoning: "wrong",
    },
    filePath,
  );
  assert(r3.written === false, "case12a: collision rejected");
  assert(
    String(r3.reason).startsWith("conflicts_with_existing_learned"),
    `case12b: reason conflicts (got ${r3.reason})`,
  );

  // Ensure file still only contains the one legit entry.
  const loaded = await loadLearnedAliasesFile(filePath);
  assert(loaded.aliases.length === 1, `case12c: file has 1 alias after collision, got ${loaded.aliases.length}`);
  assert(loaded.aliases[0].area_id === 194, "case12d: area_id preserved");

  await fs.rm(tmpDir, { recursive: true, force: true });
}

// -------- Prompt building sanity --------
{
  const sys = buildSystemPrompt();
  assert(typeof sys === "string" && sys.length > 100, "sys prompt non-trivial");
  assert(sys.includes("JSON"), "sys prompt mentions JSON");

  const user = buildUserPrompt({
    query: "Jlai3a",
    candidates: makeCandidates(),
    trigger: "not_found",
    governorateHint: "Ahmadi",
  });
  const parsed = JSON.parse(user);
  assert(parsed.customer_text === "Jlai3a", "user prompt contains customer_text");
  assert(Array.isArray(parsed.candidates), "user prompt contains candidates");
  assert(parsed.candidates.length === 3, "user prompt has 3 candidates");
  assert(parsed.other_leg_governorate_hint === "Ahmadi", "user prompt contains gov hint");
}

// -------- parseAndValidateModelOutput direct tests --------
{
  const candidates = makeCandidates();
  const ok = parseAndValidateModelOutput(
    JSON.stringify({ area_id: 194, confidence: "high", reasoning: "r" }),
    candidates,
  );
  assert(ok.ok && ok.data.area_id === 194, "parse ok high");
  const badId = parseAndValidateModelOutput(
    JSON.stringify({ area_id: 77, confidence: "high", reasoning: "r" }),
    candidates,
  );
  assert(!badId.ok && badId.reason === "area_id_not_in_candidates", "parse rejects bad id");
  const nullId = parseAndValidateModelOutput(
    JSON.stringify({ area_id: null, confidence: "low", reasoning: "r" }),
    candidates,
  );
  assert(nullId.ok && nullId.data.area_id === null, "parse accepts null area_id");
}

console.log("llm-area-resolver smoke passed");
