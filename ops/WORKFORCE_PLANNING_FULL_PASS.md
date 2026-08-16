# WORKFORCE_PLANNING_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-12 — C7 remains **FROZEN**  
**Stamp:** `WORKFORCE_PLANNING_FULL_PASS`  
**Evidence:** `ops/evidence/workforce-planning-c7-20260812T125335Z`  
**Charter:** `WAVE6_HCM_EXPANSION_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-workforce-planning-c7-staging.sh`  
**Freeze amendment:** `ops/WORKFORCE_PLANNING_C7_FREEZE_AMENDMENT.md`  
**Modules:**  
- `wathefni-orchestrator/workforce_planning_c7.py`  
- `wathefni-orchestrator/setup_console_wave6_policies.py` (workforce_planning module)  
- `apps/wathefni-dashboard/src/setup-console/Wave6WorkforcePlanningPoliciesCard.tsx`  
- Smoke: `wathefni-orchestrator/smoke-test-workforce-planning-c7.py`  

## Proved (charter C7)

- Canonical WFP authority: baseline → plan → demand → scenario → assumptions → cost → compare → approve → explicit handoff  
- Actual ≠ plan ≠ scenario ≠ approved execution  
- JA HARD; no duplicate planning job catalog  
- Baseline frozen as-of; later workforce changes do not rewrite it  
- Planned demand explicit (growth/replacement/vacancy/reduction); planned position ≠ actual position  
- Planned headcount never enters actual Wave 5 headcount; facts carry `truth_plane`  
- Assumptions explicit/versioned; Wave 5 turnover not silent forecast  
- Projection reproducible (`baseline + additions - reductions`); no AI forecast authority  
- Planned cost labeled estimated ≠ finalized payroll; KWD explicit  
- Comp / Talent / Recruiting OPTIONAL  
- Approved demand → draft requisition only when Recruiting on; else approved_unexecuted/external  
- Handoff idempotent; cancel frees retry; no auto-post/hire  
- Approved scenario immutable; revisions create governed history  
- Actual-vs-plan uses canonical actual input; WFP not actual SoT  
- Employee future-plan leakage blocked; Assistant read-only  
- Setup ownership; tenant isolation; EN/AR; module-off retains history  
- C1–C6 Wave 6 + Waves 1–5 unit freezes green  

## Stop

Owner accepted. C7 remains frozen. C8 Wave 6 Product Acceptance proceeds → `WAVE6_PRODUCT_FULL_PASS`.  
Do not reopen C7 for safe debt. Global Workforce Planning remains OFF / company-gated.
