# Reports Correctness Contract — Production Report

**Stamp:** `20260730T210638Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Tenant proof:** `WATHEFNI`  
**Audit baseline:** `ops/evidence/reports-page-ux-audit-20260730` (FAIL → addressed)  
**Metric version:** `reports-contract-v2`

## Summary

Implemented the approved Reports correctness and clarity contract. Preserved Overview → Breakdowns → Exports and cream/ink. Replaced dual `reports_v1` + silent `reports_metrics` merge with one canonical payload. Overview cards, breakdowns, and export counts share reviewable production/CV scope and actor visibility.

## Live proof (WATHEFNI)

| Check | Result |
|---|---|
| Active applications | **7** ≡ `jobs.active_pipeline` (was UI 12) |
| Candidates needing interview scheduling | **4** ≡ scheduling debt |
| Assessments needing action | **2** (Overview `assessment_pending` people; completed excluded) |
| Held/test leakage in stage bars | **Gone** (Needs role absent; 5 held still exist only outside reviewable) |
| Owner export count ≡ CSV | **PASS** (all types) |
| Manager export count ≡ CSV | **PASS** |
| Recruiter (unassigned) export count ≡ CSV | **PASS** (scoped) |
| Roles count | Full roles-export universe (≥ open roles) |
| Interviews export card | Always when module on; count ≡ CSV |
| Asset EN/AR + Profiler marks | **PASS** |
| Health | **PASS** `200` |

Evidence: `live-proof.json`, `asset-markers.json`.

## Overview contracts

| Card | Authority |
|---|---|
| Open roles | `jobs_queue_contract` open-status |
| Active applications | `jobs.active_pipeline` ∧ reviewable (+ visibility) |
| Ready for review | `prehire_overview.ready_for_review` (people) |
| Candidates needing interview scheduling | `prehire_overview.interview_scheduling_debt` (applications) |
| Assessments needing action | `prehire_overview.assessment_pending` (people; never completed) |
| Current follow-ups | `prehire_overview.follow_up_needed` (people) |

## Breakdowns

- Stage → `candidates_stage_contract` buckets under reviewable; held/Talent Pool omitted; legacy offer → Shortlisted
- Role → active pipeline, labeled **Active applications by role**
- Assessment → every-attempt axis + EN/AR vocabulary (no raw enums)
- Interview → `interview_queue_contract.normalize_status` + EN/AR labels

## Exports

- Displayed counts ≡ CSV rows under the same visibility SQL
- `exports.followup_rows` = current follow-ups; `exports.followup_delivery_history_rows` = history (keys corrected)
- `report.export` entitlement preserved; visibility applied in export SQL

## Files

### Backend
- `wathefni-orchestrator/reports_metrics.py` — canonical `build_canonical_reports_payload`
- `wathefni-orchestrator/reports_v1.py` — export SQL + visibility params; followups ≡ `follow_up_needed`
- `wathefni-orchestrator/app.py` — `GET /reports` + `/export` single authority + visibility
- `wathefni-orchestrator/test_reports_metrics_contract.py`

### Dashboard
- `apps/wathefni-dashboard/src/pages/ReportsPage.tsx` — contract UI, EN/AR/RTL, Profiler, partial/error
- `apps/wathefni-dashboard/src/pages/ReportsUxContract.test.tsx`
- `apps/wathefni-dashboard/src/App.tsx` — locale, interviews module, reportsError
- `apps/wathefni-dashboard/src/types.ts` — overview / exports keys
- `apps/wathefni-dashboard/src/lib/api.ts` / `query/*` — locale-aware reports fetch

### Ops
- `ops/deploy-reports-correctness.sh`
- `ops/prove-reports-correctness-live.py`

### Live assets
- `ReportsPage-BXxtIv6z.js`
- `dashboard-DkgpeC6v.js`

## Profiler evidence

| Event | When |
|---|---|
| `profiler_commit` · `reports:overview\|breakdowns\|exports` | React.Profiler |
| `reports_page_load` | Page data present |
| `reports_refresh` | Refreshing flag |
| `reports_export` | Download click |

Read live: `window.__WATHEFNI_DASHBOARD_PERF__.snapshot()`.

## Migration impact

**None** for lifecycle predicates. API additive: `overview`, `partial`, `error`, `exports.followup_delivery_history_rows`, `metric_version=reports-contract-v2`. Legacy `summary` keys retained with corrected meanings. Funnel/hiring-speed from old `reports_v1` GET payload no longer returned on `/reports` (exports unchanged).

## Rollback

```bash
/opt/wathefni/backups/production-pre-reports-correctness-20260730T210638Z/ROLLBACK.sh
```

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| Unit `test_reports_metrics_contract` | **PASS** 5/5 |
| Vitest `ReportsUxContract` | **PASS** 4/4 |
| Live pipeline / debt / export parity / roles / interviews | **PASS** |
| Live asset markers (EN/AR/Profiler) | **PASS** |
| Health | **PASS** `200` |
| **Overall** | **PASS** |

## Preserved

- Overview → Breakdowns → Exports structure  
- Cream/ink visual direction  
- Privacy denylist  
- `report.export` entitlement  
- Delivery failure history as separate historical export  
- Locked peer contracts (jobs / candidates stage / assessments attempt / interviews queue / overview action counts)
