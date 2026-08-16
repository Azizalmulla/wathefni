# Probation Surface Wave

**Status:** FROZEN — `PROBATION_SURFACES_FULL_PASS`  
**Evidence:** `ops/evidence/probation-surfaces-20260811T184908Z`  
**Freeze:** `ops/PROBATION_SURFACE_WAVE_FREEZE.md`  
**Backend freeze:** `ops/PROBATION_WAVE1_BACKEND_FREEZE.md` (authority unchanged)

**Thin HTTP:** `wathefni-orchestrator/probation_http.py` + `probation_surfaces.py`  
**HR Web:** `apps/wathefni-dashboard/src/posthire/ProbationWorkspace.tsx`  
**HR Mobile:** `apps/wathefni-employee-mobile/src/hr/features/probation/*`  
**Employee App:** `apps/wathefni-employee-mobile/app/probation.tsx`  
**Qualify:** `ops/qualify-probation-surfaces-staging.sh`

## Surfaces

| Surface | Scope |
|---|---|
| HR Web | Queue (Active / Review Due / Confirmed / Extended / Failed), detail, 30/60/90, confirm/extend/fail, recommend, audit |
| HR Mobile | Needs Attention / Reviews Due / Upcoming + detail recommend; decide only with `probation.decide` |
| Employee App | Period/end, milestones, owned actions, outcome — confidential notes stripped |
| Manager | Scoped by `manager_user_id`; recommendation ≠ final HR authority |
| Assistant | Explain status + deep links (`/dashboard/assistant/probation/{id}`) |

## Policy

Manager recommendation is recorded and moves case to `under_review`; it is **not** final unless company approval policy explicitly grants decide authority.
