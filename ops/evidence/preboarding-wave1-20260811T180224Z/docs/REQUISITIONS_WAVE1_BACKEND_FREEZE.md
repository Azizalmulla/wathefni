# Requisitions Wave 1 Backend — FREEZE

**Status:** FROZEN — `REQUISITIONS_WAVE1_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/requisitions-wave1-20260811T174336Z`  
**Contract doc:** `ops/REQUISITIONS_WAVE1_BACKEND.md`

## Frozen surface

| Artifact | Path |
|---|---|
| Authority | `wathefni-orchestrator/requisitions.py` |
| SQL | `wathefni-orchestrator/ops/sql/requisitions_wave1_v1.sql` |
| Job gate hook | `prehire_jobs.py` → `assert_job_publish_allowed` |
| Smokes | `smoke-test-requisitions-wave1.py` / `-db.py` |
| Qualify | `ops/qualify-requisitions-wave1-staging.sh` |

## Freeze rules

1. Do **not** change requisition SM, SoD, gate semantics, or flag triple without an explicit freeze amendment.
2. No Requisitions UI in this freeze (backend + optional job gate only).
3. Keep dark by default: `WATHEFNI_REQUISITIONS` + company allowlist + company enable.
4. Truth-sync writers remain OFF independently of this freeze.

Amendments require a dated note in this file + re-qualify.
