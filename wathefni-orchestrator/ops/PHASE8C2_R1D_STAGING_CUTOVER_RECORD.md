# Phase 8C2-R1D — Live staging permission cutover record

**Status:** accepted live-staging green  
**Company scope:** `WATHEFNI` staging only  
**Date (UTC):** 2026-07-12

## Accepted source commits

| Slice | Commit |
|---|---|
| R1A fail-closed permissions | `b312d05` |
| R1B atomic employee status | `93720ed` |
| R1C HR-only activation handoff | `b0ec347` |
| Authorization regression harnesses | `8ff5061` |

## Deployed staging artifact

| Field | Value |
|---|---|
| Staging `app.py` SHA-256 | `42f657fdb7d528f8dce25f09ef0de4ba28f8c1934d64acbb063d2cc3e36bf8d2` |
| Pre-deploy production `app.py` SHA-256 (unchanged) | `b452a64d2fdf1fdb4d192b99e958877e45522ce56a4cb0134fbc131bed15a0bd` |
| Protected flags | `WATHEFNI_EMPLOYEE_APP=off`, `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`, `WATHEFNI_ONBOARDING_SEED=off` |
| Schema | `dashboard_user_permission_grants`, `employee_status_changes` present |

## Cutover outcome summary

- Explicit employee scopes granted to one reviewed staging owner (`employees.read`, `employees.manage`, `employees.status.approve`) via audited permission-authority workflow.
- Reviewed recovery/bootstrap sessions: fingerprint captured, re-read matched, exactly 2 revoked, 0 remaining.
- Live route matrix: 27/27 passed.
- Open-session revocation: 4/4 passed.
- R1B live staging: 12/12 passed (throwaway fixtures cleaned).
- R1C live staging: 8/8 passed; no external delivery; dashboard handoff memory-only proven by `ActivationHandoff.security.test.tsx`.
- HTTP live routes: 10/10 passed.
- Fixture cleanup: employees/invites/tasks cleared; `employee_app` module left disabled.

## Evidence packet

Redacted operational evidence lives under:

`ops/evidence/phase8c2-r1d/`

Fail-closed emergency fallback (not a fail-open rollback):

`ops/PHASE8C2_R1D_FAIL_CLOSED_FALLBACK.md`

## Production note

R1D did **not** change production grants, sessions, services, flags, modules, employees, invites, or privacy content. Production security cutover is a separate Phase 8C2-R1E approval.
