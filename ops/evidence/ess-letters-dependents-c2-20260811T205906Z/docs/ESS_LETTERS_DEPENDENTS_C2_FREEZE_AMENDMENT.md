# ESS Letters + Dependents C2 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-11) — AMENDS ESS Wave 5 letter-order posture for Wave 3 **C2 only**  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C1 `EMPLOYMENT_CHANGE_FULL_PASS` ACCEPTED / frozen  
**Pass stamp:** `ESS_LETTERS_DEPENDENTS_FULL_PASS`  
**Qualify:** `ops/qualify-ess-letters-dependents-c2-staging.sh`  
**Module:** `wathefni-orchestrator/ess_letters_dependents_c2.py`

## What changes

| Prior | C2 amendment |
|---|---|
| ESS letter orders stay `pending` forever | Company-scoped fulfillment SM: `requested → under_review → approved → processing → issued` (+ rejected/cancelled) |
| No salary certificate type | `salary_certificate` + `employment_certificate` + `experience_letter` with Setup templates (placeholders only) |
| No dependents entity | Canonical `employee_dependents` CRUD/archive + optional ESS change-request + HR review |
| Soft document invent risk | `letters_fulfill` default OFF — no silent artifact when off; issued versions immutable; correction = new version |

## What does **not** change

1. Wave 1 / Wave 2 / C1 freezes  
2. Bank ESS hardened module  
3. Benefits / insurance dependents (Wave 6)  
4. Assistant mutations remain OUT  
5. Real non-synthetic termination remains dark  
6. No invented company legal wording — templates/policies belong to Setup  
7. Payroll not required; salary→payroll read is OPTIONAL  

## Commercial / modularity

- Letters work without Payroll  
- Dependents work without Benefits  
- Employee App visibility via `feature_visibility()` — disabled capabilities hide cleanly  

## Enablement (canary only)

```text
WATHEFNI_ESS_LETTERS_DEPENDENTS_C2=on
WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES=<canary>
enable_company_ess_letters_dependents(..., letters_fulfill=True/False, dependents_enabled=..., salary_cert_use_payroll=...)
```

## Rollback

```text
WATHEFNI_ESS_LETTERS_DEPENDENTS_C2=off
Clear WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES
disable_company_ess_letters_dependents(canary)
Issued letter versions + dependent history retained
```

## Next

C2 frozen after qualify. **Stop for owner review before C3 Resignation / Termination / EOC.**
