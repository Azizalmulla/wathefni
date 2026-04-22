# Turn-level semantics — `turn_intent`, `SlotEvent`, ack-aware rendering

> **Status:** target primitives agreed 2026-04-22 after the live sender-step
> incident on conversation 19399. Phased rollout; each phase shadow-first,
> behavior-second, same shape as Phase A (`awaiting_confirmation`). This
> document is scoped to the new primitives only — the base B-with-teeth
> architecture, apply boundary, and LLM-proposes / server-decides contract
> in [`ARCHITECTURE.md`](./ARCHITECTURE.md) stay exactly as they are.

## Why this layer now

The three fixes landed alongside this document (WhatsApp-equivalence
normalization, narrow `ASK_SENDER_NAME` directive, requested-slot name-
scope guard) closed the concrete 19399 bug. But each was shaped by the
same deeper pattern we've hit in several past incidents:

- "alright → sender_name" → coherence gate on the name slot.
- Ambiguous unlabeled name+phone pair → ambiguous-pair guard.
- Post-summary non-action turn falls through to re-summary → v1.1
  `awaiting_confirmation` classifier.
- Cross-side phone mirroring on one turn → `cross-side-phone-guard`.
- Stale `sender_phone` written on a name-requested turn → this PR.

Each fix is correct on its own terms, but the class they share is the
absence of a **turn-level semantic layer**. Today the apply boundary
validates _one slot write at a time_ against field shape and coherence.
Nothing summarises "what did the customer actually do on this turn,
relative to what we asked?" As a result:

- The selector only knows what's _missing_, not what the customer just
  tried to do.
- The renderer only knows the _next ask_, not what the previous answer
  resolved.
- The LLM re-asks questions whose answer the server has just captured
  under a different slot.

The primitives below give the system a small, typed vocabulary for
"what happened on this turn" so each downstream consumer can reason
about it uniformly.

## Primitive 1 — `turn_intent`

A structured classification of the customer's utterance _relative to
what the server asked_, emitted by the LLM alongside the existing
structured-output tool (`propose_turn_decision` v1.2).

Fields:

- `kind` — one of a fixed set (below).
- `addressed_fields` — array of slot names the customer's message tried
  to answer (may be empty for pure acknowledgments / clarifications).
- `confidence` — `"high" | "medium" | "low"`.

Classes (initial set, expected to grow once we see shadow data):

- `answered_full` — customer provided exactly what the server asked
  (e.g. full name for `ASK_SENDER_NAME`).
- `answered_partial` — customer addressed part of what the server
  asked (e.g. name only for a combined name+phone ask).
- `answered_unasked` — customer volunteered a field the server did not
  ask for this turn (e.g. phone on a name-only turn).
- `corrected_prior` — customer is editing a previously-filled slot
  (e.g. "block 3 to 4" post-summary).
- `clarifying_question` — customer asked a question about the offer /
  the flow rather than answering.
- `acknowledgement` — customer said "ok", "تمام", "got it" with no
  field content.
- `refused_or_stuck` — customer expressed inability or unwillingness
  to proceed ("leave it", "too expensive", "try later").
- `off_topic` — unrelated content.
- `unclear` — LLM can't confidently classify; treated as conservative
  (no policy fired).

`turn_intent` is emitted on every turn. This is a superset of
`awaiting_confirmation` which classifies the same customer utterance
only when the server is at the summary / confirmation stage. Once
`turn_intent` is live in shadow mode, `awaiting_confirmation` becomes a
specialization: `turn_intent.kind=confirm_order` implies the stage-
specific `awaiting_confirmation.kind=confirm_order`. We keep both while
shadowing, then collapse.

## Primitive 2 — `SlotEvent`

A semantic view of what happened to a slot on a turn, produced by the
apply boundary _in addition to_ today's `BoundaryResult.applied /
rejections / conflicts / normalizations`. Today's shape is a
side-effect log ("sender_name was applied, sender_phone was rejected
with reason X"). `SlotEvent` is the _semantic_ counterpart of the same
transition.

```
type SlotEvent =
  | { kind: "resolved";                     slot: SlotName; value: string; source: ProposalSource }
  | { kind: "resolved_via_equivalence";     slot: SlotName; value: string; equivalenceKind: "whatsapp_sender_phone" | ... }
  | { kind: "partially_resolved";           slot: SlotName; via: "side_partial" | "same_side_name_missing" }
  | { kind: "conflict_raised";              slot: SlotName; existing: string; incoming: string }
  | { kind: "conflict_resolved_via_edit";   slot: SlotName; from: string; to: string }
  | { kind: "out_of_scope_write_dropped";   slot: SlotName; reason: BoundaryRejectionReason }
  | { kind: "invalid_value_dropped";        slot: SlotName; reason: BoundaryRejectionReason; received: string };
```

Every event carries enough context for both the selector and the
renderer (see primitive 3) to act on it. The three fixes landed today
map onto `SlotEvent`s:

- Fix A → `resolved_via_equivalence` for sender_phone ↔ phone_decision.
- Fix C → `out_of_scope_write_dropped` with reason
  `requested_slot_name_scope`.
- The pre-existing ambiguous-pair rejection → `out_of_scope_write_dropped`
  with reason `ambiguous_pair_sender_unresolved`.

The key property: a downstream consumer reading a `SlotEvent` no longer
has to infer intent from a rejection reason string. The events are
first-class signals.

## Primitive 3 — Acknowledgement-aware renderer

Directives today are "ask"-shaped: the registry produces a single line
per directive. Once `SlotEvent`s exist, every ask becomes an
`(acknowledgement, ask)` pair where the acknowledgement is derived
_deterministically_ from the last turn's resolved SlotEvent, not from
LLM phrasing.

```
renderDirectiveReply(action, ctx)
  → { acknowledgement: string | null, ask: string }
```

Concrete examples, using the 19399 case after Fix A lands:

- Turn B SlotEvent: `resolved_via_equivalence { slot: sender_phone,
  equivalenceKind: whatsapp_sender_phone }`.
- Turn C directive: `ASK_SENDER_NAME`.
- Rendered: `{ acknowledgement: "Got your WhatsApp number.", ask:
  "Sender's full name?" }` → outbound text = `"Got your WhatsApp
  number. Sender's full name?"` (EN) / equivalent AR.

Without the acknowledgement, the narrow `ASK_SENDER_NAME` from today's
Fix B still feels like the bot ignored the phone answer — a real UX
signal in the live traces. The ack turns "I captured X, now I need Y"
into a single observable bot behavior.

Acknowledgements are rendered _only_ from `SlotEvent`s, never from the
LLM reply. That keeps the wording owned by the server, same as the
rest of the directive registry.

## Staged rollout

Same shape as Phase A's `awaiting_confirmation` (2026-04-22), which
proved that shadow-mode emit + log-review + gated flip gives us both
measurement and confidence.

### Phase 1 — `turn_intent` in shadow (1–2 weeks live)

- Schema v1.2 of `propose_turn_decision` adds the optional
  `turn_intent` block. Validator updated; JSON schema published.
- LLM prompt instructed to populate `turn_intent` on every turn,
  regardless of stage.
- `[structured-output/proposer]` log emit gains `ti_kind`,
  `ti_fields`, `ti_confidence`. No behavior change.
- Exit gate: shadow distribution on the real manual test pack shows
  high-confidence classes dominate and the `unclear` bucket is <10%.

### Phase 2 — `SlotEvent` emit alongside `BoundaryResult`

- `applyProposals` returns `events: SlotEvent[]` in addition to the
  existing arrays. Constructed from the same per-step decisions the
  current log entries already emit, so this is shape change only.
- New log line `[one-brain/boundary/event]` per event. Observation
  only; existing rejection / normalization log lines stay.
- Exit gate: events reproduce the current 19399 narrative end to end
  when replayed from stored turns.

### Phase 3 — Acknowledgement-aware renderer (ack from the prior SlotEvent)

- Directive renderer signature migrates to
  `(action, ctx, lastSlotEvent?) → { acknowledgement, ask }`.
- For directives that already have server-owned strings today, the
  `ask` half is unchanged — we only add the `acknowledgement` when the
  prior turn's event warrants it.
- Outbound substitution concatenates the two halves; provenance
  remains `registry_rendered`.
- Exit gate: live traffic shows the acknowledgement firing on the
  expected turns (resolved / resolved_via_equivalence) and not firing
  on unrelated stages (asks without a prior resolve).

### Phase 4 — `turn_intent`-driven policy

Only after Phases 1–3 have been live for at least one manual-pack
iteration each, wire `turn_intent.kind` into the next-action selector
so that:

- `answered_partial` + missing fields → narrow ask for the missing
  half (what Fix B does today for one specific case generalises to
  all fields).
- `clarifying_question` during collection → answer, don't advance.
- `corrected_prior` → edit-intent override (currently a regex +
  stage heuristic in `apply-boundary.ts`).
- `refused_or_stuck` → handoff / pause.

Each of these is an existing incident-shaped fix or a future one we
want to avoid having to ship as an individual patch.

## Non-goals for this document

- No new fields get added to the booking draft.
- No changes to the LLM-proposes / server-decides contract — the LLM
  continues to propose slot writes via `apply_booking_field` and
  continues to be ignored for outbound text on server-owned
  directives.
- No rewrites of the existing apply boundary. Every gate
  (source-quote, ambiguous-pair, coherence, edit-intent, shape) stays.
  `SlotEvent` is emitted as a read-only mirror of those gates'
  decisions.

## Relationship to the three fixes landed today

The immediate fixes are deliberately the **first three uses of
`SlotEvent`-shaped reasoning**, shipped without the primitive:

- Fix A ("WA-equivalence normalization at the boundary") is the
  hand-rolled version of `SlotEvent.resolved_via_equivalence`.
- Fix B ("narrow `ASK_SENDER_NAME` directive") is the hand-rolled
  version of an ack-aware renderer for the specific case
  `prior_event.kind === "resolved_via_equivalence"
  && missing.includes("sender_name")`.
- Fix C ("requested-slot name-scope guard") is the hand-rolled
  version of `SlotEvent.out_of_scope_write_dropped` on the
  `requested_slot_name_scope` reason.

When the primitives land, these fixes survive unchanged — they
become specialisations of the generic path instead of standalone
code. That is the signal that the primitive is correct.
