# Eval corpus reports

Generated output from `scripts/eval-corpus/runner.mjs`.

Each run produces a new directory named
`<ISO_TIMESTAMP>-<random_suffix>/` containing:

- `raw.jsonl` — one JSON record per `case × run`, with per-turn emits
  (`[drift/get-price-bypass]`, `[structured-output/proposer]`,
  `[proposer/tool-call]`, `[class-15/bypass]`) and the assistant reply.
- `report.json` — structured rollup: per-case aggregates +
  corpus-level aggregates (turn_kind × outcome, plan_vs_fire, proposer
  present / schema-valid rates, get_price fired / bypass rates).
- `report.md` — human-readable summary of `report.json`.

## What it measures

The corpus pairs two observability channels added in Phase A / Phase D:

1. `[drift/get-price-bypass]` — post-decision turn classification and
   outcome. Tells us whether `get_price` fired, whether the turn was a
   Class-15 bypass / repair, and what state the turn started in.
2. `[structured-output/proposer]` — conformance of the new
   `propose_turn_decision` tool: did the LLM call it, was the payload
   schema-valid, did the LLM's declared `planned_tool_calls` match what
   actually fired (`plan_vs_fire ∈ {aligned, drift_declared_not_fired,
   drift_fired_not_planned, n/a}`).

The rollup is the baseline against which we evaluate:

- Phase B (facts-only directive trim) — does trimming the directive
  layer regress any of the corpus metrics?
- Phase A promotion gate — is the `schema_valid` rate ≥95% across
  blocker cases to promote from shadow → `applyProposals` routing?
- Phase D — are bypass rates falling turn-over-turn as prompt + tool
  surface hardens?

## Usage

Full sweep (default N=5 runs per live case + all unit cases):

```bash
npx tsx scripts/eval-corpus/runner.mjs --n 5
```

Target a single case (handy after a prompt tweak):

```bash
npx tsx scripts/eval-corpus/runner.mjs --cases C16-paired-doha-mina-doha --n 5
```

Fast unit contract sweep (no network; ~3s):

```bash
npx tsx scripts/eval-corpus/runner.mjs --unit-only --n 1
```

## Notes

- The runner's case-level assertions are ADVISORY, not hard-fail. A
  failed live assertion is recorded in the report as a warning; the
  runner still exits 0. Only unit schema-contract failures fail the run
  (exit 1) — that indicates the in-repo Phase A contract is broken.
- Live runs reset conversation state per case via
  `resetLiveConversationState` (same primitive the existing canaries
  use). No writes happen beyond that.
- Individual report directories are gitignored; commit only this
  README unless you need to share a specific baseline snapshot with the
  team, in which case copy the small `report.md` into the PR
  description.
