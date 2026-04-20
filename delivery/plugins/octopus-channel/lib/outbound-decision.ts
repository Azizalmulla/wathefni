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
  verifyAndRepairOutbound,
  verifyCompactFactualClaims,
} from "../../shared/outbound-verify";
import type {
  RouteQuoteOption,
  StoredQuotedRoute,
  SameRouteQuoteFollowupAction,
} from "./quoted-options";

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
  logEntries: OutboundDecisionLogEntry[];
};

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
  const logEntries: OutboundDecisionLogEntry[] = [];
  let reply = input.replyText;
  let decision: OutboundDecisionKind = "allow";
  let reason: OutboundDecisionReason = "allow";

  // ------------------------------------------------------------------
  // (A0) Clarify-before-proceed substitution (Bug 1, 2026-04-20).
  //
  // When the upstream directive gate fired `CLARIFY_OPTION_BEFORE_PROCEED`
  // (vague proceed on a route with a manual-confirm option, no option
  // named by the customer), the LLM's draft reply is unreliable — it
  // may ask for sender name, emit `start_booking`, or silently default
  // to the verified option. The server's answer is deterministic: list
  // the priced options (flagging manual-confirm ones) and ask the
  // customer to pick. This branch runs FIRST so it outranks canonical
  // overwrite, empty-fill, price whitelist, and same-route quote
  // correction, all of which would substitute the wrong text here.
  // ------------------------------------------------------------------
  if (
    input.clarifyOptionBeforeProceed &&
    input.activeQuotedRoute &&
    input.buildDeterministicClarifyOptionBeforeProceedReply
  ) {
    const substitute = input.buildDeterministicClarifyOptionBeforeProceedReply({
      language: input.preferredLanguage,
      route: input.activeQuotedRoute,
    });
    logEntries.push({
      level: "warn",
      message: `[guard] Substituted clarify-before-proceed reply conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs} routeKey=${input.activeQuotedRoute.routeKey}`,
      detail: {
        routeKey: input.activeQuotedRoute.routeKey,
        sessionKey: input.sessionKeyForLogs,
        originalLen: reply ? reply.length : 0,
      },
    });
    return {
      decision: "replace_authoritative",
      reason: "replace_clarify_option_before_proceed",
      replyText: substitute,
      detectedShape: null,
      markedSummaryShown: false,
      logEntries,
    };
  }

  // ------------------------------------------------------------------
  // (A0a) Manual-confirm address-ask substitution (Bug 4, 2026-04-20).
  //
  // When the controller's directive for this turn is
  // `ASK_PICKUP_ADDRESS_FOR_MANUAL_CONFIRM` or
  // `ASK_DELIVERY_ADDRESS_FOR_MANUAL_CONFIRM`, the LLM's draft reply
  // historically dropped the "needs manual confirmation" signal and
  // blended with direct-booking address asks ("Express refrigerated
  // van is 2.250 KWD. Send the pickup address first."). We replace
  // the reply with a deterministic, server-composed text that always
  // names the option, its price, AND the manual-confirmation caveat
  // before the address ask. Runs BEFORE canonical overwrite, empty-
  // fill, price whitelist, and same-route quote correction so the
  // manual-confirm path is the dominant Region-A substitution.
  // ------------------------------------------------------------------
  if (
    input.manualConfirmAddressAsk &&
    input.activeQuotedRoute &&
    input.buildDeterministicManualConfirmAddressAskReply
  ) {
    const substitute = input.buildDeterministicManualConfirmAddressAskReply({
      language: input.preferredLanguage,
      route: input.activeQuotedRoute,
      option: input.manualConfirmAddressAsk.option,
      side: input.manualConfirmAddressAsk.side,
    });
    logEntries.push({
      level: "warn",
      message: `[guard] Substituted manual-confirm ${input.manualConfirmAddressAsk.side}-address ask conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs} routeKey=${input.activeQuotedRoute.routeKey} option=${input.manualConfirmAddressAsk.option.delivery_type}`,
      detail: {
        routeKey: input.activeQuotedRoute.routeKey,
        optionType: input.manualConfirmAddressAsk.option.delivery_type,
        side: input.manualConfirmAddressAsk.side,
        originalLen: reply ? reply.length : 0,
      },
    });
    return {
      decision: "replace_authoritative",
      reason: "replace_manual_confirm_address_ask",
      replyText: substitute,
      detectedShape: null,
      markedSummaryShown: false,
      logEntries,
    };
  }

  // ------------------------------------------------------------------
  // (A0b) Manual-confirm handoff substitution (Bug 4 companion).
  //
  // When both pickup + delivery addresses are present on a manual-
  // confirm selection, the controller emits
  // `REQUEST_HANDOFF_FOR_MANUAL_CONFIRM`. Substitute with a
  // deterministic handoff message so the customer-facing text is
  // consistent regardless of whether the LLM emits the
  // `request_handoff` op this turn.
  // ------------------------------------------------------------------
  if (
    input.manualConfirmHandoff &&
    input.activeQuotedRoute &&
    input.buildDeterministicManualConfirmHandoffReply
  ) {
    const substitute = input.buildDeterministicManualConfirmHandoffReply({
      language: input.preferredLanguage,
      route: input.activeQuotedRoute,
      option: input.manualConfirmHandoff.option,
    });
    logEntries.push({
      level: "warn",
      message: `[guard] Substituted manual-confirm handoff reply conversation=${input.conversationId} sessionKey=${input.sessionKeyForLogs} routeKey=${input.activeQuotedRoute.routeKey} option=${input.manualConfirmHandoff.option.delivery_type}`,
      detail: {
        routeKey: input.activeQuotedRoute.routeKey,
        optionType: input.manualConfirmHandoff.option.delivery_type,
        originalLen: reply ? reply.length : 0,
      },
    });
    return {
      decision: "replace_authoritative",
      reason: "replace_manual_confirm_handoff",
      replyText: substitute,
      detectedShape: null,
      markedSummaryShown: false,
      logEntries,
    };
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
