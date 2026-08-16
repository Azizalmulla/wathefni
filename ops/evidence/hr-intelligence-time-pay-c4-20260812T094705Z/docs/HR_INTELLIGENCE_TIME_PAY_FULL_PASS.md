# HR_INTELLIGENCE_TIME_PAY_FULL_PASS

**Status:** QUALIFIED — awaiting owner acceptance before C5  
**Stamp:** `HR_INTELLIGENCE_TIME_PAY_FULL_PASS`  
**Evidence:** `ops/evidence/hr-intelligence-time-pay-c4-20260812T094705Z`  
**Charter:** `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-hr-intelligence-time-pay-c4-staging.sh`  
**Freeze amendment:** `ops/HR_INTELLIGENCE_TIME_PAY_C4_FREEZE_AMENDMENT.md`  
**Module:** `wathefni-orchestrator/hr_intelligence_time_pay_c4.py`  
**Prior:** C1–C3 ACCEPTED / frozen  

## Prove results

| Gate | Result |
|---|---|
| Local gates | PASS |
| Staging DB prove | **58 passed, 0 failed** |
| C3 regression | **79 passed, 0 failed** |
| C2 regression | **74 passed, 0 failed** |
| C1 regression | **63 passed, 0 failed** |
| Global Wave 5 flags | remain **off** / company-gated |
| Verdict | **`HR_INTELLIGENCE_TIME_PAY_FULL_PASS`** |

## Proved (charter C4)

- Authoritative attendance projections (raw punches ignored)  
- Attendance rate requires expected-work days (no headcount denom)  
- Absenteeism excludes approved leave  
- Distinct lateness employees / occurrences / minutes  
- Leave utilization from ledger; rejected/cancelled excluded; zero entitlement → not_applicable  
- Optional shifts; approved OT ≠ exported ≠ paid  
- Money KPIs HARD on sealed Wathefni finalize; KWD metadata; no FX  
- Settlement finalized ≠ paid; payment ack ≠ paid  
- Payroll independent of Attendance/Leave/Shifts  
- Manager time ≠ payroll leak; monetary cohort suppression  
- Module-off → unavailable; rebuild idempotent; EN/AR  
- C1–C3 regressions  

## Stop

Stop for owner review before C5 (`HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS`).
