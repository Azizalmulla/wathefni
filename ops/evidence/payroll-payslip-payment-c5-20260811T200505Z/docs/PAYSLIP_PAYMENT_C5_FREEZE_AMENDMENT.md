# Payslips + Payment Files C5 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-11) — AMENDS payroll controlled rollout for Wave 2 **C5 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Pass stamp:** `PAYSLIP_PAYMENT_FULL_PASS`  
**Qualify:** `ops/qualify-payroll-payslip-payment-c5-staging.sh`  
**Module:** `wathefni-orchestrator/payroll_payslip_payment_c5.py`

## What changes

| Prior freeze | C5 amendment |
|---|---|
| Payslip release not company-scoped C5 gate | Company-scoped runtime `WATHEFNI_PAYROLL_PAYMENT_C5` + allowlist; generate from sealed only; release → employee visible; void = audited revoke |
| No payment-file SM | `draft → generated → acknowledged \| failed \| cancelled` with provenance fingerprint to sealed payroll |
| Wave1 `payment_processing` CHECK disabled forever as money rails | **Unchanged** — C5 entitlement lives in `payroll_c5_company_settings.payment_processing_enabled` (default OFF) |

## Semantic contract (locked)

1. **Acknowledged** = Wathefni recorded configured operational acknowledgement only  
2. Acknowledged does **not** mean employees were paid or bank settlement succeeded  
3. Format pack `kw_wps_stub_v1` is synthetic (`real_bank_format=false`, `real_wps_format=false`) — no invented WPS/bank requirements  
4. Released payslip is immutable relative to its sealed payroll snapshot; correction = void + new sealed result / proper replace — never silent PDF regeneration  
5. Kill switch `WATHEFNI_PAYROLL_PAYMENT_KILL=on` immediately blocks new payment-file generation  

## What does **not** change

1. C4 authoritative finalize SM and sealed immutability  
2. Wave1 `payment_processing='disabled'` money-rails posture  
3. No fund transfer, bank initiation, or settlement claim  
4. No auto-mark payroll paid from file generation alone  
5. Attendance / Leave / Shifts remain optional (payroll works without them)  
6. Assistant mutations remain OUT of Wave 2 MVP  
7. C6 Final Settlement + OT not started  

## Enablement sequence (canary only)

1. Process-scoped `WATHEFNI_PAYROLL_PAYMENT_C5=on`  
2. `WATHEFNI_PAYROLL_PAYMENT_COMPANIES=<canary>`  
3. C4 allowlist + sealed finalize for canary (as needed)  
4. Payslip generate/release via C5 wrappers  
5. `enable_company_payment_processing` before any payment-file draft/generate  
6. Keep `WATHEFNI_PAYROLL_PAYMENT_KILL` off only while actively generating  

## Rollback

```text
WATHEFNI_PAYROLL_PAYMENT_KILL=on   # immediate block
WATHEFNI_PAYROLL_PAYMENT_C5=off
Clear WATHEFNI_PAYROLL_PAYMENT_COMPANIES
disable_company_payment_processing(canary)
Released/voided payslips and payment-file rows retained for audit
```

## Next

C5 amendment is frozen. **Stop before C6 Final Settlement + OT** until owner accepts `PAYSLIP_PAYMENT_FULL_PASS`.
