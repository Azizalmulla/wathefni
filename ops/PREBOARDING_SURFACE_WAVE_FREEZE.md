# Preboarding Surface Wave — FREEZE

**Status:** FROZEN — `PREBOARDING_SURFACES_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/preboarding-surfaces-20260811T182515Z`  
**Contract doc:** `ops/PREBOARDING_SURFACE_WAVE.md`  
**Backend freeze (unchanged):** `ops/PREBOARDING_WAVE1_BACKEND_FREEZE.md`

## Frozen surface contract

| Artifact | Path |
|---|---|
| Thin HTTP | `wathefni-orchestrator/preboarding_http.py` |
| Surface helpers | `wathefni-orchestrator/preboarding_surfaces.py` |
| HR Web | `apps/wathefni-dashboard/src/posthire/PreboardingWorkspace.tsx` |
| HR Mobile | `apps/wathefni-employee-mobile/src/hr/features/preboarding/*` |
| Employee App | `apps/wathefni-employee-mobile/app/preboarding.tsx` |
| Qualify | `ops/qualify-preboarding-surfaces-staging.sh` |
| Smokes | `smoke-test-preboarding-surfaces.py` / `-db.py` |

## Freeze rules

1. Do **not** rewrite Preboarding SM, readiness derivation, or SoD/waive semantics via surfaces.
2. Surfaces remain thin wrappers over `preboarding.py` + `preboarding_surfaces.py`.
3. `access_mode=preboarding_only` for `pending_start` remains mandatory (no normal ESS unlock).
4. Module-off stays 403 / empty nav across Web / HR Mobile / Employee App / Assistant.
5. EN+AR and LTR+RTL remain required for any surface amendment.
6. Hire→Ready bridge may call authority APIs and add post-transition side effects; it must not reopen this surface freeze for cosmetic UX changes.

Amendments require a dated note in this file + re-qualify.
