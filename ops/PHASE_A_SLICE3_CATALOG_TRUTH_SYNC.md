# Phase A Slice 3 — Catalog / Contracts / Truth-Sync

**Status:** PHASE_A_SLICE3_FULL_PASS  
**Depends on:** Slice 1 FULL PASS · Slice 2 FULL PASS (invariants locked)  
**Writers:** `WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=off` (mandatory for this foundation)  
**pending_start:** canonical hub projection `pending_start` (never `active`) — P1–P9 zero fail on staging WATHEFNI  
**Evidence:** `ops/evidence/phase-a-slice3-20260811T153131Z` · projection re-prove `ops/evidence/pending-start-projection-20260811T173909Z`  
**Qualify:** `ops/qualify-phase-a-slice3-staging.sh` · `ops/qualify-pending-start-projection-staging.sh`

## Delivered

| Piece | Path |
|---|---|
| Module catalog Wave 1 keys | `module_catalog.py` — `requisitions`, `preboarding`, `probation` (+ hire_ready_suite) |
| Capability contracts | `capability_contracts.py` — HARD / OPTIONAL / ENHANCEMENT |
| Truth-sync dry-run | `employment_truth_sync.py` |
| Slice 2 invariant pack | `ops/sql/workflow_task_sla_phase_a_v1b_invariants.sql` |

## Truth-sync prove (dry-run only)

- Joining date authority vs offer / applicability snapshot
- Probation terms
- pending_start P1–P9 findings (including hub_status mapping honesty)
- Duplicate employment detection
- No accidental eligibility flags when present on rows
- Module-off behavior via contracts
- Rollback guidance (writers stay off)

## Out of scope

- Requisitions / Preboarding / Probation UI
- Enabling truth-sync writers
- Live SLA reminder push
