# Preboarding Wave 1 Backend — FREEZE

**Status:** FROZEN — `PREBOARDING_WAVE1_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/preboarding-wave1-20260811T180308Z`  
**Contract doc:** `ops/PREBOARDING_WAVE1_BACKEND.md`

## Frozen surface

| Artifact | Path |
|---|---|
| Authority | `wathefni-orchestrator/preboarding.py` |
| SQL | `wathefni-orchestrator/ops/sql/preboarding_wave1_v1.sql` |
| Smokes | `smoke-test-preboarding-wave1.py` / `-db.py` |
| Qualify | `ops/qualify-preboarding-wave1-staging.sh` |

## Freeze rules

1. Do **not** change assignment/item state machines, readiness derivation, or SoD/waive semantics without an explicit freeze amendment.
2. Surface Wave may add **read helpers** (`list_assignments`, events) and thin HTTP wrappers only — no business-logic rewrite.
3. `ready` remains derived from required items/gates — never cosmetic.
4. `pending_start` remains non-active for payroll/attendance/leave/shifts/normal ESS.
5. Keep dark by default: `WATHEFNI_PREBOARDING` + company allowlist + company enable.
6. Truth-sync writers remain OFF independently of this freeze.

Amendments require a dated note in this file + re-qualify.
