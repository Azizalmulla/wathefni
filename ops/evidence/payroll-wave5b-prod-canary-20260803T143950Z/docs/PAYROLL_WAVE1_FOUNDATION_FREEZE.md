# Payroll Wave 1 — Foundation Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE1_FOUNDATION_GO`  
**Evidence:** `ops/evidence/payroll-wave1b-prod-canary-20260803T043108Z/`  
**Freeze:** **GO** for Wave 1 foundation (synthetic-only production posture)

## Frozen posture

- `payment_processing=disabled` (hard CHECK + honesty)
- Production flags: `WATHEFNI_PAYROLL_WAVE1=1`, `SYNTHETIC_ONLY=1`, markers `PYW1` / phones `965539*`
- May 2026 smoke timesheets soft-quarantined (2 rows; never deleted)
- No money authority: no G2N, PIFSS, WPS/bank, EOS, payslips-as-money, journals, XBRL

## Proven on production synthetic

- Schema migrate with ACK
- Contract draft → approve → replace; self-approve + overlap denial
- All three modes; period open → lock → close → reopen
- SOD (`payroll.approve` × `payroll.export`); operator lacks export
- Real-employee mutations refused under SYNTHETIC_ONLY
- Adapter schema stubs; residual synthetic cleanup = 0
- Rollback verified; quarantine survived rollback; redeploy canary green
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Real compensation changes / real-employee payroll authority
- Wave 2 external live adapter or native preview amounts
- Any money movement or bank/WPS file posting

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave1b-*`  
(Drop-in removal restores pre-Wave-1 flags; smoke quarantine intentionally retained.)
