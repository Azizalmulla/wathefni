# Riders bug-class tracker

Running log of failure *classes* the Riders stack has been hardened against.
One row per class — not per incident. A class stays open until:

1. invariant is defined,
2. smallest server-aligned fix landed,
3. whole-class regression tests landed (not just the exact transcript),
4. live canary ran green on current main.

> **Workflow gate**: we do not widen QA while any class below has
> `status != closed`. Every new bug must be triaged into a class first
> — either an existing one (then it's recurrence evidence) or a new one
> (then it needs invariant + regression + canary before we move on).

| # | class | invariant | status | regression | live canary | recurrence seen |
|---|---|---|---|---|---|---|
| 1 | `vague_proceed_signal_advances_manual_confirm_option` | On `stage=quoted` with a manual-confirm option on the route, a vague "proceed" cue (e.g. "can we go ahead with it or?") may not advance to sender collection without the customer explicitly naming an option. | closed | `smoke-test-clarify-option-before-proceed.mjs` | 2026-04-20 ✓ | no |
| 2 | `address_subfield_asked_after_server_said_complete` | If server `missing_fields=[]` for an address, LLM must not emit any address-subfield ask. Enforced via `forbidden_reply_shapes`. | closed | `smoke-test-address-complete-no-followup.mjs`, `smoke-test-address-completeness.mjs`, `smoke-test-fast-path-address-extra.mjs` | 2026-04-20 ✓ | no |
| 3 | `loose_option_alias_match_commits_wrong_option` | Abbreviated option input ("express ref van") must resolve through class+tier structured tokens, not loose substring scoring. Ambiguous/underspecified → clarify. | closed | `smoke-test-option-matcher-class-discriminated.mjs`, `smoke-test-option-interpretation-proposals.mjs` | 2026-04-20 ✓ | no |
| 4 | `manual_confirm_drops_into_direct_booking_flow` | An explicitly selected manual-confirm option must route through the deterministic manual-confirm address + handoff branch, not the standard-sedan direct-booking path. | closed | `smoke-test-manual-confirm-address-ask-substitution.mjs`, `smoke-test-server-synthesized-handoff.mjs` | 2026-04-20 ✓ | no |
| 5 | `informational_option_question_advances_booking_flow` | Informational option/price question at `stage=quoted` must elicit answer-only; directive substitution for collection/summary asks is skipped for that turn. Does NOT skip `CLARIFY_OPTION_BEFORE_PROCEED` or `CONFIRM_SLOT_CONFLICT`. | closed | `smoke-test-informational-question-gate.mjs` | 2026-04-20 ✓ | no |
| 6 | `area_clarification_symmetric_rebind` | During area clarification, LLM must not rebind the already-resolved side. Server pins the resolved leg as `pending*AreaNameEn`; pricing tool overrides any symmetric `get_price` call; context surfaces the pinned side + `pending_area_rule` forbidding symmetric calls; `route_zero_distance` shape triggers active recovery. | closed | `smoke-test-area-clarification-binding.mjs`, `smoke-test-pending-area-preservation.mjs` | 2026-04-21 ✓ | no |
| 7 | `responder_ops_lost_due_to_conversation_id_alias_mismatch` | `set_pending_area` / `set_requested_slot` ops pushed by tools under one conversation-id shape (e.g. `SessionKey`-embedded id, `To=octopus:<wa>`) must be drainable under every other plausible alias. Dual-key push + dedup-on-drain. | closed | `smoke-test-area-clarification-binding.mjs` (A1..A4, S3, S4) | 2026-04-21 ✓ | no |
| 8 | `first_turn_clarification_state_not_materialized` | When the drain sees any `set_pending_area` or `set_requested_slot`, the controller entry must be materialized this turn with `stage≥collecting_booking_details` + `requestedSlot` + pinned pending side, even on a fresh conversation where no prior controller entry existed. | closed | `smoke-test-area-clarification-binding.mjs` (S1, S4) | 2026-04-21 ✓ | no |
| 9 | `stale_guard_state_clobbers_clarification_turn` | A controller entry may be promoted to `stage=quoted` / populated with `quote*AreaNameEn` only when the current turn's `get_price` produced a priced route. A turn whose drain contains a route-side `set_requested_slot` (`pickup_area`/`dropoff_area`) is mid-clarification; the promotion must be skipped regardless of what `sessionGuard.lastQuotedRoute` holds (persisted guard state from a prior session can otherwise bleed through). | closed | `smoke-test-clarification-turn-not-promoted.mjs` | 2026-04-21 ✓ (conv 19089 — veto didn't need to fire on fresh guard; class 10 unmasked the true root cause) | 0 |
| 10 | `module_instance_isolation_drops_responder_ops` | A push to the responder-op buffer via any import path must be visible to a subsequent drain via any other import path in the SAME process. The backing `Map` is pinned on `globalThis` so cross-plugin-bundle imports share one buffer; push/drain emit `[responder-ops/buffer-push]` + `[responder-ops/buffer-drain]` lines so divergence is instantly diagnosable. | closed | `smoke-test-responder-ops-buffer-singleton.mjs` | PENDING (next canary) | 1 (conv 19089 @ 11:09 — pricing pushed `set_pending_area(Salmiya)` + `set_requested_slot(dropoff_area)` but drain observed empty buffer; no `[one-brain] drained` log emitted; next turn fell through to symmetric rebind → `route_zero_distance` recovery) |

## Observability signals

| log line | meaning |
|---|---|
| `[one-brain/clarify-commit]` | drain materialized clarification state this turn |
| `[one-brain/clarify-commit] INVARIANT_VIOLATION stage still idle` | class 8 recurrence |
| `[one-brain/clarify-preserved] skipped_quoted_promotion` | class 9 veto fired — stale guard state was refused |
| `[one-brain/reply-attribution] reply_author=llm directive=<non-null>` | server-owned directive turn was free-composed by LLM (regression signal for any ASK_* class) |
| `[one-brain/verify] outbound_shape=route_zero_distance replaced=true` | class 6 recovery fired |
| `[one-brain/drain] unknown_op` | responder-op contract drift |
| `[responder-ops/buffer-push]` | push saw the buffer at size N (class-10 counter) |
| `[responder-ops/buffer-drain]` | drain saw the buffer at size N (class-10 counter) |
| `[one-brain/drain-attempt]` | drain ran for this conversation (even when `drained=[]`) |
| `[responder-ops/mark-slot-skip] reason=no_primary_id` | class-7 recurrence — tool ctx lost every conversation-id shape |
| `[responder-ops/mark-slot-error]` / `[responder-ops/mark-pending-error]` | class-10 push path threw (previously swallowed silently) |

## Gating rule

Before widening QA to new scenarios, every class in this table must have
`status=closed` + `regression` row non-empty + `live canary` row showing a
passing run on current main. A new bug that reproduces a class already
marked closed increments the `recurrence seen` counter AND reopens the
class until a stronger invariant lands.
