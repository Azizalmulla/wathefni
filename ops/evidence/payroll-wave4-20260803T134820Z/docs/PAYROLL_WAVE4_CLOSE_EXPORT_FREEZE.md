# Payroll Wave 4 — Close & Finance Export Foundation Freeze (Staging)

**Gate:** `STAGING_PAYROLL_WAVE4_CLOSE_EXPORT_GO`  
**Evidence:** `ops/evidence/payroll-wave4-20260803T134820Z/`  
**Freeze:** **GO** for staging close + finance export foundation only

## Production synthetic

**NO-GO** — requires a separate Wave 4-B production synthetic path (not started).

## Frozen posture

- Controlled **review → approve → close** with immutable closed-run snapshot + totals
- Generic **journal drafts** with configurable account/cost-centre mappings (no ERP posting)
- Generic **bank-export contract validation only** (no real bank format, connection, or WPS/AS’HAL)
- Export history, approvals, fingerprints, and reconciliation status
- `payment_processing=disabled`; no PIFSS, EOS, payments, or AI
- Native results remain **preview/non-authoritative**; external payroll remains **money authority**
- Additive tables only (`payroll_close_*`, `payroll_account_mappings`, `payroll_journal_*`, `payroll_bank_export_*`, `payroll_finance_exports`)
- Wave 1 / 2A / 2B / 3 DDL and frozen flows untouched

## Proven on staging

- SOD for approve, close, and export (permission conflict + same-actor bans)
- Closed runs immutable; re-close blocked
- Controlled reopen with dual approval (distinct second actor)
- Balanced journal validation; invalid mappings fail closed
- Bank-export contract validation only; idempotent exports
- Fingerprint drift detection + quarantine path
- Residual synthetic cleanup to zero
- Rollback: Wave 4 drop-in cleared then restored
- Wave 3 / 2B / 2A regressions green; sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Production synthetic / production deploy of Wave 4
- Real bank format integrations or bank connections
- WPS / AS’HAL submission
- PIFSS or EOS calculations
- ERP journal posting or payment execution
- Treating native results as payment authority
- Changes to frozen Wave 1/2A/2B/3 contracts or flows

## Rollback

Remove staging drop-in `zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf` and restart orchestrator-staging; Wave 4 tables may remain (non-money foundation). Wave 1 + 2A + 2B + 3 retained.
