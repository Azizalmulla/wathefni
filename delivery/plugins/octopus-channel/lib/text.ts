// ---------------------------------------------------------------------------
// Wave 2a extraction: pure text / language / reply sanitization helpers.
// These are deterministic string transforms used by the inbound flow to
// scrub provider error strings and render the two safety-critical
// deterministic fallback replies (grace-window offer, provider-issue
// fallback). No I/O, no module-scope state.
//
// Scope note (2026-04-24 dead-code sweep): four greeting/service-style
// deterministic reply builders were deleted here because they had zero
// callers — greeting and related flows are fully LLM-authored now.
// The remaining deterministic builders (grace-window, provider-issue)
// stay because they fire on hard failure paths where the LLM is either
// unavailable or not trusted to author.
// ---------------------------------------------------------------------------

import { asTrimmedString } from "./normalize";

// Module-internal: used only by `sanitizeAgentReplyText` below. Demoted
// from `export` in the 2026-04-24 sweep when no external caller was found.
function isProviderErrorText(value: unknown): boolean {
  const text = asTrimmedString(value);
  if (!text) return false;
  const normalized = text.replace(/\s+/g, " ").trim();
  return (
    normalized.includes("An error occurred while processing your request") ||
    normalized.includes("help.openai.com") ||
    /Please include the request ID req_[a-zA-Z0-9]+/i.test(normalized)
  );
}

export function sanitizeAgentReplyText(replyText: unknown): {
  replyText: string;
  providerErrorSuppressed: boolean;
} {
  const text = asTrimmedString(replyText);
  if (!text) {
    return { replyText: "", providerErrorSuppressed: false };
  }
  const blocks = text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const filteredBlocks = blocks.filter((block) => !isProviderErrorText(block));
  const cleaned = filteredBlocks.join("\n\n").trim();
  if (cleaned) {
    return {
      replyText: cleaned,
      providerErrorSuppressed: filteredBlocks.length !== blocks.length,
    };
  }
  if (isProviderErrorText(text)) {
    return { replyText: "", providerErrorSuppressed: true };
  }
  return { replyText: text, providerErrorSuppressed: false };
}

/**
 * Decide whether the canonical-overwrite guard is allowed to fire on this
 * turn. The guard exists for ONE specific failure mode: the LLM called
 * get_price on THIS turn and produced a degenerate reply that lost the
 * route+price grounding (e.g. just "6.000 KWD"). In that case we resurrect
 * the canonical tool message.
 *
 * It must NOT fire when:
 *   1. The tool ran on a prior turn (stale lastToolTs). The original
 *      sessionIsRecent window of 5 minutes is far too generous for this
 *      guard; it must be turn-local (~30s).
 *   2. The conversation has moved past the fresh-quote phase. In `quoted`
 *      (follow-up Q&A on an existing quote), `collecting_booking_details`,
 *      `summary_shown`, `awaiting_confirmation`, or `order_submitted`, the
 *      LLM is answering a question or driving a booking forward — its
 *      natural-language reply is correct even when it mentions the price.
 *      Overwriting it produces the "AI re-emits the quote instead of
 *      answering" regression observed on 2026-04-19 13:42 (live).
 *
 * Stage at the call site is the PRE-promotion stage (the
 * `quoted`/`order_submitted` promotions happen AFTER the guard runs).
 * So the only stage where a fresh get_price legitimately deserves a
 * canonical overwrite is `idle` (a brand-new quote turn, before the
 * controller flips to `quoted`).
 */
export function isCanonicalOverwriteAllowed(params: {
  lastToolAgeMs: number;
  controllerStage: string | null | undefined;
  /** Maximum age in ms for the tool call to count as "this turn". */
  turnLocalWindowMs?: number;
}): { allowed: boolean; reason: string } {
  const turnWindow = params.turnLocalWindowMs ?? 30_000;
  if (!Number.isFinite(params.lastToolAgeMs)) {
    return { allowed: false, reason: "no_tool_session" };
  }
  if (params.lastToolAgeMs >= turnWindow) {
    return { allowed: false, reason: "tool_stale" };
  }
  const stage = params.controllerStage || "idle";
  if (stage !== "idle") {
    return { allowed: false, reason: `post_quote_stage:${stage}` };
  }
  return { allowed: true, reason: "fresh_quote_turn" };
}

// `looksLikePriceOnlyReply`, `containsArabic`, and `containsLatin` were
// deleted in the Step-3 guard-narrowing sweep. They only served the two
// stylistic branches of `shouldPreferCanonicalToolReply` (the script-swap
// and `get_price` "lossy" rewriters) which were both retired. Factual
// price correctness is enforced by the outbound price whitelist in
// `index.ts`, not by a phrasing-based substitute.

export function buildDeterministicGraceWindowReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "هلا! عندنا طلبك السابق محفوظ. تبون نكمل من وين وقفنا ولا تبون نبدأ من جديد؟"
    : "Hi! Your previous booking is still saved. Would you like to continue where you left off or start fresh?";
}

export function buildProviderIssueFallbackReply(language: "ar" | "en"): string {
  return language === "ar"
    ? "عذراً، عندنا مشكلة مؤقتة بالنظام حالياً. حاولوا بعد شوي، وإذا مستعجلين نقدر نحولكم للموظف."
    : "Sorry, we are having a temporary system issue right now. Please try again shortly, or we can hand you to a human agent.";
}
