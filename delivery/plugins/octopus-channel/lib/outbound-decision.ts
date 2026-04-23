// ---------------------------------------------------------------------------
// Unified outbound-reply decision module (Step-4 consolidation).
//
// Before Step 4, the outbound-reply decision was spread across three regions
// of `octopus-channel/index.ts`:
//
//   Region A (~4790-4880)  — session-guard / canonical-overwrite / price
//                           whitelist / same-route quote correction
//   Region B (~4997-5014)  — transition-hint empty fallbacks + provider-issue
//                           fallback
//   Region C (~5059-5126)  — `verifyAndRepairOutbound` + `runHallucinationGuard`
//
// Each region inspected overlapping bits of state and independently mutated
// `replyText`. Adding a new guard, changing an ordering, or reading the end-
// to-end decision flow required tracing ~400 lines across three scopes.
//
// This module folds all three regions into a single file with two phased
// entry points. It is a STRAIGHT TRANSLATION of the existing ordering and
// semantics — no new behavior, no new guards, no new substitution paths.
//
// ## Why two entry points, not one?
//
// Between Region A and Regions B/C the callsite runs a controller-state
// block that reads `replyText` to compute `quotePresentedToCustomer`, then
// a persist block that writes the controller entry to disk. To preserve
// the exact pre-Step-4 behavior we must:
//
//   - Run Region A BEFORE the controller-state block (so canonical fills
//     and price repairs are visible in `quotePresentedToCustomer`).
//   - Run Regions B + C AFTER the persist block (so Region C's in-memory
//     `summary_shown` promotion doesn't leak into the persisted stage —
//     the pre-Step-4 code deliberately persisted the pre-verify stage).
//
// Collapsing both into one call would either change the
// `quotePresentedToCustomer` semantics or the persisted stage. Splitting
// preserves semantics while still giving us one file + one shared
// vocabulary for every outbound-text decision:
//
//   - `decidePreStateOutbound`   — Region A
//   - `decidePostStateOutbound`  — Regions B + C
//
// Both return the same `OutboundDecisionResult` shape with one of the ten
// stable reason codes. The final reason seen by logs / metrics is the
// stronger (post-state) one when both phases fire.
//
// The module is pure (no I/O, no module-scope state), never throws, and
// returns structured log entries instead of emitting logs directly. The
// caller applies the returned `replyText`, emits the log entries, and (if
// `markedSummaryShown === true`) promotes the controller to
// `summary_shown / summary_pending`.
// ---------------------------------------------------------------------------

import type {
  PersistedConversationControllerEntry,
} from "../../shared/conversation-policy";
import type {
  FieldRejection,
  HallucinationGuardDecision,
} from "../../shared/reply-hallucination-guard";
import { runHallucinationGuard } from "../../shared/reply-hallucination-guard";
import type {
  OutboundReplyShape,
  VerifyOutboundResult,
} from "../../shared/outbound-verify";
import {
  buildClass15BypassRepairReply,
  looksLikeFreeComposedAreaClarification,
  verifyAndRepairOutbound,
  verifyCompactFactualClaims,
} from "../../shared/outbound-verify";
import type {
  RouteQuoteOption,
  StoredQuotedRoute,
  SameRouteQuoteFollowupAction,
} from "./quoted-options";
import type {
  DirectiveReplyRendererContext as DirectiveReplyRenderContext,
  DirectiveReplyRenderResult,
} from "../../shared/directive-reply-registry";

/**
 * Top-level decision kinds — the 5-way contract from the Step-4 spec.
 *
 *   allow                  — LLM reply passes through unchanged
 *   allow_sanitized        — passes through after the provider-error
 *                            sanitizer. The sanitizer itself still runs in
 *                            `sendOctopusTextReply`; this value is reserved
 *                            for a future callsite that surfaces "the only
 *                            thing we did was strip a provider-error banner".
 *   replace_authoritative  — replaced with deterministic text backed by
 *                            authoritative server state (e.g. the canonical
 *                            tool `_customer_message`, the same-route quote
 *                            correction, or the canonical full-summary).
 *   replace_fallback       — replaced with a safe generic fallback template
 *                            (e.g. provider-issue reply, grace-window prompt,
 *                            pricing-error apology). The content is NOT
 *                            claim-backed — it only tells the customer that
 *                            something went wrong and nudges them forward.
 *   block_retry            — reserved for a future LLM retry loop; never
 *                            returned by the current implementation.
 */
export type OutboundDecisionKind =
  | "allow"
  | "allow_sanitized"
  | "replace_authoritative"
  | "replace_fallback"
  | "block_retry";

/**
 * Reply attribution (Phase 5, 2026-04-20 "observability tripwire").
 *
 * Every outbound reply gets tagged with a 3-way author so we can
 * measure, per turn, whether the customer ultimately saw
 * server-composed / LLM-composed / deterministic-fallback text. This is
 * the observability half of the directive-registry architecture:
 *
 *   - `server`   — the reply was substituted with server-rendered text
 *                  (directive registry, canonical summary, same-route
 *                  quote correction, clarify-before-proceed, manual-
 *                  confirm flow, canonical price correction, etc.).
 *                  Maps from `replace_authoritative`.
 *   - `llm`      — the LLM's draft text was passed through unchanged,
 *                  optionally after a sanitation pass. Maps from
 *                  `allow` / `allow_sanitized`.
 *   - `fallback` — a safe generic fallback fired because the primary
 *                  path could not produce a reply (empty LLM output,
 *                  provider issue, pricing error without a canonical
 *                  source). Fallbacks are incidents, not steady-state
 *                  UX — they are worth alerting on. Maps from
 *                  `replace_fallback` and `block_retry`.
 *
 * Together with the tight `OutboundDecisionReason` enum, `replyAuthor`
 * lets a triager grep production logs for two things:
 *
 *   - "what fraction of directive-active turns stayed server-composed?"
 *     (ratio of `server` attributions on turns where a directive was
 *     active — should be high after Phase 2/3.)
 *   - "is `fallback` firing more than expected?" (regression signal
 *     for provider issues or empty-reply bugs.)
 */
export type ReplyAuthor = "server" | "llm" | "fallback";

/**
 * Classify a decision kind into its customer-visible author. Pure, no
 * I/O; the outbound-decision module attaches this automatically to every
 * result in `finalizeOutboundDecision` below.
 */
export function classifyReplyAuthor(
  decision: OutboundDecisionKind,
): ReplyAuthor {
  switch (decision) {
    case "allow":
    case "allow_sanitized":
      return "llm";
    case "replace_authoritative":
      return "server";
    case "replace_fallback":
    case "block_retry":
      return "fallback";
    default: {
      const _exhaustive: never = decision;
      void _exhaustive;
      return "llm";
    }
  }
}

/**
 * Stable, customer-outcome-oriented reason codes.
 *
 * Keep this enum tight (~10 entries). Finer-grained detail (the original
 * detected shape, the specific tool name, which drift field fired) lives
 * in the attached `detail` field on each log entry, not in the reason code.
 * The reason code is the top-level "what happened to this reply" answer a
 * triager can grep for; the detail is the forensic context below it.
 */
export type OutboundDecisionReason =
  | "allow"
  | "allow_sanitized"
  | "replace_summary_fact_drift"
  | "replace_transaction_artifact_missing"
  | "replace_price_mismatch"
  | "replace_field_rejection_hallucination"
  | "replace_order_placed_hallucination"
  | "replace_clarify_option_before_proceed"
  | "replace_manual_confirm_address_ask"
  | "replace_manual_confirm_handoff"
  | "replace_directive_ask"
  // Class 15 (2026-04-21): on a route-intent turn where the LLM
  // free-composed an area clarification WITHOUT calling get_price,
  // substitute with a deterministic send-both-areas repair reply.
  // See `classFifteenBypass` input + (B3) below.
  | "replace_get_price_bypass"
  | "block_provider_error"
  | "fallback_empty_reply"
  | "preserve_clarification";

export type OutboundDecisionLogEntry = {
  level: "info" | "warn";
  message: string;
  /** Optional structured detail for triage / metrics. */
  detail?: Record<string, string | number | boolean | null | undefined>;
};

export type OutboundDecisionResult = {
  decision: OutboundDecisionKind;
  reason: OutboundDecisionReason;
  replyText: string;
  /** Outbound shape detected by `verifyAndRepairOutbound`, when run. */
  detectedShape: OutboundReplyShape | null;
  /**
   * When `decidePostStateOutbound` ran the canonical-summary substitute
   * for `summary_fact_drift`, the caller must promote the controller to
   * `stage=summary_shown / bookingStep=summary_pending`. Surfaced as a
   * flag instead of mutating the entry inside the module (keeps this
   * module pure; state transitions stay at the callsite).
   */
  markedSummaryShown: boolean;
  /**
   * Phase 5 attribution. Derived from `decision` via
   * `classifyReplyAuthor`, never computed independently. Present on
   * every returned result so the caller can emit a single
   * `[one-brain/reply-attribution]` log line without re-deriving.
   */
  replyAuthor: ReplyAuthor;
  logEntries: OutboundDecisionLogEntry[];
};

/**
 * Attach the `replyAuthor` derived field. All exported entry points
 * run every return through this so every `OutboundDecisionResult`
 * across the codebase carries a consistent attribution tag.
 */
function finalizeOutboundDecision(
  partial: Omit<OutboundDecisionResult, "replyAuthor">,
): OutboundDecisionResult {
  return {
    ...partial,
    replyAuthor: classifyReplyAuthor(partial.decision),
  };
}

/**
 * Minimal structural subset of the in-process session-guard shape. The
 * caller's richer type (defined inline in `octopus-channel/index.ts`)
 * satisfies this.
 */
export type OutboundDecisionSessionGuard = {
  allValidPrices: Set<string>;
  lastToolTs: number;
  lastToolName: string | null;
};

export type PreStateOutboundInput = {
  /** Draft reply text from the LLM. May be empty. */
  replyText: string;
  preferredLanguage: "ar" | "en";

  sessionGuard: OutboundDecisionSessionGuard | null;
  sessionIsRecent: boolean;
  preferredCanonicalText: string | null;
  guardToolAgeMs: number;
  /** Result of `isCanonicalOverwriteAllowed`, computed at the callsite
   *  because other non-decision code paths also read its fields. */
  canonicalOverwriteAllowed: boolean;
  canonicalOverwriteSkipReason: string | null;
  /** Pure helper lifted from the guard-state runtime. */
  extractPricesFromText: (text: string) => string[];

  activeQuotedRoute: StoredQuotedRoute | null;
  sameRouteQuoteAction: SameRouteQuoteFollowupAction;

  /**
   * Clarify-before-proceed signal (Bug 1, 2026-04-20). Set by the caller
   * when `next_required_action === "CLARIFY_OPTION_BEFORE_PROCEED"` was
   * emitted for this turn (i.e. the customer sent a vague proceed signal
   * on a route that has a manual-confirm option and did NOT name a
   * specific option). When set, Region A substitutes any LLM reply with
   * the deterministic clarify reply so the customer is never advanced
   * into sender collection on an ambiguous "go ahead". Left null when
   * the gate did not fire (the common case). */
  clarifyOptionBeforeProceed?: boolean;

  /**
   * Relocation 3 (2026-04-22): turn-decision layer A1 passthrough flip.
   *
   * When the callsite's pre-Region-A evaluation of
   * `deriveA1Substitute` returned one of the three semantic-gate
   * passthroughs (`pass_on_clarifying`, `pass_on_partial_answer`,
   * `pass_on_route_change`) AND the flip's live-only gates passed
   * (confidence >= medium, hallucination guard did NOT fire, env flag
   * `RIDERS_TURN_DECISION_A1_FLIP !== "off"`, sameRouteQuoteAction is
   * not a switch_option), this field is populated with
   * `{ allowed: true, policyRule, legacyWouldHave }`.
   *
   * Effect inside Region A: whichever of the A0 / A0a / A0b / A0c
   * substitution branches would have fired this turn is skipped —
   * the LLM's draft survives through the rest of the pipeline
   * (canonical overwrite, empty-reply fallback, price whitelist,
   * same-route quote correction) exactly as if those preconditions
   * had been absent.
   *
   * 2026-04-23 hoist: the skip was extended from A0c only to the full
   * A0 family. Previously the callsite-side flip layered on top of the
   * derived A0c branch, but `deriveA1Substitute` returned A0/A0a/A0b
   * BEFORE evaluating the semantic gates — so clarifying questions
   * during a clarify-before-proceed turn never passed through. Hoisting
   * the gates above A0 in the derivation + skipping the matching legacy
   * branches here closes that gap.
   *
   * Safeguards live at the CALLSITE — this struct is trusted. When
   * flip safeguards fail or the env flag is "off", the callsite
   * passes null and Region A behaves identically to the pre-Reloc-3
   * build. `[turn-decision/flip]` log line is emitted ONCE per turn
   * via `logEntries` whenever the skip actually fires.
   */
  layerA1Passthrough?: {
    allowed: boolean;
    /** e.g. "layer.a1.directive_ask.pass_on_clarifying" */
    policyRule: string;
    /** Which legacy Region-A branch would have fired absent the
     *  passthrough — either a directive name (for A0c) or one of
     *  "clarify_option_before_proceed" | "manual_confirm_address_ask" |
     *  "manual_confirm_handoff" for the A0 family. Captured at
     *  call time for the flip log. */
    legacyWouldHave: string;
    /** Which legacy Region-A branch the payload targets. Determines
     *  which of A0 / A0a / A0b / A0c this passthrough actually skips.
     *  Added 2026-04-23 alongside the semantic-gate hoist. */
    legacyBranch: "a0_clarify_before_proceed" | "a0a_manual_confirm_address_ask" | "a0b_manual_confirm_handoff" | "a0c_directive_ask";
  } | null;

  /** Plugin-local deterministic builder, injected to keep this module free
   *  of circular plugin imports. */
  buildDeterministicSelectedQuotedOptionReply: (args: {
    language: "ar" | "en";
    route: StoredQuotedRoute;
    option: RouteQuoteOption;
  }) => string;

  /** Plugin-local deterministic clarify-before-proceed reply builder. */
  buildDeterministicClarifyOptionBeforeProceedReply?: (args: {
    language: "ar" | "en";
    route: StoredQuotedRoute;
  }) => string;

  /**
   * Manual-confirm address-ask substitution (Bug 4, 2026-04-20).
   *
   * Set by the caller when `next_required_action` is one of
   * `ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM` / `ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM`
   * AND the selected option has `direct_chat_booking_status === "manual_confirmation_required"`.
   * When set, Region A substitutes the LLM reply with
   * `buildDeterministicManualConfirmAddressAskReply(...)` so the
   * "needs manual confirmation" signal can never be dropped.
   */
  manualConfirmAddressAsk?: {
    side: "pickup" | "delivery";
    option: RouteQuoteOption;
  } | null;

  /**
   * Manual-confirm handoff substitution (Bug 4 companion).
   *
   * Set when `next_required_action === "REQUEST_HANDOFF_FOR_MANUAL_CONFIRM"`.
   * Causes Region A to substitute
   * `buildDeterministicManualConfirmHandoffReply(...)`.
   */
  manualConfirmHandoff?: {
    option: RouteQuoteOption;
  } | null;

  /** Deterministic manual-confirm reply builders (see `quoted-options.ts`). */
  buildDeterministicManualConfirmAddressAskReply?: (args: {
    language: "ar" | "en";
    route: StoredQuotedRoute;
    option: RouteQuoteOption;
    side: "pickup" | "delivery";
  }) => string;
  buildDeterministicManualConfirmHandoffReply?: (args: {
    language: "ar" | "en";
    route: StoredQuotedRoute;
    option: RouteQuoteOption;
  }) => string;

  /**
   * Phase 2 (2026-04-20): directive-to-reply registry inputs.
   *
   * When `directiveAction` names a directive whose registry spec is
   * `{kind: "server"}`, Region A substitutes the LLM's draft with the
   * server-rendered ask. Directives that live in dedicated branches
   * (clarify-before-proceed, manual-confirm family) are still handled
   * by their specific substitutions — the registry dispatcher
   * short-circuits with `{kind: "existing"}` for those.
   *
   * Left null when the caller has no directive computed for this turn
   * (e.g. idle stage) or the directive is LLM-owned (post-order intent,
   * Phase-3 summary).
   */
  directiveAction?: string | null;
  /** Pre-built renderer context (draft + entry + route + turnSeed). */
  directiveRenderContext?: DirectiveReplyRenderContext | null;
  /** Registry dispatcher; injected to avoid circular imports. */
  renderDirectiveReply?: (
    action: string,
    ctx: DirectiveReplyRenderContext,
  ) => DirectiveReplyRenderResult;

  /** Short identifiers for log-entry detail (no effect on the decision). */
  conversationId: string;
  sessionKeyForLogs: string;
  controllerStage: string | null;
};

export type PostStateOutboundInput = {
  /** Draft reply text at entry (post-Region-A, post-state mutations, post-
   *  booking-transition). May be empty. */
  replyText: string;
  preferredLanguage: "ar" | "en";

  conversationControllerEntry: PersistedConversationControllerEntry | null;
  missingFields: string[];

  hallucinationGuardRejections: FieldRejection[];
  stageAtTurnStart: string | null;
  hallucinationGuardEnabled: boolean;
  /** Computed outside the module because it's derived from the draft +
   *  entry + missing fields, all of which the caller already has. */
  nextRequiredAction: string | null;

  /**
   * Full valid price set for the active quoted route — one entry per
   * available option (sedan / express-sedan / box-van / express-box-van,
   * etc.), filtered to numeric + positive values.
   *
   * Used by the hallucination guard to decide whether a mentioned price
   * is grounded. Without this set, the guard only knows the scalar
   * `entry.quotedPrice` (the currently-selected option), so any reply
   * that legitimately mentions another option's price (e.g. answering
   * "is there other options?") would falsely trigger a price_mismatch
   * and be replaced with the deterministic next-slot ask. That is the
   * 2026-04-19 incident we are anchoring.
   *
   * Callers should derive this from `activeQuotedRoute.pricesByType` at
   * the point the guard is invoked. Optional because Region-A callers
   * and the no-controller-entry path don't run the guard and don't need
   * to compute it. */
  activeQuotedPrices?: number[] | null;

  /**
   * Set by the caller when this turn's `cancel_booking` op was rejected
   * server-side because the customer's own source quote also named one
   * of the currently quoted options (the "nvm pls standard sedan" case).
   * The hallucination guard pipes this through so any "we've cancelled"
   * reply text is substituted with a disambiguating re-ask. Optional —
   * when absent, the guard's cancel detector stays silent.
   */
  cancelContradicted?: { optionLabel: string } | null;

  /** Controller transition hint that can trigger an empty-reply fallback. */
  controllerTransitionHint: string | null;

  /** Plugin-local deterministic builders, injected to keep this module free
   *  of circular plugin imports. */
  buildDeterministicGraceWindowReply: (language: "ar" | "en") => string;
  buildProviderIssueFallbackReply: (language: "ar" | "en") => string;

  /**
   * Class-15 bypass gating (2026-04-21).
   *
   * Set by the caller when:
   *
   *   - The inbound for this turn has route evidence (the customer
   *     named or clearly referenced a pickup → delivery route).
   *   - There was NO active quoted route at turn start.
   *   - `get_price` was NOT called during this turn (sessionGuard
   *     `lastToolName` / `lastToolTs` did not advance under
   *     `get_price`).
   *
   * When set, Region D inspects the current `reply` and — if the
   * shape matches `looksLikeFreeComposedAreaClarification` —
   * substitutes with the deterministic repair reply
   * (`buildClass15BypassRepairReply`). The fix stops the LLM from
   * sending a tool-less free-composed area ask that downstream
   * turns would then have to re-interpret without any server-owned
   * pending-area / requested-slot state, and it forces the next
   * customer turn to carry both areas so the tool-owned path is
   * hit cleanly.
   *
   * Left `false` in every other case so the branch is a no-op on
   * healthy turns. */
  classFifteenBypass?: boolean;

  conversationId: string;
};

const PRICING_ERROR_FALLBACK_AR =
  "عذراً، حصل خطأ في التسعير. يرجى إعادة طلب السعر مرة ثانية وسنتحقق لكم.";
const PRICING_ERROR_FALLBACK_EN =
  "Sorry, there was a pricing error. Please ask for the price again and we'll verify it for you.";

const SUMMARY_EDIT_REQUEST_AR =
  "أكيد. شنو الجزء اللي تبون نغيره بالضبط: المرسل، المستلم، الاستلام، التوصيل، الرقم، أو الخدمة؟";
const SUMMARY_EDIT_REQUEST_EN =
  "Sure. Which part should I change exactly: sender, recipient, pickup, delivery, phone, or service?";

function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function textContainsUrl(text: string): boolean {
  return /\bhttps?:\/\/\S+/i.test(text);
}

/**
 * Factual-only canonical-overwrite check (Step-3 narrowing): for
 * `create_simple_order` / `track_order` replies within 15s of the tool call,
 * restore the canonical text when the LLM lost the tracking URL or the
 * ORDER- id. These are transactional artifacts (payment link, order id) the
 * customer must be able to act on / track with.
 */
function needsCanonicalOverwriteForTxArtifacts(args: {
  toolName: string | null;
  reply: string;
  canonical: string;
  lastToolAgeMs: number;
}): boolean {
  const { toolName, reply, canonical, lastToolAgeMs } = args;
  if (!toolName) return false;
  if (toolName !== "create_simple_order" && toolName !== "track_order") return false;
  if (lastToolAgeMs > 15_000) return false;
  const canonicalHasUrl = textContainsUrl(canonical);
  const replyHasUrl = textContainsUrl(reply);
  if (canonicalHasUrl && !replyHasUrl) return true;
  const canonicalHasOrderId = /\bORDER-[A-Za-z0-9-]+\b/i.test(canonical);
  const replyHasOrderId = /\bORDER-[A-Za-z0-9-]+\b/i.test(reply);
  if (canonicalHasOrderId && !replyHasOrderId) return true;
  return false;
}

/**
 * Map a `HallucinationGuardDecision` to one of the tight reason codes. The
 * guard can fire multiple claims on a single reply; the first one (by the
 * guard's priority ordering) determines the reason surfaced to the decision
 * caller.
 */
function reasonForHallucinationClaim(
  decision: HallucinationGuardDecision,
): OutboundDecisionReason {
  const first = decision.claims[0];
  switch (first) {
    case "price_mismatch":
      return "replace_price_mismatch";
    case "field_rejection_hallucination":
      return "replace_field_rejection_hallucination";
    case "order_placed_hallucination":
      return "replace_order_placed_hallucination";
    default:
      return "allow";
  }
}

/**
 * Phase 1: pre-state outbound decision (Region A).
 *
 * Runs BEFORE the controller-state mutation block so that its reply
 * substitutions (canonical fills, price repairs) are visible to the
 * downstream `quotePresentedToCustomer` computation.
 *
 * Ordering (preserved exactly from the pre-Step-4 inline code):
 *
 *   (A1) Canonical overwrite for lost tx artifacts (order/tracking URL or
 *        ORDER- id), gated by `canonicalOverwriteAllowed` + the static
 *        transactional-artifact check.
 *   (A2) Empty-reply canonical fill (when the LLM returned nothing and a
 *        recent canonical tool message is available).
 *   (A3) Outbound price whitelist: any KWD token in the reply must be in
 *        the tool's verified price set, otherwise block and substitute.
 *   (A4) Same-route quote correction: on `switch_option`, the reply must
 *        carry the expected option's price; otherwise substitute the
 *        deterministic selected-option reply.
 */
export function decidePreStateOutbound(
  input: PreStateOutboundInput,
): OutboundDecisionResult {
  return finalizeOutboundDecision(decidePreStateOutboundImpl(input));
}

function decidePreStateOutboundImpl(
  input: PreStateOutboundInput,
): Omit<OutboundDecisionResult, "replyAuthor"> {
  const logEntries: OutboundDecisionLogEntry[] = [];
  let reply = input.replyText;
  let decision: OutboundDecisionKind = "allow";
  let reason: OutboundDecisionReason = "allow";

  // ------------------------------------------------------------------
  // Relocation 3 flip — passthrough gate (2026-04-22, hoisted
  // 2026-04-23 to cover A0 family).
  //
  // DEPLOY_CANARY_TURN_DECISION_A1_FLIP_BRANCH_MARKER.
  //
  // When `deriveA1Substitute` returned `allow` via one of the three
  // semantic gates AND the callsite's safeguards passed, skip whichever
  // legacy Region-A substitution would have fired. The flip log is
  // emitted ONCE for the turn here so grepping
  // `[turn-decision/flip]` surfaces every skip regardless of which
  // branch it targeted. Per-branch skip checks below short-circuit on
  // the same `allowed === true` flag.
  // ------------------------------------------------------------------
  const skipRegionAForLayerA1Passthrough =
    !!input.layerA1Passthrough &&
    input.layerA1Passthrough.allowed === true;
  if (skipRegionAForLayerA1Passthrough) {
    logEntries.push({
      level: "info",
      message:
        `[turn-decision/flip] conversation=${input.conversationId} ` +
        `sessionKey=${input.sessionKeyForLogs} ` +
        `rule=${input.layerA1Passthrough!.policyRule} ` +
        `legacy_branch=${input.layerA1Passthrough!.legacyBranch} ` +
        `legacy_would_have=${input.layerA1Passthrough!.legacyWouldHave} ` +
        `action=${input.directiveAction ?? "none"}`,
      detail: {
        rule: input.layerA1Passthrough!.policyRule,
        legacy_branch: input.layerA1Passthrough!.legacyBranch,
        legacy_would_have: input.layerA1Passthrough!.legacyWouldHave,
        action: input.directiveAction,
      },
    });
  }

  // Authority cutover phase 3 (2026-04-23): the A0 / A0a / A0b
  // branches (clarify-before-proceed, manual-confirm address-ask,
  // manual-confirm handoff) were deleted. The LLM composes those
  // reply shapes from prompt facts. A0c (directive registry
  // dispatch) below is still authoritative for server-owned ASK_*
  // directives.

  // ------------------------------------------------------------------
  // (A0c) Directive-to-reply registry dispatch (Phase 2, 2026-04-20).
  //
  // For directives whose registry spec is `{kind: "server"}` (field
  // asks, recipient asks, address asks, slot-conflict confirmation),
  // the server OWNS the reply text. The LLM's draft is discarded. This
  // is the "directive → renderer" contract — every new ASK_* directive
  // added to `DirectiveAction` must carry a renderer (or be explicitly
  // flagged `llm_owned` / `server_existing`), enforced by the
  // `satisfies Record<DirectiveAction, …>` check in the registry.
  //
  // Runs AFTER the dedicated branches (clarify-before-proceed + manual-
  // confirm family) because those carry richer per-option state the
  // generic registry doesn't need to replicate. For them the registry
  // dispatcher returns `{kind: "existing"}` and this block is a no-op.
  //
  // Skipped when `sameRouteQuoteAction` is a `switch_option` action
  // this turn. In that case the customer just switched to a different
  // option and the new price must be recapped — A4 below owns that
  // recap/ask composition (or the LLM's reply passes through when it
  // already contains the expected price).
  //
  // 2026-04-22 — narrowed from `switch_option | confirm_selected_option`
  // to `switch_option` only. `confirm_selected_option` does NOT change
  // the price (the customer already heard it on the quote turn), so
  // there is nothing to recap and the registry's next-slot ask
  // (ASK_SENDER_NAME_AND_PHONE_DECISION after quote acceptance) is the
  // correct outbound. Keeping `confirm_selected_option` in the skip
  // caused a language-agnostic registry miss observed in conv 19294
  // (2026-04-22): both the EN "lets go ahead woth the standard sedan"
  // and AR "خلاص سيارة عادية لو سمحت" turns rendered an LLM-authored
  // sender-name ask even though the directive was computed and tagged
  // on the outbound-provenance line.
  // ------------------------------------------------------------------
  const skipDirectiveDispatchForSameRouteSwitch =
    !!input.sameRouteQuoteAction &&
    input.sameRouteQuoteAction.kind === "switch_option";

  // Relocation 3 flip (2026-04-22, hoisted 2026-04-23): when the
  // turn-decision layer's `deriveA1Substitute` chose `allow` via a
  // semantic gate (clarifying question, partial answer, or strict
  // fresh route change) AND the callsite's live-only safeguards
  // passed, `skipRegionAForLayerA1Passthrough` is true and the A0
  // family branches above were already bypassed. Here we also bypass
  // the A0c directive-registry dispatch so the LLM's draft survives.
  // The `[turn-decision/flip]` line was already emitted at the top
  // of this function; per-branch logging is intentionally absent.
  if (
    !skipDirectiveDispatchForSameRouteSwitch &&
    !skipRegionAForLayerA1Passthrough &&
    input.directiveAction &&
    input.directiveRenderContext &&
    input.renderDirectiveReply
  ) {
    const outcome = input.renderDirectiveReply(
      input.directiveAction,
      input.directiveRenderContext,
    );
    if (outcome.kind === "render") {
      logEntries.push({
        level: "info",
        message: `[guard] Substituted directive-driven reply conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs} action=${input.directiveAction}`,
        detail: {
          action: input.directiveAction,
          originalLen: reply ? reply.length : 0,
        },
      });
      // Phase B measure-first (2026-04-21): observation-only trace so we
      // can see which renderers layer verbs/shape on top of facts. The
      // `facts` bundle captures the raw inputs a facts-only variant
      // would use (area names, options, conflicting slot, sender name).
      // Offline analysis computes the verbs-to-facts ratio by comparing
      // `rendered` length to a minimal facts-only projection — no
      // behavior change here.
      //
      // `emitOutboundDecisionLogs` only serialises `message`, so the
      // full trace payload is JSON-packed into the message string on a
      // single line for easy `rg`/`jq` post-processing.
      try {
        const ctx = input.directiveRenderContext;
        const draft = ctx?.draft ?? null;
        const entry = ctx?.entry ?? null;
        const requestedSlot = entry?.dialogState?.requestedSlot ?? null;
        const factsBundle = {
          language: ctx?.language ?? null,
          pendingPickupAreaNameEn: entry?.pendingPickupAreaNameEn ?? null,
          pendingDropoffAreaNameEn: entry?.pendingDropoffAreaNameEn ?? null,
          quotePickupAreaNameEn: entry?.quotePickupAreaNameEn ?? null,
          quoteDropoffAreaNameEn: entry?.quoteDropoffAreaNameEn ?? null,
          requested_slot_name: requestedSlot?.name ?? null,
          requested_slot_options_count: Array.isArray(requestedSlot?.options)
            ? requestedSlot.options.length
            : 0,
          senderName: draft?.senderName ?? null,
          recipientName: draft?.recipientName ?? null,
          conflictingSlot: ctx?.conflictingSlot ?? null,
          conflictValues: ctx?.conflictValues ?? null,
          turnSeed: ctx?.turnSeed ?? null,
        };
        const trace = {
          conversation: input.conversationId,
          sessionKey: input.sessionKeyForLogs,
          action: input.directiveAction,
          lang: factsBundle.language,
          rendered_chars: outcome.text.length,
          rendered: outcome.text,
          facts: factsBundle,
        };
        logEntries.push({
          level: "info",
          message: `[directive-render/trace] ${JSON.stringify(trace)}`,
          detail: {
            action: input.directiveAction,
            rendered_chars: outcome.text.length,
          },
        });
      } catch {
        // Tracing is observation-only; never block substitution on
        // logging errors.
      }
      // Phase 3 (2026-04-20): when the substituted reply is the server-
      // composed full order summary, flip `markedSummaryShown` so the
      // controller promotes to `summary_shown` / `summary_pending` in
      // the same turn. Mirrors the post-state C-drift path which also
      // promotes on substitution — keeps the two paths symmetric so
      // downstream order-guard / confirmation detection fires off the
      // real event regardless of which layer composed the summary.
      const summaryWasSubstituted =
        input.directiveAction ===
        "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";
      return {
        decision: "replace_authoritative",
        reason: "replace_directive_ask",
        replyText: outcome.text,
        detectedShape: null,
        markedSummaryShown: summaryWasSubstituted,
        logEntries,
      };
    }
    // `existing` / `llm_owned` / `unknown_action` — fall through and let
    // downstream substitutions or the LLM draft survive.
  }

  const canonical = input.preferredCanonicalText;
  const sg = input.sessionGuard;
  const recentCanonical =
    !!sg && input.sessionIsRecent && canonical ? canonical : null;

  // ------------------------------------------------------------------
  // (A1) Canonical overwrite for lost transactional artifacts
  // ------------------------------------------------------------------
  const sameRouteQuoteSkip = Boolean(input.activeQuotedRoute && input.sameRouteQuoteAction);
  const canonicalOverwriteCandidateBlocked =
    sameRouteQuoteSkip || !input.canonicalOverwriteAllowed;
  if (
    reply &&
    sg &&
    input.sessionIsRecent &&
    canonical &&
    !canonicalOverwriteCandidateBlocked &&
    needsCanonicalOverwriteForTxArtifacts({
      toolName: sg.lastToolName,
      reply: normalize(reply),
      canonical: normalize(canonical),
      lastToolAgeMs: input.guardToolAgeMs,
    })
  ) {
    logEntries.push({
      level: "info",
      message: `[guard] Replaced lossy ${String(sg.lastToolName)} reply with canonical tool message conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs}`,
      detail: {
        toolName: sg.lastToolName,
        sessionKey: input.sessionKeyForLogs,
        conversationId: input.conversationId,
      },
    });
    reply = canonical;
    decision = "replace_authoritative";
    reason = "replace_transaction_artifact_missing";
  } else if (
    reply &&
    sg &&
    input.sessionIsRecent &&
    sg.lastToolName === "get_price" &&
    !input.canonicalOverwriteAllowed
  ) {
    // Log-only observability: the pre-Step-4 code emitted this line when a
    // `get_price` reply would have been a canonical-overwrite candidate on
    // the old (stylistic) rules but the gate blocked it. Under the Step-3
    // factual-only policy we never overwrite `get_price` replies anyway, so
    // this is purely a diagnostic trail.
    logEntries.push({
      level: "info",
      message: `[guard] Skipped canonical overwrite gate=${input.canonicalOverwriteSkipReason || "na"} age=${input.guardToolAgeMs}ms stage=${input.controllerStage || "na"} conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs}`,
      detail: {
        gate: input.canonicalOverwriteSkipReason,
        ageMs: input.guardToolAgeMs,
        stage: input.controllerStage || null,
      },
    });
  }

  // ------------------------------------------------------------------
  // (A2) Empty-reply canonical fill
  // ------------------------------------------------------------------
  if (!reply && recentCanonical) {
    logEntries.push({
      level: "info",
      message: `[guard] Filled missing ${String(sg?.lastToolName)} reply with canonical tool message conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs}`,
      detail: {
        toolName: sg?.lastToolName ?? null,
      },
    });
    reply = recentCanonical;
    decision = "replace_authoritative";
    reason = "replace_transaction_artifact_missing";
  }

  // ------------------------------------------------------------------
  // (A3) Outbound price whitelist
  // ------------------------------------------------------------------
  if (reply && sg && input.sessionIsRecent && sg.allValidPrices.size > 0) {
    const quotedPrices = input.extractPricesFromText(reply);
    if (quotedPrices.length > 0) {
      const validPrices = sg.allValidPrices;
      const hallucinated = quotedPrices.filter((p) => !validPrices.has(p));
      if (hallucinated.length > 0) {
        logEntries.push({
          level: "warn",
          message: `[guard] BLOCKED hallucinated prices [${hallucinated.join(", ")}] in outbound. Valid: [${[...validPrices].join(", ")}] conversation=${input.conversationId}`,
          detail: {
            hallucinated: hallucinated.join(","),
            valid: [...validPrices].join(","),
          },
        });
        reply =
          canonical ||
          (input.preferredLanguage === "ar"
            ? PRICING_ERROR_FALLBACK_AR
            : PRICING_ERROR_FALLBACK_EN);
        decision = canonical ? "replace_authoritative" : "replace_fallback";
        reason = "replace_price_mismatch";
      }
    }
  }

  // ------------------------------------------------------------------
  // (A4) Same-route quote correction
  // ------------------------------------------------------------------
  if (
    input.activeQuotedRoute &&
    input.sameRouteQuoteAction &&
    input.sameRouteQuoteAction.kind === "switch_option"
  ) {
    const expectedOption = input.sameRouteQuoteAction.option;
    const expectedPrice =
      typeof expectedOption.quoted_price === "number" &&
      Number.isFinite(expectedOption.quoted_price)
        ? expectedOption.quoted_price.toFixed(3)
        : null;
    const replyPrices = reply ? input.extractPricesFromText(reply) : [];
    const missingExpectedPrice =
      Boolean(expectedPrice) &&
      replyPrices.length > 0 &&
      !replyPrices.includes(String(expectedPrice));
    if (!reply || missingExpectedPrice) {
      logEntries.push({
        level: "warn",
        message: `[guard] Replaced semantically wrong same-route quote reply conversation=${input.conversationId} action=${input.sameRouteQuoteAction.kind} option=${expectedOption.delivery_type} expectedPrice=${expectedPrice || "na"} replyPrices=${replyPrices.join(",") || "none"}`,
        detail: {
          action: input.sameRouteQuoteAction.kind,
          option: expectedOption.delivery_type,
          expectedPrice: expectedPrice || null,
        },
      });
      reply = input.buildDeterministicSelectedQuotedOptionReply({
        language: input.preferredLanguage,
        route: input.activeQuotedRoute,
        option: expectedOption,
      });
      decision = "replace_authoritative";
      reason = "replace_price_mismatch";
    }
  }

  return {
    decision,
    reason,
    replyText: reply,
    detectedShape: null,
    markedSummaryShown: false,
    logEntries,
  };
}

/**
 * Phase 2: post-state outbound decision (Regions B + C).
 *
 * Runs AFTER the controller-state and persist blocks so that any in-memory
 * controller promotion triggered by a summary-substitute (`markedSummaryShown`)
 * does NOT leak into the persisted stage for this turn — the pre-Step-4
 * code deliberately persisted the pre-verify stage, and we preserve that.
 *
 * Ordering (preserved exactly from the pre-Step-4 inline code):
 *
 *   (B1) Transition-hint empty fallbacks (`summary_edit_request`,
 *        `grace_window_offer`).
 *   (B2) Generic provider-issue fallback when the reply is still empty.
 *   (C1) `verifyAndRepairOutbound` — only substitutes on
 *        `summary_fact_drift` under the Step-3 factual-only policy; all
 *        other shapes are log-only.
 *   (C2) `runHallucinationGuard` — price mismatch / field-rejection /
 *        order-placed hallucination substitutions.
 */
export function decidePostStateOutbound(
  input: PostStateOutboundInput,
): OutboundDecisionResult {
  return finalizeOutboundDecision(decidePostStateOutboundImpl(input));
}

function decidePostStateOutboundImpl(
  input: PostStateOutboundInput,
): Omit<OutboundDecisionResult, "replyAuthor"> {
  const logEntries: OutboundDecisionLogEntry[] = [];
  let reply = input.replyText;
  let decision: OutboundDecisionKind = "allow";
  let reason: OutboundDecisionReason = "allow";
  let detectedShape: OutboundReplyShape | null = null;
  let markedSummaryShown = false;

  // ------------------------------------------------------------------
  // (B1) Transition-hint empty fallbacks
  // ------------------------------------------------------------------
  if (input.controllerTransitionHint === "summary_edit_request" && !reply) {
    reply =
      input.preferredLanguage === "ar"
        ? SUMMARY_EDIT_REQUEST_AR
        : SUMMARY_EDIT_REQUEST_EN;
    decision = "replace_fallback";
    reason = "fallback_empty_reply";
  }
  if (input.controllerTransitionHint === "grace_window_offer" && !reply) {
    reply = input.buildDeterministicGraceWindowReply(input.preferredLanguage);
    decision = "replace_fallback";
    reason = "fallback_empty_reply";
  }

  // ------------------------------------------------------------------
  // (B2) Generic provider-issue fallback
  // ------------------------------------------------------------------
  if (!reply) {
    reply = input.buildProviderIssueFallbackReply(input.preferredLanguage);
    decision = "replace_fallback";
    reason = "fallback_empty_reply";
    logEntries.push({
      level: "warn",
      message: `[octopus] LLM produced empty reply, using fallback conversation=${input.conversationId}`,
    });
  }

  // ------------------------------------------------------------------
  // (B3) Class-15 bypass repair (2026-04-21).
  //
  // Invariant: a route-intent turn with no active quoted route MUST
  // have gone through `get_price`. If the LLM instead free-composed
  // an area clarification ("What's the delivery area?", "Which part
  // of Kuwait City?") without calling the tool, downstream turns
  // end up with no server-owned `pendingPickupAreaNameEn` /
  // `requestedSlot`, which is the exact state shape that collapses
  // the next single-token reply into a symmetric route.
  //
  // This branch detects the shape on the CURRENT turn and substitutes
  // a short deterministic "send both areas together" reply so the
  // next turn carries a full route back into the tool-owned path.
  // It is a last-line defense: the prompt-side STRICT rule plus the
  // directive-registry / `CustomerIntentHint=pricing_request` hint
  // should already be pushing the LLM to call `get_price`, and this
  // substitution is only expected to fire when the LLM skips the
  // tool entirely.
  //
  // The gate is AND of three preconditions (all precomputed by the
  // caller) so it never fires on healthy turns:
  //
  //   - `classFifteenBypass === true` (caller saw route-evidence
  //     inbound + no active quoted route + get_price NOT called).
  //   - `reply` matches the narrow free-composed area-ask shape.
  //   - The decision is still `allow` (we haven't already replaced
  //     with a higher-priority substitution).
  // ------------------------------------------------------------------
  if (
    input.classFifteenBypass === true &&
    decision === "allow" &&
    looksLikeFreeComposedAreaClarification(reply)
  ) {
    const repaired = buildClass15BypassRepairReply(input.preferredLanguage);
    logEntries.push({
      level: "warn",
      message: `[class-15/bypass] route_intent_turn_bypassed_get_price conversation=${input.conversationId} shape=free_composed_area_clarification original=${JSON.stringify(reply).slice(0, 240)}`,
      detail: {
        shape: "free_composed_area_clarification",
        bypass: true,
      },
    });
    reply = repaired;
    decision = "replace_authoritative";
    reason = "replace_get_price_bypass";
  }

  // ------------------------------------------------------------------
  // (C1) verifyAndRepairOutbound (Step-3 factual-only policy)
  // ------------------------------------------------------------------
  if (input.conversationControllerEntry) {
    const verification: VerifyOutboundResult = verifyAndRepairOutbound({
      replyText: reply,
      entry: input.conversationControllerEntry,
      missingFields: input.missingFields,
      language: input.preferredLanguage,
    });
    detectedShape = verification.shape;
    if (verification.shape !== "ok" && verification.shape !== "empty") {
      logEntries.push({
        level: "warn",
        message: `[one-brain/verify] outbound_shape=${verification.shape} replaced=${verification.replaced} reason=${verification.reason} conversation=${input.conversationId} original=${JSON.stringify(reply).slice(0, 240)}`,
        detail: {
          shape: verification.shape,
          replaced: verification.replaced,
          verifyReason: verification.reason,
        },
      });
    }
    if (verification.replaced) {
      reply = verification.replyText;
      decision = "replace_authoritative";
      reason = "replace_summary_fact_drift";
      markedSummaryShown = true;
    } else if (verification.shape === "clarifying_question") {
      // The LLM is doing repair work (clarifying a persisted-value conflict).
      // Surface this outcome explicitly so downstream metrics can separate
      // natural clarifying turns from generic "allow" passthrough.
      if (decision === "allow") {
        reason = "preserve_clarification";
      }
    }

    // ------------------------------------------------------------------
    // (C1.5) Compact factual-drift observation (Step-5, log-only)
    //
    // Narrow backstop for the gap left by Step 3: a compact reply (stub
    // or ack) that makes a factual claim about a tracked field (phone
    // tail or stored name) with the wrong value. The full-summary path
    // can't see these because they don't pass the structural bar.
    //
    // This branch is deliberately observational-only in Step 5. We do
    // not substitute, do not change the decision kind, and do not
    // introduce a new reason code. The goal is to measure prod
    // frequency and false-positive rate before adding a substitution
    // path. If signal is clean, a later step flips substitution on.
    //
    // Skip conditions:
    //   - verifyAndRepairOutbound already substituted (full-summary
    //     drift path took over — don't double-surface).
    //   - Shape is `clarifying_question` (LLM is already repairing).
    //   - Shape is `empty` (no reply to inspect).
    //   - Shape is `summary_fact_drift` (handled by C1 above).
    //
    // We only run on `ok` / `stub_summary` / `route_price_recap` /
    // `standalone_ack`. Also require a complete-enough draft so the
    // stored phone/name comparisons are meaningful.
    // ------------------------------------------------------------------
    if (
      !verification.replaced &&
      verification.shape !== "clarifying_question" &&
      verification.shape !== "empty" &&
      verification.shape !== "summary_fact_drift"
    ) {
      const draft = input.conversationControllerEntry.bookingDraft;
      const hasStoredFacts =
        Boolean(draft.senderPhone || draft.recipientPhone) ||
        Boolean(draft.senderName || draft.recipientName);
      if (hasStoredFacts) {
        const compact = verifyCompactFactualClaims(
          reply,
          input.conversationControllerEntry,
        );
        if (!compact.consistent && compact.mismatches.length > 0) {
          const first = compact.mismatches[0];
          logEntries.push({
            level: "warn",
            message: `[one-brain/compact-fact-drift] observed kind=${first.kind} mentioned=${first.mentioned} expected=${first.expected} shape=${verification.shape} conversation=${input.conversationId} original=${JSON.stringify(reply).slice(0, 240)}`,
            detail: {
              kind: first.kind,
              mentioned: first.mentioned,
              expected: first.expected,
              shape: verification.shape,
              mismatchCount: compact.mismatches.length,
              substituted: false,
            },
          });
        }
      }
    }

    // ------------------------------------------------------------------
    // (C2) Hallucination guard
    // ------------------------------------------------------------------
    if (input.hallucinationGuardEnabled) {
      const guardDecision = runHallucinationGuard({
        replyText: reply,
        entry: input.conversationControllerEntry,
        missingFields: input.missingFields,
        rejectionsThisTurn: input.hallucinationGuardRejections,
        stageAtTurnStart: input.stageAtTurnStart,
        language: input.preferredLanguage,
        nextRequiredAction: input.nextRequiredAction,
        activeQuotedPrices: input.activeQuotedPrices ?? undefined,
        cancelContradicted: input.cancelContradicted ?? null,
      });
      if (guardDecision.claims.length > 0) {
        logEntries.push({
          level: "warn",
          message: `[one-brain/hallucination-guard] blocked=${guardDecision.blocked} claims=${guardDecision.claims.join(",")} reason=${guardDecision.reason} substituted_from=${guardDecision.substitutedFrom} conversation=${input.conversationId} original=${JSON.stringify(reply).slice(0, 240)}`,
          detail: {
            blocked: guardDecision.blocked,
            claims: guardDecision.claims.join(","),
            guardReason: guardDecision.reason,
            substitutedFrom: guardDecision.substitutedFrom,
          },
        });
      }
      if (guardDecision.blocked) {
        reply = guardDecision.replyText;
        decision = "replace_authoritative";
        reason = reasonForHallucinationClaim(guardDecision);
      }
    }
  }

  return {
    decision,
    reason,
    replyText: reply,
    detectedShape,
    markedSummaryShown,
    logEntries,
  };
}
