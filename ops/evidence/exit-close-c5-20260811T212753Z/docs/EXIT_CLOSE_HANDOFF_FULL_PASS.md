# EXIT_CLOSE_HANDOFF_FULL_PASS

**Status:** QUALIFIED 2026-08-12 — awaiting owner acceptance; **stop before C6**  
**Date:** 2026-08-12  
**Evidence:** `ops/evidence/exit-close-c5-20260811T212753Z`  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C4 `OFFBOARDING_FULL_PASS` ACCEPTED / frozen  
**Freeze amendment:** `ops/EXIT_CLOSE_C5_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-exit-close-c5-staging.sh`  
**Module:** `wathefni-orchestrator/exit_close_c5.py`

## Proven (64/64 staging, synthetic)

1. Incomplete offboarding blocks close; completed clearance opens close case  
2. Payroll absent + settlement not required → valid close  
3. Settlement required: finalized without ack blocked; ack → ready → close  
4. Settlement waiver authorized; unauthorized waiver denied; no fake settlement row  
5. Payment status remains distinct from finalize/ack  
6. LWD gate + HR override; optional access-ack semantics  
7. Employment becomes `left` only at successful close (sole authority)  
8. Active workforce domains stop; silent reopen forbidden  
9. Exit interview complete/decline/skip; non-blocking default; confidentiality RBAC  
10. Rehire eligibility + person-key alumni history; duplicate/stale/SoD; rollback preserves closed truth  
11. Real termination canary remains OFF  

## Posture

- Synthetic qualification only — no real user session revoke  
- Global `WATHEFNI_EXIT_CLOSE_C5` remains OFF  
- Real non-synthetic termination remains **dark** until C6 full Wave 3 acceptance  
- Assistant mutations OUT  

## Stop

**Do not start C6 Wave 3 Product Acceptance** until owner accepts this stamp.  
**Do not unlock any real termination yet.**
