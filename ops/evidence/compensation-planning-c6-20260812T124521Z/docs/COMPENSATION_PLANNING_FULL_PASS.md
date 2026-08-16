# COMPENSATION_PLANNING_FULL_PASS

**Status:** QUALIFIED / frozen for owner review — **stop before C7 Workforce Planning**  
**Stamp:** `COMPENSATION_PLANNING_FULL_PASS`  
**Evidence:** `ops/evidence/compensation-planning-c6-20260812T124521Z`  
**Charter:** `WAVE6_HCM_EXPANSION_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-compensation-planning-c6-staging.sh`  
**Freeze amendment:** `ops/COMPENSATION_PLANNING_C6_FREEZE_AMENDMENT.md`  
**Modules:**  
- `wathefni-orchestrator/compensation_planning_c6.py`  
- `wathefni-orchestrator/setup_console_wave6_policies.py` (comp_planning module)  
- `apps/wathefni-dashboard/src/setup-console/Wave6CompensationPlanningPoliciesCard.tsx`  
- Smoke: `wathefni-orchestrator/smoke-test-compensation-planning-c6.py`  

## Proved (charter C6)

- Canonical Compensation Planning authority: cycle → eligibility snapshot → budgets → JA-linked bands → recommendations → calibration → approvals → finalized plan → explicit apply/handoff  
- JA is HARD grade/job source; no duplicate grade hierarchy inside Comp  
- Salary bands versioned; launched cycle snapshot immutable to later band edits  
- Eligibility explicit/versioned; eligible ≠ guaranteed increase  
- Budget allocated / recommended / approved distinct; overrun hard-block / warn / exception-approval  
- Recommendation types distinct (merit / promotion / market / bonus / other)  
- Performance OPTIONAL; rating ≠ automatic increase  
- Talent OPTIONAL; HiPo/potential ≠ automatic pay  
- Manager recommendation history preserved; calibration ≠ original  
- SOD: recommend ≠ approve same actor  
- Finalized ≠ applied; explicit change package; Comp does not mutate employment/payroll  
- Payroll OPTIONAL; external payroll path works; approved bonus ≠ paid  
- Promotion plan may reference target JA grade; does not mutate role  
- Employee cannot see draft recommendations  
- KWD/currency explicit; Wave 5 typed facts; Assistant read-only  
- Setup ownership; tenant isolation; EN/AR; module-off retains history  
- C1–C5 Wave 6 + Waves 1–5 unit freezes green  

## Stop

Freeze C6 and **STOP before C7 Workforce Planning** until owner accepts.  
Do not reopen C1–C5 for Comp convenience. Global Comp Planning remains OFF / company-gated.
