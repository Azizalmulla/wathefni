# Final Settlement + OT C6 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-11) — AMENDS payroll / attendance controlled rollout for Wave 2 **C6 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Pass stamp:** `SETTLEMENT_OT_FULL_PASS`  
**Qualify:** `ops/qualify-payroll-settlement-ot-c6-staging.sh`  
**Module:** `wathefni-orchestrator/payroll_settlement_ot_c6.py`

## What changes

| Prior freeze | C6 amendment |
|---|---|
| E360 settlement packet inputs-only with no pay path | Company-scoped settlement run SM `inputs_ready → calculated → approved → finalized` consuming lifecycle packet |
| No thin `ot_request` SM | `draft → pending_approval → approved\|rejected\|cancelled → payroll_exported` |
| OT→Payroll feed flag only (C4) | Optional C6 `ot_to_payroll_enabled` (default OFF) exports approved OT as payroll input fact (no OT money outside Payroll) |

## Semantic contract (locked)

1. **Settlement finalized ≠ paid** — payslip/payment *inputs* only; external proof required for paid claims  
2. **Settlement ≠ clearance completion** — Wave 3 owns exit close / clearance coupling  
3. E360 remains **inputs-only**; no payroll math in Employees 360  
4. Leave encashment passes **quantity/entitlement**; Payroll owns money  
5. No invented EOS/PIFSS/legal formulas beyond already approved payroll authority (worksheet refs only)  
6. Correction after finalize = audited adjustment / new settlement — never silent mutation  
7. Payroll works without OT module/input  

## What does **not** change

1. C4 authoritative finalize and C5 payslip/payment file SMs  
2. Wave5 EOS/PIFSS worksheets remain review / counsel-gated honesty  
3. Wave1 `payment_processing='disabled'` money-rails posture  
4. No fund transfer / bank initiation from settlement finalize  
5. Attendance / Leave / Shifts remain optional  
6. C7 Wave 2 Product Acceptance not started  

## Enablement sequence (canary only)

1. Process-scoped `WATHEFNI_PAYROLL_SETTLEMENT_C6=on`  
2. `WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES=<canary>`  
3. `enable_company_settlement_ot` (settlement ± OT auth; `ot_to_payroll_enabled` only when exporting)  
4. Seed/consume `handed_to_payroll` lifecycle packet → calculate → approve → finalize  
5. Keep `WATHEFNI_PAYROLL_SETTLEMENT_KILL` off only while actively finalizing/exporting  

## Rollback

```text
WATHEFNI_PAYROLL_SETTLEMENT_KILL=on
WATHEFNI_PAYROLL_SETTLEMENT_C6=off
Clear WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES
disable_company_settlement_ot(canary)
Finalized settlements remain immutable; OT exports retained for audit
```

## Next

C6 amendment is frozen. **Stop before C7 Wave 2 Product Acceptance** until owner accepts `SETTLEMENT_OT_FULL_PASS`.
