# Payroll Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T080520Z`  
**Evidence:** `ops/evidence/payroll-page-refinement-wave1-prod-deploy-20260804T080520Z/`  
**Freeze:** `ops/PAYROLL_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle (live):** `/var/www/wathefni-dashboard/assets/PostHire-vCLI3hKo.js`  
**Backup:** `/opt/wathefni/backups/production-pre-payroll-page-refinement-wave1-20260804T080520Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** (`PAYROLL_WAVE1_SMOKE_OK`) |
| Freeze Payroll Page Wave 1 | **GO / FROZEN** |
| Money / remittance / payment_processing | **NO-GO** (not touched) |
| Sibling payroll package freezes reopen | **NO-GO** (not done) |

## IA correction

| Before | After |
|---|---|
| 5 peer tabs (external / payslips / close / statutory / timesheets) | **Run / Hours / Records** |
| External default buried among peers | **Run** is default (external money-path surface) |
| Loud honesty chips on first paint | Collapsed behind **Show authority details** |
| Duplicate inner h2 on Run / Records | Removed (shell owns title) |
| Delivery-failure strip on Payroll | Excluded |
| Hours Export competing as primary | Softened to secondary (`data-payroll-hours-export`) |
| Records as separate peer tabs | Payslips / Close & export / PIFSS & EOS under Records |

## Preserved contracts

- External run remains money-authority path (vendor package / mirror only)
- Payment processing stays disabled; no remittance / filing / payable invention
- `expected_row_version`, audit reason, dual reopen unchanged
- Payslip / Close / Statutory mutation APIs unchanged

## Prerequisite

- Shifts Wave 1 composer-org correction frozen (`20260804T075708Z`)
- Unrelated `tsc -b` failures in CloseExport / Payslip / Statutory fixed before this wave

## Smoke

`verify/smoke-prod.out` — `PAYROLL_WAVE1_SMOKE_OK`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-payroll-page-refinement-wave1-20260804T080520Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-payroll-page-refinement-wave1-20260804T080520Z
```
