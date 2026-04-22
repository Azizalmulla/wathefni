// ---------------------------------------------------------------------------
// Phase 2 Milestone 3 (2026-04-22): action-selection gate — SHADOW.
//
// DEPLOY_CANARY_ACTION_SELECTION_GATE_MODULE_MARKER: M3 action-selection shadow
//
// ## Architectural role
//
// Today's action-selection is a pure function of state:
// `computeOneBrainNextRequiredAction` picks the next directive from
// `missing_fields`. Whether the server then SUBSTITUTES that directive
// (vs passes the LLM's freeform reply through) is decided at dispatch
// time by two hard-coded word-list gates:
//
//   1. `isExplicitOrderConfirmation(text)` → hold on summary (LLM owns
//      the create_simple_order + confirmation reply).
//   2. `isInformationalOptionQuestion(text)` + stage=quoted + collection-
//      or-summary directive → hold (LLM owns the informational answer).
//
// Both are surface-word heuristics. They miss natural-language variants,
// misfire on borderline cases, and create the "bot plowed through the
// form while I was asking a question" failure mode that SKILL.md's
// "Answering informational questions is advancing on its own" bullet
// tries to paper over.
//
// M3 inverts action-selection on meaning. The server decides "advance /
// hold / no_op" from `turn_intent.kind` (with `awaiting_confirmation`
// preferred on summary-stage turns where both are available). The two
// legacy gates become observables — their collapse path is:
//
//   - `isExplicitOrderConfirmation` → subsumed by `awaiting_confirmation
//     = confirm_order` on summary turns.
//   - `isInformationalOptionQuestion` → subsumed by `turn_intent.kind =
//     clarifying_question` on collection / quoted turns.
//
// ## Shadow-first
//
// This module ships the pure gate + a diff computation that runs BOTH
// decisions (legacy + M3) on every directive-eligible turn and logs the
// agreement bucket: `agree`, `disagree_m3_holds`, `disagree_m3_advances`.
// Agreement rate is the core metric gating M3's flip-to-live; low
// agreement means either the classifier is wrong (tune the prompt) or
// the legacy gates were catching cases the semantic layer misses (tune
// the policy table).
//
// Live behaviour is unchanged in this commit. `computeActionSelectionShadow`
// is called AFTER the legacy gates have already decided and the caller
// has already populated `directiveActionForRender` — it only observes.
//
// ## Exhaustiveness
//
// `KIND_ACTION_POLICY` is typed `Record<TurnIntentKind, ActionPolicy>` via
// `satisfies`, same tripwire as M1/M2.
// ---------------------------------------------------------------------------

import type {
  TurnIntentKind,
  AwaitingConfirmationKind,
} from "./proposer-schema";
import type { DirectiveAction } from "./directive-reply-registry";

// ---------------------------------------------------------------------------
// Decision shape.
//
// `advance` — emit the directive + its server-rendered ask. Default path.
// `hold`    — do NOT emit the directive this turn; let the LLM's freeform
//             reply pass through. The customer asked a question, needs an
//             informational answer, or the directive is a summary turn the
//             LLM owns (confirmation + create_simple_order).
// `no_op`   — neither advance nor re-ask. The customer said "ok"/"thanks"
//             and doesn't need another ask in response to an ack. Rare;
//             falls back to whatever the LLM composed.
//
// Each carries a `reason` that the analyzer buckets against.
// ---------------------------------------------------------------------------

export type ActionSelectionDecision =
  | { kind: "advance"; reason: ActionAdvanceReason }
  | { kind: "hold"; reason: ActionHoldReason }
  | { kind: "no_op"; reason: ActionNoOpReason };

export type ActionAdvanceReason =
  | "answered_kind_advances"
  | "corrected_prior_advances"
  | "turn_intent_missing_fallback_advance"
  | "low_confidence_fallback_advance"
  | "ac_edit_order_advances"
  | "ac_cancel_order_advances";

export type ActionHoldReason =
  | "ti_clarifying_question_holds"
  | "ti_refused_or_stuck_holds_for_retry"
  | "ti_unclear_holds_for_retry"
  | "ac_confirm_order_llm_owns_reply"
  | "ac_informational_question_llm_owns_reply"
  | "ac_unclear_holds_for_retry";

export type ActionNoOpReason =
  | "ti_acknowledgement_no_op"
  | "ac_coherence_pleasantry_no_op";

// ---------------------------------------------------------------------------
// Legacy decision (what today's code computes).
//
// This is a reconstruction of the two inline gates at index.ts ~5882/5923,
// lifted into a pure function so the shadow diff is comparing like with
// like. When M3 flips, the legacy function retires and this module owns
// the decision directly.
// ---------------------------------------------------------------------------

export interface LegacyGateInput {
  directiveAction: DirectiveAction;
  stage: string | null;
  /** Result of `isInformationalOptionQuestion(customerText)`. Passed in
   *  by the caller to avoid pulling the regex tables into this module. */
  isInformationalOptionQuestion: boolean;
  /** Result of `isExplicitOrderConfirmation(customerText)`. */
  isExplicitOrderConfirmation: boolean;
}

const LEGACY_COLLECTION_OR_SUMMARY: ReadonlySet<DirectiveAction> = new Set<DirectiveAction>([
  "ASK_SENDER_NAME_AND_PHONE_DECISION",
  "ASK_SENDER_NAME",
  "ASK_SENDER_PHONE",
  "ASK_RECIPIENT_NAME_AND_PHONE",
  "ASK_PICKUP_ADDRESS",
  "ASK_DELIVERY_ADDRESS",
  "ASK_MISSING_AREAS",
  "ASK_PICKUP_AREA",
  "ASK_DELIVERY_AREA",
  "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED",
]);

export type LegacyDecisionKind = "advance" | "hold_informational" | "hold_confirm";

export function computeLegacyActionDecision(
  input: LegacyGateInput,
): LegacyDecisionKind {
  const isSummary =
    input.directiveAction ===
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";
  if (isSummary && input.isExplicitOrderConfirmation) {
    return "hold_confirm";
  }
  if (
    LEGACY_COLLECTION_OR_SUMMARY.has(input.directiveAction) &&
    input.stage === "quoted" &&
    input.isInformationalOptionQuestion
  ) {
    return "hold_informational";
  }
  return "advance";
}

// ---------------------------------------------------------------------------
// M3 decision — turn_intent / awaiting_confirmation driven.
//
// Priority order:
//   1. On summary-stage directives, prefer `awaiting_confirmation` when
//      present (richer 6-way classification specifically for that stage).
//      Fall back to `turn_intent` when absent.
//   2. On all other directives, use `turn_intent`.
//   3. Missing classification OR low confidence → advance (conservative
//      default; matches legacy fall-through).
// ---------------------------------------------------------------------------

type ActionPolicy =
  | { kind: "advance"; reason: ActionAdvanceReason }
  | { kind: "hold"; reason: ActionHoldReason }
  | { kind: "no_op"; reason: ActionNoOpReason };

const KIND_ACTION_POLICY = {
  answered_full: { kind: "advance", reason: "answered_kind_advances" },
  answered_partial: { kind: "advance", reason: "answered_kind_advances" },
  answered_unasked: { kind: "advance", reason: "answered_kind_advances" },
  corrected_prior: { kind: "advance", reason: "corrected_prior_advances" },
  clarifying_question: { kind: "hold", reason: "ti_clarifying_question_holds" },
  acknowledgement: { kind: "no_op", reason: "ti_acknowledgement_no_op" },
  refused_or_stuck: {
    kind: "hold",
    reason: "ti_refused_or_stuck_holds_for_retry",
  },
  unclear: { kind: "hold", reason: "ti_unclear_holds_for_retry" },
} as const satisfies Record<TurnIntentKind, ActionPolicy>;

type AcActionPolicy =
  | { kind: "advance"; reason: ActionAdvanceReason }
  | { kind: "hold"; reason: ActionHoldReason }
  | { kind: "no_op"; reason: ActionNoOpReason };

const AC_ACTION_POLICY = {
  confirm_order: { kind: "hold", reason: "ac_confirm_order_llm_owns_reply" },
  cancel_order: { kind: "advance", reason: "ac_cancel_order_advances" },
  edit_order: { kind: "advance", reason: "ac_edit_order_advances" },
  informational_question: {
    kind: "hold",
    reason: "ac_informational_question_llm_owns_reply",
  },
  coherence_pleasantry: {
    kind: "no_op",
    reason: "ac_coherence_pleasantry_no_op",
  },
  unclear: { kind: "hold", reason: "ac_unclear_holds_for_retry" },
} as const satisfies Record<AwaitingConfirmationKind, AcActionPolicy>;

export interface ActionSelectionInput {
  directiveAction: DirectiveAction;
  stage: string | null;
  tiKind: TurnIntentKind | null;
  tiConfidence: "high" | "medium" | "low" | null;
  acKind: AwaitingConfirmationKind | null;
}

export function decideActionSelection(
  input: ActionSelectionInput,
): ActionSelectionDecision {
  const isSummary =
    input.directiveAction ===
    "WRITE_FULL_ORDER_SUMMARY_OR_PLACE_ORDER_IF_CONFIRMED";

  // Summary turns: prefer AC classification.
  if (isSummary && input.acKind) {
    return AC_ACTION_POLICY[input.acKind];
  }

  // Everything else: turn_intent.
  if (input.tiKind === null) {
    return {
      kind: "advance",
      reason: "turn_intent_missing_fallback_advance",
    };
  }
  if (input.tiConfidence === "low") {
    return {
      kind: "advance",
      reason: "low_confidence_fallback_advance",
    };
  }
  return KIND_ACTION_POLICY[input.tiKind];
}

// ---------------------------------------------------------------------------
// Agreement diff.
//
// Maps the legacy three-value enum onto the M3 decision and reports one
// of three buckets:
//
//   - `agree`                 → both say the same thing (allowing the
//                               equivalence hold_informational ≡
//                               hold_informational, hold_confirm ≡ hold).
//   - `disagree_m3_holds`     → legacy advances, M3 holds. New coverage
//                               M3 would add (e.g. a question the word
//                               list didn't catch).
//   - `disagree_m3_advances`  → legacy holds, M3 advances. Potential
//                               regression — the legacy heuristic
//                               caught something M3 misses. These are
//                               the cases to inspect most carefully
//                               before flipping.
// ---------------------------------------------------------------------------

export type ActionAgreement =
  | "agree"
  | "disagree_m3_holds"
  | "disagree_m3_advances"
  | "disagree_other";

export function diffActionDecisions(
  legacy: LegacyDecisionKind,
  m3: ActionSelectionDecision,
): ActionAgreement {
  const legacyIsHold = legacy !== "advance";
  const m3IsHold = m3.kind === "hold" || m3.kind === "no_op";
  if (legacyIsHold && m3IsHold) return "agree";
  if (!legacyIsHold && !m3IsHold) return "agree";
  if (!legacyIsHold && m3IsHold) return "disagree_m3_holds";
  if (legacyIsHold && !m3IsHold) return "disagree_m3_advances";
  return "disagree_other";
}

// ---------------------------------------------------------------------------
// Shadow emit.
// ---------------------------------------------------------------------------

export interface ActionSelectionShadowEmit {
  conversation_id: string;
  directive_action: string;
  stage: string;
  ti_kind: string;
  ti_confidence: string;
  ac_kind: string;
  legacy_decision: string;
  m3_decision_kind: string;
  m3_decision_reason: string;
  agreement: ActionAgreement;
}

export function formatActionSelectionShadowLog(
  e: ActionSelectionShadowEmit,
): string {
  return (
    `[action-selection/shadow] ` +
    `conversation=${e.conversation_id} ` +
    `directive=${e.directive_action} ` +
    `stage=${e.stage} ` +
    `ti_kind=${e.ti_kind} ` +
    `ti_confidence=${e.ti_confidence} ` +
    `ac_kind=${e.ac_kind} ` +
    `legacy=${e.legacy_decision} ` +
    `m3=${e.m3_decision_kind} ` +
    `m3_reason=${e.m3_decision_reason} ` +
    `agreement=${e.agreement}`
  );
}
