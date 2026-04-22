// ---------------------------------------------------------------------------
// Unified turn-decision layer — SCAFFOLD + A4 DISPATCH (relocations 1–2).
//
// DEPLOY_CANARY_TURN_DECISION_MODULE_MARKER: turn-decision scaffold observer
// DEPLOY_CANARY_TURN_DECISION_A4_RELOC_MARKER: deriveDispatch
//
// ## What this file is, in one paragraph
//
// The contract in `delivery/ARCHITECTURE_TURN_DECISION.md` describes a
// single entry point (`decideTurn`) that collapses the four current
// control-plane authorities (A1 pre-state substitution branches, A2
// state-only directive selection, A3 op-layer side-effects, A4 reply
// render) into one decision. This PR is the FIRST of the five
// relocations that arc toward that end-state. It is explicitly a PURE
// OBSERVER: it reads the outcome that the four authorities already
// produced for the current turn and repackages it into the target
// `TurnDecision` shape so we can emit one structured trace per turn.
// Zero behaviour change.
//
// Why observer-first:
//
//   * It verifies the `TurnDecision` output shape is complete against
//     every real turn shape in production, not just test fixtures.
//     Relocations 2–5 only need to replace "how" the shape is filled,
//     never "what" shape it has.
//
//   * It produces one `[turn-decision/trace]` log line per turn that
//     becomes the regression gate for subsequent relocations: each
//     relocation's correctness is "this trace line matches what the
//     authority-shaped pipeline would have produced". We can diff.
//
//   * It is trivially revertible. Deleting this module leaves the bot
//     identical.
//
// ## What this file is NOT, yet
//
//   * NOT authoritative. No production code reads a decision FROM
//     `decideTurn` yet. The callsite only observes.
//
//   * NOT wired to `TurnDecisionInput`. The full contract input shape
//     is exported here as a type for relocations 2–5 to target, but
//     the scaffold observer consumes the narrower
//     `TurnDecisionObservedContext`.
//
//   * NOT making any novel decisions. Every field of the returned
//     `TurnDecision` is derived directly from signals the callsite
//     passes in. Relocations 2–5 each replace one of those "read from
//     observed" derivations with a "decide from input" branch.
//
// ---------------------------------------------------------------------------

import type {
  PersistedBookingDraft,
  PersistedConversationControllerEntry,
} from "./conversation-policy";
import type { StoredQuotedRoute } from "./booking-draft";
import type {
  DirectiveAction,
  DirectiveReplyRendererContext,
} from "./directive-reply-registry";
import type {
  ProposedTurnKind,
  ProposedPricingDecision,
  ProposedTurnIntent,
  ProposedAwaitingConfirmation,
  ProposedPostOrderIntent,
  TurnIntentKind,
  AwaitingConfirmationKind,
  PostOrderIntentKind,
} from "./proposer-schema";
import type {
  OutboundDecisionKind,
  OutboundDecisionReason,
  ReplyAuthor,
  SameRouteQuoteFollowupAction,
} from "../octopus-channel/lib/outbound-decision";
import type { BookingFieldPatch } from "./booking-draft";
import type { SlotName } from "./dialog-state";
import type { BoundaryRejection } from "./apply-boundary";

// ---------------------------------------------------------------------------
// Reply source archetypes (six, exhaustive — see
// ARCHITECTURE_TURN_DECISION.md §"Outputs > Reply composition").
// ---------------------------------------------------------------------------

export type ReplySource =
  /** Server picks a DirectiveAction; registry renders its ask from state.
   *  Covers `replace_directive_ask`, summary render, and the
   *  summary-fact-drift repair path (delegated to the same summary
   *  builder). */
  | "server_rendered_directive"
  /** Registry-rendered ask with a `turn_intent`-keyed ack prefix (M1
   *  flip target). The ack prefix is chosen from `ACK_PREFIX_REGISTRY`
   *  and concatenated in front of the directive render. */
  | "server_ack_plus_directive"
  /** Happy-path substitution: server has better contextual information
   *  than the LLM for this specific turn shape and composes a targeted
   *  reply. Covers clarify-option, manual-confirm address-ask /
   *  handoff, same-route switch-option recap, canonical overwrite. */
  | "server_substitute_text"
  /** Something went wrong; the reply falls back to a safe neutral
   *  template that doesn't try to be contextually smart. Covers
   *  price-repair, field-rejection-hallucination repair,
   *  order-placed-hallucination repair, transaction-artifact-missing,
   *  class-15 bypass repair, grace-window, provider-issue, generic and
   *  post-order nudges, and the empty-LLM-text empty-fill path. */
  | "server_recovery_template"
  /** The layer rejected an op and needs the customer to confirm before
   *  the action is taken. Currently unused in today's four authorities;
   *  becomes possible once relocation 5 (A3 → layer) wires
   *  `cancel_disposition`. */
  | "deferred_confirm_prompt"
  /** Pass-through; the LLM's draft is emitted unchanged. Every
   *  llm_authored reply must carry a non-null `llm_authored_reason` so
   *  carve-outs are explicit. */
  | "llm_authored";

export const REPLY_SOURCES: readonly ReplySource[] = [
  "server_rendered_directive",
  "server_ack_plus_directive",
  "server_substitute_text",
  "server_recovery_template",
  "deferred_confirm_prompt",
  "llm_authored",
] as const;

// ---------------------------------------------------------------------------
// Classification: today's `OutboundDecisionReason` → `ReplySource`.
//
// Compile-time exhaustive. Every enum value is mapped explicitly. New
// reasons added to `OutboundDecisionReason` will fail to compile here
// and force a deliberate archetype choice (the same tripwire discipline
// the directive-reply-registry uses).
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// A1 substitute intents — the set of pre-state reasons that cause the legacy
// pipeline to override the LLM's reply. The layer consumes this as an input
// (observed from `preDecision.reason` when `replyAuthor === "server"`) rather
// than re-deriving A1 triggers from state, because A1 relocation is its own
// step (relocation 3).
// ---------------------------------------------------------------------------

export type A1SubstituteIntent =
  | "replace_directive_ask"
  | "replace_summary_fact_drift"
  | "replace_clarify_option_before_proceed"
  | "replace_manual_confirm_address_ask"
  | "replace_manual_confirm_handoff"
  | "replace_transaction_artifact_missing"
  | "replace_price_mismatch"
  | "replace_field_rejection_hallucination"
  | "replace_order_placed_hallucination"
  | "replace_get_price_bypass"
  | "block_provider_error"
  | "fallback_empty_reply"
  | "preserve_clarification"
  | "allow"
  | "allow_sanitized";

export function classifyReplySource(
  reason: OutboundDecisionReason,
  llmAuthoredReason?: string | null,
): { source: ReplySource; llm_authored_reason: string | null } {
  switch (reason) {
    case "allow":
    case "allow_sanitized":
      return {
        source: "llm_authored",
        llm_authored_reason: llmAuthoredReason || "authority_allow",
      };

    case "replace_directive_ask":
      return { source: "server_rendered_directive", llm_authored_reason: null };

    // Summary-fact-drift delegates to the same canonical summary
    // builder the directive registry uses on `WRITE_FULL_ORDER_SUMMARY_*`
    // turns. It's a rendered directive, not a recovery template.
    case "replace_summary_fact_drift":
      return { source: "server_rendered_directive", llm_authored_reason: null };

    case "replace_clarify_option_before_proceed":
    case "replace_manual_confirm_address_ask":
    case "replace_manual_confirm_handoff":
      return { source: "server_substitute_text", llm_authored_reason: null };

    // Recovery templates — neutral fallback text. Distinct from
    // substitute because these fire when something is off, not because
    // the server has better contextual information for a healthy turn.
    case "replace_transaction_artifact_missing":
    case "replace_price_mismatch":
    case "replace_field_rejection_hallucination":
    case "replace_order_placed_hallucination":
    case "replace_get_price_bypass":
    case "block_provider_error":
    case "fallback_empty_reply":
      return { source: "server_recovery_template", llm_authored_reason: null };

    // `preserve_clarification` preserves the LLM's reply on a
    // clarification turn (specifically tagged so post-state knows not
    // to C-drift-substitute). From the archetype contract, that is
    // just `llm_authored` with a specific reason.
    case "preserve_clarification":
      return {
        source: "llm_authored",
        llm_authored_reason: "clarification_preserved",
      };

    default: {
      // Exhaustiveness tripwire — adding a new reason without updating
      // this switch is a compile error.
      const _exhaustive: never = reason;
      void _exhaustive;
      return {
        source: "llm_authored",
        llm_authored_reason: "unclassified_reason",
      };
    }
  }
}

// ---------------------------------------------------------------------------
// Full contract input shape.
//
// Target of relocations 2–5. Not consumed by the scaffold observer.
// Lives here so future relocations have a concrete shape to target; the
// `legacy` sub-object shrinks as each authority's logic moves in.
// ---------------------------------------------------------------------------

export type ControllerStage =
  | "idle"
  | "quoted"
  | "collecting_booking_details"
  | "summary_shown"
  | "awaiting_confirmation"
  | "order_submitted"
  | "tracking"
  | string;

export interface TurnDecisionInput {
  conversation_id: string;
  turn_id: string;
  turn_start_ms: number;

  inbound: {
    text: string;
    script: "english" | "arabic" | "arabizi";
    language: "en" | "ar";
    media_types: string[];
  };

  state: {
    stage: ControllerStage;
    booking_draft: PersistedBookingDraft;
    controller_entry: PersistedConversationControllerEntry | null;
    missing_fields: SlotName[];
    active_quoted_route: StoredQuotedRoute | null;
    whatsapp_number: string | null;
    session_guard: {
      all_valid_prices: ReadonlySet<string>;
      last_tool_name: string | null;
      last_tool_ts: number;
      last_quoted_route: StoredQuotedRoute | null;
      is_recent: boolean;
      tool_age_ms: number;
      preferred_canonical_text: string | null;
      canonical_overwrite_allowed: boolean;
      canonical_overwrite_skip_reason: string | null;
    } | null;
    fast_path_pre_applied_fields: (keyof BookingFieldPatch)[] | null;
    controller_transition_hint: string | null;
    rejections_this_turn: BoundaryRejection[];
  };

  proposer: {
    present: boolean;
    valid: boolean;
    turn_kind: ProposedTurnKind | null;
    pricing_decision: ProposedPricingDecision | null;
    planned_tool_calls: string[];
    customer_reply_draft: string;
    turn_intent: ProposedTurnIntent | null;
    awaiting_confirmation: ProposedAwaitingConfirmation | null;
    post_order_intent: ProposedPostOrderIntent | null;
  };

  llm_ops: Array<{ op: string; payload: unknown }>;

  tool_results: {
    get_price: unknown;
    option_reconciliation: {
      matched_option_type: string | null;
      confidence: "high" | "medium" | "low" | "none";
      source: "llm_proposal" | "deterministic" | "both" | "none";
    } | null;
  };

  legacy: {
    clarify_option_before_proceed_flag: boolean;
    manual_confirm_address_ask: {
      side: "pickup" | "delivery";
      option_type: string;
    } | null;
    manual_confirm_handoff: { option_type: string } | null;
    same_route_quote_action: SameRouteQuoteFollowupAction | null;
    cancel_contradicted: { optionLabel: string } | null;
    class_fifteen_bypass: boolean;
  };
}

// ---------------------------------------------------------------------------
// Scaffold observer input — what the callsite knows at end-of-turn.
//
// A narrower shape than `TurnDecisionInput`. This is what relocation 1
// actually consumes. Each relocation (2–5) replaces one pair of
// (narrow-observed-field, authority-that-produced-it) with a
// (full-input-field, layer-branch-that-decides). Eventually
// `TurnDecisionObservedContext` disappears and `decideTurn` consumes
// `TurnDecisionInput` directly.
// ---------------------------------------------------------------------------

export interface TurnDecisionObservedContext {
  conversation_id: string;
  turn_id: string | null;

  // Final outcome as produced by the existing four authorities.
  outcome: {
    decision: OutboundDecisionKind;
    reason: OutboundDecisionReason;
    reply_author: ReplyAuthor;
    reply_text_chars: number;
    directive_action: string | null;
    directive_render_context_present: boolean;
    marked_summary_shown: boolean;
  };

  // A4 dispatch inputs (relocation 2). Optional because earlier smoke
  // tests and older callsites may not supply them; when absent, the
  // layer skips dispatch derivation and the trace omits layer_source /
  // dispatch_agreement (behaves exactly like the scaffold).
  a4_inputs?: {
    // A1 substitute signal (pre-state decision). Null when the LLM
    // reply was not overridden by A1. When non-null, this is the same
    // value as `preDecision.reason` in the legacy pipeline, captured
    // before A4 ran.
    a1_substitute_intent: A1SubstituteIntent | null;

    // Was the LLM's raw reply text empty at turn start? This is the
    // unconditional empty-fill signal that would trigger a recovery
    // template even without any A1 intent.
    llm_reply_empty: boolean;

    // Did the centralized hallucination guard reject any field this
    // turn? The layer treats a non-empty rejection set as evidence
    // the LLM's reply is not trustworthy for direct passthrough.
    hallucination_guard_fired: boolean;

    // Does the directive selector's candidate action have a
    // server-side renderer? Required to decide whether rendering is
    // even a physical option when the layer elects it.
    directive_has_server_renderer: boolean;
  };

  // Proposer-derived signals (already validated upstream).
  proposer: {
    present: boolean;
    schema_valid: boolean;
    schema_version: string;
    turn_kind: ProposedTurnKind | null;
    ti_kind: TurnIntentKind | null;
    ti_confidence: "high" | "medium" | "low" | null;
    ac_kind: AwaitingConfirmationKind | null;
    po_kind: PostOrderIntentKind | null;
  };

  // Staged ops that drained this turn (names only; full payloads stay
  // with their own trace lines).
  drained_op_names: string[];
  apply_boundary_rejection_fields: string[];

  // State summary — the minimum needed to log. Not the full state
  // snapshot (that arrives in relocation 2 via `TurnDecisionInput`).
  state_summary: {
    stage_at_turn_start: string | null;
    stage_at_turn_end: string | null;
    has_active_quoted_route: boolean;
    has_draft: boolean;
    missing_fields_count: number;
  };

  language: "en" | "ar";
}

// ---------------------------------------------------------------------------
// Full contract output shape — consumed by the trace emit.
// ---------------------------------------------------------------------------

export interface TurnDecision {
  op_plan: {
    entries: Array<{
      op_name: string;
      verdict: "accept" | "accept_masked" | "reject" | "defer_confirm";
      mask?: string[];
      reason: string;
    }>;
  };

  reply: {
    // Observed projection: mirrors what the legacy A4 actually did
    // this turn. Derived from `outcome.reason` via `classifyReplySource`.
    source: ReplySource;
    directive?: DirectiveAction;
    render_context?: DirectiveReplyRendererContext;
    ack_prefix?: string;
    substitute_text_chars?: number;
    llm_authored_reason?: string;

    // Layer decision (relocation 2): what the unified turn-decision
    // layer would have dispatched, computed fresh from `a4_inputs` +
    // proposer signals. Present only when `a4_inputs` was supplied.
    // This is NOT executed; legacy A4 still drives the wire reply.
    // The value exists so divergences between layer and legacy become
    // first-class trace output and can be reviewed before any flip.
    derived_source?: ReplySource;
    derived_reason?: string;
    derived_policy_rule?: string;
    dispatch_agreement?:
      | "agree"
      | "disagree_layer_passthrough"
      | "disagree_layer_substitute"
      | "disagree_other";
  };

  transitions: {
    stage_promote?: string;
    requested_slot_override?: string | null;
    marked_summary_shown: boolean;
    cancel_disposition?:
      | "confirmed_cancel"
      | "require_confirm_first"
      | "route_to_edit"
      | null;
  };

  trace: {
    decision_id: string;
    policy_hits: string[];
    semantic_signals: {
      ti_kind: TurnIntentKind | null;
      ac_kind: AwaitingConfirmationKind | null;
      po_kind: PostOrderIntentKind | null;
    };
    observed_reason: OutboundDecisionReason;
    observed_decision: OutboundDecisionKind;
    observed_reply_author: ReplyAuthor;
  };
}

// ---------------------------------------------------------------------------
// A4 DISPATCH DERIVATION (relocation 2).
//
// Fresh decision from structured inputs — the layer's own answer to
// "what reply source should this turn have?" computed independently
// of `outcome.reason`. Intended to run in parallel with legacy A4 so
// divergences surface explicitly in the trace.
//
// Policy rules are ordered; first match wins. Each rule emits a
// stable `policy_rule` id for grep-level auditing. New rules must
// claim a fresh id — never repurpose an existing one.
//
// Divergence handling:
//   - The layer does NOT bias its decision toward legacy. If the
//     layer's clean policy says `llm_authored` and legacy said
//     `server_rendered_directive`, the trace records
//     `dispatch_agreement=disagree_layer_passthrough` rather than
//     muting the difference. We want honest divergence data before
//     flipping execution.
//   - Conversely, any rule that intentionally matches legacy should
//     say so in its reason id (e.g. `a1_directive_ask_with_renderer`
//     is legacy-aligned; `a1_directive_ask_ack_passthrough` is a
//     deliberate divergence).
// ---------------------------------------------------------------------------

export interface A4DispatchInputs {
  a1_substitute_intent: A1SubstituteIntent | null;
  llm_reply_empty: boolean;
  hallucination_guard_fired: boolean;
  directive_has_server_renderer: boolean;
  proposer_ti_kind: TurnIntentKind | null;
  proposer_ti_confidence: "high" | "medium" | "low" | null;
  proposer_ac_kind: AwaitingConfirmationKind | null;
  proposer_po_kind: PostOrderIntentKind | null;
}

export interface A4DispatchDerivation {
  source: ReplySource;
  reason: string;
  policy_rule: string;
}

const A1_RECOVERY_INTENTS: ReadonlySet<A1SubstituteIntent> = new Set<A1SubstituteIntent>([
  "replace_transaction_artifact_missing",
  "replace_price_mismatch",
  "replace_field_rejection_hallucination",
  "replace_order_placed_hallucination",
  "replace_get_price_bypass",
  "block_provider_error",
  "fallback_empty_reply",
]);

const A1_SUBSTITUTE_TEXT_INTENTS: ReadonlySet<A1SubstituteIntent> = new Set<A1SubstituteIntent>([
  "replace_clarify_option_before_proceed",
  "replace_manual_confirm_address_ask",
  "replace_manual_confirm_handoff",
]);

export function deriveDispatch(input: A4DispatchInputs): A4DispatchDerivation {
  // Rule 1: A1 recovery-class intents — always recovery template.
  if (
    input.a1_substitute_intent &&
    A1_RECOVERY_INTENTS.has(input.a1_substitute_intent)
  ) {
    return {
      source: "server_recovery_template",
      reason: input.a1_substitute_intent,
      policy_rule: `layer.a1_recovery.${input.a1_substitute_intent}`,
    };
  }

  // Rule 2: A1 substitute-text intents — targeted server reply.
  if (
    input.a1_substitute_intent &&
    A1_SUBSTITUTE_TEXT_INTENTS.has(input.a1_substitute_intent)
  ) {
    return {
      source: "server_substitute_text",
      reason: input.a1_substitute_intent,
      policy_rule: `layer.a1_substitute.${input.a1_substitute_intent}`,
    };
  }

  // Rule 3: summary fact drift — canonical summary renderer.
  if (input.a1_substitute_intent === "replace_summary_fact_drift") {
    return {
      source: "server_rendered_directive",
      reason: "replace_summary_fact_drift",
      policy_rule: "layer.a1_summary_fact_drift",
    };
  }

  // Rule 4: A1 directive-ask — semantic gates apply here.
  //
  // This is where legacy behaviour and layer policy can legitimately
  // differ. Legacy fires `replace_directive_ask` whenever the pre-state
  // gate deems the LLM off-track, regardless of `turn_intent`. The
  // layer's policy consults `ti_kind`:
  //   - `acknowledgement` → passthrough (LLM's ack reply is fine)
  //   - `clarifying_question` → passthrough (user asked, LLM answers)
  //   - otherwise (and directive has renderer) → server_rendered_directive
  //
  // Low-confidence semantic signals fall through to the legacy-aligned
  // render branch to avoid acting on a classifier the layer can't
  // trust.
  if (input.a1_substitute_intent === "replace_directive_ask") {
    const tiIsHigh =
      input.proposer_ti_confidence === "high" ||
      input.proposer_ti_confidence === "medium";

    if (tiIsHigh && input.proposer_ti_kind === "acknowledgement") {
      return {
        source: "llm_authored",
        reason: "a1_directive_ask_ack_passthrough",
        policy_rule: "layer.a1_directive_ask.ack_passthrough",
      };
    }
    if (tiIsHigh && input.proposer_ti_kind === "clarifying_question") {
      return {
        source: "llm_authored",
        reason: "a1_directive_ask_clarifying_passthrough",
        policy_rule: "layer.a1_directive_ask.clarifying_passthrough",
      };
    }

    if (input.directive_has_server_renderer) {
      return {
        source: "server_rendered_directive",
        reason: "a1_directive_ask_with_renderer",
        policy_rule: "layer.a1_directive_ask.render",
      };
    }

    // No renderer — can't actually substitute; pass through with an
    // explicit reason.
    return {
      source: "llm_authored",
      reason: "a1_directive_ask_no_renderer",
      policy_rule: "layer.a1_directive_ask.no_renderer_passthrough",
    };
  }

  // Rule 5: A1 preserve_clarification — passthrough with stable reason.
  if (input.a1_substitute_intent === "preserve_clarification") {
    return {
      source: "llm_authored",
      reason: "preserve_clarification",
      policy_rule: "layer.a1_preserve_clarification",
    };
  }

  // Rule 6: Empty LLM reply + no A1 substitute → recovery (legacy has
  // its own fallback_empty_reply path; layer agrees here).
  if (input.llm_reply_empty) {
    return {
      source: "server_recovery_template",
      reason: "fallback_empty_reply",
      policy_rule: "layer.empty_llm_fallback",
    };
  }

  // Rule 7: Hallucination guard fired without an A1 intent. Legacy's
  // guard already runs inside `preDecision`, so in practice this rule
  // fires only when the guard rejected a field but the pre-state
  // pipeline decided to `allow` anyway (e.g. rejection promoted to a
  // soft warning). The layer treats it as a divergence candidate.
  if (input.hallucination_guard_fired) {
    return {
      source: "server_recovery_template",
      reason: "hallucination_guard_rejected",
      policy_rule: "layer.hallucination_guard",
    };
  }

  // Default: authority allow — LLM's reply stands.
  return {
    source: "llm_authored",
    reason: "authority_allow",
    policy_rule: "layer.authority_allow",
  };
}

export function classifyDispatchAgreement(
  observed: ReplySource,
  derived: ReplySource,
): TurnDecision["reply"]["dispatch_agreement"] {
  if (observed === derived) return "agree";
  if (derived === "llm_authored" && observed !== "llm_authored") {
    return "disagree_layer_passthrough";
  }
  if (observed === "llm_authored" && derived !== "llm_authored") {
    return "disagree_layer_substitute";
  }
  return "disagree_other";
}

// ---------------------------------------------------------------------------
// Scaffold observer: derive a TurnDecision from what actually happened.
//
// Rule of this function: it does not DECIDE anything. Every field of
// the returned decision is a mechanical projection from the observed
// outcome. If the observer and the real pipeline ever disagree, the
// observer is wrong and needs fixing — because the scaffold's
// entire purpose is to mirror, not to contradict.
//
// Relocations 2–5 will each replace one branch of this projection with
// a real decision made from `TurnDecisionInput`.
// ---------------------------------------------------------------------------

export function observeTurnDecision(
  ctx: TurnDecisionObservedContext,
): TurnDecision {
  const policyHits: string[] = [];

  // Reply source archetype from the observed reason.
  const { source, llm_authored_reason } = classifyReplySource(
    ctx.outcome.reason,
    ctx.outcome.reply_author === "llm" ? "authority_allow" : null,
  );
  policyHits.push(`classifier:${ctx.outcome.reason}->${source}`);

  // Op-plan entries — the scaffold doesn't re-verdict ops. It records
  // the observed result. If the apply boundary rejected a field, we
  // mark the corresponding entries as `accept_masked` with the
  // rejected field listed in `mask`. This is an approximation during
  // scaffold; relocation 5 replaces it with real verdicts.
  const entries: TurnDecision["op_plan"]["entries"] = [];
  for (const opName of ctx.drained_op_names) {
    const maskedHere = ctx.apply_boundary_rejection_fields.length > 0 &&
      (opName === "apply_booking_field" || opName === "fast_path_apply_booking_field");
    entries.push({
      op_name: opName,
      verdict: maskedHere ? "accept_masked" : "accept",
      mask: maskedHere ? [...ctx.apply_boundary_rejection_fields] : undefined,
      reason: maskedHere ? "observed_boundary_rejection" : "observed_applied",
    });
  }

  // Transitions — only the summary-shown promotion is observable today
  // at this emit point. The rest (stage_promote, requested_slot_override,
  // cancel_disposition) fill in as relocations 4–5 land.
  const transitions: TurnDecision["transitions"] = {
    marked_summary_shown: ctx.outcome.marked_summary_shown,
  };
  if (source === "server_rendered_directive" && ctx.outcome.directive_action) {
    transitions.stage_promote =
      ctx.state_summary.stage_at_turn_end ||
      ctx.state_summary.stage_at_turn_start ||
      undefined;
  }

  // Relocation 2: layer-derived dispatch. Runs in parallel with the
  // observed projection when `a4_inputs` is supplied. Emits an explicit
  // agreement token so divergences are grep-able.
  let derivedDispatch: A4DispatchDerivation | null = null;
  let dispatchAgreement: TurnDecision["reply"]["dispatch_agreement"] | undefined;
  if (ctx.a4_inputs) {
    derivedDispatch = deriveDispatch({
      a1_substitute_intent: ctx.a4_inputs.a1_substitute_intent,
      llm_reply_empty: ctx.a4_inputs.llm_reply_empty,
      hallucination_guard_fired: ctx.a4_inputs.hallucination_guard_fired,
      directive_has_server_renderer: ctx.a4_inputs.directive_has_server_renderer,
      proposer_ti_kind: ctx.proposer.ti_kind,
      proposer_ti_confidence: ctx.proposer.ti_confidence,
      proposer_ac_kind: ctx.proposer.ac_kind,
      proposer_po_kind: ctx.proposer.po_kind,
    });
    dispatchAgreement = classifyDispatchAgreement(source, derivedDispatch.source);
    policyHits.push(derivedDispatch.policy_rule);
    policyHits.push(`dispatch:${dispatchAgreement}`);
  }

  const decision: TurnDecision = {
    op_plan: { entries },
    reply: {
      source,
      ...(ctx.outcome.directive_action
        ? { directive: ctx.outcome.directive_action as DirectiveAction }
        : {}),
      ...(source === "server_substitute_text" ||
      source === "server_recovery_template"
        ? { substitute_text_chars: ctx.outcome.reply_text_chars }
        : {}),
      ...(llm_authored_reason ? { llm_authored_reason } : {}),
      ...(derivedDispatch
        ? {
            derived_source: derivedDispatch.source,
            derived_reason: derivedDispatch.reason,
            derived_policy_rule: derivedDispatch.policy_rule,
            dispatch_agreement: dispatchAgreement,
          }
        : {}),
    },
    transitions,
    trace: {
      decision_id: `${ctx.conversation_id}:${ctx.turn_id ?? "-"}`,
      policy_hits: policyHits,
      semantic_signals: {
        ti_kind: ctx.proposer.ti_kind,
        ac_kind: ctx.proposer.ac_kind,
        po_kind: ctx.proposer.po_kind,
      },
      observed_reason: ctx.outcome.reason,
      observed_decision: ctx.outcome.decision,
      observed_reply_author: ctx.outcome.reply_author,
    },
  };

  return decision;
}

// ---------------------------------------------------------------------------
// Trace emit — one single-line JSON-packed log per turn.
//
// Shape is designed for jq/rg post-processing: the outer shell is
// space-separated `key=value` tokens so simple grep still works; the
// structured payload is JSON under `payload=`.
// ---------------------------------------------------------------------------

export interface TurnDecisionTraceEmit {
  conversation_id: string;
  turn_id: string | null;
  language: "en" | "ar";
  decision: TurnDecision;
  input_summary: {
    stage_at_turn_start: string | null;
    stage_at_turn_end: string | null;
    has_active_quoted_route: boolean;
    drained_op_count: number;
    reply_text_chars: number;
    schema_version: string;
    proposer_present: boolean;
    proposer_valid: boolean;
  };
}

export function formatTurnDecisionTrace(e: TurnDecisionTraceEmit): string {
  const payload = {
    decision_id: e.decision.trace.decision_id,
    reply_source: e.decision.reply.source,
    directive: e.decision.reply.directive ?? null,
    llm_authored_reason: e.decision.reply.llm_authored_reason ?? null,
    ack_prefix_chars: e.decision.reply.ack_prefix?.length ?? 0,
    substitute_text_chars: e.decision.reply.substitute_text_chars ?? 0,
    // Relocation 2: layer-derived dispatch and its divergence token.
    // Always emitted (null when the callsite didn't supply `a4_inputs`)
    // so downstream analyzers can rely on field presence.
    layer: {
      derived_source: e.decision.reply.derived_source ?? null,
      derived_reason: e.decision.reply.derived_reason ?? null,
      derived_policy_rule: e.decision.reply.derived_policy_rule ?? null,
      dispatch_agreement: e.decision.reply.dispatch_agreement ?? null,
    },
    op_plan: e.decision.op_plan.entries.map((x) => ({
      op: x.op_name,
      verdict: x.verdict,
      reason: x.reason,
      mask: x.mask ?? null,
    })),
    transitions: e.decision.transitions,
    semantic_signals: e.decision.trace.semantic_signals,
    observed: {
      reason: e.decision.trace.observed_reason,
      decision: e.decision.trace.observed_decision,
      reply_author: e.decision.trace.observed_reply_author,
    },
    policy_hits: e.decision.trace.policy_hits,
    input: e.input_summary,
  };
  return (
    `[turn-decision/trace] ` +
    `conversation=${e.conversation_id} ` +
    `turn_id=${e.turn_id || "-"} ` +
    `lang=${e.language} ` +
    `reply_source=${e.decision.reply.source} ` +
    `layer_source=${e.decision.reply.derived_source || "-"} ` +
    `dispatch_agreement=${e.decision.reply.dispatch_agreement || "-"} ` +
    `observed_reason=${e.decision.trace.observed_reason} ` +
    `ti=${e.decision.trace.semantic_signals.ti_kind || "-"} ` +
    `ac=${e.decision.trace.semantic_signals.ac_kind || "-"} ` +
    `po=${e.decision.trace.semantic_signals.po_kind || "-"} ` +
    `payload=${JSON.stringify(payload)}`
  );
}
