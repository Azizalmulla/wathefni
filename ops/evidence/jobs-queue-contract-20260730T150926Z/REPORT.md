# Jobs Queue Contract — Production Report

**Stamp:** `20260730T150926Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Tenant proof:** `WATHEFNI`

## Summary

Implemented the approved Jobs applicant-count and status-alias contract. Clickable Applications, close-job confirmation, and View candidates (`role_active`) now share `jobs.active_pipeline`. Historical funnel / `application_count` retain all statuses and are not the clickable active count. Job status aliases normalize through one shared contract.

## Contract

| Scope | Predicate |
|---|---|
| `jobs.applications_total` | all statuses (production + CV gate) |
| `jobs.active_pipeline` | exclude `hired`, `rejected`, `withdrawn`, `archived` |
| `jobs.role_active_candidates` | identical to `active_pipeline` + `position_code` |

| Alias | Canonical |
|---|---|
| `active`, `published` | `open` |
| `inactive` | `closed` |

Lifecycle unchanged; reopen remains `closed → open`.

## Live proof (WATHEFNI)

| Job | Historical total | Badge (`active_count`) | Opened Candidates (`role_active`) | Result |
|---|---:|---:|---:|---|
| `IT_MAINTENANCE` | 1 | **0** | **0** | **PASS** |
| `MARKETING_SPECIALIST` | 1 | **0** | **0** | **PASS** |
| `SOCIAL_MEDIA_MANAGER` | 2 | **1** | **1** | **PASS** |

Status aliases: `published`/`active` → `open`, `inactive` → `closed` — **PASS**.  
List filter `status=published` ≡ `status=open` (9 roles) — **PASS**.

Evidence: `live-proof.json`.

## Files

### Backend
- `wathefni-orchestrator/jobs_queue_contract.py` (**new**)
- `wathefni-orchestrator/app.py` — inventory / summary / roles report counts + status filter
- `wathefni-orchestrator/prehire_jobs.py` — `normalize_status` delegates to contract
- `wathefni-orchestrator/prehire_overview.py` — `role_active_predicate` ≡ `active_pipeline`
- `wathefni-orchestrator/reports_metrics.py` / `reports_v1.py` — open-role aliases + active apps
- `wathefni-orchestrator/test_jobs_queue_contract.py` (**new**)

### Dashboard
- `apps/wathefni-dashboard/src/pages/JobsPage.tsx` — clickable Applications uses `active_count`
- `apps/wathefni-dashboard/src/components/JobWorkspace.tsx` — Applicants count / Applications fact use `active_count`; shared `normalizedJobStatus`
- `apps/wathefni-dashboard/src/pages/shared/format.ts` — `inactive` → `closed`
- Vitest: `JobsPage.test.tsx`, `format.jobStatus.test.ts`

### Live assets
- `JobsPage-BR33iP0M.js`
- `JobWorkspace-eitVT8bu.js`
- `dashboard-hfZ7xwXr.js`

## Migration impact

**None.** Runtime normalize + aggregate SQL only. No schema change. Funnel `stage_counts` unchanged (historical).

## Rollback

```bash
/opt/wathefni/backups/production-pre-jobs-queue-contract-20260730T150926Z/ROLLBACK.sh
```

Restores prior orchestrator modules + dashboard dist; removes `jobs_queue_contract.py` if it was new.

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| Unit contract suite (prod) | **PASS** 10/10 |
| Local vitest JobsPage + status aliases | **PASS** 12/12 |
| Live three-job badge ≡ Candidates | **PASS** |
| Status alias serialize + filter | **PASS** |
| Health after restart | **PASS** `200` |

## Out of scope (unchanged)

Candidates / Assessments / Ranking product surfaces beyond the shared `role_active` predicate used by Jobs → View candidates.
