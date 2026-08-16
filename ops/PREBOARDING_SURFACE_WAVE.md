# Preboarding Surface Wave

**Status:** FROZEN — `PREBOARDING_SURFACES_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/preboarding-surfaces-20260811T182515Z`  
**Freeze:** `ops/PREBOARDING_SURFACE_WAVE_FREEZE.md`

**Backend freeze:** `ops/PREBOARDING_WAVE1_BACKEND_FREEZE.md` (authority unchanged)  

**Thin HTTP:** `wathefni-orchestrator/preboarding_http.py` + `preboarding_surfaces.py`  
**HR Web:** `apps/wathefni-dashboard/src/posthire/PreboardingWorkspace.tsx`  
**HR Mobile:** `apps/wathefni-employee-mobile/src/hr/features/preboarding/*`  
**Employee App:** `apps/wathefni-employee-mobile/app/preboarding.tsx`  
**Qualify:** `ops/qualify-preboarding-surfaces-staging.sh`

## Surfaces

| Surface | Scope |
|---|---|
| HR Web | Full workspace: queue, detail, blockers, waive, joining date, template/settings, audit |
| HR Mobile | Needs Attention / Joining Soon / Ready / Blocked + detail review/waive |
| Employee App | Pre-join owned items only; `access_mode=preboarding_only` while pending_start |
| Manager | Scoped by `manager_user_id` + manager role on queue/detail |
| Assistant | Explain blockers + deep links (`/dashboard/assistant/preboarding/{id}`) |

## Flags

Same as backend freeze — company-scoped dark by default. Surfaces call `preboarding_enabled_for_company`.

## Invariants preserved

- No SM rewrite; ready remains derived
- pending_start ≠ active; ESS modules stay off in preboarding_only mode
- Module-off returns 403 / empty nav
