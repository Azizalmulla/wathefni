# Payroll Wave 2A-D — External Run Operability Freeze (staging)

**Gate:** `STAGING_PAYROLL_WAVE2AD_GO`  
**Evidence:** `ops/evidence/payroll-wave2ad-20260803T181542Z/`  
**Production synthetic:** **NO-GO until separate Wave 2A-D-B qualify**

## Frozen posture (unchanged money)

- External remains money authority; native non-authoritative
- `payment_processing=disabled`
- No vendor connector; no bank/WPS/PIFSS/EOS/payments/AI
- No attendance/leave/shifts package expansion

## Proven (staging)

- Setup status + guided run checklist
- Package contents honesty + CSV guide
- HR/finance wording (input snapshot)
- Export rollback with concurrency token from UI
- Import run pickers (payslips + close)
- Quarantine acknowledge with audit reason (no money admit)
- Timesheets labeled Hours review vs External payroll run
- Wave 2A + 2A-C regressions green; sibling freezes green

## Explicit NO-GO

- Production synthetic without Wave 2A-D-B
- Another Payroll money / differentiation wave
- Vendor connector / package expansion / remittance
