// Outbound coverage-claim guard — Phase B (2026-04-24, log-only).
//
// Purpose
// -------
// Detect outbound replies that make a POSITIVE coverage claim ("we
// deliver to X" / "نوصل لـ X") about an area that is NOT in our live
// pricing sheet. The LLM has a grounded tool for this class of question
// (`check_area_coverage`); if the LLM authors a coverage claim without
// calling the tool, it is asserting a factual business claim from
// memory, which is exactly the class of error the prompt rewrite on
// 2026-04-24 was designed to prevent. This guard exists to observe when
// the LLM deviates from the rule so we can decide later whether to
// promote from log-only → block.
//
// Architecture fit
// ----------------
//   * LLM    — owns meaning + wording; primary path for coverage
//              answers is via `check_area_coverage`.
//   * Tool   — `check_area_coverage` returns grounded truth.
//   * Guard  — THIS module. Blocks / observes false factual claims.
//              Current deployment is LOG-ONLY; block mode is reserved
//              for a follow-up once false-positive rate is quantified.
//
// Why log-only first
// ------------------
// 1. Detector regexes are fuzzy across EN/AR/Arabizi. A v1 detector
//    will have false positives; blocking on v1 risks customer-visible
//    weirdness.
// 2. "Block and let the LLM retry" isn't a pattern that exists in
//    `outbound-verify` today — it's either pass-through or rewrite.
//    Introducing block requires retry infra. Log-only needs none.
// 3. Same pattern as Z2-V1 (`route_zero_distance` demotion): keep
//    detection, emit metric, flag-gated promotion to substitute later.
//    That playbook worked.
//
// Scope
// -----
// This module is **pure decision + read-only pricing-sheet lookup**. It
// never touches controller state, never mutates reply text, never
// throws outward. The caller wraps the evaluator in a try/catch so a
// guard bug cannot break the outbound pipeline.

import { promises as fs } from "node:fs";
import path from "node:path";
import url from "node:url";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type CoverageClaimPolarity = "positive" | "negative";
export type CoverageClaimLanguage = "en" | "ar";

export interface CoverageClaim {
  /** The claim shape we matched (e.g. `we_deliver_to`, `نوصل_لـ`). */
  pattern: string;
  /** The full verbatim phrase that triggered the match (bounded). */
  phrase: string;
  /** The area token extracted from the capture group (trimmed, untouched). */
  areaToken: string;
  language: CoverageClaimLanguage;
  polarity: CoverageClaimPolarity;
}

export type CoverageGuardAction =
  | "disabled_by_flag"
  | "no_claim_detected"
  | "negative_claim_skipped"
  | "grounded"
  | "ungrounded_log_only"
  | "ungrounded_would_block"
  | "evaluator_error";

export interface CoverageGuardDecision {
  action: CoverageGuardAction;
  claim: CoverageClaim | null;
  normalizedArea: string | null;
  /** Optional close-match area name from the sheet (for ungrounded claims). */
  nearestCoveredArea: string | null;
}

export interface CoverageGuardInputs {
  replyText: string;
  /** Value of `RIDERS_OUTBOUND_GUARD_COVERAGE` env var. */
  envValue: string | null | undefined;
  /** Injectable loader for tests; production callers use
   *  `loadCoveredAreaIndex` below. */
  loadIndex: () => Promise<CoveredAreaIndex>;
}

// ---------------------------------------------------------------------------
// Env-flag helper
// ---------------------------------------------------------------------------
//
// Three states:
//   * unset / "off" / "0" / "false"  → disabled, short-circuit PASS.
//   * "log" / "log_only"             → detect + log_only metric, no block.
//   * "on" / "block" / "1" / "true"  → reserved for future block promotion;
//                                      today still log-only but the metric
//                                      action is `ungrounded_would_block`
//                                      so we can measure impact before
//                                      flipping the real substitute wire.

type FlagMode = "off" | "log" | "block";

function readFlagMode(envValue: string | null | undefined): FlagMode {
  if (typeof envValue !== "string") return "off";
  const v = envValue.trim().toLowerCase();
  if (v === "log" || v === "log_only" || v === "observe") return "log";
  if (v === "on" || v === "block" || v === "1" || v === "true" || v === "enabled") return "block";
  return "off";
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------
//
// Deliberately narrow. We'd rather miss ambiguous phrasings than flag
// grounded replies. The capture group on each pattern isolates the area
// token; downstream logic normalizes + looks it up.
//
// We do NOT try to handle every possible phrasing. The goal is to
// catch the SHAPES the LLM most commonly uses when it's authoring a
// confident coverage claim. When we promote past log-only, we'll tune
// this list against production metrics.

// English positive claims.
//
// Each pattern is anchored on a coverage verb ("deliver", "cover",
// "serve", "ship", "service") OR a direct affirmation of an area
// ("<AREA> is fine / is covered / is in our coverage"). The capture
// group grabs 1–4 words of area token; a closing lookahead stops the
// capture at a natural phrase boundary so we don't greedily consume
// the rest of the sentence.
const EN_POSITIVE_PATTERNS: Array<{
  name: string;
  re: RegExp;
  group: number;
}> = [
  {
    name: "en.we_deliver_to",
    re: /\b(?:yes,?\s+)?we\s+(?:do\s+)?(?:deliver|cover|serve|ship|service|go)\s+(?:to\s+)?(?:the\s+)?([A-Za-z][A-Za-z' \-]{1,40}?)(?=[.,!?;:\n]|\s+(?:if|want|send|the|and|or|but|from|for|please|pickup|dropoff|drop\-?off|area)\b|$)/i,
    group: 1,
  },
  {
    name: "en.area_is_covered",
    re: /\b(?:the\s+)?([A-Za-z][A-Za-z' \-]{1,40}?)\s+(?:is|are)\s+(?:fine|covered|in\s+our\s+(?:coverage|list|areas?))\b/i,
    group: 1,
  },
  {
    name: "en.we_cover_area",
    re: /\b(?:yes,?\s+)?we\s+(?:cover|serve|have|reach)\s+([A-Za-z][A-Za-z' \-]{1,40}?)(?=[.,!?;:\n]|\s+(?:if|want|send|and|or|but|from|for|please|pickup|dropoff|area)\b|$)/i,
    group: 1,
  },
];

// Arabic positive claims. The Arabic verbs and their common colloquial
// variants. Note that Arabic has no word boundaries like `\b`, so we
// use explicit whitespace/punctuation delimiters and lookahead stops.
const AR_POSITIVE_PATTERNS: Array<{
  name: string;
  re: RegExp;
  group: number;
}> = [
  {
    // Matches `نوصل لـ <AREA>` / `نوصل لل<AREA>` / `نوصل ل<AREA>` /
    // `نوصل الى <AREA>`. The `لل` alternation is listed BEFORE the
    // single `ل` so the preposition+article contraction is consumed as
    // one unit — otherwise a greedy single-`ل` match leaves `ل` glued
    // to the area token ("للخالدية" → captured "لخالدية") and breaks
    // the sheet lookup.
    name: "ar.nuwassil_le",
    re: /(?:^|[\s،,.!؟?])(?:اي\s+|نعم\s+)?ن(?:و|ُو)?صل\s*(?:الى\s+|إلى\s+|لـ\s*|لل|ل\s*)([\u0600-\u06FF][\u0600-\u06FF' \-]{1,40}?)(?=[.،,!؟?:;\n]|\s+(?:اذا|إذا|ان|إن|ابي|تبي|تبين|من|الى|وين|و\s)|$)/u,
    group: 1,
  },
  {
    name: "ar.nakhdum_area",
    re: /(?:^|[\s،,.!؟?])ن(?:خ|َخ)دم\s+([\u0600-\u06FF][\u0600-\u06FF' \-]{1,40}?)(?=[.،,!؟?:;\n]|\s+(?:اذا|إذا|ان|إن|من|الى|و\s)|$)/u,
    group: 1,
  },
  {
    name: "ar.area_dimn_manaatiq",
    re: /(?:^|[\s،,.!؟?])([\u0600-\u06FF][\u0600-\u06FF' \-]{1,40}?)\s+(?:ضمن|من)\s+مناطق(?:نا|ن)/u,
    group: 1,
  },
  {
    name: "ar.naam_nuwassil",
    re: /(?:^|[\s،,.!؟?])(?:اي|نعم)\s+نوصل\s+([\u0600-\u06FF][\u0600-\u06FF' \-]{1,40}?)(?=[.،,!؟?:;\n]|\s+(?:اذا|إذا|ان|ابي|تبي|من)|$)/u,
    group: 1,
  },
];

// Negative markers — if ANY of these appear in the reply, we classify
// the claim as negative and skip the guard. Negative coverage statements
// ("we don't deliver to X") are honest and self-consistent; they are
// not the class we're watching for.
const EN_NEGATIVE_RE =
  /\b(?:don'?t|do\s+not|won'?t|can'?t|cannot|will\s+not|unfortunately|sorry|not\s+(?:in\s+our|yet|available|covered)|outside\s+our|beyond\s+our|isn'?t\s+(?:in|covered))\b/i;
const AR_NEGATIVE_RE = /(?:للأسف|للاسف|ما\s*نوصل|مانوصل|مو\s*ضمن|ليس\s*ضمن|ما\s*نخدم|ما\s*نغطي|آسفين)/u;

// Area-token stopwords: if the captured "area" is one of these generic
// nouns, skip the guard. Avoids flagging grounded replies like "we
// cover most areas" / "we serve all of Kuwait".
const EN_STOPWORD_TOKENS = new Set(
  [
    "all",
    "most",
    "many",
    "several",
    "multiple",
    "various",
    "every",
    "areas",
    "the areas",
    "locations",
    "places",
    "kuwait",
    "kw",
    "the whole",
    "this",
    "that",
    "these",
    "those",
    "you",
    "them",
    "us",
    "our",
    "your",
    "anywhere",
    "everywhere",
  ].map((s) => s.toLowerCase()),
);

const AR_STOPWORD_TOKENS = new Set([
  "كل",
  "كل المناطق",
  "المناطق",
  "كثير",
  "أغلب",
  "اغلب",
  "معظم",
  "الكويت",
  "كويت",
  "لك",
  "لكم",
  "لكي",
]);

function containsArabicScript(s: string): boolean {
  return /[\u0600-\u06FF]/.test(s);
}

/**
 * Detect the first positive coverage claim in a reply. Returns `null`
 * if no positive claim matched OR the reply contains a negative
 * marker (which short-circuits even if a positive phrase also matched,
 * to avoid flagging "we don't deliver to Messilah but we cover Salwa"
 * as two competing claims).
 *
 * Pure function — no I/O, no globals.
 */
export function detectCoverageClaim(replyText: string): CoverageClaim | null {
  if (!replyText || typeof replyText !== "string") return null;
  const text = replyText.trim();
  if (text.length === 0 || text.length > 800) return null;

  const arabic = containsArabicScript(text);

  // Negative short-circuit. Checked first because a negative claim is
  // the honest case — no need to flag it.
  if (arabic && AR_NEGATIVE_RE.test(text)) return null;
  if (!arabic && EN_NEGATIVE_RE.test(text)) return null;

  // Try language-appropriate patterns first, fall back to the other
  // language patterns as a safety net (bilingual replies exist).
  const primary = arabic ? AR_POSITIVE_PATTERNS : EN_POSITIVE_PATTERNS;
  const secondary = arabic ? EN_POSITIVE_PATTERNS : AR_POSITIVE_PATTERNS;
  const primaryLang: CoverageClaimLanguage = arabic ? "ar" : "en";
  const secondaryLang: CoverageClaimLanguage = arabic ? "en" : "ar";

  for (const group of [
    { patterns: primary, lang: primaryLang },
    { patterns: secondary, lang: secondaryLang },
  ]) {
    for (const { name, re, group: captureIdx } of group.patterns) {
      const m = text.match(re);
      if (!m) continue;
      const captured = (m[captureIdx] || "").trim();
      if (!captured) continue;
      const normalizedToken = captured.toLowerCase();
      // Stopword check — match on the FULL token AND on its first
      // word. The regex greedily captures up to the next stop
      // boundary, so a generic phrase like "most areas in Kuwait"
      // arrives as the multi-word token. Checking the first word
      // catches the class without false-positive-ing on area names
      // that happen to contain a common noun (e.g. "South Surra").
      const firstWordEn = normalizedToken.split(/\s+/)[0] || "";
      const firstWordAr = captured.split(/\s+/)[0] || "";
      const isStop =
        group.lang === "en"
          ? EN_STOPWORD_TOKENS.has(normalizedToken) ||
            EN_STOPWORD_TOKENS.has(firstWordEn)
          : AR_STOPWORD_TOKENS.has(captured) ||
            AR_STOPWORD_TOKENS.has(firstWordAr);
      if (isStop) continue;
      return {
        pattern: name,
        phrase: m[0].trim(),
        areaToken: captured,
        language: group.lang,
        polarity: "positive",
      };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Covered-area index (lazy-cached load of the published pricing sheet)
// ---------------------------------------------------------------------------
//
// The sheet is updated infrequently (manual admin action + redeploy);
// caching forever per process is fine. If that changes, the guard can
// be extended with a mtime check or invalidation signal.

export interface CoveredAreaIndex {
  /** Normalized lowercase English names. */
  en: Set<string>;
  /** Normalized Arabic names (ال prefix stripped, hamza/taa-marbouta normalized). */
  ar: Set<string>;
  /** Original {en, ar} pairs for best-match suggestions. */
  areas: ReadonlyArray<{ nameEn: string; nameAr: string }>;
  /** Where the index was loaded from (for diagnostics). */
  source: string;
}

// Exported with `__` prefix so tests can build an index that matches
// the production normalization exactly. Not part of the public API.
export function __normalizeEnForTests(s: string): string {
  return normalizeEn(s);
}
export function __normalizeArForTests(s: string): string {
  return normalizeAr(s);
}

function normalizeEn(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[^\w\s'-]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function normalizeAr(s: string): string {
  return s
    .replace(/[أإآ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/[ًٌٍَُِّْ]/g, "")
    .replace(/^ال/, "")
    .replace(/\s+/g, " ")
    .trim();
}

let cachedIndex: Promise<CoveredAreaIndex> | null = null;

function defaultPricingPath(): string {
  const overrideDir =
    (globalThis as any).process?.env?.RIDERS_WORKSPACE_DIR ||
    (globalThis as any).process?.env?.RIDERS_PRICING_DIR ||
    null;
  if (typeof overrideDir === "string" && overrideDir.trim().length > 0) {
    return path.join(overrideDir, "data", "pricing.published.json");
  }
  // Fall back to the source-tree relative path (same constant
  // `plugins/riders-tools/index.ts` uses at module init).
  return url.fileURLToPath(
    new URL(
      "../../workspaces/riders/data/pricing.published.json",
      import.meta.url,
    ),
  );
}

export async function loadCoveredAreaIndex(): Promise<CoveredAreaIndex> {
  if (!cachedIndex) {
    cachedIndex = (async (): Promise<CoveredAreaIndex> => {
      const pricingPath = defaultPricingPath();
      const raw = await fs.readFile(pricingPath, "utf8");
      const data = JSON.parse(raw);
      const areasSource: any[] = Array.isArray(data?.areas)
        ? data.areas
        : Array.isArray(data?.data?.areas)
          ? data.data.areas
          : [];
      const en = new Set<string>();
      const ar = new Set<string>();
      const areas: Array<{ nameEn: string; nameAr: string }> = [];
      for (const a of areasSource) {
        const nameEn = typeof a?.name_en === "string" ? a.name_en : "";
        const nameAr = typeof a?.name_ar === "string" ? a.name_ar : "";
        if (nameEn) en.add(normalizeEn(nameEn));
        if (nameAr) ar.add(normalizeAr(nameAr));
        if (nameEn || nameAr) areas.push({ nameEn, nameAr });
      }
      return { en, ar, areas, source: pricingPath };
    })().catch((err) => {
      // On failure, blow the cache so the next call retries (avoids
      // a permanent silent hole if the disk was briefly unavailable).
      cachedIndex = null;
      throw err;
    });
  }
  return cachedIndex;
}

/** Test helper — drops the module-level cache. Never called in prod. */
export function __resetCoveredAreaIndexCacheForTests(): void {
  cachedIndex = null;
}

// ---------------------------------------------------------------------------
// Evaluation
// ---------------------------------------------------------------------------

export async function evaluateOutboundCoverageGuard(
  inputs: CoverageGuardInputs,
): Promise<CoverageGuardDecision> {
  const mode = readFlagMode(inputs.envValue);
  if (mode === "off") {
    return {
      action: "disabled_by_flag",
      claim: null,
      normalizedArea: null,
      nearestCoveredArea: null,
    };
  }

  const claim = detectCoverageClaim(inputs.replyText);
  if (!claim) {
    return {
      action: "no_claim_detected",
      claim: null,
      normalizedArea: null,
      nearestCoveredArea: null,
    };
  }

  // Defense-in-depth: the detector already short-circuits on negative
  // markers, but if a future refactor adds polarity directly without
  // the short-circuit, this keeps the guard honest.
  if (claim.polarity === "negative") {
    return {
      action: "negative_claim_skipped",
      claim,
      normalizedArea: null,
      nearestCoveredArea: null,
    };
  }

  let index: CoveredAreaIndex;
  try {
    index = await inputs.loadIndex();
  } catch {
    return {
      action: "evaluator_error",
      claim,
      normalizedArea: null,
      nearestCoveredArea: null,
    };
  }

  const normalized =
    claim.language === "en"
      ? normalizeEn(claim.areaToken)
      : normalizeAr(claim.areaToken);

  const grounded =
    claim.language === "en" ? index.en.has(normalized) : index.ar.has(normalized);

  if (grounded) {
    return {
      action: "grounded",
      claim,
      normalizedArea: normalized,
      nearestCoveredArea: null,
    };
  }

  // Not in the sheet — this is the case we care about. Find a close
  // suggestion so the metric has actionable context (e.g. "Messilah"
  // didn't match; closest was "Mishrif").
  const nearest = findNearestCoveredArea(normalized, claim.language, index);

  return {
    action: mode === "block" ? "ungrounded_would_block" : "ungrounded_log_only",
    claim,
    normalizedArea: normalized,
    nearestCoveredArea: nearest,
  };
}

function findNearestCoveredArea(
  normalized: string,
  language: CoverageClaimLanguage,
  index: CoveredAreaIndex,
): string | null {
  if (!normalized) return null;
  let best: { name: string; score: number } | null = null;
  for (const area of index.areas) {
    const candidate =
      language === "en" ? normalizeEn(area.nameEn) : normalizeAr(area.nameAr);
    if (!candidate) continue;
    if (candidate === normalized) {
      return language === "en" ? area.nameEn : area.nameAr;
    }
    // Cheap similarity: shared-prefix length / max length. Good enough
    // for the "Messilah → Mishrif" class without pulling in a Damerau
    // dependency. We're only surfacing a hint, not making a decision.
    const score = prefixSimilarity(normalized, candidate);
    if (score >= 0.5 && (!best || score > best.score)) {
      best = {
        name: language === "en" ? area.nameEn : area.nameAr,
        score,
      };
    }
  }
  return best ? best.name : null;
}

function prefixSimilarity(a: string, b: string): number {
  const max = Math.max(a.length, b.length);
  if (max === 0) return 0;
  let i = 0;
  const limit = Math.min(a.length, b.length);
  while (i < limit && a[i] === b[i]) i++;
  return i / max;
}

// ---------------------------------------------------------------------------
// Metric formatter
// ---------------------------------------------------------------------------

export function formatCoverageGuardMetric(
  decision: CoverageGuardDecision,
  context: { conversationId?: string | null; replyLength?: number },
): string {
  const parts = [
    `[metric] outbound_verify.coverage_claim`,
    `action=${decision.action}`,
  ];
  if (decision.claim) {
    parts.push(`pattern=${decision.claim.pattern}`);
    parts.push(`language=${decision.claim.language}`);
    parts.push(`area_token=${JSON.stringify(decision.claim.areaToken)}`);
  }
  if (decision.normalizedArea) {
    parts.push(`normalized=${JSON.stringify(decision.normalizedArea)}`);
  }
  if (decision.nearestCoveredArea) {
    parts.push(`nearest=${JSON.stringify(decision.nearestCoveredArea)}`);
  }
  if (context.conversationId) {
    parts.push(`conversation=${context.conversationId}`);
  }
  if (typeof context.replyLength === "number") {
    parts.push(`reply_length=${context.replyLength}`);
  }
  return parts.join(" ");
}
