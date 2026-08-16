# Wave 2 — Product Freeze

**Status:** FROZEN (qualified 2026-08-11)  
**Pass stamp:** `WAVE2_PRODUCT_FULL_PASS`  
**Evidence:** `ops/evidence/wave2-product-acceptance-20260811T203748Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md` (`WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`)  
**Qualify:** `ops/qualify-wave2-product-acceptance-staging.sh`

## Frozen surface

Workforce Truth modular layer (C1–C7):

1. Attendance Truth (ingest → projection → correction apply)  
2. Leave Enforcement (+ N-step / delegation)  
3. Shifts MSS unlock (scoped manager)  
4. Authoritative Payroll (+ optional Attendance/Leave/OT feeds; manual/imported independence)  
5. Payslips release + Payment files (ack ≠ paid)  
6. Final Settlement + OT contract (finalized ≠ paid/clearance)  
7. Product acceptance / modularity matrix / Setup ownership  

## Locked honesty

- Global runtime flags remain **OFF** by default  
- Empty company allowlists = nobody  
- Payment file acknowledged ≠ paid / ≠ bank settlement  
- Settlement finalized ≠ paid / ≠ clearance completion  
- E360 remains inputs-only  
- No invented EOS/PIFSS/WPS requirements  
- Assistant mutations **OUT** of Wave 2 MVP  
- Payroll works without Attendance / Leave / Shifts  

## What does **not** change

1. Wave 1 Hire→Ready freeze (`WAVE1_PRODUCT_FULL_PASS`)  
2. Wave1 `payment_processing='disabled'` money-rails column posture  
3. No fund transfer / bank initiation from Wave 2  
4. No broad enable beyond canary without owner decision  

## Rollback (any slice)

```text
Set corresponding WATHEFNI_*_C# / ingest / enforcement flag = off
Clear company allowlists
Use per-slice kill switches (payment / settlement) for immediate block
Entitlement disable preserves sealed/audited records
```

## Next

Wave 2 is frozen and **owner-accepted**. Safe debt remains documented — do not reopen Wave 2 for it.  
Wave 3 proceeds only via approved charter: `ops/WATHEFNI_HCM_WAVE3_EMPLOYEE_LIFECYCLE_BUILD_CHARTER.md`.
