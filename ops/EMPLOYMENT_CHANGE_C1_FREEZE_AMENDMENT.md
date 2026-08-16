# Employment Change C1 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-11) — AMENDS E360 / org change posture for Wave 3 **C1 only**  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Pass stamp:** `EMPLOYMENT_CHANGE_FULL_PASS`  
**Qualify:** `ops/qualify-employment-change-c1-staging.sh`  
**Module:** `wathefni-orchestrator/employment_change_c1.py`

## What changes

| Prior | C1 amendment |
|---|---|
| Org Wave 4 assignment changes without governed case SM | Company-scoped `employment_change_case` SM: `draft → pending_approval → approved\|rejected\|cancelled → applied` |
| Salary people events loosely coupled | OPTIONAL `link_comp_contracts` → payroll compensation draft; default OFF — payroll independence preserved |
| No append-only employment-change history product | `employment_change_history` append-only; rollback does not purge |

## What does **not** change

1. Wave 1 / Wave 2 freezes  
2. Offboarding module (later slices)  
3. Assistant mutations remain OUT  
4. Real non-synthetic termination remains dark  
5. No invented legal / EOS formulas  
6. Canonical `employees` remains SoT — no duplicate employment ledger  

## Enablement (canary only)

```text
WATHEFNI_EMPLOYMENT_CHANGE_C1=on
WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES=<canary>
enable_company_employment_change(...)
```

## Rollback

```text
WATHEFNI_EMPLOYMENT_CHANGE_C1=off
Clear WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES
disable_company_employment_change(canary)
History rows retained
```

## Next

C1 frozen and owner-accepted 2026-08-11. C2 ESS Letters + Dependents may proceed; do not reopen C1.
