/**
 * Reuse-intent classifier — pure text → intent mapping for the
 * `carry_over_from_last_order` fast-path.
 *
 * When the customer writes a short phrase asking to reuse details from their
 * previous order ("same as last time", "نفس الأرقام", "same sender and
 * recipient"), this module returns the explicit bucket list the orchestrator
 * should copy from `CustomerProfile.last_successful_order`.
 *
 * Architecture notes:
 * - This is a fast-path, NOT the load-bearing fix. The LLM still has the
 *   `carry_over_from_last_order` tool and SKILL.md guidance to call it
 *   directly. This module exists so the orchestrator can pre-emit the op
 *   deterministically when the customer's message is unambiguous — closing
 *   the gap where the LLM recognizes the intent in prose but fails to emit
 *   the tool call (the exact bug in the transcript on 2026-04-19).
 * - Returns `null` for ambiguous or unrelated text. The orchestrator falls
 *   back to the LLM's judgment in that case — never guess.
 * - Buckets are always explicit; "same everything" maps to
 *   `["sender_identity", "recipient_identity"]`. `payer` is left out of V1
 *   — the backend payer concept is order-level and not yet wired into the
 *   reuse tool. Location buckets (`pickup_location`, `delivery_location`)
 *   are intentionally NOT matched here in V1 — the drain handler returns
 *   `ask_fresh` for those, so firing them from the fast-path would just
 *   produce a "please re-send the address" reply which the LLM handles
 *   better with conversational context. We'll add address-phrase matching
 *   when V2 lands real location carry-over.
 * - No side effects, no I/O. Pure function so it's trivially testable.
 */

import type { CarryOverBucket } from "./responder-state-ops";

/** The subset of `CarryOverBucket` the V1 classifier is allowed to emit.
 *  Address buckets are deliberately excluded — see header for rationale. */
export type ReuseBucket = Extract<
  CarryOverBucket,
  "sender_identity" | "recipient_identity" | "payer"
>;

export type ReuseIntent = {
  /** Which buckets the customer asked to reuse. Non-empty when `kind` is
   *  `"carry_over"`. */
  buckets: ReuseBucket[];
  /** Machine-readable classification. `"carry_over"` means we detected an
   *  explicit reuse-intent and the orchestrator should pre-emit the op.
   *  `"none"` means nothing matched — fall through to the LLM. */
  kind: "carry_over" | "none";
  /** Machine-readable reason the classifier chose this output. */
  reason: string;
  /** The verbatim substring that triggered the match. Used as the
   *  `source_quote` when the op is emitted. Null when `kind === "none"`. */
  matchedText: string | null;
};

/**
 * English phrases that signal "reuse the customer + recipient identity from
 * the last successful order". These are matched case-insensitive on the
 * collapsed/whitespace-normalized input. Each pattern returns the bucket set
 * it implies.
 *
 * Patterns are intentionally narrow: they must be unambiguous enough that
 * firing a pre-LLM carry-over op is always safe. Partial/ambiguous matches
 * fall through to the LLM.
 */
const EN_PATTERNS: Array<{
  rx: RegExp;
  buckets: ReuseBucket[];
  reason: string;
}> = [
  {
    rx: /\bsame\s+(names?\s+and\s+(number|numbers|phones?|contacts?)|details|info(rmation)?|(as\s+)?last\s+(order|time|one))\b/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "en_same_as_last",
  },
  {
    rx: /\b(same|identical)\s+(sender\s+and\s+recipient|recipient\s+and\s+sender)\b/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "en_same_sender_and_recipient",
  },
  {
    rx: /\b(use|reuse|keep)\s+(my|the)\s+(last|previous|saved|same)\s+(order|details|info|names?)\b/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "en_use_my_last",
  },
  {
    rx: /\b(same|identical)\s+everything\b/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "en_same_everything",
  },
  {
    rx: /\bsame\s+sender\b/,
    buckets: ["sender_identity"],
    reason: "en_same_sender",
  },
  {
    rx: /\bsame\s+recipient\b/,
    buckets: ["recipient_identity"],
    reason: "en_same_recipient",
  },
];

/**
 * Arabic and Arabizi phrases. Arabic regex can't rely on `\b` word
 * boundaries, so patterns use character-class / surrounding-space checks.
 */
const AR_PATTERNS: Array<{
  rx: RegExp;
  buckets: ReuseBucket[];
  reason: string;
}> = [
  {
    rx: /نفس\s*(الأسماء|الاسماء|الاسم)\s*و?\s*(الأرقام|الارقام|الرقم|رقم)/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "ar_same_names_and_numbers",
  },
  {
    rx: /نفس\s*(تفاصيل|بيانات|معلومات)\s*(الطلب|السابق|الماضي|الأخير|الاخير)/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "ar_same_details_last_order",
  },
  {
    rx: /نفس\s*الطلب\s*(السابق|الماضي|الأخير|الاخير)/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "ar_same_previous_order",
  },
  {
    rx: /نفس\s*المرسل\s*و\s*المستلم/,
    buckets: ["sender_identity", "recipient_identity"],
    reason: "ar_same_sender_and_recipient",
  },
  {
    rx: /نفس\s*المرسل/,
    buckets: ["sender_identity"],
    reason: "ar_same_sender",
  },
  {
    rx: /نفس\s*المستلم/,
    buckets: ["recipient_identity"],
    reason: "ar_same_recipient",
  },
];

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\u200f\u200e]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Classify a customer utterance for reuse-intent. Returns a structured
 * intent the orchestrator can use to pre-emit a `carry_over_from_last_order`
 * op. Never throws.
 *
 * Requires `hasSavedOrder: true` for any non-`none` result — reuse-intent is
 * meaningless when the customer has no previous order to carry over from,
 * and we don't want the fast-path firing in that case.
 */
export function classifyReuseIntent(params: {
  text: string | null | undefined;
  hasSavedOrder: boolean;
}): ReuseIntent {
  if (!params.hasSavedOrder) {
    return { buckets: [], kind: "none", reason: "no_saved_order", matchedText: null };
  }
  const raw = (params.text ?? "").trim();
  if (!raw) return { buckets: [], kind: "none", reason: "empty", matchedText: null };
  const norm = normalize(raw);
  if (norm.length > 300) {
    return { buckets: [], kind: "none", reason: "too_long", matchedText: null };
  }

  for (const pat of EN_PATTERNS) {
    const m = pat.rx.exec(norm);
    if (m) {
      return {
        buckets: [...pat.buckets],
        kind: "carry_over",
        reason: pat.reason,
        matchedText: m[0],
      };
    }
  }
  for (const pat of AR_PATTERNS) {
    const m = pat.rx.exec(raw);
    if (m) {
      return {
        buckets: [...pat.buckets],
        kind: "carry_over",
        reason: pat.reason,
        matchedText: m[0],
      };
    }
  }
  return { buckets: [], kind: "none", reason: "no_match", matchedText: null };
}
