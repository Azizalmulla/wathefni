# Payroll Wave 3 — Payslip Documents Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE3_GO`  
**Evidence:** `ops/evidence/payroll-wave3b-prod-canary-20260803T132904Z/`  
**Staging evidence:** `ops/evidence/payroll-wave3-20260803T132313Z/`  
**Freeze:** **GO** for Wave 3 payslip documents (synthetic-only production posture)

## Frozen posture

- Payslip **documents only** — `payslips_as_money=false`
- Native payslips: **non-authoritative** preview (`money_authority=preview_non_authoritative`)
- External payslips: mirror of Wave 2A imports; **external remains money authority**
- `payment_processing=disabled`; no bank/WPS, PIFSS, EOS, journals, payments, or AI
- Production flags: `WATHEFNI_PAYROLL_WAVE3=1`, `SYNTHETIC_ONLY=1`, markers `PYW3`/`PYW1`/`W3B`, phones `965541*`/`965540*`/`965539*`
- Additive tables only (`payroll_payslip_*`); Wave 1 / 2A / 2B DDL and flows untouched
- Replace/revoke retain history (never hard-delete)

## Proven on production synthetic

- Migrate/ACK `ACK_PRODUCTION_PAYROLL_W3B=YES`
- Canary ×2 (before rollback + after redeploy): **51/51** each, residual **0**
- Native preview payslip generation + EN/AR download
- External import payslip generation with external authority labels
- Manager scope denial + `SYNTHETIC_ONLY` real-employee refusal
- Idempotent generation; replace (v2) + revoke with history retained
- EN/AR + mobile UX smoke (local + prod)
- Rollback verified; Wave 1 + 2A + 2B retained; Wave 3 drop-in cleared then redeployed
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)
- Wave 1 / 2A / 2B freezes retained

## Explicit NO-GO (outside this freeze)

- Bank files, WPS, remittance, payment execution
- Treating native payslips as payment authority
- PIFSS, EOS, journals, AI calculations
- Real-employee payroll authority / money movement
- Changes to frozen Wave 1/2A/2B contracts or external ops flows
- Next payroll wave (not started)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave3b-*`  
(Removes Wave 3 drop-in + restores pre-3-B `app.py`/modules; Wave 1 + 2A + 2B drop-ins retained. Payslip schema tables remain additive.)
