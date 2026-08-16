# Probation Wave 1 Backend — FREEZE

**Status:** FROZEN — `PROBATION_WAVE1_FULL_PASS` qualified 2026-08-11  
**Evidence:** `ops/evidence/probation-wave1-20260811T183704Z`  
**Contract doc:** `ops/PROBATION_WAVE1_BACKEND.md`

## Frozen surface

| Artifact | Path |
|---|---|
| Authority | `wathefni-orchestrator/probation.py` |
| SQL | `wathefni-orchestrator/ops/sql/probation_wave1_v1.sql` |
| Soft hire hook | `hire_ready_bridge.py` → `maybe_create_case_on_hire` (optional; dark) |
| Schema ensure | `app.py` → `ensure_probation_schema` |
| Smokes | `smoke-test-probation-wave1.py` / `-db.py` |
| Qualify | `ops/qualify-probation-wave1-staging.sh` |

## Freeze rules

1. Do **not** change case/milestone state machines without an explicit freeze amendment.
2. **No Probation UI / surfaces** in this freeze — backend authority + staging qualify only.
3. Keep dark by default: `WATHEFNI_PROBATION` + company allowlist + company enable.
4. Extension must write a new `probation_end` + audit; decisions require reason.
5. Hire→Ready soft auto-plan remains optional and company-gated; never force Probation on.

Amendments require a dated note in this file + re-qualify.
