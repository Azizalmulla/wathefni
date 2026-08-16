# Payroll Wave 3 — Payslip Documents Freeze (Staging)

**Gate:** `STAGING_PAYROLL_WAVE3_PAYSLIP_GO`  
**Evidence:** `ops/evidence/payroll-wave3-20260803T132313Z/`  
**Freeze:** **GO** for staging payslip documents only

## Production synthetic

**NO-GO** — requires a separate Wave 3-B production synthetic path (not started).

## Frozen posture

- Payslip **documents only** — `payslips_as_money=false`
- Native payslips: **non-authoritative** preview (`money_authority=preview_non_authoritative`)
- External payslips: mirror of Wave 2A imports; **external remains money authority**
- `payment_processing=disabled`; no bank/WPS, PIFSS, EOS, journals, payments, or AI
- Additive tables only (`payroll_payslip_*`); Wave 1 / 2A / 2B DDL and flows untouched
- Replace/revoke retain history (never hard-delete)

## Proven on staging

- Native preview generation + EN/AR download
- External import payslip generation with external authority labels
- Manager scope denial + SYNTHETIC_ONLY real-employee refusal
- Idempotent generation; replace (v2) + revoke with history retained
- EN/AR + mobile UX smoke
- Wave 2A + Wave 2B regression green; sibling freezes green

## Explicit NO-GO (outside this freeze)

- Production synthetic / production deploy of Wave 3
- Bank files, WPS, remittance, payment execution
- Treating native payslips as payment authority
- Changes to frozen Wave 1/2A/2B contracts or external ops flows

## Rollback

Remove staging drop-in `zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf` and restart orchestrator-staging; payslip tables may remain (non-money documents). Wave 1 + 2A + 2B retained.
