# HR_INTELLIGENCE_REGISTRY_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-12 — C1 remains **FROZEN** (do not reopen for C2+)  
**Stamp:** `HR_INTELLIGENCE_REGISTRY_FULL_PASS`  
**Evidence:** `ops/evidence/hr-intelligence-registry-c1-20260812T085833Z`  
**Charter:** `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-hr-intelligence-registry-c1-staging.sh`  
**Freeze amendment:** `ops/HR_INTELLIGENCE_REGISTRY_C1_FREEZE_AMENDMENT.md`  
**Module:** `wathefni-orchestrator/hr_intelligence_registry_c1.py`  

## Proved (charter C1)

- Versioned KPI Registry (draft / published / retired / blocked)  
- Definition edits create new versions; prior formula meaning preserved  
- Company publication required before evaluate (no card without published def)  
- Fact spine ingest + idempotent keys + governed correction/supersession  
- Shared evaluator with drill population IDs + pinned definition version  
- Honest statuses: `not_applicable` (zero denom), `suppressed` (cohort &lt; min_n), `unavailable`, `forbidden`, `blocked`  
- `min_cohort_n` default 5, upward-only  
- FTE definition seeded **blocked**; not company-publishable  
- Headcount/future-starters reserved as draft for C2 with binding inclusion policy  
- Assistant refuses invented metrics and universal scores  
- Commercial key `analytics`; internal namespace `hr_intelligence` (no duplicate module)  
- Tenant allowlist / kill switch / disable preserves history  
- EN+AR status labels  

## Not in C1

- Workforce headcount production KPI (C2)  
- Recruiting / time / payroll / performance / talent domain KPIs  
- Intelligence UI / exports surfaces (C6)  

## Stop

Owner accepted. C1 remains frozen. C2 Workforce Intelligence may proceed under charter §17.
