# Phase 8C2-R1E — Production fail-closed security cutover record

**Status:** accepted production fail-closed green  
**Scope:** dashboard permission-authority security cutover only  
**Date (UTC):** 2026-07-12  
**Execution status:** canary not authorized by this record

## Accepted release baseline

| Slice | Commit |
|---|---|
| R1A fail-closed permissions | `b312d05` |
| R1B atomic employee status | `93720ed` |
| R1C HR-only activation handoff | `b0ec347` |
| Authorization regression harnesses | `8ff5061` |
| R1D staging evidence docs | `684b16f` |

## Deployed production artifact

| Field | Value |
|---|---|
| Production `app.py` SHA-256 | `42f657fdb7d528f8dce25f09ef0de4ba28f8c1934d64acbb063d2cc3e36bf8d2` |
| Pre-cutover fail-open snapshot hash | `b452a64d2fdf1fdb4d192b99e958877e45522ce56a4cb0134fbc131bed15a0bd` |
| Rollback snapshot | `/opt/wathefni/backups/r1e-predeploy-20260712T150938Z` |
| Approved rollback target? | **No** — old fail-open artifact is forensic only |

## Cutover outcome

- Additive schema present: `dashboard_user_permission_grants`, `employee_status_changes`
- Explicit grants only: one reviewed normal workspace owner received `employees.read`, `employees.manage`, `employees.status.approve`
- Legacy bootstrap recovery sessions cleared; remaining active recovery sessions: `0`
- Preflight PASS before activation
- Service activated; health `200`; `/dashboard/auth/me` returns `permission_authority=backend_current`
- Route matrix `28/28`; open-session revocation `4/4`
- R1B production wiring verified read-only (no real employee mutation)
- R1C verified gated: `hr_task_only` present; no invite/session/module enablement
- Protected flags remained OFF throughout
- Employee-app zero state retained: modules `0`, invites `0`, sessions `0`

## Protected state (intentional; not canary blockers)

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`

These remain OFF until a separate Phase 8C execution GO.

## Evidence packet

Redacted operational evidence:

`ops/evidence/phase8c2-r1e/`

Fail-closed fallback (retain; never restore fail-open):

`ops/PHASE8C2_R1D_FAIL_CLOSED_FALLBACK.md`
