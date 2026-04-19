// ---------------------------------------------------------------------------
// LLM fallback area resolver (Option B).
//
// Why this exists
// ---------------
// The deterministic pipeline (alias table → fuzzy match → embeddings) handles
// 95%+ of Kuwaiti area inputs. But customers will always type something we
// didn't predict: a brand new colloquial form, a mall nickname, a tribal
// area name, a novel Arabizi digit placement. This module is the safety net
// for that long tail.
//
// Contract
// --------
// - Called ONLY when the deterministic pipeline returned not_found or an
//   ambiguous match that couldn't self-resolve. Not called on every query.
// - Given: customer's raw text, a shortlist of top-K candidate areas
//   (pre-filtered by deterministic similarity scoring), and optional
//   governorate hint (e.g. from a previously-resolved pickup).
// - Returns: { status, area_id, confidence, reasoning, should_learn }
//   where `should_learn` only goes true on high-confidence exact-ID matches.
// - Strict JSON output: uses OpenAI's native response_format json_object,
//   temperature=0, and we validate the returned area_id against the real
//   catalog before accepting it. If the LLM hallucinates an area_id that
//   doesn't exist, we reject — no silent corruption.
//
// Safety layers (defense in depth)
// --------------------------------
// 1. Kill switch: RIDERS_LLM_AREA_RESOLVER_ENABLED=0 disables the whole path.
// 2. Cost cap: max calls per conversation + global daily cap.
// 3. Schema enforcement: JSON mode + post-parse validation.
// 4. Catalog validation: returned area_id must exist in the 222-area catalog.
// 5. Governorate sanity: if a hint is provided, reject matches in a wildly
//    different governorate unless confidence is "high" AND reasoning is
//    explicit about why the customer crossed governorates.
// 6. Collision check: learned aliases must not collide with existing
//    canonical lookup keys for a DIFFERENT area (same logic as the generator).
// 7. Confidence gating:
//       high   → resolve directly + learn alias (if safe)
//       medium → return as suggestion ("Do you mean X?") + don't learn
//       low    → fall through to area_not_found (don't pretend we know)
//
// Learn-back
// ----------
// High-confidence acceptances write an entry to
// `pricing.resolver.learned-aliases.json` (SEPARATE file from the
// hand-curated overlay). On next service restart, the resolver merges
// this file on top of the main overlay. Deploys preserve the learned
// file (it lives on the VPS data dir, not in git). Periodically a human
// can promote learned aliases into the main overlay for permanence.
// ---------------------------------------------------------------------------

import type { PricingArea } from "./types";

export type LlmAreaResolverTrigger = "not_found" | "ambiguous_fallback";

export interface LlmAreaResolverInput {
  query: string;
  candidates: Array<{ area: PricingArea; similarity: number }>;
  /** If the other half of the delivery was resolved, its governorate is a
   *  strong hint. Pickup in Hawalli + unknown dropoff → the dropoff is more
   *  likely a Hawalli-local colloquial than a distant area's misspelling. */
  governorateHint?: string | null;
  trigger: LlmAreaResolverTrigger;
  /** For logging/rate-limiting only. Never sent to the LLM. */
  conversationId?: string | null;
}

export type LlmAreaConfidence = "high" | "medium" | "low";

export interface LlmAreaResolverResult {
  status: "resolved" | "suggested" | "unresolved";
  area_id: number | null;
  confidence: LlmAreaConfidence;
  reasoning: string;
  /** True only when we'd be safe to persist this as a deterministic alias. */
  should_learn: boolean;
  /** True when we actually did persist a new alias row. */
  learned: boolean;
  /** Shape of the LLM's raw response, retained for debugging / audits. */
  raw_model_output: unknown;
  /** Observability: tokens/latency/cost for the call. */
  diagnostics: {
    model: string | null;
    latency_ms: number;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    estimated_cost_usd: number | null;
    fallback_used: boolean;
  };
}

const DEFAULT_MODEL = "gpt-4o-mini";
const DEFAULT_TIMEOUT_MS = 6_000;
const DEFAULT_MAX_TOKENS = 200;

// Token pricing for gpt-4o-mini (2026 rates). Used for observability only;
// we do not enforce a hard per-call cap on cost because we already cap by
// call count (see llmAreaResolverBudget).
const MODEL_PRICING: Record<string, { prompt: number; completion: number }> = {
  "gpt-4o-mini": { prompt: 0.15 / 1_000_000, completion: 0.60 / 1_000_000 },
  "gpt-4o": { prompt: 2.50 / 1_000_000, completion: 10.0 / 1_000_000 },
};

export function isLlmAreaResolverEnabled(
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  const raw = env.RIDERS_LLM_AREA_RESOLVER_ENABLED;
  if (raw == null) return false; // default OFF until you flip it — safer.
  const s = String(raw).trim().toLowerCase();
  if (["1", "true", "on", "yes", "enabled"].includes(s)) return true;
  return false;
}

// Per-conversation + global call budget. Keeps rogue loops from draining
// the OpenAI account if something upstream is misbehaving.
class LlmAreaResolverBudget {
  private perConversation = new Map<string, number>();
  private globalCount = 0;
  private globalResetAt = Date.now() + 24 * 60 * 60 * 1000;

  constructor(
    private readonly maxPerConversation = 3,
    private readonly maxGlobalPerDay = 500,
  ) {}

  tryConsume(conversationId: string | null): { allowed: boolean; reason?: string } {
    if (Date.now() > this.globalResetAt) {
      this.globalCount = 0;
      this.globalResetAt = Date.now() + 24 * 60 * 60 * 1000;
      this.perConversation.clear();
    }
    if (this.globalCount >= this.maxGlobalPerDay) {
      return { allowed: false, reason: "global_daily_cap_reached" };
    }
    const key = conversationId || "__global__";
    const current = this.perConversation.get(key) || 0;
    if (current >= this.maxPerConversation) {
      return { allowed: false, reason: "per_conversation_cap_reached" };
    }
    this.perConversation.set(key, current + 1);
    this.globalCount += 1;
    return { allowed: true };
  }
}

export const llmAreaResolverBudget = new LlmAreaResolverBudget();

function estimateCostUsd(
  model: string,
  promptTokens: number | null,
  completionTokens: number | null,
): number | null {
  const pricing = MODEL_PRICING[model];
  if (!pricing) return null;
  const p = (promptTokens ?? 0) * pricing.prompt;
  const c = (completionTokens ?? 0) * pricing.completion;
  return p + c;
}

// ---------------------------------------------------------------------------
// Prompt construction. Designed to make the LLM's job small and auditable:
// we do NOT send the entire 222-area catalog. We send a shortlist of the
// top-K deterministic candidates + key metadata. That bounds the LLM's
// decision to options we already think are plausible, lowering the
// hallucination surface.
// ---------------------------------------------------------------------------

export function buildSystemPrompt(): string {
  return [
    "You are an area-name disambiguator for Riders, a delivery service in Kuwait.",
    "Customers type area names in English, Arabic, or Arabizi (Latin letters with digits: 3=ع, 7=ح, 5=خ, 2=ء, 9=س, 6=ت).",
    "Given the customer's raw text and a shortlist of candidate areas from our catalog, pick the one they MOST LIKELY meant.",
    "Respect these hard rules:",
    "1. You may ONLY return an area_id that appears in the candidates list. Do NOT invent area_ids.",
    "2. If none of the candidates are a plausible match, return area_id=null with confidence=low.",
    "3. Set confidence=high ONLY when you are very confident (exact phonetic match, obvious colloquial form, transliteration is unambiguous).",
    "4. Set confidence=medium when you have a preferred candidate but the customer should probably confirm.",
    "5. Set confidence=low when multiple candidates are equally plausible or none feel right.",
    "6. Respond ONLY in this JSON shape: {\"area_id\": number|null, \"confidence\": \"high\"|\"medium\"|\"low\", \"reasoning\": string}.",
    "7. The reasoning field must be ≤30 words and factual (e.g. \"Jlai3a is the Arabizi form of Jlea'a with 3 representing ع\").",
  ].join("\n");
}

export function buildUserPrompt(input: LlmAreaResolverInput): string {
  const shortlist = input.candidates.slice(0, 10).map((c, i) => ({
    area_id: c.area.id,
    name_en: c.area.name_en,
    name_ar: c.area.name_ar,
    governorate: c.area.governorate,
    similarity_score: Number(c.similarity.toFixed(3)),
    rank: i + 1,
  }));
  const payload: Record<string, unknown> = {
    customer_text: input.query,
    candidates: shortlist,
    trigger: input.trigger,
  };
  if (input.governorateHint) {
    payload.other_leg_governorate_hint = input.governorateHint;
  }
  return JSON.stringify(payload);
}

// ---------------------------------------------------------------------------
// Response validation: the contract between us and the LLM is strict.
// Anything that doesn't match the schema gets rejected into an "unresolved"
// result rather than being trusted.
// ---------------------------------------------------------------------------

export function parseAndValidateModelOutput(
  raw: string,
  candidates: LlmAreaResolverInput["candidates"],
): {
  ok: boolean;
  reason?: string;
  data?: { area_id: number | null; confidence: LlmAreaConfidence; reasoning: string };
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, reason: "not_json" };
  }
  if (!parsed || typeof parsed !== "object") {
    return { ok: false, reason: "not_object" };
  }
  const obj = parsed as Record<string, unknown>;
  const { area_id, confidence, reasoning } = obj;

  if (confidence !== "high" && confidence !== "medium" && confidence !== "low") {
    return { ok: false, reason: "invalid_confidence" };
  }
  if (typeof reasoning !== "string") {
    return { ok: false, reason: "missing_reasoning" };
  }

  if (area_id === null) {
    return { ok: true, data: { area_id: null, confidence, reasoning } };
  }
  if (typeof area_id !== "number" || !Number.isInteger(area_id)) {
    return { ok: false, reason: "invalid_area_id_type" };
  }

  // Catalog guard: the LLM may ONLY pick from the candidates we gave it.
  // If it picks an area_id outside the shortlist, treat it as hallucination.
  const allowedIds = new Set(candidates.map((c) => c.area.id));
  if (!allowedIds.has(area_id)) {
    return { ok: false, reason: "area_id_not_in_candidates" };
  }

  return { ok: true, data: { area_id, confidence, reasoning } };
}

// ---------------------------------------------------------------------------
// The top-level resolver. This is what pricing.ts calls.
// ---------------------------------------------------------------------------

export interface LlmAreaResolverDeps {
  openaiApiKey: string | null;
  model?: string;
  timeoutMs?: number;
  /** Optional override for the fetch impl (tests). */
  fetchImpl?: typeof fetch;
  /** Optional clock override (tests). */
  now?: () => number;
}

export async function resolveAreaWithLlm(
  input: LlmAreaResolverInput,
  deps: LlmAreaResolverDeps,
): Promise<LlmAreaResolverResult> {
  const model = deps.model || DEFAULT_MODEL;
  const now = deps.now || Date.now;
  const fetchFn = deps.fetchImpl || fetch;
  const start = now();

  const diagnostics = {
    model,
    latency_ms: 0,
    prompt_tokens: null as number | null,
    completion_tokens: null as number | null,
    estimated_cost_usd: null as number | null,
    fallback_used: false,
  };

  if (!isLlmAreaResolverEnabled()) {
    return unresolved("disabled", diagnostics, null, now, start);
  }
  if (!deps.openaiApiKey) {
    return unresolved("no_api_key", diagnostics, null, now, start);
  }
  if (input.candidates.length === 0) {
    return unresolved("no_candidates", diagnostics, null, now, start);
  }

  const budget = llmAreaResolverBudget.tryConsume(input.conversationId || null);
  if (!budget.allowed) {
    return unresolved(budget.reason || "budget_exhausted", diagnostics, null, now, start);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    deps.timeoutMs || DEFAULT_TIMEOUT_MS,
  );

  let rawContent = "";
  try {
    const response = await fetchFn(
      "https://api.openai.com/v1/chat/completions",
      {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${deps.openaiApiKey}`,
        },
        body: JSON.stringify({
          model,
          temperature: 0,
          max_tokens: DEFAULT_MAX_TOKENS,
          response_format: { type: "json_object" },
          messages: [
            { role: "system", content: buildSystemPrompt() },
            { role: "user", content: buildUserPrompt(input) },
          ],
        }),
      },
    );
    if (!response.ok) {
      const errText = await response.text().catch(() => "");
      return unresolved(
        `openai_http_${response.status}_${errText.slice(0, 120)}`,
        diagnostics,
        null,
        now,
        start,
      );
    }
    const json: any = await response.json();
    rawContent = json?.choices?.[0]?.message?.content || "";
    diagnostics.prompt_tokens = json?.usage?.prompt_tokens ?? null;
    diagnostics.completion_tokens = json?.usage?.completion_tokens ?? null;
    diagnostics.estimated_cost_usd = estimateCostUsd(
      model,
      diagnostics.prompt_tokens,
      diagnostics.completion_tokens,
    );
  } catch (err) {
    return unresolved(
      `fetch_failed_${err instanceof Error ? err.message : String(err)}`,
      diagnostics,
      null,
      now,
      start,
    );
  } finally {
    clearTimeout(timeoutId);
  }

  const validation = parseAndValidateModelOutput(rawContent, input.candidates);
  if (!validation.ok) {
    return unresolved(
      `model_validation_${validation.reason}`,
      diagnostics,
      rawContent,
      now,
      start,
    );
  }

  const { area_id, confidence, reasoning } = validation.data!;
  diagnostics.latency_ms = now() - start;

  if (area_id === null || confidence === "low") {
    return {
      status: "unresolved",
      area_id: null,
      confidence,
      reasoning,
      should_learn: false,
      learned: false,
      raw_model_output: rawContent,
      diagnostics,
    };
  }

  const pickedCandidate = input.candidates.find((c) => c.area.id === area_id)!;

  // Governorate sanity check: if the customer's other leg was in Hawalli
  // and the LLM picked a farm in Wafra (2 governorates away), that's a
  // red flag. We downgrade high→medium to force a confirmation turn.
  let effectiveConfidence = confidence;
  if (input.governorateHint && confidence === "high") {
    const hintNormalized = input.governorateHint.toLowerCase().replace(/governorate/g, "").trim();
    const pickedGov = pickedCandidate.area.governorate.toLowerCase().replace(/governorate/g, "").trim();
    if (hintNormalized && pickedGov && hintNormalized !== pickedGov) {
      // Same delivery crossing governorates is common and fine — we're
      // NOT enforcing same-gov. We just downgrade confidence so the AI
      // asks for confirmation when the LLM thinks "high" across govs.
      effectiveConfidence = "medium";
    }
  }

  const status: "resolved" | "suggested" =
    effectiveConfidence === "high" ? "resolved" : "suggested";
  const should_learn = effectiveConfidence === "high";

  return {
    status,
    area_id,
    confidence: effectiveConfidence,
    reasoning,
    should_learn,
    learned: false, // set to true by the caller after writing to the file
    raw_model_output: rawContent,
    diagnostics,
  };
}

function unresolved(
  reason: string,
  diagnostics: LlmAreaResolverResult["diagnostics"],
  rawModelOutput: unknown,
  now: () => number,
  start: number,
): LlmAreaResolverResult {
  diagnostics.latency_ms = now() - start;
  return {
    status: "unresolved",
    area_id: null,
    confidence: "low",
    reasoning: `fallback_used: ${reason}`,
    should_learn: false,
    learned: false,
    raw_model_output: rawModelOutput,
    diagnostics: { ...diagnostics, fallback_used: true },
  };
}

// ---------------------------------------------------------------------------
// Learn-back: append a new alias to pricing.resolver.learned-aliases.json.
// ---------------------------------------------------------------------------

export interface LearnedAliasesFile {
  _meta: {
    version: number;
    last_updated_at: string | null;
  };
  aliases: Array<{
    alias: string;
    area_id: number;
    _source: "llm_learned";
    _learned_at: string;
    _model: string | null;
    _confidence: LlmAreaConfidence;
    _conversation_id: string | null;
    _reasoning: string;
  }>;
}

export function emptyLearnedAliasesFile(): LearnedAliasesFile {
  return {
    _meta: { version: 1, last_updated_at: null },
    aliases: [],
  };
}

// collisionCheckLearnedAlias is exposed so the caller can validate a
// candidate alias string against the ALREADY-LOADED resolver config.
// This keeps the resolver config the single source of truth for what
// counts as a collision.
export function collisionCheckLearnedAlias(
  alias: string,
  targetAreaId: number,
  resolverLookupKeysFn: (s: string) => Set<string>,
  keyOwner: Map<string, number>,
): { ok: boolean; reason?: string; key?: string; owner?: number } {
  for (const k of resolverLookupKeysFn(alias)) {
    const owner = keyOwner.get(k);
    if (owner && owner !== targetAreaId) {
      return { ok: false, reason: "collides", key: k, owner };
    }
  }
  return { ok: true };
}
