# Payroll Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp:** `20260804T080520Z`  
**Evidence:** `ops/evidence/payroll-page-refinement-wave1-prod-deploy-20260804T080520Z/`  
**Report:** `ops/PAYROLL_PAGE_REFINEMENT_WAVE1.md`  
**Live bundle:** `/var/www/wathefni-dashboard/assets/PostHire-vCLI3hKo.js`

## Frozen surface

- Peer IA is only **Run / Hours / Records** (default **Run** = External payroll workspace)
- Records sub-panels: Payslips / Close & export / PIFSS & EOS
- Delivery strip excluded on Payroll
- Authority honesty collapsed by default on Run + Records workspaces (`data-payroll-honesty-toggle`)
- No duplicate inner Payroll / workspace h2 on first paint
- Hours **Export payroll** is secondary; row Approve remains the timesheet primary
- Quiet refresh affordances on Records; External uses ghost refresh icon

## Frozen non-goals

- Reopening payroll money freezes (Waves 1–5 package / payslip / close / statutory / PIFSS-EOS)
- Enabling payment_processing, remittance, bank filing, or payable invention
- Changing `expected_row_version` / audit-reason / dual-reopen contracts
- Expanding vendor connectors or claiming a named payroll vendor
- Backend payroll calculation / authority changes
- Reopening Shifts / Leave / Attendance / Onboarding freezes

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-payroll-page-refinement-wave1-20260804T080520Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-payroll-page-refinement-wave1-20260804T080520Z
```
