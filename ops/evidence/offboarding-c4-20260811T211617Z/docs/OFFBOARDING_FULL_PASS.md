# OFFBOARDING_FULL_PASS

**Status:** QUALIFIED 2026-08-12 — awaiting owner acceptance; **stop before C5**  
**Date:** 2026-08-12  
**Evidence:** `ops/evidence/offboarding-c4-20260811T211617Z`  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C3 `RESIGNATION_TERMINATION_FULL_PASS` ACCEPTED / frozen  
**Freeze amendment:** `ops/OFFBOARDING_C4_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-offboarding-c4-staging.sh`  
**Module:** `wathefni-orchestrator/offboarding_c4.py`  
**Commercial key:** `offboarding` (clearance = sub-workflow)

## Proven (63/63 staging, synthetic)

1. Exit intent `ready_for_offboarding` → one offboarding case; duplicate handoff idempotent
2. Setup template required/optional items; dependency block/unblock
3. Manager/HR/department/IT scoped completion; RBAC deny wrong owner
4. Reject/return → blocked; cannot cosmetic ready/complete
5. Authorized waiver + reason; unauthorized waiver denied
6. Handover + asset clearance reference (not full AM product)
7. Manual IT confirmation without IdP; optional IdP request≠revoked until ack
8. All required satisfied → `ready_to_close` → completed
9. No false settlement/paid/exit-interview/employment-left
10. Stale protection; EN/AR; module-off history intact; real termination canary OFF

## Posture

- Synthetic qualification only  
- Global `WATHEFNI_OFFBOARDING_C4` remains OFF in systemd  
- `WATHEFNI_REAL_TERMINATION_CANARY` remains OFF  
- C4 completion ≠ exit close employment left (C5+)  
- Assistant mutations OUT  

## Stop

**Do not start C5 Exit Close / settlement ack/waiver / exit interview / rehire** until owner accepts this stamp.
