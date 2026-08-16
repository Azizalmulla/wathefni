# Payroll Wave 2A — External Adapter Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE2A_GO`  
**Evidence:** `ops/evidence/payroll-wave2ab-prod-canary-20260803T044431Z/`  
**Freeze:** **GO** for Wave 2A external adapter foundation (synthetic-only production posture)

## Frozen posture

- `money_authority=external` (Wathefni is not money authority)
- `payment_processing=disabled`
- `vendor_claimed=false` — synthetic generic CSV/SFTP only
- Production flags: `WATHEFNI_PAYROLL_WAVE2A=1`, `SYNTHETIC_ONLY=1`, markers `PYW2AB`/`PYW1` · phones `965540*`/`965539*`
- Wave 1 foundation freeze remains intact

## Proven on production synthetic

- Migrate + `ACK_PRODUCTION_PAYROLL_W2AB=YES`
- Clean export/import, idempotent replay, unmatched + malformed quarantine
- Fingerprint drift detection, reconciliation differences, export rollback
- Residual synthetic cleanup = 0
- Rollback of Wave 2A-B flags verified (Wave 1 retained); redeploy canary green
- Sibling freezes green

## Explicit NO-GO (outside this freeze)

- Real vendor schema / live SFTP to a named payroll engine
- Bank files, native G2N, PIFSS, WPS, EOS, journals, XBRL
- Wave 2B native payroll calculations
- Real-employee compensation mutation / money authority in Wathefni

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave2ab-*`  
(Removes Wave 2A-B drop-in only; Wave 1 drop-in retained.)
