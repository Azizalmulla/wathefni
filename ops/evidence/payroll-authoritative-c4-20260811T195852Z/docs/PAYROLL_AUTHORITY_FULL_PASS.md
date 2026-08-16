# PAYROLL_AUTHORITY_FULL_PASS

**Status:** QUALIFIED — awaiting owner accept; C4 freeze amendment locked pending accept  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/payroll-authoritative-c4-20260811T195852Z`  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Freeze amendment:** `ops/PAYROLL_AUTHORITY_C4_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-payroll-authoritative-c4-staging.sh`

## Proven (synthetic canary)

1. Global `WATHEFNI_PAYROLL_AUTHORITATIVE_C4` off denies authoritative claim  
2. Empty company allowlist denies (fail closed)  
3. Explicit `payroll.authoritative_finalize` opt-in required  
4. Compensation contract snapshot → earnings / allowances / deductions  
5. Gross-to-net calc remains `preview_non_authoritative` until seal  
6. Approval SoD (creator cannot approve)  
7. Stale/concurrent approval → `stale_finalize_decision`  
8. Authoritative finalize → `money_authority=wathefni` sealed snapshots  
9. Post-finalize immutability (`sealed_snapshot_immutable`)  
10. Duplicate finalize idempotent  
11. Audit before/after on finalize  
12. Period reopen forbidden after authoritative seal  
13. Modularity matrix: manual · imported · attendance · leave · ot · all  
14. Disabled optional feeds do not break payroll  
15. Independent of Attendance / Leave / Shifts modules  
16. Tenant isolation; payment_processing stays disabled  
17. Rollback entitlement off preserves sealed records  

## Posture

- Canary company-scoped only — **no global unlock**  
- Production systemd: `WATHEFNI_PAYROLL_AUTHORITATIVE_C4` remains **OFF**  
- No payment movement / WPS / bank send in C4  
- No invented PIFSS/EOS rates  
- E360 remains inputs-only  
- Synthetic/preview tenants remain explicitly non-authoritative by default  

## Stop

**Do not start C5 Payslips + Payment Files** until owner accepts this stamp.
