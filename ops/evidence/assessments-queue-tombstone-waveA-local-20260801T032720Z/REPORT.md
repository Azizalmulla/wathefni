# Wave A — Assessments orphan queue route tombstone (local)

**Verdict: PASS**  
**Stamp:** `20260801T032720Z`  
**Deployment:** **NO — local only (awaiting approval)**  
**Scope:** Orphan `GET /dashboard/prehire/assessments/queue` only — Assessments cohort UI/API/permissions/contracts unchanged

## Root cause

There was **no product route** for `/dashboard/prehire/assessments/queue`.

FastAPI matched `queue` to `GET /dashboard/prehire/assessments/{attempt_id}`. That collision produced an opaque **HTTP 500** (`text/plain: Internal Server Error`) in production probes, instead of a controlled not-found response.

The live Assessments send cohort never used this path. It uses:

`GET /dashboard/prehire/applications?overview_cohort=<cohort>&assessment_cohort=<cohort>`

via `fetchAssessmentQueuePage` in `apps/wathefni-dashboard/src/lib/query/fetchers.ts`.

## Exact fix

Added an explicit tombstone **before** `{attempt_id}` in `wathefni-orchestrator/app.py`:

- `GET /dashboard/prehire/assessments/queue`
- Auth still via `assessments_dashboard_context`
- Returns **410 Gone** JSON:

```json
{
  "detail": {
    "error": "assessment_queue_route_removed",
    "message": "…Use GET /dashboard/prehire/applications with overview_cohort and assessment_cohort…"
  }
}
```

Never 500. No change to applications cohort logic, attempt detail, config, UI, or permissions.

## Caller audit

See `CALLER_AUDIT.md`.

- Dashboard `src/**/*.ts(x)`: **0** `assessments/queue` callers  
- Only non-product reference: prior E2E probe script  

## Tests

| Suite | Result |
|---|---|
| `smoke-test-assessments-queue-tombstone.py` | **9/9 PASS** |
| `smoke-test-assessment-cohorts-unit.py` | **PASS** |
| Local AS02 re-gate + happy-path route presence | **8/8 PASS** (`verify/as02-and-happy-path.json`) |

AS02 after fix: orphan route **410** + error `assessment_queue_route_removed`; UI applications cohort contract unchanged in source.

## Evidence path

`ops/evidence/assessments-queue-tombstone-waveA-local-20260801T032720Z/`

## Final

**PASS (local).** Do not deploy until approved.
