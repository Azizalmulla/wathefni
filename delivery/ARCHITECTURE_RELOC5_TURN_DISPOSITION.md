# Relocation 5 — `decideTurnDisposition` contract (the cure)

> **Status:** contract draft, 2026-04-23. Drafted during the
> post-hoist bake window. Not yet in shadow. Supersedes the vetoing
> shape introduced by Relocation 4 (directive disposition); Reloc 4
> remains the current shadow observation while this contract is
> reviewed. See [`ARCHITECTURE_TURN_DECISION.md`](./ARCHITECTURE_TURN_DECISION.md)
> for the umbrella unified-layer contract and the relocation discipline.
>
> This doc is a **contract**, not a plan. It names shapes, inputs,
> outputs, and what "state machine as consistency check" means
> mechanically. Implementation happens via the relocation commits in
> [Migration plan](#migration-plan).

## TL;DR

> **Meaning authors. State grounds.** Every customer turn begins by
> classifying what the customer is trying to do _right now_
> (`TurnDisposition`). Only when that classification is `continue_step`
> does the state machine get asked "given where the booking is, which
> field is next?" — the narrowly-scoped question it's actually good at.
> Every other disposition authors its own directive (or authors `null`,
> meaning "no server directive; LLM owns this turn").
> `computeOneBrainNextRequiredAction` becomes a subroutine of the
> disposition layer, not a parallel authority.

---

## Why this layer now

Tonight's step-loop symptom survived Reloc 3 (A1 semantic gate) and
Reloc 3-hoist (gates above A0 family) because all three cuts operate
the same way: the legacy pipeline produces a directive, the layer
reviews it and _vetoes_ bad ones. Review authority is necessary for
safety but insufficient for intelligence:

* Suppressing "sender name?" on a clarifying question prevents the
  loud override but does not _author_ the answer. We rely on the
  LLM's draft surviving — fine when the draft is good, a silent
  failure when it isn't.
* Suppressing the directive on a cancel-intent turn silences the
  wrong ask but does not _author_ `CONFIRM_CANCEL_ORDER`. We ship the
  LLM's cancel ack, which may or may not be shaped correctly.
* Fresh-route mid-collection passes through the LLM's re-quote text,
  but the state machine still thinks we're on "sender collection"
  next turn — meaning and state diverge silently.

The veto shape also compounds a subtler failure: the layer can never
decide that a turn _should_ bypass state entirely. Under Reloc 4, if
the state machine returns `null` the layer gets no input to reason
about disposition, so the trace is blank even when meaning clearly
authored a specific kind of action.

Reloc 5 inverts this. Meaning classifies first; state is called only
where its narrow expertise applies.

---

## Name

```ts
export function decideTurnDisposition(
  input: TurnDispositionInputs,
): TurnDispositionDecision;
```

Module: `plugins/shared/turn-disposition.ts` (new file, sibling to
`turn-decision.ts`). `decideTurn` (the umbrella unified entry point)
calls `decideTurnDisposition` first and feeds its output into the
downstream A1/A3/A4 derivations that already live in
`turn-decision.ts`.

---

## The disposition set

Tight and closed. New kinds only added with an explicit relocation
bump; unknown values are rejected.

```ts
export type TurnDisposition =
  | "continue_step"          // the turn meant "continue the form"
  | "answer"                 // informational / clarifying: respond, do not advance
  | "requote"                // fresh route or route edit → re-run pricing path
  | "cancel_confirmation"    // cancel intent → confirm-to-cancel, not sender ask
  | "edit_field"             // correction to a specific field → re-ask that field only
  | "acknowledge"            // pleasantries, fillers, empty acks → passthrough, no advance
  | "handoff"                // manual-confirm or customer-support → request handoff
  | "idle";                  // no booking in flight; SKILL.md governs, layer is silent
```

### Why these seven

Each kind corresponds to a distinct _control-flow outcome_ — whether
state should advance, whether a directive should be authored, and
what the render contract is. They are not classification labels for
their own sake; each row in the policy table below acts differently.

| disposition | state advances? | authors directive? | LLM reply scope |
|---|---|---|---|
| `continue_step` | yes, consult state machine | yes (from state machine) | drafted by LLM, may be substituted by renderer |
| `answer` | no | no (`null`) | LLM owns; A3/A4 guards still apply |
| `requote` | yes (route/quote path) | yes (authored: `START_PRICING` or equivalent) | LLM draft with guard |
| `cancel_confirmation` | no advance; stage→`awaiting_cancel_confirm` | yes (authored: `CONFIRM_CANCEL_ORDER`) | server-rendered |
| `edit_field` | yes, rewind stage to re-collect | yes (authored: `ASK_<FIELD>`) | server-rendered |
| `acknowledge` | no | no (`null`) | LLM owns (short draft) |
| `handoff` | stage→`awaiting_manual_confirm` | yes (authored: `REQUEST_HANDOFF_*`) | server-rendered |
| `idle` | no (pre-quote / chit-chat) | no (`null`) | LLM owns; SKILL rules |

### What's intentionally NOT in the set

* `confirm_order` — does NOT need its own disposition. A confirm turn
  at `awaiting_confirmation` is `continue_step` (state machine knows
  the next action is `SUBMIT_ORDER`). The disposition layer only
  splits meaning; it does not re-implement existing deterministic
  transitions.
* `refuse` / `unclear` — classifier ambiguity maps to
  `acknowledge` (low-confidence default) with a trace note. No live
  behaviour hinges on distinguishing "refused" from "pleasantry"
  today; if it ever does, we add a disposition then.
* `meta` (bot-about-bot) — falls under `answer`. Not a control-flow
  split.

The seven-disposition set is the v1 target. It is explicitly _not_ a
cartesian product of meaning × stage; it is the minimum set that
produces one unambiguous control-flow decision per turn.

---

## Exact inputs

The struct is closed. Only fields listed here are consumed; adding a
field is a contract change.

```ts
export interface TurnDispositionInputs {
  // -------------------------------------------------------------
  // 1. Meaning signals — proposer-derived, first-class.
  // -------------------------------------------------------------
  proposer: {
    turn_kind: ProposedTurnKind | null;               // v1.0
    ti_kind: TurnIntentKind | null;                   // v1.2
    ti_confidence: TurnIntentConfidence | null;       // v1.2
    ti_addressed_fields: TurnIntentAddressedField[];  // v1.2
    ac_kind: AwaitingConfirmationKind | null;         // v1.1
    po_kind: PostOrderIntentKind | null;              // v1.3
  } | null;

  // -------------------------------------------------------------
  // 2. Addressed-fields bookkeeping — computed by the callsite.
  // -------------------------------------------------------------
  // Which of the caller's "missing" fields the customer actually
  // addressed THIS turn (intersection of `ti_addressed_fields` with
  // the state machine's `missing` list). Drives edit-vs-continue
  // and partial-answer rendering.
  addressed_missing_fields: string[];

  // Whether the classifier reported addressing something NOT in
  // `missing` — a correction signal even when `ti_kind` isn't
  // `corrected_prior`.
  addressed_non_missing_fields: string[];

  // -------------------------------------------------------------
  // 3. State snapshot — the only state reads the layer does.
  //    Everything else is looked up by the state-machine subroutine
  //    if and only if the layer decides `continue_step`.
  // -------------------------------------------------------------
  state: {
    stage_at_turn_start: ConversationStage | null;
    has_active_quoted_route: boolean;
    active_quoted_route_has_manual_confirm_option: boolean;
    has_summary_shown: boolean;
    is_post_order: boolean;
    missing_fields_count: number;      // scalar — not the list; cheap.
  };

  // -------------------------------------------------------------
  // 4. Tool-result context that materially affects disposition.
  // -------------------------------------------------------------
  // Only fields that CHANGE THE DISPOSITION go here. Prices the
  // guard already validated, catalog entries, etc. live in A4 and
  // are not disposition inputs.
  tool_context: {
    // `get_price` ran THIS turn — authors `requote` even when the
    // proposer misclassified the turn (defense against classifier
    // noise on fresh routes).
    get_price_ran_this_turn: boolean;
    // `start_booking` drained THIS turn — means the LLM just
    // advanced; layer must not author a disposition that contradicts
    // it (maps to `continue_step` with a trace note).
    start_booking_drained_this_turn: boolean;
    // Hallucination guard rejected the LLM's draft — force
    // `continue_step` so the state-machine render owns the turn
    // (safety net; overrides classifier).
    hallucination_guard_fired: boolean;
  };

  // -------------------------------------------------------------
  // 5. Callsite hints (kept minimal — the layer should not need
  //    callsite opinions to reach a disposition).
  // -------------------------------------------------------------
  hints: {
    // Current turn is a switch-option turn (same-route quote switch).
    // Legacy A4 owns the recap; disposition is `continue_step` with a
    // skip marker so the state-machine subroutine is NOT called
    // (A4 will render the recap directly).
    same_route_switch_option: boolean;
  };
}
```

### What is _not_ an input

* Raw user text. The layer does not reparse; it trusts the proposer's
  classification of the turn.
* The legacy `observed` A1/A2/A3/A4 outcomes. Reloc 5 is an author
  layer, not a reviewer. Agreement with legacy is a bake-time
  analyzer concern, not a runtime input.
* Prior-turn memory beyond `stage_at_turn_start`. Stage already
  encodes the conversation phase; anything else is state-machine
  territory.

---

## Exact outputs

```ts
export interface TurnDispositionDecision {
  disposition: TurnDisposition;

  // What the layer authored. `null` means "layer decided no server
  // directive this turn" (disposition ∈ {answer, acknowledge, idle}).
  authored_directive: DirectiveAction | null;

  // Set only when `disposition === "continue_step"`. Names which
  // narrow question the layer delegated to the state machine. Lets
  // the trace distinguish "state machine computed this directive"
  // from "layer authored this directive".
  state_machine_call: {
    called: boolean;
    subroutine: "next_missing_field" | "post_order_routing" | null;
    result_directive: DirectiveAction | null;
  };

  // Stable policy-rule id for auditability. Matches
  // `layer.disposition.<rule>` naming already used by Reloc 4.
  policy_rule: string;
  reason: string;

  // Trace annotations the `[turn-decision/trace]` line will surface.
  trace_annotations: {
    // When the classifier was untrustworthy and the disposition
    // fell through to a safety default, the layer names the default
    // path so the analyzer can bucket "noise-driven fallthroughs"
    // separately from "confident authoring".
    fallthrough_reason: string | null;
  };
}
```

### Trace shape

One new line per turn (reuses `[turn-decision/trace]`, just adds a
`disposition=` key cluster):

```
[turn-decision/trace] conversation=... turn_id=... reply_source=... …
  disposition=answer
  disposition_rule=layer.disposition.answer_on_clarifying
  authored_directive=none
  state_machine_called=false
  disposition_fallthrough=none
```

Agreement with the state machine (did the layer pick what the state
machine would have picked?) is computed by the bake analyzer off the
trace, not emitted as a runtime token, to keep the line small.

---

## Precise role of `computeOneBrainNextRequiredAction`

The state machine is demoted from generator-of-behaviour to two
things:

### 1. A narrow subroutine called by `decideTurnDisposition`

Called **only** when the layer has already decided
`disposition === "continue_step"`. Input: the draft / entry / missing
list exactly as today. Output: the authored directive for the
specific next field. That's it — the same function, same signature,
but called with the pre-condition "meaning says continue."

The four in-line policy branches currently inside
`computeOneBrainNextRequiredAction` get reclassified:

| current branch | Reloc 5 home |
|---|---|
| `stage === "order_submitted"` → `POST_ORDER_ONLY_…` | stays; invoked via `state_machine_call.subroutine = "post_order_routing"` |
| Clarify-before-proceed gate (manual-confirm ambiguity) | moves OUT; disposition layer authors `handoff` or `continue_step` from meaning + catalog snapshot |
| Missing-field sequencing | stays; sole remaining responsibility |
| Awaiting-confirmation branches | stay; invoked on `continue_step` when `stage === "summary_shown"` |

### 2. A consistency check run post-authoring (off-path, trace-only)

After the disposition layer authors a directive, we call
`computeOneBrainNextRequiredAction` in an _observer_ mode and compare
its output to the authored directive. Disagreements are written to
`[turn-decision/trace]` as `state_consistency=agree|disagree_<shape>`
and drive the bake analyzer. No behaviour change from the
consistency check itself; it's the regression gate during migration.

### What it is NOT anymore

* Not the kingpin. Never called before the disposition layer.
* Not the place where meaning is deduced (clarify-before-proceed,
  ambiguity guards). Those move to the disposition layer where the
  proposer signals live.
* Not an authority for non-`continue_step` dispositions. The function
  still exists and still returns a value, but the disposition layer
  ignores the return value on anything other than `continue_step`.

---

## Policy rules (v1)

Each rule is a closed-world match; order matters. Rule 1 wins first.

```
Rule  | disposition          | precondition (abbreviated)
------+----------------------+-------------------------------------------------
1     | idle                 | state.stage_at_turn_start ∈ {null, "idle"}
                              ∧ proposer.turn_kind ∉ {initial_route, …}
2     | handoff              | tool_context.hallucination_guard_fired ∧
                              state.active_quoted_route_has_manual_confirm_option
                              ∧ proposer.ti_kind ∉ {clarifying_question,
                              answered_partial, corrected_prior}
                              (safety: route the ambiguous manual-confirm turn
                              to a human rather than letting the layer guess)
3     | cancel_confirmation  | proposer.ac_kind === "cancel_order" ∧
                              state.stage_at_turn_start ∈ {"summary_shown",
                              "awaiting_confirmation", "collecting_booking_details"}
                              ∧ ti_confidence ∈ {high, medium}
4     | requote              | (proposer.turn_kind === "initial_route" ∧
                              state.has_active_quoted_route) ∨
                              tool_context.get_price_ran_this_turn
5     | edit_field           | proposer.ti_kind === "corrected_prior" ∧
                              addressed_non_missing_fields.length > 0 ∧
                              ti_confidence ∈ {high, medium}
6     | answer               | proposer.ti_kind ∈ {clarifying_question,
                              answered_partial (with non-empty
                              addressed_missing_fields)} ∧ ti_confidence ∈ {high,
                              medium}
                              (NB: answered_partial is answer + partial state
                              update; state advance happens via addressed_fields,
                              not via state-machine call)
7     | acknowledge          | proposer.turn_kind === "post_order_chat" ∧
                              proposer.po_kind ∈ {unclear, customer_support} ∨
                              proposer.ti_kind ∈ {acknowledgement, unclear,
                              refused_or_stuck}
8     | continue_step        | default — layer calls state-machine subroutine
                              to author the directive
```

Low-confidence classifications fall through to Rule 8
(`continue_step`) with `fallthrough_reason = "low_confidence_<kind>"`.
This is the intentional safety net: when meaning can't be trusted,
state grounds the turn.

---

## Migration plan

Same relocation discipline as the earlier cuts. No live cutover until
shadow data is clean.

### Phase 5.0 — shadow observer (no behaviour change)

* Land `decideTurnDisposition` in `turn-disposition.ts`.
* Extend `TurnDecisionObservedContext` with `disposition_inputs`
  (a strict subset of the struct above — no runtime consumption).
* Add canary markers:
  * `DEPLOY_CANARY_TURN_DISPOSITION_MODULE_MARKER`
  * `DEPLOY_CANARY_TURN_DISPOSITION_CALLSITE_MARKER`
* Emit `disposition=/disposition_rule=/authored_directive=`
  tokens on `[turn-decision/trace]`.
* State machine is called unchanged; its output is the live
  directive. The layer's `authored_directive` is trace-only.
* Agreement analyzer: `authored vs state_machine_result` bucketed by
  rule and confidence. Same shape as the Reloc 2 dispatch-divergence
  analyzer; same noise heuristics.

### Phase 5.1 — live flip, bounded subset

Flip behind `RIDERS_TURN_DISPOSITION_FLIP` (default off). The first
live-subset is intentionally narrow:

* `disposition === "answer"` with `ti_confidence === "high"` and
  `authored_directive === null` → _actually_ author null (suppresses
  the state-machine directive this turn). This subsumes Reloc 4's
  veto on clarifying questions; when it's live, retire the
  `RIDERS_TURN_DECISION_DIRECTIVE_FLIP` path.
* `disposition === "requote"` → _actually_ author the pricing
  directive when the classifier is high-confidence.

Everything else stays in shadow until one more bake cycle.

### Phase 5.2 — expand flip

* `cancel_confirmation` live (authored `CONFIRM_CANCEL_ORDER`).
* `edit_field` live (authored `ASK_<FIELD>`; stage rewind).
* `handoff` live (authored `REQUEST_HANDOFF_*`).

### Phase 5.3 — retirement

* Delete the clarify-before-proceed gate from
  `computeOneBrainNextRequiredAction` (the disposition layer handles
  it via `handoff` + catalog snapshot).
* Retire `RIDERS_TURN_DECISION_A1_FLIP` — subsumed by `answer`
  authoring.
* Mark `computeOneBrainNextRequiredAction` as
  `internal/subroutine-only`. Consumer count drops to 1
  (`decideTurnDisposition`), which is the end-state we wanted.

### Phase 5.4 — consistency-check retirement

Once the bake is clean (≥2 weeks, zero `state_consistency=disagree_*`
that aren't explained by known rules), remove the post-authoring
consistency call and keep only the narrow subroutine invocation.

---

## Non-goals

* Not a replacement for the proposer. The layer does not classify;
  it reads the proposer's classifications and routes on them.
* Not a state mutator. Disposition decisions do not touch draft or
  stage directly — authored directives still flow through the
  existing op-apply boundary (Reloc 3 territory, not Reloc 5).
* Not a reply renderer. Authored directives hand off to the existing
  directive-reply registry for text.
* Not a place for forbidden-shape lists. Those live with the
  directive registry.

---

## Open questions (for iteration during the bake)

1. **`answered_partial` on a first-missing-field turn.** Rule 6
   routes `answered_partial` to `answer`, but the state machine would
   normally continue to the _next_ missing field after recording the
   partial. Does the disposition layer author the next-field ask, or
   does state advancement happen purely via the apply boundary and
   the next turn's disposition inherits the new state? Leaning
   toward the latter — keeps Reloc 5 disposition-only, state changes
   flow through ops.

2. **`requote` + `has_active_quoted_route = false`.** Fresh-route on
   an empty quote IS the quote — not a re-quote. Do we need a
   separate `first_quote` disposition, or does `requote` subsume it?
   Leaning toward subsume; the authored directive differs
   (`START_PRICING` vs `REQUOTE`) but the disposition is the same.

3. **Cancel during `collecting_booking_details`.** Rule 3 allows it,
   but historically cancel mid-collection has been rare. Do we ship
   it in 5.1 (live) or keep it shadow until we see it in real
   traffic?

4. **What happens when `proposer === null`?** (Classifier failure,
   timeout, or structured-output reject.) The safe answer is Rule 8
   with `fallthrough_reason = "no_proposer"`. Confirm we're OK with
   state-machine authoring on those turns rather than forcing
   `handoff`.

5. **Consistency-check emit volume.** Every turn will write a
   `state_consistency=` token; is that OK, or do we emit only on
   disagreement? Emit-only-on-disagreement is cheaper but loses the
   "no disagreements today" signal. Leaning toward always-emit for
   bake; switch to on-disagreement after Phase 5.4.

---

## What this doc is not

* Not a code diff. Nothing in this doc ships until the Phase 5.0
  shadow commit lands.
* Not a replacement for `ARCHITECTURE_TURN_DECISION.md`. That umbrella
  contract still names the unified layer; Reloc 5 is the cut that
  finally makes the layer the _author_ rather than a reviewer.
* Not closed. Open questions above get decided off real bake data
  (post-hoist traces from tonight + whatever the next pack surfaces).
