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
  buildDeterministicOrderSummaryFromSnapshot,
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
import type { BookingTruthSnapshot } from "../../shared/booking-truth-snapshot";

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
  | "replace_summary_completion_checkpoint"
  | "replace_transaction_artifact_missing"
  | "replace_price_mismatch"
  | "replace_field_rejection_hallucination"
  | "replace_order_placed_hallucination"
  | "replace_state_write_hallucination"
  | "replace_stale_missing_field_ask"
  | "replace_untracked_multi_edit_ask"
  | "replace_clarify_option_before_proceed"
  | "replace_manual_confirm_address_ask"
  | "replace_manual_confirm_handoff"
  | "replace_directive_ask"
  // Class 15 (2026-04-21): legacy get_price-bypass replacement. This
  // reason remains in the enum for log compatibility, but the live
  // customer-facing replacement path is demoted to observe-only.
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

  // Authority-cutover Phase 6 (2026-04-23): the A0 / A0a / A0b Region-A
  // substitutions for clarify-before-proceed and manual-confirm
  // address-ask / handoff were deleted in phases 2-3, along with their
  // consumer branches in `decidePreStateOutbound`. The corresponding
  // optional inputs (`buildDeterministicClarifyOptionBeforeProceedReply`,
  // `manualConfirmAddressAsk`, `manualConfirmHandoff`,
  // `buildDeterministicManualConfirmAddressAskReply`,
  // `buildDeterministicManualConfirmHandoffReply`) are gone too. The LLM
  // handles those flows end-to-end via hard rule 8 and the active-route
  // facts in the system-context block.

  /**
   * Phase 2 (2026-04-20): directive-to-reply registry inputs.
   *
   * When `directiveAction` names a directive whose registry spec is
   * `{kind: "server"}`, Region A substitutes the LLM's draft with the
   * server-rendered ask. Directives whose registry spec is
   * `{kind: "llm_owned"}` (post-order intent, summary gate) pass the
   * LLM's draft through unchanged.
   *
   * Left null when the caller has no directive computed for this turn
   * (e.g. idle stage).
   */
  directiveAction?: string | null;
  /** Pre-built renderer context (draft + entry + route + turnSeed). */
  directiveRenderContext?: DirectiveReplyRenderContext | null;
  /** Registry dispatcher; injected to avoid circular imports. */
  renderDirectiveReply?: (
    action: string,
    ctx: DirectiveReplyRenderContext,
  ) => DirectiveReplyRenderResult;
  /** Plan B: GPT final snapshot pass owns normal booking wording. */
  planBSnapshotFinalReply?: boolean;
  /** Optional bake trace for legacy authors demoted by Plan B. */
  planBLogLegacyAuthority?: boolean;

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
  bookingTruthSnapshot?: BookingTruthSnapshot | null;

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

  /**
   * Transaction checkpoint for the same turn that successfully submitted an
   * order. When true, `order_submitted` is server-owned transaction truth:
   * normal LLM wording, stale slot asks, and clarifications must not pass.
   */
  transactionResultRequired?: boolean;
  canonicalTransactionText?: string | null;

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

  /**
   * Authority cutover (2026-04-25): coverage questions intentionally do
   * NOT call `get_price`. The grounded path is:
   *
   *   LLM meaning -> check_area_coverage -> LLM wording
   *
   * When the proposer declared `pricing_action=informational_only` and
   * planned `check_area_coverage`, Class-15 may still observe a
   * route-evidence/no-get_price shape, but it must not author customer
   * text. The branch logs observe-only instead.
   */
  classFifteenCoverageInformationalOnly?: boolean;

  /** Plan B: final reply already came from the post-drain snapshot pass, so
   *  old normal reply authors become observe-only while factual and
   *  transaction validators remain active. */
  planBSnapshotFinalReply?: boolean;
  /** Optional bake trace for legacy authors demoted by Plan B. */
  planBLogLegacyAuthority?: boolean;

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
const PENDING_ORDER_EDIT_TTL_MS = 15 * 60 * 1000;

function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function textContainsUrl(text: string): boolean {
  return /\bhttps?:\/\/\S+/i.test(text);
}

function textContainsOrderId(text: string): boolean {
  return /\bORDER-[A-Za-z0-9-]+\b/i.test(text);
}

function transactionSafeOrderSubmittedFallback(language: "ar" | "en"): string {
  return language === "ar"
    ? "تم إنشاء الطلب، لحظة أجهز لك تفاصيل الطلب ورابط الدفع."
    : "Your order has been created. Give me a moment to prepare the order details and payment link.";
}

function transactionSafeSubmitFailure(language: "ar" | "en"): string {
  return language === "ar"
    ? "آسف، ما أقدر أأكد إنشاء الطلب من غير نتيجة آمنة من النظام. بحوله للدعم يتأكدون من الطلب."
    : "Sorry, I can't safely confirm that the order was created without a system result. I'll pass it to support to verify the booking.";
}

function waitForConfirmationReply(language: "ar" | "en"): string {
  return language === "ar" ? "تبي تأكد الطلب؟" : "Shall I confirm this order?";
}

function slotLabel(language: "ar" | "en", field: string | null | undefined): string {
  const key = String(field || "").trim();
  const en: Record<string, string> = {
    sender_name: "sender name",
    recipient_name: "recipient name",
    sender_phone: "sender phone",
    recipient_phone: "recipient phone",
    pickup_area: "pickup area",
    dropoff_area: "delivery area",
    pickup_block: "pickup block",
    pickup_street: "pickup street",
    pickup_house: "pickup house/building",
    pickup_extra: "pickup address details",
    delivery_block: "delivery block",
    delivery_street: "delivery street",
    delivery_house: "delivery house/building",
    delivery_extra: "delivery address details",
  };
  const ar: Record<string, string> = {
    sender_name: "اسم المرسل",
    recipient_name: "اسم المستلم",
    sender_phone: "رقم المرسل",
    recipient_phone: "رقم المستلم",
    pickup_area: "منطقة الاستلام",
    dropoff_area: "منطقة التوصيل",
    pickup_block: "قطعة الاستلام",
    pickup_street: "شارع الاستلام",
    pickup_house: "منزل/مبنى الاستلام",
    pickup_extra: "تفاصيل الاستلام",
    delivery_block: "قطعة التوصيل",
    delivery_street: "شارع التوصيل",
    delivery_house: "منزل/مبنى التوصيل",
    delivery_extra: "تفاصيل التوصيل",
  };
  return (language === "ar" ? ar[key] : en[key]) || key.replace(/_/g, " ") || "this field";
}

function renderSlotConflictReply(
  snapshot: BookingTruthSnapshot,
  language: "ar" | "en",
): string {
  const action = snapshot.nextAction;
  const field = action.type === "resolve_slot_conflict" ? action.field : snapshot.conflictSlot;
  const conflict = snapshot.slotConflicts.find((item) => item.field === field);
  const label = slotLabel(language, field);
  const current = String(conflict?.value || "").trim();
  const incoming = String(conflict?.conflictCandidate || "").trim();
  if (language === "ar") {
    if (current && incoming) return `${label}: «${current}» أو «${incoming}»؟`;
    return `ممكن تأكد ${label}؟`;
  }
  if (current && incoming) return `${label}: "${current}" or "${incoming}"?`;
  return `Please confirm the ${label}.`;
}

function renderPendingEditReply(snapshot: BookingTruthSnapshot, language: "ar" | "en"): string {
  const fields = snapshot.pendingOrderEdits?.fields || [];
  const labels = fields.map((field) => slotLabel(language, field)).join(", ");
  if (language === "ar") return labels ? `أرسل القيم الجديدة لـ ${labels}.` : "أرسل التعديل المطلوب.";
  return labels ? `Send the updated value for: ${labels}.` : "Send the update you want to make.";
}

function renderSnapshotNextActionReply(params: {
  snapshot: BookingTruthSnapshot;
  language: "ar" | "en";
  canonicalTransactionText?: string | null;
}): { text: string; markSummaryShown: boolean } | null {
  const { snapshot, language } = params;
  switch (snapshot.nextAction.type) {
    case "show_summary":
      return {
        text: buildDeterministicOrderSummaryFromSnapshot({ snapshot, language }),
        markSummaryShown: true,
      };
    case "wait_for_confirmation":
      return { text: waitForConfirmationReply(language), markSummaryShown: false };
    case "show_quote": {
      const pickup = snapshot.route.pickup.nameEn || snapshot.route.pickup.nameAr || "pickup";
      const dropoff = snapshot.route.dropoff.nameEn || snapshot.route.dropoff.nameAr || "delivery";
      const options = (snapshot.quote.optionCatalog || [])
        .filter((option: any) => option.quoted_price != null)
        .slice(0, 6)
        .map((option: any) => {
          const label =
            language === "ar"
              ? option.label_ar || option.label_en || option.delivery_type
              : option.label_en || option.label_ar || option.delivery_type;
          const price =
            option.formatted_price ||
            `${Number(option.quoted_price).toFixed(3)} KWD`;
          return `- ${label}: ${price}`;
        });
      return {
        text:
          language === "ar"
            ? [`سعر التوصيل من ${pickup} إلى ${dropoff}:`, ...options].join("\n")
            : [`Delivery quote from ${pickup} to ${dropoff}:`, ...options].join("\n"),
        markSummaryShown: false,
      };
    }
    case "ask_edit_target":
      return {
        text:
          language === "ar"
            ? "أكيد، شنو التعديل اللي تبونه؟"
            : "Sure, what would you like to change?",
        markSummaryShown: false,
      };
    case "answer_question_then_wait_for_confirmation":
      return {
        text:
          language === "ar"
            ? "أكيد، شنو حابين تعرفون قبل ما نكمل؟"
            : "Sure, what would you like to know before we continue?",
        markSummaryShown: false,
      };
    case "pause_confirmation":
      return {
        text: language === "ar" ? "أكيد، خذوا وقتكم." : "Sure, take your time.",
        markSummaryShown: false,
      };
    case "cancel_or_confirm_cancel":
      return {
        text:
          language === "ar"
            ? "تبون ألغي مسودة الطلب؟"
            : "Would you like me to cancel this draft booking?",
        markSummaryShown: false,
      };
    case "ask_clarification_about_confirmation":
      return {
        text:
          language === "ar"
            ? "تبون تأكدون الطلب، تعدلون شي، توقفون شوي، أو تلغونه؟"
            : "Would you like to confirm, change something, pause, or cancel?",
        markSummaryShown: false,
      };
    case "resolve_slot_conflict":
      return { text: renderSlotConflictReply(snapshot, language), markSummaryShown: false };
    case "resolve_pending_edit":
      return { text: renderPendingEditReply(snapshot, language), markSummaryShown: false };
    case "submit_order":
      return { text: transactionSafeSubmitFailure(language), markSummaryShown: false };
    case "show_order_result": {
      const canonical = String(params.canonicalTransactionText || "").trim();
      return {
        text: canonical || transactionSafeOrderSubmittedFallback(language),
        markSummaryShown: false,
      };
    }
    case "handoff_or_transaction_failure":
      return { text: transactionSafeSubmitFailure(language), markSummaryShown: false };
    default:
      return null;
  }
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
  const canonicalHasOrderId = textContainsOrderId(canonical);
  const replyHasOrderId = textContainsOrderId(reply);
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
    case "state_write_hallucination":
      return "replace_state_write_hallucination";
    case "stale_missing_field_ask":
      return "replace_stale_missing_field_ask";
    default:
      return "allow";
  }
}

function detectMultiEditAsk(reply: string): string[] {
  const text = String(reply || "").toLowerCase();
  if (!/\b(?:send|share|provide|give|tell)\b/.test(text)) return [];
  if (!/\b(?:new|updated?|change|edit|correct|replacement)\b/.test(text)) return [];
  const fields: string[] = [];
  const add = (field: string, re: RegExp) => {
    if (re.test(text)) fields.push(field);
  };
  add("sender name", /\bsender(?:'s)?\s+name\b/);
  add("sender phone", /\bsender(?:'s)?\s+(?:phone|number)\b/);
  add("recipient name", /\brecipient(?:'s)?\s+name\b/);
  add("recipient phone", /\brecipient(?:'s)?\s+(?:phone|number)\b/);
  add("service", /\b(?:service|option|delivery\s+type)\b/);
  add("pickup address", /\bpick\s*up\s+address\b|\bpickup\s+address\b/);
  add("delivery address", /\bdelivery\s+address\b|\bdrop\s*off\s+address\b|\bdropoff\s+address\b/);
  return fields;
}

function untrackedMultiEditFallback(
  fields: string[],
  language: "ar" | "en",
): string {
  if (language === "ar") {
    return "أي تعديل نبدأ فيه؟ ارسل اسم الحقل والقيمة الجديدة.";
  }
  const firstTwo = fields.slice(0, 2);
  if (firstTwo.length === 2) {
    return `Which should we change first: ${firstTwo[0]} or ${firstTwo[1]}?`;
  }
  return "Which field should we change first?";
}

function hasActivePendingOrderEdits(entry: PersistedConversationControllerEntry | null): boolean {
  const pending = entry?.pendingOrderEdits ?? null;
  if (!pending || !Array.isArray(pending.fields) || pending.fields.length === 0) return false;
  return Date.now() - Number(pending.askedTs || 0) <= PENDING_ORDER_EDIT_TTL_MS;
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
 *        ORDER- id), gated by the static transactional-artifact check. This
 *        intentionally survives post-quote stages because payment/tracking
 *        artifacts are safety-critical business truth, not stylistic wording.
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
      if (input.planBSnapshotFinalReply) {
        if (input.planBLogLegacyAuthority) {
          logEntries.push({
            level: "info",
            message: `[plan-b/legacy-authority] observe_only phase=pre directive=${input.directiveAction} conversation=${input.conversationId}`,
            detail: {
              action: input.directiveAction,
              wouldRenderChars: outcome.text.length,
            },
          });
        }
      } else {
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
  if (
    reply &&
    sg &&
    input.sessionIsRecent &&
    canonical &&
    !sameRouteQuoteSkip &&
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
  // (B1.5) Post-order transaction invariant
  // ------------------------------------------------------------------
  if (
    input.transactionResultRequired === true &&
    input.conversationControllerEntry?.stage === "order_submitted"
  ) {
    const canonical = String(input.canonicalTransactionText || "").trim();
    const canonicalHasTransactionArtifact =
      !!canonical && (textContainsUrl(canonical) || textContainsOrderId(canonical));
    const replacement = canonicalHasTransactionArtifact
      ? canonical
      : transactionSafeOrderSubmittedFallback(input.preferredLanguage);
    logEntries.push({
      level: canonicalHasTransactionArtifact ? "info" : "warn",
      message:
        `[post-order/invariant] replaced non-transaction reply conversation=${input.conversationId} ` +
        `canonical_artifact=${canonicalHasTransactionArtifact ? "yes" : "no"} original=${JSON.stringify(reply).slice(0, 240)}`,
      detail: {
        canonicalArtifact: canonicalHasTransactionArtifact,
        originalLen: reply ? reply.length : 0,
      },
    });
    return {
      decision: "replace_authoritative",
      reason: "replace_transaction_artifact_missing",
      replyText: replacement,
      detectedShape: null,
      markedSummaryShown: false,
      logEntries,
    };
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
  // (B2.2) Snapshot next-action authority
  // ------------------------------------------------------------------
  const snapshotAuthorityReply = input.bookingTruthSnapshot
    && !input.planBSnapshotFinalReply
    ? renderSnapshotNextActionReply({
        snapshot: input.bookingTruthSnapshot,
        language: input.preferredLanguage,
        canonicalTransactionText: input.canonicalTransactionText,
      })
    : null;
  if (snapshotAuthorityReply) {
    logEntries.push({
      level: "info",
      message:
        `[booking-truth-snapshot/authority] conversation=${input.conversationId} ` +
        `next_action=${input.bookingTruthSnapshot?.nextAction.type || "-"} ` +
        `replaced=${snapshotAuthorityReply.text === reply ? "no" : "yes"}`,
      detail: {
        nextAction: input.bookingTruthSnapshot?.nextAction.type || null,
        previousDecision: decision,
      },
    });
    return {
      decision:
        snapshotAuthorityReply.text === reply ? decision : "replace_authoritative",
      reason:
        snapshotAuthorityReply.text === reply ? reason : "replace_directive_ask",
      replyText: snapshotAuthorityReply.text,
      detectedShape: null,
      markedSummaryShown: snapshotAuthorityReply.markSummaryShown,
      logEntries,
    };
  }

  // ------------------------------------------------------------------
  // (B2.5) Multi-edit asks must be backed by controller state
  // ------------------------------------------------------------------
  if (
    !input.planBSnapshotFinalReply &&
    reply &&
    input.conversationControllerEntry &&
    !hasActivePendingOrderEdits(input.conversationControllerEntry) &&
    input.conversationControllerEntry.stage !== "idle"
  ) {
    const editFields = detectMultiEditAsk(reply);
    if (editFields.length >= 2) {
      logEntries.push({
        level: "warn",
        message: `[guard] Replaced untracked multi-edit ask conversation=${input.conversationId} fields=${editFields.join(",")}`,
        detail: {
          fields: editFields.join(","),
        },
      });
      reply = untrackedMultiEditFallback(editFields, input.preferredLanguage);
      decision = "replace_authoritative";
      reason = "replace_untracked_multi_edit_ask";
    }
  }

  // ------------------------------------------------------------------
  // (B3) Class-15 get_price-bypass observation (2026-04-25).
  //
  // This branch used to replace any tool-less area ask on an idle
  // route-evidence turn with a deterministic "send pickup and delivery
  // together" template. That was old state-first authority: normal
  // booking starts like "Hello I want to order food" could be treated as
  // error recovery and the LLM's natural reply was stomped.
  //
  // It is now observe-only. Tool omission is a signal for metrics and
  // prompt/tool-boundary work, not permission to author customer-facing
  // text from a state-shape heuristic.
  // ------------------------------------------------------------------
  if (
    input.classFifteenBypass === true &&
    decision === "allow" &&
    looksLikeFreeComposedAreaClarification(reply)
  ) {
    logEntries.push({
      level: input.classFifteenCoverageInformationalOnly === true ? "info" : "warn",
      message: `[class-15/bypass] observe_only conversation=${input.conversationId} coverage_informational=${input.classFifteenCoverageInformationalOnly === true ? "yes" : "no"} shape=free_composed_area_clarification original=${JSON.stringify(reply).slice(0, 240)}`,
      detail: {
        shape: "free_composed_area_clarification",
        bypass: true,
        observe_only: true,
        coverage_informational:
          input.classFifteenCoverageInformationalOnly === true,
      },
    });
  }

  // ------------------------------------------------------------------
  // (C1) verifyAndRepairOutbound (Step-3 factual-only policy)
  // ------------------------------------------------------------------
  if (input.conversationControllerEntry) {
    const entry = input.conversationControllerEntry;
    const stageAtTurnEnd = (entry as any).stage ?? null;
    const bookingStepAtTurnEnd = (entry as any).bookingStep ?? null;
    const stageStartedAtSummary =
      input.stageAtTurnStart === "summary_shown" ||
      input.stageAtTurnStart === "awaiting_confirmation";
    const summaryStageReached =
      stageAtTurnEnd === "summary_shown" ||
      stageAtTurnEnd === "awaiting_confirmation" ||
      bookingStepAtTurnEnd === "summary_pending" ||
      bookingStepAtTurnEnd === "awaiting_summary_confirmation";
    const hasAuthoritativeQuoteFacts =
      input.missingFields.length === 0 &&
      Boolean(entry.quotePickupAreaNameEn || entry.quotePickupAreaNameAr) &&
      Boolean(entry.quoteDropoffAreaNameEn || entry.quoteDropoffAreaNameAr) &&
      Boolean(entry.selectedDeliveryType) &&
      entry.quotedPrice != null;
    const snapshotAllowsSummaryCheckpoint =
      !input.planBSnapshotFinalReply &&
      input.bookingTruthSnapshot?.nextAction.type === "show_summary";
    const summaryCompletionCheckpoint =
      snapshotAllowsSummaryCheckpoint &&
      input.stageAtTurnStart !== null &&
      summaryStageReached &&
      !stageStartedAtSummary &&
      hasAuthoritativeQuoteFacts;

    const verification: VerifyOutboundResult = verifyAndRepairOutbound({
      replyText: reply,
      entry,
      missingFields: input.missingFields,
      language: input.preferredLanguage,
      summaryCompletionCheckpoint,
      bookingTruthSnapshot: input.bookingTruthSnapshot ?? null,
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
          summaryCompletionCheckpoint,
        },
      });
    }
    if (verification.replaced && !input.planBSnapshotFinalReply) {
      reply = verification.replyText;
      decision = "replace_authoritative";
      reason =
        verification.reason === "substituted_summary_completion_checkpoint"
          ? "replace_summary_completion_checkpoint"
          : "replace_summary_fact_drift";
      markedSummaryShown = true;
    } else if (verification.replaced && input.planBSnapshotFinalReply) {
      if (input.planBLogLegacyAuthority) {
        logEntries.push({
          level: "warn",
          message: `[plan-b/legacy-authority] observe_only phase=verify reason=${verification.reason} conversation=${input.conversationId}`,
          detail: {
            shape: verification.shape,
            verifyReason: verification.reason,
            wouldReplace: true,
          },
        });
      }
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
        activeQuotedPrices:
          input.activeQuotedPrices ??
          input.bookingTruthSnapshot?.quote.validQuotedPrices ??
          undefined,
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
