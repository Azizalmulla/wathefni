# LEAVE_ENFORCEMENT_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-11 — C2 remains **FROZEN** (do not reopen for C3+)  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/leave-enforcement-c2-20260811T194020Z`  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Freeze amendment:** `ops/LEAVE_ENFORCEMENT_C2_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-leave-enforcement-c2-staging.sh`

## Proven (Kuwait synthetic canary)

1. Global `WATHEFNI_LEAVE_ENFORCEMENT` off denies enforcement  
2. Empty company allowlist denies (fail closed)  
3. Cannot enable without versioned/reviewed pack attestation  
4. Company-entitled `leave.enforced=true` after attestation  
5. Sufficient annual balance → normal reserve path  
6. Insufficient annual → fail closed when enforced  
7. Unpaid leave skips balance (no invented pool)  
8. Privileged override requires reason + actor + audit  
9. Balance adjustment → append-only ledger + recompute  
10. Cancel/withdraw releases reservation; available restored  
11. Approved cancel reverses consumption correctly  
12. Optional `workflow_approvals` N-step (2+) bind  
13. Self-approval denial (SoD)  
14. Stale concurrent decision → conflict  
15. Delegation in-scope succeeds; expired / revoked / out-of-scope denied  
16. Module-off / WA-off → single-step / observe fallback  
17. Tenant isolation; prior leave freeze regression green  
18. Leave independent of Attendance and Payroll  

## Posture

- Canary only after pack qualification — **no broad enable**  
- Production systemd: global leave enforcement remains **OFF**; empty allowlist = nobody  
- Existing leave SM + frozen UX preserved  
- Append-only ledger remains balance authority  
- Assistant mutations: **OUT** of Wave 2 MVP  

## Stop

Owner accepted. C2 remains frozen. C3 Shifts MSS proceeded under charter §15.
