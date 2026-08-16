# Probation Surface Wave — FREEZE

**Status:** FROZEN — `PROBATION_SURFACES_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/probation-surfaces-20260811T184908Z`  
**Contract doc:** `ops/PROBATION_SURFACE_WAVE.md`  
**Backend freeze (unchanged):** `ops/PROBATION_WAVE1_BACKEND_FREEZE.md`

## Frozen surface contract

| Artifact | Path |
|---|---|
| Thin HTTP | `wathefni-orchestrator/probation_http.py` |
| Surface helpers | `wathefni-orchestrator/probation_surfaces.py` |
| HR Web | `apps/wathefni-dashboard/src/posthire/ProbationWorkspace.tsx` |
| HR Mobile | `apps/wathefni-employee-mobile/src/hr/features/probation/*` |
| Employee App | `apps/wathefni-employee-mobile/app/probation.tsx` |
| Qualify | `ops/qualify-probation-surfaces-staging.sh` |
| Smokes | `smoke-test-probation-surfaces.py` / `-db.py` |

## Freeze rules

1. Do **not** rewrite Probation SM, milestone transitions, or decide/extend semantics via surfaces.
2. Surfaces remain thin wrappers; queue `list_cases` stays in `probation_surfaces.py` only.
3. Employee App must never expose confidential manager/HR recommendation notes.
4. Manager recommendation is not final HR authority by default.
5. Module-off stays 403 / empty nav across Web / HR Mobile / Employee App / Assistant.
6. EN+AR and LTR+RTL remain required for any surface amendment.

Amendments require a dated note in this file + re-qualify.
