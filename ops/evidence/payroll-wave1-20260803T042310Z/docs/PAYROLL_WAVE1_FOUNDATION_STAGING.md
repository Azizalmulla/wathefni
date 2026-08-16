# Payroll Wave 1 — Mode-agnostic foundation (staging GO)

**Evidence:** `ops/evidence/payroll-wave1-20260803T042310Z/`  
**Gate:** `STAGING_PAYROLL_WAVE1_FOUNDATION_GO`  
**Money:** `payment_processing=disabled` (hard)  
**Production synthetic canary:** **NO-GO** until Wave 1B prod migrate/quarantine/qualify path exists  
**Production money:** **NO-GO**

## Delivered

1. Effective-dated compensation contracts + salary components  
2. Modes: `native` | `external` | `parallel_shadow`  
3. Pay periods: open → lock → close → reopen  
4. Real `payroll.approve` + SOD vs `payroll.export`; self-approval bans  
5. Versioned input contract stubs from Employees / Shifts / Attendance / Leave classifications  
6. `PayrollInputExport@1.0.0` + `PayrollResultImport@1.0.0`  
7. May 2026 smoke timesheets soft-quarantined on staging (2 rows)

## Prove (staging)

All required proofs green — see evidence `REPORT.md`. Sibling freezes green.

## Rules held

No G2N, PIFSS, bank/WPS, EOS, payslips-as-money, journals, XBRL, or real money.  
Accepted offers seed draft contracts only. No overlapping approved contracts.  
No mixing legacy Attendance and approved snapshots in one period.  
Leave handoff classifications only; Art. 70 = 6 months.  
Approvals require reason, concurrency, and SOD.
