# Migration Wave 1 — Foundation + Chunked CV Intake Freeze

**Status:** staging qualified  
**Stamp:** 20260803T211505Z  
**Evidence:** `ops/evidence/migration-wave1-staging-20260803T211505Z/`  
**Gate:** `STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO`

## Frozen surface
- Contract: `migration_wave1_foundation_cv_chunked` v1.0.0
- Module: `wathefni-orchestrator/migration_wave1_cv_foundation.py`
- Flag: `WATHEFNI_MIGRATION_WAVE1=1` (staging)
- Stage root: `WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT` / workspace `migration_wave1_stage/`
- Authority: **held-by-default**; Wave 1 path forces `auto_admit_enabled=False`
- Dedupe: content SHA-256; **no identity auto-merge**
- Jobs: `migration_chunk_jobs` with lease, retry, dead-letter, replay
- Rollback: deletes held applications + import artifacts for the migration batch

## Proven on staging (synthetic only)
- Core contract (dry-run, resume, retry/DLQ, tenant isolation, external ATS ids)
- 1 000 synthetic CVs
- 10 000 synthetic CVs
- Residual 0 after rollback/teardown
- Sibling freezes green

## Explicit NO-GO / unchanged
- Production synthetic Wave 1-B — **NO-GO** until separately authorized
- Real customer CV migration — **NO-GO**
- Millions-of-CVs cutover — **NO-GO** (not claimed)
- Full Migration Center UI — **not this wave**
- Employee / leave / compensation migration — **not this wave**
- Payroll money — unchanged / off this path
- Attendance `CAPTURE_INGEST` — remains **off**
- AI assistant / mobile — not widened
- Migration Wave 2 — **not started**

## Honesty
Synthetic fixtures only. No real customer files. No millions claim.
