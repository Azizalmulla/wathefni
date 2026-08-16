# Payroll Wave 2A-D — External Run Operability Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE2AD_GO`  
**Staging:** `STAGING_PAYROLL_WAVE2AD_GO` · `ops/evidence/payroll-wave2ad-20260803T181542Z/`  
**Production synthetic:** `ops/evidence/payroll-wave2adb-prod-canary-20260803T182513Z/`  
**Freeze Wave 2A-D:** **GO**

## Frozen posture (unchanged money)

- External remains money authority; native non-authoritative
- `payment_processing=disabled`
- No vendor connector; no bank/WPS/PIFSS/EOS/payments/AI
- No attendance/leave/shifts package expansion
- Production remains **SYNTHETIC_ONLY** (`PYW2ADB` markers / `965540*`)

## Proven

### Staging
- Setup status + guided run checklist
- Package contents honesty + CSV guide
- HR/finance wording (input snapshot)
- Export rollback with concurrency token from UI
- Import run pickers (payslips + close)
- Quarantine acknowledge with audit reason (no money admit)
- Timesheets labeled Hours review vs External payroll run
- Wave 2A + 2A-C regressions green; sibling freezes green

### Production synthetic (Wave 2A-D-B)
- Deployed operability workflow + migrate/ACK
- Canaries ×2: **84/0**, residual **0**
- Setup / checklist / package honesty / quarantine ack / rollback concurrency
- EN/AR + mobile UX + dist operability copy
- Rollback proof (Wave 1 + Wave 2A retained) → redeploy → second canary
- Sibling freezes (Employees 360, Onboarding, Attendance, Leave, Shifts) green

## Explicit NO-GO

- Real vendor connection / money authority in Wathefni
- Bank / WPS / PIFSS / EOS / payments / AI
- Attendance / leave / shifts package expansion
- Native G2N / another Payroll or differentiation wave
