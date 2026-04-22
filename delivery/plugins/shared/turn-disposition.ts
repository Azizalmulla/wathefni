// ---------------------------------------------------------------------------
// Turn disposition — relocation 5 (Phase 5.0 shadow).
//
// DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER: decideTurnDisposition
//
// Shadow-only in this cut. The layer runs in parallel with the existing
// state machine and emits `disposition=` / `disposition_rule=` /
// `authored_directive=` / `state_machine_called=` /
// `state_consistency=` tokens on `[turn-decision/trace]`. Nothing in
// production reads the disposition yet; the callsite continues to run
// `computeOneBrainNextRequiredAction` unchanged and that output drives
// the live directive.
//
// This file implements the contract in
// `ARCHITECTURE_RELOC5_TURN_DISPOSITION.md`.
//
// ## What this file is, in one paragraph
//
// The layer's classification of what the customer is trying to do THIS
// turn, chosen from a tight, closed set of eight kinds
// (`TurnDisposition`). The classification is the AUTHORING decision —
// state advance? server-authored directive? render scope? — independent
// of the state machine's missing-field-first view of the world. When
// the disposition is `continue_step` the layer delegates to the state
// machine (the narrow subroutine the state machine is actually good
// at); every other disposition is layer-authored.
//
// Reloc 4 shape: "state generates a directive, layer may veto it."
// Reloc 5 shape: "layer authors what the turn should do; state
// machine is a narrow subroutine called only when layer says
// `continue_step`."
//
// ## Safeguards
//
//   * Low-confidence / null proposer classifications fall through to
//     `continue_step` with a named `fallthrough_reason`. Meaning must
//     be trustworthy before it authors behaviour.
//   * Hallucination-guard fires still take precedence over the layer's
//     classification when manual-confirm ambiguity is present —
//     shipping the customer to handoff is safer than letting the
//     layer guess.
//   * Shadow-only: the callsite does not consume the decision yet.
//
// ## Not in this file
//
//   * Trace emit (lives in `turn-decision.ts`).
//   * Callsite wiring (lives in `octopus-channel/index.ts`).
//   * State-machine subroutine invocation (stays on legacy path for
//     Phase 5.0; flip happens in Phase 5.1).
// ---------------------------------------------------------------------------

import type {
  AwaitingConfirmationKind,
  PostOrderIntentKind,
  ProposedTurnKind,
  TurnIntentConfidence,
  TurnIntentKind,
  TurnIntentAddressedField,
} from "./proposer-schema";

// ---------------------------------------------------------------------------
// Disposition set (v1).
//
// Tight and closed. Each row corresponds to a distinct control-flow
// outcome — state advance, authored directive, render scope. New kinds
// require a relocation-5 revision; unknown values are rejected.
// ---------------------------------------------------------------------------

export type TurnDisposition =
  | "continue_step"
  | "answer"
  | "requote"
  | "cancel_confirmation"
  | "edit_field"
  | "acknowledge"
  | "handoff"
  | "idle";

export const TURN_DISPOSITIONS: readonly TurnDisposition[] = [
  "continue_step",
  "answer",
  "requote",
  "cancel_confirmation",
  "edit_field",
  "acknowledge",
  "handoff",
  "idle",
] as const;

// ---------------------------------------------------------------------------
// Inputs.
//
// Closed struct; adding a field is a contract change. See
// `ARCHITECTURE_RELOC5_TURN_DISPOSITION.md` for field-by-field rationale.
// ---------------------------------------------------------------------------

export interface TurnDispositionInputs {
  // (1) Meaning signals — proposer-derived, first-class. `null` covers
  // classifier failure / timeout / structured-output reject; rule 2
  // routes that to `continue_step` with `fallthrough_reason=no_proposer`.
  proposer: {
    turn_kind: ProposedTurnKind | null;
    ti_kind: TurnIntentKind | null;
    ti_confidence: TurnIntentConfidence | null;
    ti_addressed_fields: TurnIntentAddressedField[];
    ac_kind: AwaitingConfirmationKind | null;
    po_kind: PostOrderIntentKind | null;
  } | null;

  // (2) Addressed-fields bookkeeping — intersection of the proposer's
  // addressed_fields with state-machine `missing`, plus the non-missing
  // delta. Drives edit-vs-continue and partial-answer rendering.
  addressed_missing_fields: string[];
  addressed_non_missing_fields: string[];

  // (3) State snapshot — the only state reads the layer does. Missing
  // fields COUNT (not the list) is enough for disposition; resolving
  // WHICH missing field is the state-machine subroutine's job.
  state: {
    stage_at_turn_start: string | null;
    has_active_quoted_route: boolean;
    active_quoted_route_has_manual_confirm_option: boolean;
    has_summary_shown: boolean;
    is_post_order: boolean;
    missing_fields_count: number;
  };

  // (4) Tool-result context that materially affects disposition.
  tool_context: {
    get_price_ran_this_turn: boolean;
    start_booking_drained_this_turn: boolean;
    hallucination_guard_fired: boolean;
  };

  // (5) Callsite hints (kept minimal).
  hints: {
    same_route_switch_option: boolean;
  };

  // (6) State-machine's candidate directive for THIS turn, read from the
  // legacy path. Used in shadow so `continue_step` can populate
  // `state_machine_call.result_directive` by delegation and the
  // consistency check can compare layer-authored directives against
  // state-machine output.
  state_machine_candidate_directive: string | null;
}

// ---------------------------------------------------------------------------
// Outputs.
// ---------------------------------------------------------------------------

export interface TurnDispositionDecision {
  disposition: TurnDisposition;

  // What the layer authored. `null` means "layer decided no server
  // directive this turn" (answer / acknowledge / idle, plus the
  // other non-continue_step dispositions in Phase 5.0 shadow — real
  // directive strings come in Phase 5.1+).
  authored_directive: string | null;

  // Set on every turn. Names whether the layer delegated to the state
  // machine (disposition = continue_step) and which narrow subroutine.
  state_machine_call: {
    called: boolean;
    subroutine: "next_missing_field" | "post_order_routing" | null;
    result_directive: string | null;
  };

  // Stable policy-rule id for auditability. Shape:
  // `layer.disposition.<rule>` to match the existing naming in Reloc
  // 2/3/4 policy hits.
  policy_rule: string;
  reason: string;

  // Trace annotations. `fallthrough_reason` names the safety path the
  // decision took when meaning was untrustworthy (null proposer / low
  // confidence / etc.), so the bake analyzer can bucket
  // noise-driven fallthroughs separately from confident authoring.
  trace_annotations: {
    fallthrough_reason: string | null;
  };
}

// ---------------------------------------------------------------------------
// State-consistency classification.
//
// `state_consistency` is the trace-time comparison between what the
// layer authored and what the state machine would have done. Phase 5.0
// uses always-emit (compact values; cheap) so the analyzer can bucket
// cleanly by rule and measure quiet-agree turns vs loud-disagree turns.
// If the volume proves noisy, Phase 5.1 can switch to emit-on-disagree.
// ---------------------------------------------------------------------------

export type StateConsistency =
  | "agree"
  // Layer delegated to the state machine; by construction they're the
  // same directive (continue_step).
  | "agree_delegated"
  // Layer authored null; state machine would have authored a directive.
  | "disagree_layer_suppress"
  // Layer authored a directive; state machine would have authored null.
  | "disagree_layer_author"
  // Both authored non-null but different strings.
  | "disagree_mismatch";

export function classifyStateConsistency(
  disposition: TurnDisposition,
  layerAuthored: string | null,
  stateMachineCandidate: string | null,
): StateConsistency {
  if (disposition === "continue_step") {
    return "agree_delegated";
  }
  if (layerAuthored === null && stateMachineCandidate === null) {
    return "agree";
  }
  if (layerAuthored === null && stateMachineCandidate !== null) {
    return "disagree_layer_suppress";
  }
  if (layerAuthored !== null && stateMachineCandidate === null) {
    return "disagree_layer_author";
  }
  if (layerAuthored === stateMachineCandidate) {
    return "agree";
  }
  return "disagree_mismatch";
}

// ---------------------------------------------------------------------------
// Internal helpers.
// ---------------------------------------------------------------------------

function tiConfidenceIsTrustworthy(
  confidence: TurnIntentConfidence | null,
): boolean {
  // Matches the A1 semantic-gate trust floor (Reloc 3). Low / null
  // classifications fall through to continue_step.
  return confidence === "high" || confidence === "medium";
}

const CANCEL_ELIGIBLE_STAGES: ReadonlySet<string> = new Set<string>([
  "summary_shown",
  "awaiting_confirmation",
  "collecting_booking_details",
]);

const IDLE_TURN_KINDS_EXCLUDE: ReadonlySet<ProposedTurnKind> = new Set<ProposedTurnKind>([
  "initial_route",
  "address_collection",
  "booking_detail_collection",
  "confirmation_or_cancel",
  "post_order_chat",
]);

const HANDOFF_EXEMPT_TI_KINDS: ReadonlySet<TurnIntentKind> = new Set<TurnIntentKind>([
  "clarifying_question",
  "answered_partial",
  "corrected_prior",
]);

const ACK_TI_KINDS: ReadonlySet<TurnIntentKind> = new Set<TurnIntentKind>([
  "acknowledgement",
  "unclear",
  "refused_or_stuck",
]);

const ACK_PO_KINDS: ReadonlySet<PostOrderIntentKind> = new Set<PostOrderIntentKind>([
  "unclear",
  "customer_support",
]);

function buildContinueStep(
  input: TurnDispositionInputs,
  policyRule: string,
  reason: string,
  fallthroughReason: string | null,
): TurnDispositionDecision {
  return {
    disposition: "continue_step",
    authored_directive: input.state_machine_candidate_directive,
    state_machine_call: {
      called: true,
      subroutine: input.state.is_post_order ? "post_order_routing" : "next_missing_field",
      result_directive: input.state_machine_candidate_directive,
    },
    policy_rule: policyRule,
    reason,
    trace_annotations: { fallthrough_reason: fallthroughReason },
  };
}

function buildAuthored(
  disposition: Exclude<TurnDisposition, "continue_step">,
  policyRule: string,
  reason: string,
): TurnDispositionDecision {
  return {
    disposition,
    // Phase 5.0 shadow: non-continue dispositions author null. Phase
    // 5.1+ will substitute real DirectiveAction strings (e.g.
    // CONFIRM_CANCEL_ORDER, REQUEST_HANDOFF_FOR_MANUAL_CONFIRM) as
    // each disposition is flipped live.
    authored_directive: null,
    state_machine_call: {
      called: false,
      subroutine: null,
      result_directive: null,
    },
    policy_rule: policyRule,
    reason,
    trace_annotations: { fallthrough_reason: null },
  };
}

// ---------------------------------------------------------------------------
// Main decision function — ordered rule match. Rule 1 wins first.
//
// Rule order mirrors `ARCHITECTURE_RELOC5_TURN_DISPOSITION.md#policy-rules-v1`
// with one explicit safeguard ordering: rule 2 (no_proposer) is placed
// AFTER rule 1 (idle) so pre-booking chit-chat stays idle even when
// the proposer failed; and BEFORE every other rule so missing meaning
// never silently authors behaviour.
// ---------------------------------------------------------------------------

export function decideTurnDisposition(
  input: TurnDispositionInputs,
): TurnDispositionDecision {
  const { proposer, state, tool_context, hints } = input;

  // Rule 1: idle. Pre-booking / chit-chat turns — SKILL.md governs.
  // Check this BEFORE the no_proposer fallthrough so a chit-chat turn
  // with a failed classifier stays idle rather than waking the state
  // machine.
  const stageIsIdle =
    state.stage_at_turn_start === null ||
    state.stage_at_turn_start === "idle";
  if (stageIsIdle) {
    const turnKindTriggersBooking =
      proposer?.turn_kind !== null &&
      proposer?.turn_kind !== undefined &&
      IDLE_TURN_KINDS_EXCLUDE.has(proposer.turn_kind);
    if (!turnKindTriggersBooking) {
      return {
        disposition: "idle",
        authored_directive: null,
        state_machine_call: {
          called: false,
          subroutine: null,
          result_directive: null,
        },
        policy_rule: "layer.disposition.idle",
        reason: "pre_booking_chit_chat",
        trace_annotations: { fallthrough_reason: null },
      };
    }
  }

  // Rule 2: no_proposer → continue_step (safety net for classifier
  // failure). State grounds the turn; trace names the fallthrough.
  if (!proposer) {
    return buildContinueStep(
      input,
      "layer.disposition.continue_step.no_proposer",
      "no_proposer_fallthrough",
      "no_proposer",
    );
  }

  // Rule 3: handoff. When the hallucination guard fired on a
  // manual-confirm-capable route AND the turn isn't clearly a
  // clarifying question / partial answer / correction, route to a
  // human. Safer than letting the layer guess on an ambiguous turn
  // where the LLM's draft was already untrusted.
  if (
    tool_context.hallucination_guard_fired &&
    state.active_quoted_route_has_manual_confirm_option &&
    (proposer.ti_kind === null ||
      !HANDOFF_EXEMPT_TI_KINDS.has(proposer.ti_kind))
  ) {
    return buildAuthored(
      "handoff",
      "layer.disposition.handoff.manual_confirm_guard",
      "hallucination_guard_on_manual_confirm_route",
    );
  }

  // Rule 4: cancel_confirmation. Cancel at summary / awaiting-confirm /
  // mid-collection (shipped live in Phase 5.2 per open-Q3). Shadow
  // still classifies it so the analyzer has a full picture.
  if (
    proposer.ac_kind === "cancel_order" &&
    state.stage_at_turn_start !== null &&
    CANCEL_ELIGIBLE_STAGES.has(state.stage_at_turn_start) &&
    tiConfidenceIsTrustworthy(proposer.ti_confidence)
  ) {
    return buildAuthored(
      "cancel_confirmation",
      "layer.disposition.cancel_confirmation.at_eligible_stage",
      `cancel_order_at_${state.stage_at_turn_start}`,
    );
  }

  // Rule 5: requote. A fresh route turn on top of an existing quote,
  // OR `get_price` drained this turn (classifier noise defence: even
  // if turn_kind was misclassified, the tool call proves intent).
  const freshRouteOnActiveQuote =
    proposer.turn_kind === "initial_route" && state.has_active_quoted_route;
  if (freshRouteOnActiveQuote || tool_context.get_price_ran_this_turn) {
    return buildAuthored(
      "requote",
      "layer.disposition.requote.fresh_route_or_get_price",
      freshRouteOnActiveQuote
        ? "initial_route_on_active_quote"
        : "get_price_ran_this_turn",
    );
  }

  // Rule 6: edit_field. Correction with a concrete non-missing field
  // addressed. Fine-grained edits stay under `continue_step` (state
  // machine handles the re-ask).
  if (
    proposer.ti_kind === "corrected_prior" &&
    input.addressed_non_missing_fields.length > 0 &&
    tiConfidenceIsTrustworthy(proposer.ti_confidence)
  ) {
    return buildAuthored(
      "edit_field",
      "layer.disposition.edit_field.corrected_prior",
      `corrected_fields=${input.addressed_non_missing_fields.length}`,
    );
  }

  // Rule 7: answer. Clarifying question OR answered_partial (with a
  // real addressed-missing field). For partial answers the layer does
  // NOT author the next-field ask (per open-Q1 decision); state
  // progression happens via apply-boundary and the NEXT turn's
  // disposition rolls through `continue_step` to the state-machine
  // subroutine.
  const isClarifying = proposer.ti_kind === "clarifying_question";
  const isPartialWithAddressed =
    proposer.ti_kind === "answered_partial" &&
    input.addressed_missing_fields.length > 0;
  if (
    (isClarifying || isPartialWithAddressed) &&
    tiConfidenceIsTrustworthy(proposer.ti_confidence)
  ) {
    return buildAuthored(
      "answer",
      isClarifying
        ? "layer.disposition.answer.clarifying_question"
        : "layer.disposition.answer.answered_partial",
      isClarifying ? "clarifying_question" : "answered_partial_addressed",
    );
  }

  // Rule 8: acknowledge. Pleasantries / fillers / post-order noise.
  const isAckTiKind =
    proposer.ti_kind !== null && ACK_TI_KINDS.has(proposer.ti_kind);
  const isPostOrderAck =
    proposer.turn_kind === "post_order_chat" &&
    proposer.po_kind !== null &&
    ACK_PO_KINDS.has(proposer.po_kind);
  if (isAckTiKind || isPostOrderAck) {
    return buildAuthored(
      "acknowledge",
      "layer.disposition.acknowledge.passthrough",
      isPostOrderAck
        ? `post_order_chat_${proposer.po_kind}`
        : `ti_${proposer.ti_kind}`,
    );
  }

  // Rule 9 (default): continue_step. Low-confidence / unmatched turns
  // fall through here with a named fallthrough_reason. Explicit skip
  // for switch-option turns so the layer doesn't duplicate A4's
  // recap authoring.
  if (hints.same_route_switch_option) {
    return buildContinueStep(
      input,
      "layer.disposition.continue_step.switch_option_skip",
      "same_route_switch_option_skip",
      "same_route_switch_option",
    );
  }
  const confidenceFallthrough =
    proposer.ti_kind !== null &&
    !tiConfidenceIsTrustworthy(proposer.ti_confidence)
      ? `low_confidence_${proposer.ti_kind}`
      : null;
  return buildContinueStep(
    input,
    "layer.disposition.continue_step.default",
    "default_continue_step",
    confidenceFallthrough,
  );
}
