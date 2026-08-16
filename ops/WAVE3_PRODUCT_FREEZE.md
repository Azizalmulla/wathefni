# Wave 3 — Product Freeze

**Status:** FROZEN — owner-accepted 2026-08-12  
**Pass stamp:** `WAVE3_PRODUCT_FULL_PASS` (ACCEPTED)  
**Evidence:** `ops/evidence/wave3-product-acceptance-20260811T213549Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE3_EMPLOYEE_LIFECYCLE_BUILD_CHARTER.md` (`WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`)  
**Qualify:** `ops/qualify-wave3-product-acceptance-staging.sh`

## Frozen surface

Employee Lifecycle modular layer (C1–C6):

1. Employment Changes (promotion / transfer / secondment / salary / manager / position)  
2. ESS Letters + Dependents  
3. Resignation / Termination / EOC + notice-period authority (synthetic)  
4. Offboarding + Clearance sub-workflow (deps / waive / return / IT / optional IdP)  
5. Exit Close + settlement ack/waiver + exit interview + alumni/rehire (sole `employment_status=left` writer)  
6. Product acceptance / modularity matrix / Setup ownership  

## Locked honesty

- Global runtime flags remain **OFF** by default  
- Empty company allowlists = nobody  
- Real termination canary remains **OFF** until explicit C6+ owner unlock  
- Offboarding complete ≠ employment left ≠ paid ≠ settlement finalized  
- Settlement finalized ≠ acknowledged ≠ paid ≠ clearance complete  
- IdP revoke requested ≠ revoked until acknowledgement  
- Exit close is the **sole** writer of employment `left`  
- Assistant mutations **OUT** of Wave 3 MVP (read / explain / deep-link / remind only)  
- Commercial module key for clearance = `offboarding`  

## What does **not** change

1. Wave 1 Hire→Ready freeze (`WAVE1_PRODUCT_FULL_PASS`)  
2. Wave 2 Workforce Truth freeze (`WAVE2_PRODUCT_FULL_PASS`)  
3. No automatic real-termination unlock from C6  
4. No broad enable beyond canary without owner decision  

## Rollback (any slice)

```text
Set corresponding WATHEFNI_*_C# flag = off
Clear company allowlists
WATHEFNI_OFFBOARDING_KILL=on (optional immediate block)
WATHEFNI_REAL_TERMINATION_CANARY must stay off unless owner unlocks C6+
Entitlement disable preserves sealed/audited lifecycle history
```

## Next

Wave 3 is frozen and **owner-accepted**. Safe debt remains documented — do not reopen Wave 3 for it.  
**Real termination remains locked** (`WATHEFNI_REAL_TERMINATION_CANARY=off`) until the owner explicitly names a real canary company/case.  
Wave 4 proceeds only via approved charter: `ops/WATHEFNI_HCM_WAVE4_PERFORMANCE_TALENT_BUILD_CHARTER.md`.
