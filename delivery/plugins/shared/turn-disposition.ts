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

// ---------------------------------------------------------------------------
// Cut #6 (2026-04-23, Reloc 5 input-side): pre-LLM prompt-shaping
// disposition.
//
// DEPLOY_CANARY_PROMPT_SHAPING_DISPOSITION_MODULE_MARKER.
//
// ## Why this exists
//
// Cut #5 inverted the OUTPUT side: `decideTurnDisposition` runs after
// the LLM returns, using proposer signals (`turn_intent`,
// `awaiting_confirmation`, `post_order_intent`) to decide whether the
// state-machine directive is consumed. That fixed the authoring axis
// on the way OUT of the LLM. But the prompt going IN to the LLM was
// still state-authored: `next_required_action`, `forbidden_reply_shapes`,
// `requested_slot_rule`, and hard rules 4 and 10 were injected every
// turn, biasing the LLM to draft as a state machine. On turns where
// meaning ≠ `continue_step`, Cut #5 would then suppress the directive
// substitution and let the (already biased) draft through — yielding
// step-shaped replies despite the inverted gate.
//
// Cut #6 inverts the INPUT side. A pre-LLM heuristic disposition is
// computed from server-side signals only (no LLM call) and shapes the
// prompt: on `continue_step` the prompt is identical to today; on
// anything else, the prompt carries state FACTS but drops state
// AUTHORING imperatives.
//
// ## The chicken-and-egg and how we resolve it
//
// `decideTurnDisposition` reads proposer output. Proposer output is the
// LLM's tool-call. The LLM is invoked with the prompt. So the exact
// same function can't gate the prompt. Three options on the table were
// (a) pre-LLM heuristic, (b) two-call turn (cheap classify → main
// reply), (c) soften the prompt unconditionally. User chose (a): the
// prompt-shaping disposition is a weaker classifier than the post-LLM
// disposition, but its default is identity-safe (`continue_step` ≡
// today), and the four-cell matrix (pre × post) guarantees every
// combination is ≥ today's behaviour:
//
//   pre=continue_step, post=continue_step → prompt imperatives + A0c   (today)
//   pre=continue_step, post≠continue_step → prompt imperatives + passthrough
//                                            (Cut #5 alone; robotic draft, ≡ today)
//   pre≠continue_step, post=continue_step → prompt facts-only + A0c    (≡ today)
//   pre≠continue_step, post=≠continue_step → prompt facts-only + passthrough
//                                            (target state)
//
// Post-LLM is the authoritative decision; pre-LLM is a hint. Neither
// reads the other's output. Keeping them decoupled prevents a
// heuristic false-positive from cascading into an incorrect output
// decision.
//
// ## Coverage (what heuristics can reliably catch)
//
// Strong signals (regex-level is enough):
//   * `acknowledge`  — bare greeting/thanks/filler during active flow
//   * `cancel_confirmation` — cancel keywords at eligible stage
//   * `answer` (informational option/price question) — matches the
//     existing `isInformationalOptionQuestion` heuristic
//   * `requote`  — two-area/route evidence on an existing quote
//
// Weak signals (default to `continue_step` → fall through to Cut #5):
//   * `edit_field` without an explicit correction token
//   * `answer` not about informational options
//   * subtle `requote` in prose without area tokens
//
// Those weak cases remain in the "cell 2" bucket of the matrix — same
// behaviour as today, no regression.
//
// ## Not in this file
//
//   * The env flag and trace emit live at the callsite in
//     `octopus-channel/index.ts`.
//   * The prompt-gating behaviour (which imperatives to drop) lives in
//     `octopus-channel/lib/one-brain-context.ts`.
//   * The post-LLM authoritative disposition stays `decideTurnDisposition`.
// ---------------------------------------------------------------------------

export interface PromptShapingDispositionInputs {
  // Server-side signals only. All fields must be resolvable BEFORE the
  // LLM invocation — adding a field that depends on LLM output breaks
  // the contract.
  customer_text: string | null;
  stage_at_turn_start: string | null;
  has_active_quoted_route: boolean;
  requested_slot_name: string | null;
  missing_fields_count: number;

  // Injected detector callbacks so this module stays free of
  // octopus-channel dependencies (avoids a cycle: conversation-policy
  // imports from shared, shared can't import back). The callsite in
  // index.ts supplies the real regex-backed functions from
  // `conversation-policy.ts` and `quoted-options.ts`.
  detectors: {
    isInformationalOptionQuestion: (text: string | null) => boolean;
    isSimpleGreeting: (text: string) => boolean;
    isExplicitOrderConfirmation: (text: string | null) => boolean;
    // Cut 7b (2026-04-23): implicit / contextual clarifying-question
    // detector. Catches turns like "so i cant order rn if its manual
    // confirmation" that lack explicit interrogative markers but still
    // read as a question. Feeds Rule 6 (answer) so the pre-LLM
    // disposition recognises the turn as `answer`, which the A0/A0a/A0b
    // arming gate in index.ts uses to skip the legacy Region-A
    // substitutions.
    //
    // DEPLOY_CANARY_A0_DISPOSITION_ARMING_GATE_DISPOSITION_INJECTION_MARKER.
    isContextualClarifyingQuestion: (text: string | null) => boolean;
  };
}

// Stages where a cancel keyword is eligible to flag the turn as a
// pre-LLM cancel_confirmation. Matches `CANCEL_ELIGIBLE_STAGES` above
// so the two layers don't drift.
const PROMPT_SHAPING_CANCEL_ELIGIBLE_STAGES: ReadonlySet<string> =
  CANCEL_ELIGIBLE_STAGES;

// Active-flow stages where `acknowledge` can trigger. Wider than
// cancel-eligible because `acknowledge` covers the early collection
// phase too. `idle` is explicitly excluded — an `ok` with no booking
// context should remain idle and let SKILL.md govern.
const PROMPT_SHAPING_ACTIVE_FLOW_STAGES: ReadonlySet<string> = new Set<string>([
  "quoted",
  "collecting_booking_details",
  "summary_shown",
  "awaiting_confirmation",
  "order_submitted",
]);

// Narrow regex-only cancel keyword list. Intentionally tight: an
// option-switch phrase ("nvm, actually sedan") MUST NOT match here;
// those fall through to `continue_step`. If in doubt, we prefer a
// false NEGATIVE (cell 2, ≡ today) over a false POSITIVE (cell 3,
// which would drop imperatives on a real step-advance).
const PROMPT_SHAPING_CANCEL_REGEX =
  /(\bcancel(?:\s+the)?\s+(?:booking|order|request)\b|\b(?:never\s+mind|nvm)\s+the\s+whole\s+thing\b|\bstop\s+(?:the|this)\s+(?:booking|order)\b|ألغ[يى]\s*(?:الطلب|الحجز)|إلغاء\s*(?:الطلب|الحجز)|لغاء\s*(?:الطلب|الحجز))/iu;

// Option-switch short-circuit — the "cancel, actually sedan" class
// must NOT be classified as cancel. Mirrors hard rule 7.
const PROMPT_SHAPING_OPTION_SWITCH_REGEX =
  /\b(sedan|van|box|cooled?|refrig(?:erated)?|helper|express|standard|fast|normal|مبرد|مساعد|سريع|عادي|فان|بوكس|سيدان)\b/i;

// Bare-ack list for `acknowledge` during active flow. Intentionally
// tiny and post-trim; the turn must be ONLY an ack (not a cancel, not
// a question, not a route-pair, etc.). The calling code handles the
// active-flow gating; this regex is the surface-shape test.
const PROMPT_SHAPING_BARE_ACK_REGEX =
  /^(?:ok(?:ay)?|thanks?(?:\s*you)?|thx|ty|noted|got\s+it|cool|sure|hmm+|lol|alright|awesome|great|perfect|nice|تمام|تمامـ+|تمامــ+|اوك(?:ي|يه)?|شكر(?:ا|ا\s*لك|ا\s*جزيلا)?|مشكور(?:ين)?|مشكور\s+يا\s*معلم|زين|ماشي|يسلمو|يعطيك\s+العافية|ايوه|ايوا|اها|آه|اهم|لحظة|لحظه|ثانية|ثانيه)[!.?\s]*$/iu;

// Requote trigger — a fresh route/area pair on top of an existing
// quote. Keeps the bar high: requires two capitalised/area-like
// tokens separated by a "to"/"إلى"/"الى"/"من" connector. This is a
// coarse shape test; the full `get_price` tool call will
// disambiguate. False negatives (prose like "change it to salmiya")
// fall through to continue_step and rely on Cut #5.
const PROMPT_SHAPING_ROUTE_PAIR_REGEX =
  /(\b[\p{L}]{2,}\s+(?:to|till|until|>)\s+[\p{L}]{2,}\b|من\s+[\p{L}]{2,}\s+(?:إلى|الى|لـ?)\s+[\p{L}]{2,})/iu;

function buildShapingAuthored(
  disposition: Exclude<TurnDisposition, "continue_step" | "handoff">,
  policyRule: string,
  reason: string,
): TurnDispositionDecision {
  return {
    disposition,
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

function buildShapingContinue(
  policyRule: string,
  reason: string,
  fallthrough: string | null,
): TurnDispositionDecision {
  return {
    disposition: "continue_step",
    authored_directive: null,
    state_machine_call: {
      called: false,
      subroutine: null,
      result_directive: null,
    },
    policy_rule: policyRule,
    reason,
    trace_annotations: { fallthrough_reason: fallthrough },
  };
}

/**
 * Pre-LLM heuristic disposition used to shape the system prompt.
 *
 * Identity-safe default: when no rule matches, returns `continue_step`
 * and the caller keeps today's prompt unchanged. The function is a
 * pure transform — no I/O, no env reads, no logger — so it's trivially
 * testable and never blocks a turn.
 *
 * Rule order mirrors `decideTurnDisposition`'s intent (idle →
 * cancel → requote → answer → acknowledge → continue), but each rule's
 * signal is regex/structural, not proposer-structured.
 */
export function computePromptShapingDisposition(
  input: PromptShapingDispositionInputs,
): TurnDispositionDecision {
  const rawText = (input.customer_text || "").trim();

  // Rule 1: idle — no active booking. Pre-booking chit-chat turns the
  // prompt-author gate wouldn't help on anyway (SKILL.md governs).
  const stageIsIdle =
    input.stage_at_turn_start === null ||
    input.stage_at_turn_start === "idle";
  if (stageIsIdle) {
    return buildShapingAuthored(
      "idle",
      "shaping.disposition.idle",
      "pre_booking_no_active_stage",
    );
  }

  // Rule 2: no text — nothing to classify. Default to continue_step so
  // prompt carries authoring imperatives (identity-safe).
  if (!rawText) {
    return buildShapingContinue(
      "shaping.disposition.continue_step.no_text",
      "no_customer_text",
      "no_customer_text",
    );
  }

  // Rule 3: explicit order confirmation during summary/awaiting-confirm
  // is decisively a `continue_step` advance (server places the order).
  // Short-circuit so a confirmation token like "yes" doesn't look like
  // a bare ack.
  if (
    input.detectors.isExplicitOrderConfirmation(rawText) &&
    (input.stage_at_turn_start === "summary_shown" ||
      input.stage_at_turn_start === "awaiting_confirmation")
  ) {
    return buildShapingContinue(
      "shaping.disposition.continue_step.confirmation",
      "explicit_order_confirmation_at_summary",
      null,
    );
  }

  // Rule 4: cancel_confirmation — cancel keyword at eligible stage,
  // AND no option-switch token in the same utterance. Option-switch
  // phrases ("cancel, actually sedan") fall through to continue_step.
  if (
    input.stage_at_turn_start !== null &&
    PROMPT_SHAPING_CANCEL_ELIGIBLE_STAGES.has(input.stage_at_turn_start) &&
    PROMPT_SHAPING_CANCEL_REGEX.test(rawText) &&
    !PROMPT_SHAPING_OPTION_SWITCH_REGEX.test(rawText)
  ) {
    return buildShapingAuthored(
      "cancel_confirmation",
      "shaping.disposition.cancel_confirmation.keyword_at_eligible_stage",
      `cancel_keyword_at_${input.stage_at_turn_start}`,
    );
  }

  // Rule 5: requote — fresh route/area evidence while an active quote
  // exists. Bar is intentionally high (two-area pair regex); prose
  // restates fall through.
  if (
    input.has_active_quoted_route &&
    PROMPT_SHAPING_ROUTE_PAIR_REGEX.test(rawText)
  ) {
    return buildShapingAuthored(
      "requote",
      "shaping.disposition.requote.route_pair_on_active_quote",
      "route_pair_evidence_on_active_quote",
    );
  }

  // Rule 6: answer — informational option/price question on an active
  // quote. Two paths, first match wins:
  //
  //   6a. Explicit interrogative — `isInformationalOptionQuestion`.
  //       Requires a wh-word, `how much`, `?`, or Arabic analogue
  //       PAIRED with price/option/vehicle vocab. This is the pre-
  //       existing path; keep it to ensure prompt-shaping and hard
  //       rule 5 agree on what "answer-only" means.
  //
  //   6b. Implicit / contextual clarifying question (Cut 7b) —
  //       `isContextualClarifyingQuestion`. Catches indirect forms
  //       ("so i cant order rn if its manual confirmation", "if its
  //       manual confirm then i cant continue", "does that mean i
  //       need to wait") that the explicit detector misses. This is
  //       the detector that closes the Cut 7b arming-gate loop: the
  //       same turn that should skip A0/A0a/A0b arming also reads
  //       as `answer` at the pre-LLM layer.
  //
  // Both require an active quoted route so we don't promote
  // pre-quote banter; the downstream prompt-shape / arming-gate
  // effects only matter once options exist.
  if (input.has_active_quoted_route) {
    if (input.detectors.isInformationalOptionQuestion(rawText)) {
      return buildShapingAuthored(
        "answer",
        "shaping.disposition.answer.informational_option_question",
        "informational_option_question_on_active_quote",
      );
    }
    if (input.detectors.isContextualClarifyingQuestion(rawText)) {
      return buildShapingAuthored(
        "answer",
        "shaping.disposition.answer.contextual_clarifying_question",
        "contextual_clarifying_question_on_active_quote",
      );
    }
  }

  // Rule 7: acknowledge — bare greeting / thanks / filler during
  // active flow. Must NOT be cancel (ruled out by order), NOT an
  // informational question (ruled out by order), NOT an explicit
  // confirmation (ruled out by rule 3). Short-text-only, post-trim.
  if (
    input.stage_at_turn_start !== null &&
    PROMPT_SHAPING_ACTIVE_FLOW_STAGES.has(input.stage_at_turn_start) &&
    (input.detectors.isSimpleGreeting(rawText) ||
      PROMPT_SHAPING_BARE_ACK_REGEX.test(rawText))
  ) {
    return buildShapingAuthored(
      "acknowledge",
      "shaping.disposition.acknowledge.bare_filler_in_active_flow",
      `bare_ack_at_${input.stage_at_turn_start}`,
    );
  }

  // Rule 8 (default): continue_step. Identity-safe — caller keeps
  // today's prompt unchanged. `fallthrough_reason` is null on the
  // happy path (the customer is actually advancing the flow) and
  // named when a heuristic sub-matched but didn't promote.
  return buildShapingContinue(
    "shaping.disposition.continue_step.default",
    "default_continue_step",
    null,
  );
}
