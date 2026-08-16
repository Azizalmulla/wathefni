# Employee Payslips P0.1 — Official PDF

**Keeps P0 release gate frozen.** Employee-visible iff `status=active AND employee_visibility=released`.

## Official PDF eligibility (strict — Payroll Authority P1)

```
source_kind = external_import
AND money_authority = external
AND authority_snapshot_id → sealed snapshot (money_authority=external)
```

**Never** generate an official PDF from `native_preview` / `preview_non_authoritative`.  
**Never** treat Wave 4 period close alone as money authority.

## Why native is non-authoritative

Wave 2B `calculate_native_preview` and honesty payload set `money_authority=preview_non_authoritative`, `authoritative=False`, `wathefni_money_authority=False`.  
Wave 3 `_labels_for_source(native_preview)` copies that label onto payslip documents. This is intentional — native is a preview engine, not a money authority.

## PDF rules

- Generated from the immutable payslip snapshot (`document_payload` + lines) bound to `payslip_id` / `content_fingerprint`
- Stored privately under workspace `…/files/employee/{key}/payslip_official_pdf/`
- Self-scoped authenticated download only (`GET /app/payslips/{id}/download`) — no public URLs
- `payment_date` omitted when unknown (never invented)
- Replace → new `payslip_id` + new PDF; starts `not_released`
- Released PDF never silently rewrites under a different fingerprint

## Production-authority blocker (exact)

Even after P0.1 PDF capability PASS:

1. Native remains non-authoritative by design (do not fake it for PDF)
2. External slips are **mirrors** (`authoritative_in_wathefni=False`) — external system remains money authority
3. `payment_processing=disabled` globally; no real `payment_date` field
4. Wave 3 is **synthetic-only** in production

**Remaining gate:** enable non-synthetic payroll with a real money-authority source (external system of record, or a future Wathefni-authoritative engine) before claiming production-authoritative employee payslips. Do not flip native preview to authoritative merely to ship a PDF.

## Smoke

`ops/smoke-test-employee-payslips-p0_1.py`
