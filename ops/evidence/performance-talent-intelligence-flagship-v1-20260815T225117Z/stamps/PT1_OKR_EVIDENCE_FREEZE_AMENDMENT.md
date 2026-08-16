# PT1 — Freeze Amendment

**Stamp:** `PT1_OKR_EVIDENCE_FULL_PASS`  
**Prior:** `PERFORMANCE_TALENT_INTELLIGENCE_PT0_DESIGN_ACCEPTED`  
**Modules:** `wathefni-orchestrator/okr_operating_pt1.py`, `wathefni-orchestrator/talent_evidence_index_pt1.py`  
**Surfaces:** existing Performance + Talent HTTP / HR Web / Employee App / Setup

## What this slice owns

- First-class **OKR operating cycle** (`perf_okr_cycles`) — not a C2 review cycle
- Cycle-scoped objective membership without altering `perf_objectives`
- Alignment tree + alignment history over frozen `perf_alignment_links`
- OKR update thread (`perf_okr_updates`) with `mutates_progress = false`
- Optional configured confidence/health — never a second progress percentage
- Trajectory-ready history without trajectory classification
- Talent Evidence Index (`talent_evidence_refs`) — pointers, provenance, consume contracts
- Explicit opt-in `okr_as_talent_evidence_v1`

## What this slice does **not** own

- Configurable Talent models / WHY graph (PT2)
- Role-fit / Job Architecture scoring (PT3+)
- Talent Map (PT4)
- Succession intelligence (PT5)
- Trajectory labels (PT6)
- Assistant Talent tools (PT7)
- Full workforce what-if (PT8+)
- Production Readiness R7

## Additive freeze rules

- Do not create `okr_objectives_v2` or a second generic Goals table
- Do not store OKRs as `goal_kind`
- Do not reopen C1–C6 canonical math/state unless a genuine correctness blocker is proven
- Alignment must never inherit scores
- Check-in / confidence must never become progress authority
- Evidence index must not copy canonical ratings as a second SoT
- Consume contracts default OFF except existing frozen exceptions
- AI-SYNTHESIZED cannot be a Talent classification input
- Employee-claimed skills remain display/context, not verified competency
- Performance remains usable with Talent OFF; Talent remains usable with Performance OFF

## Prior freezes

- Wave 4 C1–C6 remain frozen
- R5B / R5C surfaces remain adapters — PT1 deepens them
- R2–R6 remain valid
- R7 stays **PAUSED**

## Rollback

```text
Disable okr_as_talent_evidence in Setup
Disable company Performance entitlement if OKR writes must stop
WATHEFNI_PERFORMANCE_GOALS_C1=off (kill switch)
Do not hard-delete evidence or cycle history
```

## Next

PT1 frozen. **Stop before PT2.** Do not resume R7 automatically.
