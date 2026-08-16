# Requisitions — Wave 1 Backend + Job Publish Gate

**Status:** REQUISITIONS_WAVE1_FULL_PASS (unit + staging DB) — **FROZEN**  
**Freeze:** `ops/REQUISITIONS_WAVE1_BACKEND_FREEZE.md`  
**Evidence:** `ops/evidence/requisitions-wave1-20260811T174336Z`  

**Charter:** `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md` (W1.1 / W1.2)  
**Code:** `wathefni-orchestrator/requisitions.py`  
**SQL:** `wathefni-orchestrator/ops/sql/requisitions_wave1_v1.sql`  
**Smoke:** `wathefni-orchestrator/smoke-test-requisitions-wave1.py`  
**DB prove:** `wathefni-orchestrator/smoke-test-requisitions-wave1-db.py`  
**Qualify:** `ops/qualify-requisitions-wave1-staging.sh`

## Scope this slice

- Requisitions authority module (SM, SoD, events, job links)
- OPTIONAL_INTEGRATION job publish gate in `prehire_jobs` create(open)/publish/reopen/resume
- Dark schema via `app.ensure_schema`
- **No** Requisitions / Preboarding / Probation UI
- **No** global enable; process-scoped flags only for prove
- Truth-sync writers remain OFF

## Rollout flag (fail closed)

All three required for requisitions:

1. `WATHEFNI_REQUISITIONS=on`
2. `WATHEFNI_REQUISITIONS_COMPANIES=<CSV>` (empty = nobody)
3. `requisition_settings.enabled=true` **or** `company_modules.requisitions.enabled=true`

Job publish gate additionally requires:

- `company_modules.pre_hiring.enabled=true`
- `requisition_settings.jobs_require_approved_requisition=true` (default true)

## State machine

`draft → pending_approval → approved → open → filled|cancelled`  
`pending_approval → rejected → draft|cancelled`  
SoD: creator cannot self-approve (user id or phone).

## Rollback

1. `WATHEFNI_REQUISITIONS=off`
2. Remove company from allowlist
3. `UPDATE requisition_settings SET enabled=false …`
4. Optionally `jobs_require_approved_requisition=false`
5. Retain tables; do not DROP
6. Job publish resumes without gate when module/setting off

## Out of scope

- HTTP public API / dashboard UI
- Preboarding
- Migrating open jobs → fake approved requisitions
- Truth-sync writers
