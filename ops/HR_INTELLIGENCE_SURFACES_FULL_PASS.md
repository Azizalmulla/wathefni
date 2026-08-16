# HR_INTELLIGENCE_SURFACES_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-12 — C6 remains **FROZEN**  
**Stamp:** `HR_INTELLIGENCE_SURFACES_FULL_PASS`  
**Evidence:** `ops/evidence/hr-intelligence-surfaces-c6-20260812T102727Z`  
**Charter:** `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-hr-intelligence-surfaces-c6-staging.sh`  
**Freeze amendment:** `ops/HR_INTELLIGENCE_SURFACES_C6_FREEZE_AMENDMENT.md`  
**Modules:**  
- `wathefni-orchestrator/hr_intelligence_surfaces_c6.py`  
- `wathefni-orchestrator/hr_intelligence_surfaces_http.py`  
- `apps/wathefni-dashboard/src/posthire/intelligence/IntelligenceWorkspace.tsx`  
- `apps/wathefni-dashboard/src/lib/intelligenceApi.ts`  

**Prior:** C1–C5 ACCEPTED / frozen  

## Proved (charter C6)

- HR Web Intelligence workspace over published Registry KPIs only  
- Ops Attention remains separate (`inbox`)  
- Overview composition by family; module-off KPIs disappear  
- Distinct honesty states (ok / 0 / unavailable / insufficient / not_applicable / suppressed)  
- About-metric, trend, compare, segment, drill via shared C1 evaluator  
- Saved live views re-evaluate; pinned views store definition versions  
- CSV export = same evaluator + metadata; suppression preserved  
- Assistant refuses invented metrics  
- No frontend KPI formulas; no second analytics engine  
- C1–C5 regressions green (C5→C1 qualify scripts)  
- Surfaces fail-closed on domain-handler errors (module-off → unavailable, not crash)  

## Hygiene during C6 (C2)

- `hr_intelligence_workforce_c2._handler_turnover`: when workforce population resolve is not ok, return `unavailable` instead of `KeyError` on missing `headcount` (freeze hygiene; no KPI math change).  

## Stop

Owner accepted. C6 remains frozen. C7 proceeds as product acceptance only → `WAVE5_PRODUCT_FULL_PASS`.
