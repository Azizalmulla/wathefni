# PAYSLIP_PAYMENT_FULL_PASS

**Status:** QUALIFIED 2026-08-11 — C5 **FROZEN** (stop before C6)  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/payroll-payslip-payment-c5-20260811T200505Z`  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Freeze amendment:** `ops/PAYSLIP_PAYMENT_C5_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-payroll-payslip-payment-c5-staging.sh`  
**Module:** `wathefni-orchestrator/payroll_payslip_payment_c5.py`

## Proven (synthetic canary)

1. Unreleased payslip invisible to employee  
2. Release → immediately visible/downloadable  
3. Released artifact tied to finalized (sealed) payroll  
4. Void path audited; voided not employee-visible  
5. Correction via new payslip after void (not silent PDF regen)  
6. Payment generation blocked while C5 `payment_processing` entitlement off  
7. Valid payment-file draft + generation when entitlement enabled  
8. Kill switch immediately blocks new generation  
9. Duplicate/idempotent draft + generation  
10. Stale/concurrent generate protection (`stale_payment_file_decision`)  
11. Tenant isolation + payroll SoD still enforceable  
12. EN/AR payslip fields + official PDF renderer present  
13. Payment-file states: generated → acknowledged | failed | cancelled  
14. Acknowledged = operational ack only (≠ paid / ≠ bank settlement)  
15. Wave1 `payment_processing` column remains `disabled` (no money rails)  
16. Module independence: no Attendance / Leave / Shifts coupling  
17. Global C5 off + empty allowlist fail closed  

## Posture

- Canary company-scoped only — **no global unlock**  
- Production systemd: `WATHEFNI_PAYROLL_PAYMENT_C5` remains **OFF**  
- Format pack `kw_wps_stub_v1` only — `real_bank_format=false`, `real_wps_format=false`  
- No fund transfer, bank initiation, settlement claim, or auto-paid from file gen  
- C4 remains frozen (`PAYROLL_AUTHORITY_FULL_PASS` ACCEPTED)  

## Stop

**Do not start C6 Final Settlement + OT** until owner accepts this stamp.
