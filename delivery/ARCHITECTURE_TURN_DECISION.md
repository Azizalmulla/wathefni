# Unified turn-decision layer — contract

> **Status:** target architecture agreed 2026-04-22 after the three-bug
> post-shadow-deploy diagnosis session. Supersedes the fragmented control
> plane that grew organically through Phase 1–Phase 3c. This doc is
> the single reference for what the unified layer IS, what it consumes,
> what it produces, and how we migrate toward it.
>
> This document is a **contract**, not a plan. Implementation happens via
> relocation commits described in [Migration discipline](#migration-discipline).
> See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the base B-with-teeth shape
> (LLM proposes, server decides, one apply boundary) and
> [`ARCHITECTURE_TURN_SEMANTICS.md`](./ARCHITECTURE_TURN_SEMANTICS.md) for
> the semantic primitives this layer consumes.

## TL;DR

> **One layer, one trace per turn.** Every control decision the bot makes
> on a customer turn — which ops actually apply to state, whether the LLM's
> reply gets substituted, which directive renders, any side-effect that
> changes stage or dialog state — goes through a single function with a
> single auditable output. The LLM's proposer output + the turn's drained
> tool calls + the current state + the inbound utterance are its inputs.
> Semantic classifications (`turn_intent`, `awaiting_confirmation`,
> `post_order_intent`) are first-class inputs, not side-channel shadows.

## Why this layer now

Tonight's three live failures (conv 19534, 2026-04-22) were each decided
in a different place:

| failure | decided at |
|---|---|
| `"wdym manual confirmation?"` → option list | pre-state clarify-option gate |
| `"Ahamad basha"` → same re-ask | state-only directive selector |
| `"No"` on summary → restart from sender | op-layer hard-coded side-effect + downstream state-driven directive |

The semantic layer (Phase 1 `turn_intent`, Phase 2 M1/M2/M3, Phase 3c
`post_order_intent`) was classifying each turn correctly. None of its
signals were consumed by the three authorities above. That's the
diagnosis: semantics is a passenger because decisions are fragmented
across four independent control-plane authorities, and semantics is
wired into exactly one of them.

Continuing to wire semantics INTO each of the four authorities (path (a)
from the 2026-04-22 design discussion) mitigates the symptom but keeps
the disease — every future semantic primitive pays the fragmentation
tax. This document specifies the collapse (path (b)): one authority,
semantic-native, with the four old sites becoming empty shells as their
logic relocates inward.

## The four current authorities (what we're collapsing)

Named for audit clarity. Each is a concrete place in today's code.

### (A1) Pre-state substitution branches

`octopus-channel/lib/outbound-decision.ts`, Region A, branches `A0*`.
Fires BEFORE any directive dispatch. Triggers on state + keyword/regex
match on inbound text. Substitutes the LLM's reply outright.

Members today:
- Clarify-before-proceed (`input.clarifyOptionBeforeProceed`)
- Manual-confirm address-ask (`input.manualConfirmAddressAsk`)
- Manual-confirm handoff (`input.manualConfirmHandoff`)
- Same-route switch_option recap (`input.sameRouteQuoteAction`)
- Canonical overwrite / empty-fill / price whitelist (pre-2026 guards)

**Does not consume `turn_intent`, `awaiting_confirmation`, or
`post_order_intent` today.** The clarify-before-proceed gate is
computed a second time inside `computeOneBrainNextRequiredAction`
(`one-brain-context.ts:233`) using the same keyword heuristic —
duplication.

### (A2) Directive selection

`octopus-channel/lib/one-brain-context.ts::computeOneBrainNextRequiredAction`.
Pure function of `(draft, entry, missing, currentCustomerText,
activeQuotedRoute)`. Picks which `ASK_*` directive the dispatcher
should emit.

**Takes `currentCustomerText` but only for the clarify-before-proceed
branch; no semantic classifications are consumed.** Directive choice
is essentially `missing_fields` → next directive, with no awareness of
what the customer addressed this turn.

Consequence: on "Ahamad basha" (recipient name only), `missing_fields`
still contains `recipient_phone`, so the selector picks the same
compound ask — there is no narrow `ASK_RECIPIENT_PHONE` directive AND
no mechanism to select one even if it existed, because the selector
has no `addressed_fields` input.

### (A3) Op-layer side-effects

`octopus-channel/index.ts`, responder-op drain loop (~lines 4880-5500).
Each LLM-emitted op has hardcoded consequences baked into the drain
branch that handles it:

- `apply_booking_field` → boundary evidence contract → draft mutation
- `cancel_booking` → draft cleared, stage → idle, controller reset (with only a narrow "contradicted-by-option-mention" guard)
- `start_booking` → stage promotion
- `confirm_summary` → order submission
- `set_pending_area` / `set_requested_slot` → dialog state mutation

**No op decision currently routes through any semantic layer.** The
cancel-guard regex is the only semantic-adjacent gate on an op today
and it's a keyword heuristic, not a classifier consumer.

Consequence: "No" on a summary triggers `cancel_booking` (LLM's call,
mechanically), draft clears, missing_fields repopulates, selector
fires `ASK_SENDER_NAME_AND_PHONE_DECISION`. Customer experiences this
as "the bot forgot everything." No point in the flow consulted whether
this cancel was firm or tentative.

### (A4) Reply render

`shared/directive-reply-registry.ts` + its dispatcher in
`outbound-decision.ts`. Given a chosen directive + context, produces
the ask text. This authority IS semantic-aware in the sense that
Phase 2 M1 (ack prefix) was designed to invert render keyed on
`turn_intent`. It's the only authority where the semantic layer has a
defined input.

But (A4) runs AFTER (A2) has chosen the directive and (A1) has
optionally substituted. If (A1) fires, (A4) never runs. If (A2) picks
wrong, (A4) renders the wrong directive faithfully.

## Target: one layer, one trace

### Name

`turn-decision` — module: `plugins/shared/turn-decision.ts`. One exported
entry point: `decideTurn(input): TurnDecision`.

### Inputs (exact shape)

```ts
interface TurnDecisionInput {
  // --- Turn context ---
  conversation_id: string;
  turn_id: string;
  turn_start_ms: number;
  inbound: {
    text: string;
    script: "english" | "arabic" | "arabizi";
    language: "en" | "ar";
    media_types: string[];              // text / image / voice / paste
  };

  // --- State snapshot at turn start ---
  state: {
    stage: ControllerStage;             // idle / quoted / collecting_booking_details / summary_shown / awaiting_confirmation / order_submitted
    booking_draft: PersistedBookingDraft;
    dialog_state: DialogState | null;
    missing_fields: SlotName[];
    active_quoted_route: StoredQuotedRoute | null;
    whatsapp_number: string | null;

    // Session-guard snapshot — spelled out because every field below
    // is load-bearing for at least one of the four current authorities.
    session_guard: {
      all_valid_prices: ReadonlySet<string>;   // hallucination-guard valid set
      last_tool_name: string | null;
      last_tool_ts: number;
      last_quoted_route: StoredQuotedRoute | null;
      is_recent: boolean;                      // gates canonical-overwrite
      tool_age_ms: number;                     // gates class-15 + overwrite
      preferred_canonical_text: string | null; // prior canonical text
      canonical_overwrite_allowed: boolean;
      canonical_overwrite_skip_reason: string | null;
    } | null;

    // Carry-over from within the turn's own prior phases.
    fast_path_pre_applied_fields: (keyof BookingFieldPatch)[] | null;
    controller_transition_hint: string | null;
    rejections_this_turn: BoundaryRejection[]; // produced by the boundary
                                               // when the layer's op_plan
                                               // executes; empty at first
                                               // decideTurn call, populated
                                               // if the layer re-enters
                                               // post-apply (rare; see
                                               // Ordering).
  };

  // --- LLM proposal for this turn ---
  proposer: {
    present: boolean;                   // did the LLM call propose_turn_decision?
    valid: boolean;                     // did it pass validation?
    turn_kind: ProposedTurnKind | null;
    pricing_decision: ProposedPricingDecision | null;
    planned_tool_calls: string[];
    customer_reply_draft: string;       // what the LLM wanted to say
    turn_intent: ProposedTurnIntent | null;
    awaiting_confirmation: ProposedAwaitingConfirmation | null;
    post_order_intent: ProposedPostOrderIntent | null;
    option_interpretation: ProposedOptionInterpretation | null;
  };

  // --- What the LLM actually did this turn (staged, not applied) ---
  llm_ops: ResponderOp[];               // ordered list of ops the LLM emitted

  // --- Results of tools that RAN during this turn ---
  tool_results: {
    get_price: GetPriceResult | null;
    // Option-interpretation reconciliation. Computed by
    // `quoted-options.ts::resolveOptionFromProposals` by combining the
    // LLM's `propose_option_interpretation` op (above, under proposer)
    // with the server's deterministic option-match. Consumed by the
    // sameRouteQuoteAction derivation and the manual-confirm gate.
    option_reconciliation: {
      matched_option: RouteQuoteOption | null;
      confidence: "high" | "medium" | "low" | "none";
      source: "llm_proposal" | "deterministic" | "both" | "none";
    } | null;
  };

  // --- Upstream fixtures (deprecated; preserved for bridge period only) ---
  // Every field here is something ONE of the four authorities reads
  // directly today. Relocation commits delete these one by one as the
  // corresponding decision moves into the layer's own branches.
  legacy: {
    clarify_option_before_proceed_flag: boolean;    // A1 legacy trigger
    manual_confirm_address_ask: { side: "pickup" | "delivery"; option: RouteQuoteOption } | null;
    manual_confirm_handoff: { option: RouteQuoteOption } | null;
    same_route_quote_action: SameRouteQuoteFollowupAction | null;
    cancel_contradicted: { optionLabel: string } | null;
    class_fifteen_bypass: boolean;
  };
}
```

Everything the four current authorities read from is present. Nothing
is hidden. The `legacy` sub-object is explicitly marked as the
temporary bridge — relocation commits read from it and delete it field
by field as each legacy consumer moves into the layer.

#### Composition primitives (not inputs; direct imports)

The layer composes server-side reply text by calling a fixed set of
pure builder functions. Under today's architecture these are injected
through the `outbound-decision` input surface as callbacks to avoid a
circular import back into the plugin. Under the unified layer, the
layer IS the central module, so the circular-import concern goes away
and these become direct imports:

- `buildDeterministicSelectedQuotedOptionReply` (switch-option recap)
- `buildDeterministicClarifyOptionBeforeProceedReply`
- `buildDeterministicManualConfirmAddressAskReply`
- `buildDeterministicManualConfirmHandoffReply`
- `buildDeterministicGraceWindowReply`
- `buildProviderIssueFallbackReply`
- `buildClass15BypassRepairReply`
- `buildDeterministicOrderSummary` (via directive registry; same reference)
- `PRICE_REPAIR_TEMPLATE`, `POST_ORDER_NUDGE`, `GENERIC_NUDGE` (neutral
  fallback templates in `reply-hallucination-guard.ts`; stay there and
  get imported)
- `renderDirectiveReply` (directive-reply-registry dispatcher)

These are composition primitives, not control inputs. They do not
appear on `TurnDecisionInput`; the layer imports them.

#### Apply-boundary — not an input

Correcting a potential misread of the sketch above: `apply-boundary.ts`
does NOT appear on the input surface. It runs INSIDE the layer during
`op_plan` execution. The layer produces verdicts, the layer's executor
runs the boundary evidence contract on accepted ops, and the resulting
`BoundaryRejection[]` surfaces as `state.rejections_this_turn` on any
re-entry (or is returned with the `TurnDecision` if the layer only
runs once). Hallucination-guard is likewise outside the layer
(post-layer verification, per Non-goals).

### Outputs (exact shape)

```ts
interface TurnDecision {
  // --- Op disposition ---
  op_plan: {
    // One entry per LLM-emitted op, in order.
    // `accept` runs it with the patch unchanged.
    // `accept_masked` runs it but drops certain fields.
    // `reject` does not run it; records the reason.
    // `defer_confirm` does not run it; emits a confirm-first reply.
    entries: Array<{
      op: ResponderOp;
      verdict: "accept" | "accept_masked" | "reject" | "defer_confirm";
      mask?: string[];                  // for accept_masked
      reason: string;                   // machine-readable tag
    }>;
  };

  // --- Reply composition ---
  reply: {
    source: ReplySource;
    directive?: DirectiveAction;        // when source references a directive
    render_context?: DirectiveReplyRendererContext;
    ack_prefix?: string;                // M1 prefix, when source is ack+directive
    substitute_text?: string;           // when source is substitute / recovery
    llm_authored_reason?: string;       // when source=llm_authored, why (e.g. "informational_answer", "create_simple_order_placed")
  };
```

The archetype set — exhaustively mapped against every replacement path
that exists in today's code:

| `ReplySource` | Example today's paths it subsumes | Semantics |
|---|---|---|
| `server_rendered_directive` | `replace_directive_ask`, summary render, `replace_summary_fact_drift` | Server picks a `DirectiveAction`; the registry renders its ask from state. |
| `server_ack_plus_directive` | (M1 flip target) | Same as above but with a `turn_intent`-keyed ack prefix concatenated in front. |
| `server_substitute_text` | `replace_clarify_option_before_proceed`, `replace_manual_confirm_address_ask`, `replace_manual_confirm_handoff`, switch-option recap, canonical overwrite | Happy-path substitution: server has better contextual information than the LLM for this specific turn shape and composes a targeted reply. |
| `server_recovery_template` | `replace_price_mismatch` (PRICE_REPAIR_TEMPLATE), `replace_field_rejection_hallucination`, `replace_order_placed_hallucination`, `replace_transaction_artifact_missing`, `replace_get_price_bypass`, grace-window, provider-issue fallback, generic/post-order nudges, empty-fill | Something is wrong; the reply falls back to a safe neutral template that doesn't try to be contextually smart. |
| `deferred_confirm_prompt` | (new — "Are you sure you want to cancel?" becomes possible) | The layer rejected an op and needs the customer to confirm before the action is taken. |
| `llm_authored` | Any turn the layer decides to let the LLM's draft through (informational questions, post-order routing until Phase 3c flips, `create_simple_order` confirmation, pre-booking quote, greetings). | Pass-through; `llm_authored_reason` required so every carve-out is explicit, not a default. |

Line drawn between `server_substitute_text` and `server_recovery_template`:

- **Substitute** = "the server has better contextual information than
  the LLM for this specific turn shape and composes a targeted reply."
  Examples: option disambiguation, manual-confirm address ask,
  switched-option recap.
- **Recovery** = "something is off (hallucination, empty text,
  provider error, bypass); the reply falls back to a safe neutral
  template that doesn't try to be contextually smart." Examples: price
  repair, generic nudge, grace-window.

This line has one grey edge (`canonical_overwrite` could be argued as
either — the text DOES drift, but the substitute IS contextual). We
commit to substitute for that case because the canonical text is
specific state, not a template. Future refinements to this boundary
are allowed; they're doc edits, not code changes.

**Reserved, not v1:** composable replies (server prefix + LLM body, or
LLM answer + server trailing prompt). Today no path does this. If the
post-layer world wants "LLM answers the informational question and the
server appends the next ASK," we add a seventh archetype at that
point. Not now.

```ts
// (continuing TurnDecision)

  // --- State-transition requests ---
  transitions: {
    stage_promote?: ControllerStage;
    requested_slot_override?: SlotName | null;
    marked_summary_shown?: boolean;
    // cancel routing:
    cancel_disposition?: "confirmed_cancel" | "require_confirm_first" | "route_to_edit" | null;
  };

  // --- Observability ---
  trace: {
    decision_id: string;                // uuid per turn, logged as tag
    inputs_summary: Record<string, unknown>;
    policy_hits: string[];              // ordered list of policy rules that fired
    semantic_signals: {
      ti_kind: TurnIntentKind | null;
      ti_addressed: TurnIntentAddressedField[];
      ac_kind: AwaitingConfirmationKind | null;
      po_kind: PostOrderIntentKind | null;
    };
    tentative_to_final_override?: string;  // if a semantic signal overrode a legacy-style decision
  };
}
```

Every output field corresponds to a decision that currently lives in
one of the four authorities. After migration, those authorities execute
the decision instead of making it:

- (A3) op drain reads `op_plan.entries[i].verdict` and applies /
  masks / rejects accordingly. It no longer decides.
- (A4) reply render reads `reply.*` and produces text. It no longer
  chooses between substitution branches.
- (A1) Region-A branches collapse: the `substitute_text` path subsumes
  clarify-option / manual-confirm substitutions; the `server_rendered_directive`
  path subsumes ordinary directive render.
- (A2) directive selection disappears as a standalone function; it's a
  branch inside `decideTurn` that reads `ti_addressed_fields` alongside
  `missing_fields`.

### Ordering — when does `decideTurn` run?

**Once per turn**, after the LLM's ops have been drained into a
**staging buffer** but BEFORE any of them has mutated persistent state,
and BEFORE reply composition. The staging buffer is the mechanism that
makes the single-call contract possible: ops arrive, get staged (not
applied), the decision layer inspects them, then the layer's `op_plan`
is what actually executes against state.

Tool calls that produce tool-results (e.g. `get_price`) still run
during the LLM turn — they're inputs to the decision, not outputs.
State-mutating ops (`apply_booking_field`, `cancel_booking`,
`start_booking`, `confirm_summary`, `set_*`) stage only.

Fast-path pre-apply (which runs BEFORE the LLM turn today) is itself a
source of proposals that stage into the same buffer. The decision
layer sees fast-path-proposed ops and LLM-proposed ops uniformly.

This is the architectural shift: **no path applies state without
going through `decideTurn`**. Today both fast-path and LLM-drain can
mutate state directly. After migration, neither can.

### LLM's role — still B-with-teeth

Unchanged in principle, sharpened in shape. The LLM:

- Produces proposals: ops + reply_draft + semantic classifications.
- Does **not** drive state mutation. Its ops are staging inputs.
- Retains authorship of replies in cases the layer explicitly delegates
  (informational answers, post-order routing until Phase 3c flips,
  `create_simple_order` confirmation reply, pre-booking quote phase).
  Those delegations are spelled out by `reply.source = "llm_authored"`
  with an `llm_authored_reason` tag — which forces the decision layer
  to acknowledge each one as an explicit carve-out, not a default.

The proposer schema becomes the LLM's I/O contract with the decision
layer. Every field the layer reads off `proposer.*` is a field the
LLM is prompted to provide. Every op the layer admits is an op type
the LLM is prompted about.

## Migration discipline

### Rule

Every commit in the migration arc is **one of**:

1. **Contract**: edits to this document.
2. **Scaffold**: introduces the unified module, wires its signature,
   ships it as a pure observer (shadow). Adds an entry to the trace
   log but does not change behaviour.
3. **Relocate**: moves decision logic from one of (A1)–(A4) INTO
   `turn-decision.ts` AND removes it from the source. Behaviour is
   preserved bit-for-bit in this commit; what changes is *where* the
   decision is made. A relocation commit never adds new semantic
   logic — it literally moves code.
4. **Activate**: once relocated, swap a consumer from "live authority
   path" to "read from `TurnDecision`." At this point the old authority's
   code is either deleted or marked `@deprecated bridge — collapses in
   next commit`.
5. **Extend**: only AFTER relocate+activate of a surface is complete
   may we add new semantic consumption to that relocated logic.

No commit is allowed to simultaneously move code AND change behaviour
AND add new features. Exactly one of those per commit. This is the
discipline that makes rollback-at-any-step possible.

### Bridge markers

During migration, every piece of code on the collapse path carries an
inline comment of the form:

```ts
// BRIDGE(turn-decision): this block will move to
// plugins/shared/turn-decision.ts::<branch_name>. See
// ARCHITECTURE_TURN_DECISION.md §<section>.
```

A grep for `BRIDGE(turn-decision)` produces the full migration TODO
at any point. The last bridge deleted signals the arc is complete.

### Relocation order (proposed; open to revision)

Smallest / lowest-risk first, high-value last:

1. **Scaffold** `turn-decision.ts` as a pass-through shadow: consumes
   all inputs, produces a trace log, returns a `TurnDecision` derived
   entirely from reading what the other authorities already decided.
   Zero behaviour change. Verifies the input surface is complete.
2. **Relocate (A4) directive dispatch** into the decision layer. The
   directive-reply-registry stays; what moves is the decision "which
   directive + render context" from `index.ts` into `turn-decision`.
   Blast radius: small. This mirrors Phase 2 M1 and gives the layer
   its first real output.
3. **Relocate (A1) substitution branches** one at a time, easiest
   first (canonical overwrite → empty-fill → clarify-before-proceed →
   manual-confirm). Each becomes a `reply.source = "server_substitute_text"`
   branch in the layer. `outbound-decision.ts`'s Region A shrinks.
4. **Relocate (A2) directive selection.** The `computeOneBrainNextRequiredAction`
   function moves wholesale into the layer, gains `addressed_fields`
   as input, and the narrow directives missing today (e.g. `ASK_RECIPIENT_PHONE`)
   can be added as an (5)-style extension afterward.
5. **Relocate (A3) op-layer side-effects.** Hardest. The op drain
   stops being a mutating loop and becomes a staging loop. Decision
   layer reads staged ops, produces `op_plan`, an executor applies.
   This is where the "cancel confirmation" behaviour becomes
   expressible — as a `defer_confirm` verdict on `cancel_booking`.
6. **Extend** — now that everything routes through one layer, wire
   the remaining semantic consumptions (post_order_intent, ac_kind
   into the cancel-disposition logic, ti_kind=clarifying_question
   into the substitution branches) as additive policy rules.

Each step ships with its own deploy canaries and shadow-to-live flip
where applicable. Expected cadence: roughly one relocation per session.

## Non-goals

Explicitly out of scope for this layer:

- **Not a replacement for the apply boundary.** `apply-boundary.ts`
  still owns the evidence contract (source-quote, coherence,
  ambiguous-pair, shape). The decision layer sits above it; when
  `op_plan` says "accept apply_booking_field," the apply boundary
  still validates. The layer is *whether and with what mask*; the
  boundary is *does the mask pass schema*.
- **Not a replacement for the hallucination guard.** Post-reply
  verification (price-mismatch, summary fact-drift) stays in the
  existing guard module and runs after the decision layer produces
  its reply.
- **Not a rewrite of the LLM prompt.** `SKILL.md` and the context
  assembler stay as-is through the migration. The prompt-side
  contract is sharpened by the proposer schema, not by this doc.
- **Not a state-machine rewrite.** Stages, controller lifecycle,
  persistence — unchanged. The layer reads stage; it doesn't redefine
  it.

## Open questions (for iteration)

These are deliberately not resolved in v1 of this doc. Each is a place
I expect us to learn the answer during relocation 1 or 2.

1. **Fast-path timing.** Today fast-path pre-apply runs BEFORE the LLM.
   Under the layer, does fast-path become a proposer alongside the
   LLM (both stage, layer decides)? Or does fast-path disappear (LLM
   handles everything)? Argument for keeping fast-path: latency and
   deterministic-shape guarantees. Argument against: another source
   of ops we have to reason about. Defer until after relocate (A3).

2. **Multi-op turns.** When the LLM emits 3 ops (say,
   `apply_booking_field`, `set_pending_area`, `get_price`), can the
   decision layer reject one and accept the others, or is it all-or-
   nothing? Leaning: per-op verdict is what `op_plan.entries[]`
   already encodes, so yes, granular — but we need to verify in
   relocate (A3).

3. **Reply + op co-decision.** Does the layer ever produce
   `reply.source = "llm_authored"` WITH `op_plan.entries[i].verdict = "reject"`?
   i.e., "let the LLM's reply through but don't apply its ops." Likely
   yes (informational-answer turns), but we need to think about
   whether that's coherent or a sign of bad inputs.

4. **Turn atomicity on failure.** If `decideTurn` throws, what's the
   fallback? Proposal: fall back to the legacy path for that turn,
   log loudly. Defer formalisation until scaffold commit.

5. **Observability format.** The trace object is described above. Open
   whether it emits as one structured JSON line or multiple. Leaning
   one line, JSON-encoded, tag `[turn-decision/trace]`.

## What this doc is not

This doc describes a *contract* and a *migration discipline*. It does
not describe the implementation. The first `turn-decision.ts` file will
be a scaffold, not a finished layer, and the shape above will almost
certainly refine during the first two relocations. This doc updates
with every refinement; commits reference this doc by section.
