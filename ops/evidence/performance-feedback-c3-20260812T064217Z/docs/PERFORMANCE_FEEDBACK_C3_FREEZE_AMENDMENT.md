# PERFORMANCE_FEEDBACK_C3_FREEZE_AMENDMENT

**Slice:** Wave 4 C3 — Check-ins + Competencies + Durable Development  
**Stamp:** `PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS`  
**Status:** QUALIFIED / FROZEN after staging prove — stop for owner review before C4  
**Module:** `wathefni-orchestrator/performance_feedback_c3.py`  
**Flags:** `WATHEFNI_PERFORMANCE_FEEDBACK_C3` + `WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES` (empty = nobody)  
**Shared kill:** `WATHEFNI_PERFORMANCE_KILL`

## Frozen authority

C3 owns:

1. Canonical `check_in` records (employee↔manager; scheduled/ad-hoc) with commitments, optional Objective/KR/KPI links, visibility/sensitive notes, immutable-after-complete + audited amendment  
2. Versioned company competency library (`perf_c3_*`) independent of pre-hire Assessment and of C2 cycle snapshot stubs  
3. Explicit Assessment→Performance mapping contract (no silent reuse)  
4. Self / manager / other competency assessment layers (never silently → overall rating)  
5. Durable `development_plan` / `development_action` with provenance (`review` / `check_in` / `competency_gap` / `manual`)  
6. Optional `hr_tasks` with `action_is_sot` completion contract  

## Explicit non-goals (do not reopen into C3)

- L&D courses/certifications/programs  
- Talent potential / HiPo / 9-box / succession / rankings  
- Auto-mutation of goal progress or review ratings from check-in text  
- Reopening C1 Goals or C2 Reviews for safe debt  

## Next

C3 frozen after qualify. **Stop for owner review before C4.** Do not reopen C1–C3 for safe debt.
