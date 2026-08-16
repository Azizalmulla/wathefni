# Payroll Authority C4 — Freeze Amendment

**Status:** AMENDS `ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` for Wave 2 **C4 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Pass stamp:** `PAYROLL_AUTHORITY_FULL_PASS`  
**Qualify:** `ops/qualify-payroll-authoritative-c4-staging.sh`

## What changes

| Prior freeze | C4 amendment |
|---|---|
| Native results non-authoritative | Company-scoped `payroll.authoritative_finalize` via `payroll_authoritative_c4` after opt-in |
| Synthetic-only money posture forever | **Global** `WATHEFNI_PAYROLL_AUTHORITATIVE_C4` stays **off**; empty `*_COMPANIES` = nobody |
| No Mode A seal claim for entitled canary | Entitled canary seals `money_authority=wathefni` through existing P5 finalize SM |

## What does **not** change

1. Existing Mode A period → snapshot → calc → approve → finalize SM (P2/P3/P5/P6)  
2. `payment_processing=disabled` — **no payment movement, no WPS/bank send**  
3. Payslip broad release remains C5 (internal generate-from-seal may exist; not a C4 rollout)  
4. PIFSS/EOS ownership remains counsel-gated honesty (no invented rates)  
5. E360 stays inputs-only  
6. Corrections after finalize = audited replace / next period — never silent edits  
7. Attendance / Leave / Shifts remain optional feeds via contracts  
8. Assistant mutations remain OUT of Wave 2 MVP  

## Enablement sequence (canary only)

1. Process-scoped `WATHEFNI_PAYROLL_AUTHORITATIVE_C4=on`  
2. `WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES=<canary>`  
3. `enable_company_authoritative_finalize` (+ optional feed contracts)  
4. P6 allowlist employees as needed  
5. Run Mode A finalize through `authoritative_finalize`  

## Rollback

```text
WATHEFNI_PAYROLL_AUTHORITATIVE_C4=off
Clear WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES
disable_company_authoritative_finalize(canary) → preview_only
Sealed snapshots remain immutable
```

## Next

Stop for owner review. **Do not start C5 Payslips + Payment Files** until `PAYROLL_AUTHORITY_FULL_PASS` is accepted.
