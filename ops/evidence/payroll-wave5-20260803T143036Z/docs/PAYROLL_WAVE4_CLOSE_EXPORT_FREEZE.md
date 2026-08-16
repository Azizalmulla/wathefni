# Payroll Wave 4 — Close & Finance Export Foundation Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE4_GO`  
**Evidence:** `ops/evidence/payroll-wave4b-prod-canary-20260803T135930Z/`  
**Staging evidence:** `ops/evidence/payroll-wave4-20260803T134820Z/`  
**Freeze:** **GO** for Wave 4 close + finance export foundation (synthetic-only production posture)

## Frozen posture

- Controlled **review → approve → close** with immutable closed-run snapshot + totals
- Generic **journal drafts** with configurable account/cost-centre mappings (no ERP posting)
- Generic **bank-export contract validation only** (no real bank format, connection, or WPS/AS’HAL)
- Export history, approvals, fingerprints, and reconciliation status
- `payment_processing=disabled`; no PIFSS, EOS, payments, or AI
- Native results remain **preview/non-authoritative**; external payroll remains **money authority**
- Production flags: `WATHEFNI_PAYROLL_WAVE4=1`, `SYNTHETIC_ONLY=1`, markers `PYW4`/`PYW1`/`W4B`, phones `965541*`/`965540*`/`965539*`
- Additive tables only (`payroll_close_*`, `payroll_account_mappings`, `payroll_journal_*`, `payroll_bank_export_*`, `payroll_finance_exports`)
- Wave 1 / 2A / 2B / 3 DDL and frozen flows untouched

## Proven on production synthetic

- Migrate/ACK `ACK_PRODUCTION_PAYROLL_W4B=YES`
- Canary ×2 (before rollback + after redeploy): **92/92** each, residual **0**
- SOD for approve, close, and export (permission conflict + same-actor bans)
- Closed runs immutable; re-close blocked
- Controlled reopen with dual approval (distinct second actor)
- Balanced journal validation; invalid mappings fail closed
- Bank-export contract validation only; idempotent exports
- Fingerprint drift detection + quarantine path
- EN/AR + mobile UX smoke (local + prod)
- Rollback verified; Wave 1 + 2A + 2B + 3 retained; Wave 4 drop-in cleared then redeployed
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)
- Wave 1 / 2A / 2B / 3 freezes retained

## Explicit NO-GO (outside this freeze)

- Real bank format integrations or bank connections
- WPS / AS’HAL submission
- PIFSS or EOS calculations
- ERP journal posting or payment execution
- Treating native results as payment authority
- Changes to frozen Wave 1/2A/2B/3 contracts or flows
- Next payroll wave (not started)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave4b-*`  
(Removes Wave 4 drop-in + restores pre-4-B `app.py`/modules; Wave 1 + 2A + 2B + 3 drop-ins retained. Close/export schema tables remain additive.)
