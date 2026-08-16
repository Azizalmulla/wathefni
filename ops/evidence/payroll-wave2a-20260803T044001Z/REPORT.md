# Payroll Wave 2A — External adapter foundation (staging)

**Stamp:** `20260803T044001Z`  
**Evidence:** `ops/evidence/payroll-wave2a-20260803T044001Z/`  
**Gate:** `STAGING_PAYROLL_WAVE2A_EXTERNAL_ADAPTER_GO`  
**Production synthetic canary:** **NO-GO** until Wave 2A-B prod ACK path exists  
**Money / bank / native G2N:** **NO-GO**  
**Wave 1 contracts:** unchanged  

## What shipped

### New module (does not alter Wave 1 DDL)
- `payroll_external_adapter_wave2a.py` v1.0.0
- `ops/sql/payroll_external_adapter_wave2a_v1.sql`
- Tables: `payroll_adapter_export_runs`, `import_runs`, `import_lines`, `quarantine`, `reconciliations`, `events`

### Synthetic generic CSV/SFTP adapter
- Adapter kind: `synthetic_csv_sftp`
- **Vendor claimed: false** — not Menaitech/ZenHR/Warah/etc.
- Contracts: `PayrollInputExport@1.0.0` → CSV artifact; CSV → `PayrollResultImport@1.0.0` (mirror-only)

### Honesty
```
payment_processing = disabled
money_authority = external
wathefni_money_authority = false
posts_payment = false
bank_files = false
native_gross_to_net = false
```

## Staging proofs (41/0)

| Proof | Result |
|---|---|
| Clean export | PASS |
| Clean import | PASS |
| Duplicate/idempotent export + import replay | PASS |
| Unmatched employee → quarantine | PASS |
| Changed input fingerprint detection | PASS |
| Reconciliation differences | PASS |
| Malformed file quarantine (soft) | PASS |
| Export rollback | PASS |
| Sibling freezes | green |

## Sibling freezes
E360 / Onboarding / Attendance / Leave / Shifts — all green (see `tests/freeze-*.out`).

## Blockers for production synthetic qualification

1. No prod migrate/ACK script (`ACK_PRODUCTION_PAYROLL_W2A`)  
2. No prod-synthetic systemd drop-in / qualify pack  
3. No confirmed real-vendor schema (by design — synthetic only)  
4. Money/bank/WPS remain hard NO-GO  

## GO / NO-GO

| Gate | Verdict |
|---|---|
| Staging Wave 2A external adapter foundation | **GO** |
| Production synthetic Wave 2A | **NO-GO** (next: Wave 2A-B) |
| Real vendor cutover | **NO-GO** |
| Native payroll calculations (Wave 2B) | **NO-GO / not started** |
| Payment execution / bank files | **NO-GO** |
