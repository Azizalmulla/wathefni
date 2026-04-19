# Riders Conversation Architecture

> **Status:** Target architecture agreed 2026-04-19. This document is the single
> reference for conversation-layer design decisions. Every PR that touches
> slot-filling, state writes, reply composition, or the LLM prompt is expected
> to be consistent with it. Incident-driven local patches that conflict with
> this document are a signal we should fix the architecture, not the patch.

## TL;DR

> **LLM proposes. Server decides. Deterministic code observes — and may also
> propose on unambiguous shapes. There is exactly one apply boundary, and every
> slot write on every path goes through the same evidence contract.**

This is shape **B-with-teeth**: LLM-first orchestration with hard server-side
validation of every structured output, and a deterministic feature extractor
that (a) always emits features and (b) may directly emit proposals for shapes
that cannot be ambiguous — but those proposals are validated identically.

## Why this shape

Before this direction was set, the runtime had accumulated three defensive
layers around an LLM core we didn't fully trust:

1. a deterministic pre-applier that wrote state before the LLM ran,
2. post-LLM guards at the apply boundary (slot-coherence, ambiguous-pair,
   compact-factual-drift, canonical-overwrite), and
3. prompt-level tightening in `SKILL.md` hoping the LLM behaves.

Each was added in response to a specific production incident. The cumulative
effect was a mixed hybrid whose behavior on any new input required tracing
which of the three layers happened to catch it. New failure categories —
"alright" misread as a sender name, a letterless turn flipping reply script
to Arabic — kept slipping past because no single layer was authoritative.

The two alternatives were rejected:

- **Pure deterministic (A)** — loses multilingual free text, code-switching,
  repair turns, soft intents, paraphrase. The LLM is genuinely good at
  "turn natural language into a typed proposal," and we shouldn't give that up.
- **Pure LLM-first with post-hoc validation only** — every incident so far
  shows the LLM will confidently propose nonsense when nudged. Prompt
  discipline alone does not hold in production.

**B-with-teeth** keeps the LLM's language strength, removes its commit
authority, and draws one bright line (the apply boundary) where every
proposal is tested against one contract.

## The three layers

```
┌───────────────────────────────────────────────────────────────────────┐
│  Layer 1 — Deterministic Feature Extractor (observer + fast-path)     │
│  pure functions, no state writes                                      │
│  emits: Features + (optionally) Proposals[] on unambiguous shapes     │
└───────────────────────────────────────┬───────────────────────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Layer 2 — LLM Proposer                                               │
│  sees: utterance + features + draft + state + next_required_action    │
│  emits: Proposals[] with mandatory source_quote per field             │
│  no state writes. no reply composition for deterministic moves.       │
└───────────────────────────────────────┬───────────────────────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Layer 3 — Decision Engine (the ONE apply boundary)                   │
│  takes: Proposals[] from L1 + L2, Features, draft, state              │
│  runs: the evidence contract (see §Evidence contract)                 │
│  emits: committed delta, rejections, next_required_action, reply      │
└───────────────────────────────────────────────────────────────────────┘
```

### Layer 1 — Deterministic Feature Extractor

- Pure functions. Zero state writes.
- Always emits `Features` — detected areas, phone shape, decision markers,
  address completeness, language, script mode, intent hint, coherence
  classification of the utterance against the currently-asked slot.
- **May also emit `Proposals[]`** on shapes that cannot be ambiguous:
  - bare phone digits when the asked slot is a phone,
  - explicit `use_whatsapp` / `different number` markers,
  - labeled complete addresses (passes the completeness predicate),
  - single-confident area matches from the area resolver.
- Those proposals carry `source: "fast_path"` and go through the same Layer 3
  contract as LLM proposals. The fast-path never writes state directly.

This is why "alright → sender_name" and similar incidents become impossible:
the fast-path cannot commit, and its proposal fails Layer 3's coherence gate
regardless of whether it looked like a name.

### Layer 2 — LLM Proposer

- Sees the full context: utterance, Layer 1 features, current draft, dialog
  state, `next_required_action`, and any rejections from the previous turn.
- Outputs typed `Proposal[]` with a **mandatory `source_quote`** per field.
  Proposals without a `source_quote` are dropped at Layer 3 with
  `missing_source_quote`.
- Does **not** write state. Does **not** compose replies for deterministic
  ASK_* / transactional / fixed-clarification moves.
- **Still composes replies** for genuinely conversational turns — greeting
  returns, off-topic redirects, empathy, apologies, and anything that needs
  to reference the customer's specific wording. See §Reply composition.

### Layer 3 — Decision Engine (the one apply boundary)

- The **only** code that mutates draft state.
- Runs the evidence contract below on every proposal, regardless of origin.
- Returns a structured `CommitResult`:
  ```
  CommitResult {
    committed:   FieldDelta,
    rejections:  FieldRejection[],   // fed back into next turn's directive
    nextAction:  NextRequiredAction,
    reply:       ComposedReply,      // deterministic for ASK_*/system; LLM-composed for conversational
  }
  ```
- Replaces, in one place, what is today spread across: fast-path pre-applier,
  `applyBookingFieldPatch`, ambiguous-pair-guard, slot-coherence gate,
  compact-factual-drift, canonical-overwrite-gate, per-slot validators.

## Evidence contract

Every proposal — fast-path or LLM — is evaluated on this struct at Layer 3:

| Check              | What it enforces                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| `source_quote`     | The exact customer utterance this value came from. **Mandatory.** Missing → reject.               |
| `slot_asked`       | Which slot was actually being collected. Proposals for other slots are low-confidence.            |
| `shape_valid`      | Passes the slot's shape predicate (name rules, phone digits, address completeness).               |
| `coherence_ok`     | The utterance is a coherent answer to `slot_asked` — not greeting, question, acknowledgment, topic-change. |
| `ambiguity_check`  | Unlabeled name+phone pairs do not silently populate recipient while sender is unresolved.         |
| `drift_check`      | Proposed value does not silently conflict with an already-stored canonical value.                 |
| `confidence`       | Derived: `high` if all pass cleanly; `medium` if any ambiguous; `low` if any fail.                |

Decision matrix:

- **high + all pass** → commit silently.
- **medium** → commit and annotate; next turn's directive includes a soft
  confirmation hint ("I noted X; let me know if that's wrong").
- **low / any check fails** → **reject**. Return a structured `FieldRejection`
  with a reason code. No silent drops. The rejection is fed into the next
  turn's LLM directive so the LLM sees why its proposal didn't land.

**Closing the feedback loop** — the LLM directive in `one-brain-context` will
always include, for the currently asked slot, the list of rejection reasons
the server will emit. The LLM learns what the server will not accept, and
when it proposes something that gets rejected, it sees the reason structured
in the next turn's context. This is how we stop blind LLM retries.

## Reply composition

Reply text is composed at **Layer 3**, not by the LLM, for the following
move classes:

- **ASK_\*** — every deterministic slot ask (`ASK_SENDER_PHONE`,
  `ASK_RECIPIENT_NAME_AND_PHONE`, `ASK_PICKUP_ADDRESS`, etc.).
- **System / transactional** — price quote, booking confirmed, cancelled,
  hard errors, explicit apologies for failed operations.
- **Fixed clarifying re-asks** — "I didn't catch the phone number, could you
  resend it?", "Could you confirm if that name is for the sender or the
  recipient?" (the ambiguous-pair clarification).

For these moves, reply text is a pure function of state + `next_required_action`
+ `customer_script_mode`. That makes language/script bugs like "letterless
turn flipped to Arabic" structurally impossible: the script is a server
decision, not an LLM choice.

Reply text remains **LLM-composed** for:

- greeting returns ("hey" → "hi, welcome to Riders. …"),
- off-topic redirects and empathy turns,
- any turn that needs to reference the customer's specific wording back to
  them,
- repair/change acknowledgments where the phrasing benefits from naturalness.

The split is: **deterministic moves get deterministic replies. Conversational
moves stay conversational.** We deliberately stop short of over-templating —
the LLM's language is still the product's voice, just not on the moves where
correctness trumps naturalness.

## Language and script

Both `customer_script_mode` (`english` | `arabic`) and the outbound reply
language are **server-decided functions of state**, never LLM-decided:

- Turns with Latin letters only → `english`.
- Turns with Arabic letters only → `arabic`.
- Turns in Arabizi (Latin + digit-substitutions) → `english` (Kuwaiti
  customers prefer English replies over back-transliterated Arabizi).
- **Letterless turns (digits, punctuation, whitespace, emoji only) inherit
  the conversation's existing script/language.** They carry no signal and
  must not flip the mode.
- Mixed-script turns prefer Arabic to preserve the primary language unless
  an explicit English signal is present.

Reply templates are rendered in `customer_script_mode`. LLM-composed replies
carry the mode as a hard directive and are post-validated to catch drift.

## State-write rules

- **Only Layer 3 writes draft state.** No exceptions. Grep the codebase for
  draft mutations outside this boundary — any hit is a bug.
- **Every write has a `source` tag**: `fast_path` or `llm`. For debugging and
  for per-source telemetry on the evidence contract.
- **Every rejected proposal is logged** with structured reason codes so that
  log aggregation reveals *categories* of failure, not single incidents.

## Migration arc

This is the plan we are executing. Each step is independently shippable and
leaves the system more correct than it was, not less.

1. **Write this doc.** (done — this file)
2. **Fast-path from pre-applier to observer + proposer.** The fast-path
   stops mutating state. It emits features always, and proposals on
   unambiguous shapes. Proposals flow into Layer 3's apply boundary with
   `source: "fast_path"`.
3. **Collapse all apply-time validators into one `applyProposal` function.**
   The evidence contract above lives in one place. Every proposal from every
   source goes through it. The current validators become inline checks of a
   single pipeline.
4. **Deterministic reply rendering for ASK_\* / system / fixed-clarification
   moves.** The LLM keeps free-text replies only for genuinely conversational
   turns. Language/script becomes a server decision at Layer 3.
5. **Category-level tests from prod logs.** Replace per-incident regressions
   with a corpus of customer turns tagged by category (greeting /
   acknowledgment / question / topic-change / answer / repair / multi-field /
   ambiguous). Run every category against every slot and assert the coherence
   gate's verdict. New categories from prod feed back into the corpus.

After step 5, the class of bugs we've been shipping fixes for every day is
structurally impossible. Not because we remembered to add a check — because
the architecture has no place for them to live.

## What this document is not

- Not a rewrite plan. We are ~70% of the way to this shape already.
- Not a freeze on SKILL.md or prompt work — but SKILL.md is now documentation
  of expected LLM behavior, not a load-bearing safety layer.
- Not a ban on incident-driven fixes — but every fix lands as a slice of one
  of the five migration steps, not as a fourth defensive layer.

## Glossary

- **Draft** — the in-progress booking state being collected across turns
  (sender, recipient, pickup, dropoff, vehicle, etc.).
- **Slot** — one field of the draft.
- **Proposal** — a typed suggestion to write a value to a slot. Carries
  `field`, `value`, `source`, `source_quote`. Never a commit.
- **Apply boundary** — the one function, at Layer 3, that turns proposals
  into committed state after running the evidence contract.
- **Evidence contract** — the fixed set of checks every proposal passes (or
  fails) before any state changes. See §Evidence contract.
- **Coherence** — whether a customer utterance is a coherent answer to the
  slot we asked for (not a greeting, question, acknowledgment, topic-change).
- **Script mode** — `english` or `arabic`; determines reply script and is a
  server-decided function of state.
