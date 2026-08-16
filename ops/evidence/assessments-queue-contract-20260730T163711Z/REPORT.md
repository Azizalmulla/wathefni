# Assessments Queue Contract — Production Report

**Stamp:** `20260730T163711Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Tenant proof:** `WATHEFNI`

## Summary

Implemented the approved Assessments three-authority consistency contract. Cohort badges use detail/assignment visibility and `application_count` only (no attempt `status_counts` fallback). Attempts history stays every-attempt. Needs review and Reports use shared backend predicates with pagination. Cancelled attempts are Attempts-only. Ranking untouched; no UI redesign.

## Contract

| Axis | Unit | Owns |
|---|---|---|
| `assessments.cohort.*` | applications (latest attempt) | Send operational queues |
| `assessments.attempt.*` | every historical attempt | Attempts totals / status breakdowns |
| `assessments.review.*` | completed attempts | Needs review + Reports |

## Live proof (WATHEFNI)

| Check | Result |
|---|---|
| Resend cohort apps | **2** |
| Expired attempt history | **3** |
| Cohort badge ≡ opened list (company-wide) | **PASS** (all operational keys) |
| Owner / manager unscoped badge ≡ list | **PASS** |
| Recruiter empty-assignment badge ≡ list (both 0) | **PASS** |
| Cancelled → no Send cohort | **PASS** (0 cancelled live; presentation/SQL locked) |
| In progress / Completed | `application_count` only; completed unit=`applications` |
| Needs review count ≡ opened filter (incl. page stability) | **PASS** (0≡0) |
| Reports `report_ready_count` ≡ `status=completed` list total | **PASS** (1≡1) |
| Delivery failed aliases in predicate | **PASS** |

Evidence: `live-proof.json`.

## Files

### Backend
- `wathefni-orchestrator/assessments_queue_contract.py` (**new**)
- `wathefni-orchestrator/assessment_cohorts.py` — detail `visibility_sql`; completed uses applications unit
- `wathefni-orchestrator/assessment_presentation.py` — cancelled → no cohort / Cancelled label
- `wathefni-orchestrator/prehire_overview.py` — thread visibility into assessment cohorts
- `wathefni-orchestrator/app.py` — `dashboard_assessments_payload` + assessments route (detail scope for list/summary/cohorts; full `needs_review` / `report_ready` totals; overview visibility)
- `wathefni-orchestrator/test_assessments_queue_contract.py` (**new**)

### Dashboard
- `apps/wathefni-dashboard/src/lib/assessmentsQueueContract.ts` (**new**)
- `apps/wathefni-dashboard/src/lib/assessmentsQueueContract.test.ts` (**new**)
- `apps/wathefni-dashboard/src/pages/AssessmentsPage.tsx` — no status_counts fallback; backend Needs review / Reports pagination
- `apps/wathefni-dashboard/src/pages/shared/format.ts` — `assessmentQueue` presentation-only
- `apps/wathefni-dashboard/src/pages/shared/primitives.tsx` — optional metric click for Needs review
- `apps/wathefni-dashboard/src/App.tsx` / query hooks / types / api — scoped cohorts + filter wiring

### Live assets
- `AssessmentsPage-79dB_Emb.js`
- `dashboard-B3owVp2X.js`

## Migration impact

**None.** Runtime count/scope predicates only. No schema change.

## Rollback

```bash
/opt/wathefni/backups/production-pre-assessments-queue-contract-20260730T163711Z/ROLLBACK.sh
```

Restores prior orchestrator modules + `app.py` + dashboard dist; removes `assessments_queue_contract.py` if it was new.

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| Unit contract suite (prod) | **PASS** 8/8 |
| Local vitest `assessmentsQueueContract` | **PASS** 2/2 |
| Live Resend 2 / expired 3 | **PASS** |
| Live badge ≡ opened list | **PASS** |
| Live Needs review / Reports totals | **PASS** |
| Health | **PASS** `200` |

## Out of scope (unchanged)

Ranking, visual redesign, Jobs/Candidates contracts (already shipped).
