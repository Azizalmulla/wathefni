# Employee Payslips P0.1 — Official PDF Qualification

**Verdict: PASS**  
**Stamp:** `20260807T205203Z`  
**Smoke:** 52 PASS / 0 FAIL

## Authority (frozen from P0)

Employee-visible iff `status=active AND employee_visibility=released`.

## Official PDF eligibility

`source_kind=external_import AND money_authority=external`  
Native `preview_non_authoritative` **never** becomes official PDF.

## Sample PDFs

Under `ops/evidence/employee-payslips-p0_1-20260807T205203Z/pdf/`:

- `unit-sample-en.pdf` / `unit-sample-ar.pdf`
- `employee-*-en.pdf` / `employee-*-ar.pdf` (released canary downloads)

## Prove matrix

| Case | Result |
|---|---|
| PDF from one immutable payslip version | PASS |
| Unreleased inaccessible | PASS |
| Release → employee PDF download | PASS |
| Peer isolation | PASS |
| Replace → new PDF after re-release | PASS |
| Revoke/unrelease remove access | PASS |
| EN/AR render | PASS |
| Amounts match API | PASS |
| No invented payment_date | PASS |
| Native refuses official PDF | PASS |

## Why native is non-authoritative

Wave 2B native preview intentionally sets `money_authority=preview_non_authoritative` / `authoritative=False`. Wave 3 copies that onto `native_preview` payslip documents. This is by design — not a bug to flip for PDF shipping.

## Exact remaining production-authority blocker

1. External slips are **mirrors** (`authoritative_in_wathefni=False`); external system remains money authority  
2. `payment_processing=disabled`; no genuine `payment_date` field  
3. Wave 3 is **synthetic-only** in production  

**Gate:** enable non-synthetic payroll with a real money-authority source before claiming production-authoritative employee payslips. Do **not** mark native preview authoritative merely to pass a PDF check.

## Deploy

- Backend: `payroll_payslip_official_pdf.py` + wave3 v1.2.0 + download returns `application/pdf`
- Mobile OTA: see canary log  
- Rollback: restore prior orchestrator files from backup stamped at deploy time
