// ---------------------------------------------------------------------------
// Cut 9.0 (2026-04-23): Turn Router — top-level meaning-first dispatcher.
//
// DEPLOY_CANARY_TURN_ROUTER_MODULE_MARKER.
//
// ## Architectural context (why this exists)
//
// Before Cut 9, every customer turn ran `computeOneBrainNextRequiredAction`
// unconditionally. Its output — a directive like `ASK_PICKUP_AREA` — was
// injected into the prompt as `next_required_action` +
// `forbidden_reply_shapes`, biased the LLM toward a form-shaped draft, and
// then A0c rendered the server-composed field ask. Three narrow gates
// (Cut #5 authoring / Cut #6 prompt-shaping / Cut 7b A0 arming) each vetoed
// one branch when meaning disagreed, but the *default* was always "state
// authors unless meaning positively disagrees". Under uncertainty, state
// won. That's why the Khairan case fell through: none of the three vetoes
// had a positive rule for pre-quote coverage questions, so the fallthrough
// `continue_step` authored `ASK_PICKUP_AREA`.
//
// This module inverts that shape. It runs ONCE per customer turn, BEFORE
// the state machine, and classifies the turn into a router MODE. Downstream
// consumers read the returned `TurnRouterDecision` to answer three
// questions:
//
//   1. `invoke_state_machine`            — should `computeOneBrainNextRequiredAction`'s
//                                          output be CONSUMED as this turn's author?
//   2. `shape_prompt_imperatives`        — should the system prompt carry
//                                          state-authoring imperatives
//                                          (next_required_action, hard
//                                          rules 4 / 10, requested_slot_rule)?
//   3. `invoke_region_a_substitutions`   — should the Region-A pre-state
//                                          substitutions (A0 clarify /
//                                          A0a manual-confirm ask / A0b
//                                          manual-confirm handoff) be
//                                          allowed to arm?
//
// Under `default_mode === "advance_form"` the router preserves today's
// behaviour exactly — fallthrough maps to `advance_form` and all three
// flags are `true`, so the runtime acts as before. Under
// `default_mode === "meaning_first"` the default flips: fallthrough maps
// to `answer`, all three flags go `false` for uncertain turns, and the
// LLM composes the reply while state stays a subroutine. State machine
// becomes invoked only when there's POSITIVE evidence the customer is
// advancing the form.
//
// ## What constitutes "positive evidence of advance_form"
//
// The router reuses the pre-LLM heuristic classifier
// (`computePromptShapingDisposition`). That classifier emits one of three
// `continue_step` policy rules today:
//
//   * `shaping.disposition.continue_step.no_text`      — customer turn had no text (empty / media-only);
//                                                        preserving advance_form is neutral, nothing to
//                                                        divert to.
//   * `shaping.disposition.continue_step.confirmation` — explicit "yes" / "confirm" at summary /
//                                                        awaiting_confirmation; textbook advance.
//   * `shaping.disposition.continue_step.default`      — FALLTHROUGH; no positive rule matched.
//
// Only the first two are "positive evidence". The default fallthrough
// loses under `meaning_first` and routes to `answer`. All other
// dispositions (`answer` / `requote` / `acknowledge` /
// `cancel_confirmation` / `edit_field` / `handoff` / `idle`) route to
// their named mode regardless of default — because a classifier that
// fired an explicit non-continue_step rule is itself positive evidence
// of whatever rule it hit.
//
// ## Scope of this initial scaffold (Cut 9.0)
//
// DARK LAND. The module exists, `classifyTurn()` runs per customer turn,
// the decision is computed, and `[turn-router/dispatch]` emits. Exactly
// ONE consumer is wired: the state-machine authoring gate at
// `octopus-channel/index.ts` ORs `routerStateMachineGateFires` into the
// existing Cut #5 `stateMachineAuthoringSkipped` boolean. That gate fires
// ONLY when the env flag is explicitly `meaning_first`; under the
// legacy default (`advance_form`), the router's flags are effectively
// inert.
//
// Env flag: `RIDERS_TURN_ROUTER_DEFAULT_MODE`
//   * unset / `"advance_form"` (default) — legacy behaviour; zero change.
//   * `"meaning_first"`                   — flip the default; fallthrough
//                                           continue_step routes to
//                                           `answer` and state machine
//                                           authoring is suppressed.
//
// The other two consumer flags (`shape_prompt_imperatives`,
// `invoke_region_a_substitutions`) are computed and traced but NOT yet
// wired — Cut #6 and Cut 7b continue to own their respective gates via
// their own env flags. Cut 9.1+ will migrate them onto the router.
//
// ## Safety story
//
// * `apply_booking_field` / proposer ops / tool pipeline run regardless
//   of router mode — slot values the customer provides still get written,
//   so the booking advances coherently even when the router lets the LLM
//   author the reply.
// * Hallucination guard, DST apply-boundary, validation, canonicalization,
//   and the summary composer all stay as subroutines — they're not in
//   the author path, they're safety nets on facts.
// * Classification errors under `meaning_first` default produce a "lost
//   turn" at worst (LLM writes a natural reply; next turn's router
//   re-classifies). No booking is broken; no invariant is violated.
// * The legacy default remains available via the env flag at all times;
//   a one-line rollback restores every byte of today's behaviour.
//
// ## Not in this file
//
// * The callsite, env flag parse, and trace emit live in
//   `octopus-channel/index.ts`. This module is pure (no logger, no env
//   reads, no Node-specific imports) so it can be unit-tested in
//   isolation and loaded by the smoke-test harness without any runtime.
// * The pre-LLM disposition heuristic (`computePromptShapingDisposition`)
//   is reused here; this module adds dispatch semantics on top. No
//   detector logic is duplicated.
// ---------------------------------------------------------------------------

import type {
  TurnDisposition,
  TurnDispositionDecision,
} from "./turn-disposition";

// ---------------------------------------------------------------------------
// Router mode.
//
// One-to-one rename from `TurnDisposition` with `continue_step` →
// `advance_form`. The rename disentangles the classifier's semantic label
// ("what did this turn mean?") from the runtime's dispatch action ("what
// should happen next?"). Future cuts may introduce modes that don't map
// 1:1 to a disposition (e.g. `advance_form_with_conflict_first` when a
// conflict-pin overrides the next missing field); keeping the vocabulary
// separate leaves room.
// ---------------------------------------------------------------------------

export type TurnRouterMode =
  | "advance_form"        // state machine authors; Region-A arms; prompt imperatives
  | "answer"              // LLM authors; state is silent on this turn
  | "requote"             // re-pricing path fires; state silent on fields
  | "acknowledge"         // short pleasantry / filler; state silent
  | "cancel_confirmation" // cancel flow
  | "edit_field"          // correction path
  | "handoff"             // manual-confirm / escalation
  | "idle";               // pre-booking; SKILL.md governs

export const TURN_ROUTER_MODES: readonly TurnRouterMode[] = [
  "advance_form",
  "answer",
  "requote",
  "acknowledge",
  "cancel_confirmation",
  "edit_field",
  "handoff",
  "idle",
] as const;

export type TurnRouterDefaultMode = "advance_form" | "meaning_first";

// ---------------------------------------------------------------------------
// Inputs & outputs.
//
// Closed structs. Adding a field is a contract change; the smoke test
// pins the keys so accidental drift is caught.
// ---------------------------------------------------------------------------

export interface TurnRouterInputs {
  /**
   * The pre-LLM heuristic classifier's decision for this turn
   * (`computePromptShapingDisposition`). `null` when:
   *   * the turn is non-customer (router never runs on agent turns), or
   *   * the classifier threw / its inputs were unavailable.
   * On `null` the router falls back to `default_mode` unconditionally —
   * safer than guessing.
   */
  classifier_decision: TurnDispositionDecision | null;

  /**
   * Runtime default; typically read from env
   * `RIDERS_TURN_ROUTER_DEFAULT_MODE` at the callsite.
   */
  default_mode: TurnRouterDefaultMode;
}

export interface TurnRouterDecision {
  /** The router's dispatch mode for this turn. */
  mode: TurnRouterMode;

  /** Policy-rule id explaining how `mode` was arrived at. */
  reason: string;

  /**
   * True when the classifier did NOT match a named rule and the runtime
   * default was applied. `default_applied=true` with
   * `mode === "advance_form"` means legacy fallthrough. With
   * `mode === "answer"` means `meaning_first` took over.
   */
  default_applied: boolean;

  /**
   * Named positive-evidence signal that proved `advance_form` when the
   * mode is `advance_form` and the default was NOT applied. `null` for
   * every other mode and for default fallthroughs.
   */
  positive_evidence: string | null;

  /**
   * Downstream consumer flags. Consumers MUST additionally check
   * `trace_annotations.default_mode === "meaning_first"` before honouring
   * these — under the legacy default, the router's gate is inert by
   * design (zero-change scaffold landing).
   */
  invoke_state_machine: boolean;
  shape_prompt_imperatives: boolean;
  invoke_region_a_substitutions: boolean;

  trace_annotations: {
    classifier_disposition: TurnDisposition | null;
    classifier_policy_rule: string | null;
    classifier_fallthrough_reason: string | null;
    default_mode: TurnRouterDefaultMode;
  };
}

// ---------------------------------------------------------------------------
// Classifier policy rules that count as POSITIVE evidence of
// `continue_step` (i.e. the classifier matched an explicit
// `continue_step` rule, not the catch-all default).
//
// See `computePromptShapingDisposition` in `turn-disposition.ts`:
//   * Rule 2 → `shaping.disposition.continue_step.no_text`
//   * Rule 3 → `shaping.disposition.continue_step.confirmation`
//   * Rule 8 → `shaping.disposition.continue_step.default`   (FALLTHROUGH)
//
// Positive rules keep `advance_form` under BOTH defaults. The
// fallthrough rule is the one that flips to `answer` under
// `meaning_first`.
// ---------------------------------------------------------------------------

const CLASSIFIER_CONTINUE_STEP_POSITIVE_RULES: ReadonlySet<string> =
  new Set<string>([
    "shaping.disposition.continue_step.no_text",
    "shaping.disposition.continue_step.confirmation",
  ]);

const MODE_FROM_DISPOSITION: Record<TurnDisposition, TurnRouterMode> = {
  continue_step: "advance_form",
  answer: "answer",
  requote: "requote",
  acknowledge: "acknowledge",
  cancel_confirmation: "cancel_confirmation",
  edit_field: "edit_field",
  handoff: "handoff",
  idle: "idle",
};

// ---------------------------------------------------------------------------
// `classifyTurn`
//
// Pure function. No logger, no env reads. Callsite parses env and passes
// `default_mode` in.
// ---------------------------------------------------------------------------

export function classifyTurn(input: TurnRouterInputs): TurnRouterDecision {
  const decision = input.classifier_decision;
  const classifierDisposition = decision?.disposition ?? null;
  const classifierPolicyRule = decision?.policy_rule ?? null;
  const classifierFallthroughReason =
    decision?.trace_annotations?.fallthrough_reason ?? null;
  const defaultMode = input.default_mode;

  // Case 0: classifier unavailable. Fall through to runtime default.
  if (!classifierDisposition) {
    const mode: TurnRouterMode =
      defaultMode === "meaning_first" ? "answer" : "advance_form";
    return buildDecision(mode, "router.no_classifier_decision", {
      default_applied: true,
      positive_evidence: null,
      classifier_disposition: null,
      classifier_policy_rule: null,
      classifier_fallthrough_reason: null,
      default_mode: defaultMode,
    });
  }

  const classifierMode = MODE_FROM_DISPOSITION[classifierDisposition];

  // Case 1: classifier fired a NON-continue_step rule. These are
  // `answer` / `requote` / `acknowledge` / `cancel_confirmation` /
  // `edit_field` / `idle` (handoff isn't emitted by the pre-LLM shaper
  // today but is allowed in the mapping for completeness). The
  // classifier matched an explicit rule → positive evidence of that
  // mode → honoured regardless of default.
  if (classifierMode !== "advance_form") {
    return buildDecision(
      classifierMode,
      `router.from_classifier.${classifierMode}`,
      {
        default_applied: false,
        positive_evidence: null,
        classifier_disposition: classifierDisposition,
        classifier_policy_rule: classifierPolicyRule,
        classifier_fallthrough_reason: classifierFallthroughReason,
        default_mode: defaultMode,
      },
    );
  }

  // Case 2: classifier fired `continue_step`. Distinguish positive
  // (explicit rule matched) from fallthrough (catch-all default).
  const isPositiveContinueStep = classifierPolicyRule
    ? CLASSIFIER_CONTINUE_STEP_POSITIVE_RULES.has(classifierPolicyRule)
    : false;

  if (isPositiveContinueStep) {
    return buildDecision(
      "advance_form",
      `router.positive_evidence.${classifierPolicyRule!}`,
      {
        default_applied: false,
        positive_evidence: classifierPolicyRule,
        classifier_disposition: classifierDisposition,
        classifier_policy_rule: classifierPolicyRule,
        classifier_fallthrough_reason: classifierFallthroughReason,
        default_mode: defaultMode,
      },
    );
  }

  // Case 3: fallthrough `continue_step`. Under `meaning_first`, flip
  // to `answer`. Under `advance_form`, stay.
  if (defaultMode === "meaning_first") {
    return buildDecision(
      "answer",
      "router.default_meaning_first.classifier_fell_through",
      {
        default_applied: true,
        positive_evidence: null,
        classifier_disposition: classifierDisposition,
        classifier_policy_rule: classifierPolicyRule,
        classifier_fallthrough_reason: classifierFallthroughReason,
        default_mode: defaultMode,
      },
    );
  }

  return buildDecision(
    "advance_form",
    "router.default_advance_form.classifier_fell_through",
    {
      default_applied: true,
      positive_evidence: null,
      classifier_disposition: classifierDisposition,
      classifier_policy_rule: classifierPolicyRule,
      classifier_fallthrough_reason: classifierFallthroughReason,
      default_mode: defaultMode,
    },
  );
}

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------

function buildDecision(
  mode: TurnRouterMode,
  reason: string,
  fields: {
    default_applied: boolean;
    positive_evidence: string | null;
    classifier_disposition: TurnDisposition | null;
    classifier_policy_rule: string | null;
    classifier_fallthrough_reason: string | null;
    default_mode: TurnRouterDefaultMode;
  },
): TurnRouterDecision {
  const isAdvanceForm = mode === "advance_form";
  return {
    mode,
    reason,
    default_applied: fields.default_applied,
    positive_evidence: fields.positive_evidence,
    // The three consumer flags mirror `mode === "advance_form"`:
    //   * advance_form → all three true (state subroutines run).
    //   * any other    → all three false (meaning owns the turn).
    // Consumers additionally gate on `default_mode === "meaning_first"`
    // before honouring; under legacy default, these are computed for
    // trace visibility only.
    invoke_state_machine: isAdvanceForm,
    shape_prompt_imperatives: isAdvanceForm,
    invoke_region_a_substitutions: isAdvanceForm,
    trace_annotations: {
      classifier_disposition: fields.classifier_disposition,
      classifier_policy_rule: fields.classifier_policy_rule,
      classifier_fallthrough_reason: fields.classifier_fallthrough_reason,
      default_mode: fields.default_mode,
    },
  };
}

/**
 * Parse an env-string into a `TurnRouterDefaultMode`. Lenient on case /
 * whitespace; any unrecognised value (including unset / empty) falls
 * back to `"advance_form"` so the legacy behaviour is the safe default.
 *
 * Exposed as a helper so the callsite and the smoke test share the same
 * parse.
 */
export function parseTurnRouterDefaultModeEnv(
  value: string | undefined,
): TurnRouterDefaultMode {
  const normalised = (value || "").trim().toLowerCase();
  return normalised === "meaning_first" ? "meaning_first" : "advance_form";
}
