# Migration Wave 1 — Foundation + Chunked CV Intake Freeze

**Status:** production synthetic qualified  
**Gate:** `PROD_SYNTHETIC_MIGRATION_WAVE1_FOUNDATION_CV_GO`  
**Freeze gate:** `MIGRATION_WAVE1_FOUNDATION_CV_GO`  
**Evidence:** `ops/evidence/migration-wave1b-prod-canary-20260804T024331Z/`  
**Staging prerequisite:** `ops/evidence/migration-wave1-staging-20260803T211505Z/` (`STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO`)

## Frozen posture

- Contract: `migration_wave1_foundation_cv_chunked` v1.0.0
- Module: `wathefni-orchestrator/migration_wave1_cv_foundation.py`
- Flag: `WATHEFNI_MIGRATION_WAVE1=1`
- `WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1`
- `WATHEFNI_MIGRATION_WAVE1_COMPANIES=WATHEFNI`
- Authority: **held-by-default**; Wave 1 path forces `auto_admit_enabled=False`
- Dedupe: content SHA-256; **no identity auto-merge**
- Jobs: durable chunks with lease, retry, dead-letter, replay
- Production ACK retained in `migration_wave_acks`

## Proven on production synthetic (WATHEFNI)

- Dry-run, chunked intake, resume, retry/DLQ, duplicates, external ATS IDs
- Held-by-default; no auto-admit; tenant isolation; audit/progress/rollback
- 1 000 and 10 000 synthetic CV imports
- Residual 0 after canary teardown
- Sibling freezes green
- Deploy rollback verified; redeploy canary green

## Explicit NO-GO / unchanged

- Real customer CV migration — **NO-GO**
- Millions-of-CVs cutover — **NO-GO** (not claimed)
- Full Migration Center UI — **not this wave**
- Employee / leave / compensation / shifts / compliance migration — **not this wave**
- Payroll money — unchanged / off this path
- Attendance `CAPTURE_INGEST` — remains **off**
- AI assistant / mobile — not widened
- Migration Wave 2 — **not started**

## Honesty

Synthetic fixtures only. No real customer files. No millions claim.
