// ---------------------------------------------------------------------------
// Outbound provenance (2026-04-22).
//
// Every outbound WhatsApp reply crosses exactly one wire-send call
// (`sendOctopusTextReply`). Before this module landed, that boundary
// carried a loose `source: OctopusReplySource` string (e.g. "reply",
// "inactivity_nudge") and a separate, single-level `replyAuthor` enum
// (`server | llm | fallback`) emitted via `[one-brain/reply-attribution]`.
//
// Those two surfaces answered different questions. `source` told the
// sender which CODE PATH enqueued the text; `replyAuthor` told metrics
// which top-level ACTOR composed it. Neither of them answered the
// invariant we actually want to prove after Phase B + guard unification:
//
//     "Every byte that reaches the customer either came from the
//      directive registry, or passed through the verify + hallucination
//      guard, or is a fully deterministic canned template — nothing
//      else."
//
// `OutboundProvenance` is that third, stricter enum. It is orthogonal to
// `OctopusReplySource` (which channel-level observers use) and it is a
// refinement of `ReplyAuthor` (which Phase 5 dashboards use). The
// `fromReplyAuthor` helper below does the mechanical mapping from the
// existing Phase 5 `(reply_author, reason)` pair to the new enum so the
// caller never has to compute provenance by hand.
//
// ## The five values
//
//   - `registry_rendered`         — text was produced by
//                                   `renderDirectiveReply` (the directive
//                                   registry). Trusted by construction;
//                                   the registry is the single source of
//                                   truth for deterministic asks.
//
//   - `authoritative_substitute`  — text was produced by a server-side
//                                   deterministic builder that overwrote
//                                   whatever the LLM proposed. Examples:
//                                     - `buildDeterministicOrderSummary`
//                                     - `buildZeroDistanceRouteRecovery`
//                                     - `buildClass15BypassRepairReply`
//                                     - `buildDeterministicLocationClarificationReply`
//                                     - the hallucination-guard's
//                                       directive-registry-backed repair
//                                   Trusted because it is built from
//                                   server state, not LLM text.
//
//   - `deterministic_fallback`    — text came from a canned template that
//                                   is not backed by a specific
//                                   server-state record. Examples:
//                                     - inactivity close / nudge strings
//                                     - provider-issue fallback
//                                     - image-OCR / audio-transcription
//                                       failure strings
//                                   Trusted because it is a static
//                                   localised string, never derived from
//                                   LLM output.
//
//   - `llm_verified`              — LLM-authored text that was inspected
//                                   by BOTH `verifyAndRepairOutbound`
//                                   (C1) AND `runHallucinationGuard`
//                                   (C2) and survived both unchanged.
//                                   Trusted only as far as the two
//                                   gates' heuristics go — they are the
//                                   only thing standing between the
//                                   model and the wire.
//
//   - `llm_unverified`            — LLM-authored text that reached the
//                                   wire WITHOUT passing C1+C2. After
//                                   this PR, the main webhook path
//                                   always goes through C1+C2 and every
//                                   early wire-send call site produces
//                                   one of the three trusted classes
//                                   above, so `llm_unverified` should
//                                   NEVER fire in steady state. When it
//                                   does, the guard at
//                                   `emitOutboundProvenance` escalates
//                                   to `warn`, surfacing the exact call
//                                   site and reason so the caller can
//                                   be re-routed through the pipeline.
//
// ## Compatibility
//
// `OutboundProvenance` does NOT replace `ReplyAuthor`. Phase 5
// dashboards still key off `reply_author` and that field is preserved
// verbatim in the new `[outbound/provenance]` log line. The new enum is
// strictly additive.
// ---------------------------------------------------------------------------

import type {
  OutboundDecisionKind,
  OutboundDecisionReason,
  ReplyAuthor,
} from "../octopus-channel/lib/outbound-decision";

export type OutboundProvenance =
  | "registry_rendered"
  | "authoritative_substitute"
  | "deterministic_fallback"
  | "llm_verified"
  | "llm_unverified";

/**
 * Runtime-introspectable list of the five provenance values, ordered
 * identically to the type union above. Exported so the wire-send
 * boundary can validate the caller's provenance param at runtime even
 * when TypeScript has been bypassed (JavaScript callers, future
 * plugins, or any code path that landed without a type check).
 *
 * Kept as a readonly tuple (not an enum) so narrowing remains
 * string-literal based — `isValidOutboundProvenance` below is the
 * runtime type guard that closes the loop.
 */
export const OUTBOUND_PROVENANCE_VALUES = [
  "registry_rendered",
  "authoritative_substitute",
  "deterministic_fallback",
  "llm_verified",
  "llm_unverified",
] as const satisfies readonly OutboundProvenance[];

const OUTBOUND_PROVENANCE_SET: ReadonlySet<string> = new Set(
  OUTBOUND_PROVENANCE_VALUES,
);

/**
 * Runtime type guard. True iff `candidate` is exactly one of the five
 * OutboundProvenance literals. Does NOT normalise case, trim
 * whitespace, or accept synonyms — provenance is a closed enum and any
 * drift from the canonical spelling is a bug the wire-send boundary
 * should surface loudly rather than silently accept.
 */
export function isValidOutboundProvenance(
  candidate: unknown,
): candidate is OutboundProvenance {
  return typeof candidate === "string" && OUTBOUND_PROVENANCE_SET.has(candidate);
}

/**
 * Ordered severity: the caller treats any return value whose index is
 * greater than the current turn's provenance as an upgrade. Used when
 * multiple decision phases touch the same reply (pre-state vs
 * post-state) and we want to report the WEAKEST trust level that still
 * applies. Higher index = stronger claim.
 *
 * The ordering intentionally treats `llm_unverified` as the floor so a
 * turn that started as `llm_unverified` and later got a
 * `deterministic_fallback` substitute still reports the stronger tag
 * (the customer actually saw the fallback, not the unverified text).
 */
const PROVENANCE_RANK: Record<OutboundProvenance, number> = {
  llm_unverified: 0,
  llm_verified: 1,
  deterministic_fallback: 2,
  authoritative_substitute: 3,
  registry_rendered: 4,
};

export function isStrongerProvenance(
  candidate: OutboundProvenance,
  current: OutboundProvenance,
): boolean {
  return PROVENANCE_RANK[candidate] > PROVENANCE_RANK[current];
}

export function strongerProvenance(
  a: OutboundProvenance,
  b: OutboundProvenance,
): OutboundProvenance {
  return PROVENANCE_RANK[a] >= PROVENANCE_RANK[b] ? a : b;
}

/**
 * Derive provenance from the Phase 5 `(reply_author, reason)` pair that
 * `decidePreStateOutbound` / `decidePostStateOutbound` already compute.
 *
 * Mapping rules:
 *
 *   - `replace_directive_ask` → `registry_rendered` (the pre-state
 *     directive dispatcher called `renderDirectiveReply`; this is the
 *     only reason code tied to registry output).
 *   - Any other `replace_authoritative` reason → `authoritative_substitute`.
 *   - `replace_fallback` / `fallback_empty_reply` / `block_retry`
 *     → `deterministic_fallback`.
 *   - `allow` / `allow_sanitized` / `preserve_clarification`
 *     → `llm_verified` IF AND ONLY IF the caller confirms C1+C2 ran
 *     (signalled via `verifiedByPostDecision`). Otherwise
 *     `llm_unverified`.
 *
 * The `verifiedByPostDecision` flag is an explicit caller signal rather
 * than a derived field because C2 (`runHallucinationGuard`) is gated on
 * `hallucinationGuardEnabled` and on having a `conversationControllerEntry`.
 * The caller knows whether both passes actually executed; the decision
 * result alone does not.
 */
export function provenanceFromDecision(params: {
  decision: OutboundDecisionKind;
  reason: OutboundDecisionReason;
  replyAuthor: ReplyAuthor;
  verifiedByPostDecision: boolean;
}): OutboundProvenance {
  const { decision, reason, verifiedByPostDecision } = params;

  if (decision === "replace_authoritative") {
    if (reason === "replace_directive_ask") return "registry_rendered";
    return "authoritative_substitute";
  }
  if (decision === "replace_fallback" || decision === "block_retry") {
    return "deterministic_fallback";
  }
  // decision === "allow" | "allow_sanitized"
  return verifiedByPostDecision ? "llm_verified" : "llm_unverified";
}
