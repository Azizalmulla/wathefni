# SETTLEMENT_OT_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-11 — C6 remains **FROZEN** (do not reopen for C7+)  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/payroll-settlement-ot-c6-20260811T201244Z`  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Freeze amendment:** `ops/SETTLEMENT_OT_C6_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-payroll-settlement-ot-c6-staging.sh`  
**Module:** `wathefni-orchestrator/payroll_settlement_ot_c6.py`

## Proven (synthetic canary)

1. Settlement from valid lifecycle inputs (`handed_to_payroll` packet)  
2. Finalize seals result (immutable; payslip/payment inputs emitted)  
3. Stale approval + duplicate finalize protection  
4. Adjustment path after finalization (prior superseded; no silent mutation)  
5. Settlement payslip/payment inputs present  
6. No false paid state (`claims_paid=false`; finalized ≠ paid)  
7. OT approve / reject / cancel  
8. OT→Payroll optional feed (default OFF; export when enabled; money not calculated in OT)  
9. Payroll without OT remains green  
10. Tenant isolation / RBAC-SoD / manager scope  
11. Module-off + empty allowlist + kill switch  
12. EN/AR contracts (settlement + OT labels)  
13. No invented EOS/PIFSS formulas; encashment quantity-only until Payroll money  
14. Independent of Attendance / Leave / Shifts modules  

## Posture

- Canary company-scoped only — **no global unlock**  
- Production systemd: `WATHEFNI_PAYROLL_SETTLEMENT_C6` remains **OFF**  
- `ot_to_payroll_enabled` default **OFF**  
- Settlement ≠ clearance; Wave 3 owns exit-close coupling  
- C5 remains frozen (`PAYSLIP_PAYMENT_FULL_PASS` ACCEPTED)  

## Stop

**Do not start C7 Wave 2 Product Acceptance** until owner accepts this stamp.
