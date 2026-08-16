# Wave A caller audit — `/dashboard/prehire/assessments/queue`

**Stamp:** local Wave A  
**Question:** Is this route used by the current product?

## Product callers

| Surface | Path pattern | Result |
|---|---|---|
| Dashboard TS/TSX (`apps/wathefni-dashboard/src`) | `assessments/queue` | **0 hits** |
| Live Assessments queue fetcher | `fetchAssessmentQueuePage` → `getApplications({ overview_cohort, assessment_cohort })` | **canonical** |
| React Query key | `assessment-queue` (cache key only, not HTTP path) | unrelated |

## Backend routes (before fix)

| Route | Role |
|---|---|
| `GET /dashboard/prehire/assessments` | Attempt list |
| `GET /dashboard/prehire/assessments/config` | Config |
| `GET /dashboard/prehire/assessments/{attempt_id}` | Attempt detail/report — **captured `queue` as attempt_id** |
| `GET /dashboard/prehire/assessments/queue` | **Did not exist** |

## Non-product references

| Location | Role |
|---|---|
| `ops/evidence/prehire-e2e-prod-qual-*/verify/run-api-qual.py` | Qualification probe that discovered the 500 |
| Historical dist bundles / evidence | No live product dependency |

## Verdict

**Unused by current product.** Safe to tombstone with controlled 410 without changing Assessments cohort logic, UI, permissions, or data contracts.
