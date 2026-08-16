# EMPLOYMENT_CHANGE_FULL_PASS

**Status:** QUALIFIED 2026-08-11 — awaiting owner acceptance; **stop before C2**  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/employment-change-c1-20260811T205148Z`  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Freeze amendment:** `ops/EMPLOYMENT_CHANGE_C1_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-employment-change-c1-staging.sh`  
**Module:** `wathefni-orchestrator/employment_change_c1.py`

## Proven (42/42 staging)

1. Global `WATHEFNI_EMPLOYMENT_CHANGE_C1` off + empty allowlist deny (fail closed)
2. Company enable → transfer case: draft → submit → SoD blocks self-approve → stale row_version fails → approve → apply mutates department/position + append-only history
3. Reject path; cancel draft
4. Promotion apply
5. Secondment requires end date; apply → active; return restores home department
6. Salary change without payroll link preserves payroll independence
7. Salary change with OPTIONAL `link_comp_contracts` creates compensation contract draft
8. Assistant mutations OUT; Offboarding / Attendance Truth not required
9. Disable company entitlement preserves history; module-off after disable
10. Rollback guidance: history intact

## Posture

- Canary only — **no broad enable**
- Production systemd: global employment-change remains **OFF**
- Payroll / Offboarding optional; salary→payroll link default OFF
- Assistant mutations: **OUT** of Wave 3 MVP
- Real non-synthetic termination remains **dark** (later slices)

## Stop

**Do not start C2 ESS Letters + Dependents** until owner accepts this stamp.
