# Payroll Wave 2A-C — External Ops Workflow Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE2AC_GO`  
**Evidence:** `ops/evidence/payroll-wave2acb-prod-canary-20260803T111959Z/`  
**Freeze:** **GO** for Wave 2A-C external payroll operations workflow (synthetic-only production posture)

## Frozen posture

- External payroll ops UI + APIs wrap frozen Wave 2A adapter
- `money_authority=external`, `payment_processing=disabled`, `vendor_claimed=false`
- Imported results never silently become Wathefni payment authority
- Production flags: `WATHEFNI_PAYROLL_WAVE2A=1`, `SYNTHETIC_ONLY=1`, markers include `PYW2ACB`/`PYW1` · phones `965540*`/`965539*`
- Wave 1 + Wave 2A foundation freezes remain intact
- Wave 2B not started

## Proven on production synthetic

- Migrate/ACK `ACK_PRODUCTION_PAYROLL_W2ACB=YES` (ops helpers + routes; Wave 2A DDL unchanged)
- Dashboard dist deployed (`ExternalPayrollWorkspace` EN/AR)
- Canary ×2 (before rollback + after redeploy): **50/50** each, residual **0**
- Readiness, export, upload/replace, quarantine, reconciliation, fingerprint drift, history
- Manager empty-scope + permission/route surface
- Rollback verified; Wave 1 + Wave 2A retained
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Real vendor schema / live SFTP to a named payroll engine
- Bank files, native G2N, PIFSS, WPS, EOS, journals, XBRL
- Wave 2B native payroll calculations
- Real-employee compensation mutation / money authority in Wathefni

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave2acb-*`  
(Restores Wave 2A-C-B code/UI; Wave 1 + Wave 2A drop-in posture retained.)
