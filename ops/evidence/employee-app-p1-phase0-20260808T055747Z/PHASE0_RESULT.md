# Employee App P1 — Phase 0 (authority, truth, release baseline)

Stamp: `20260808T055747Z` · base commit `cf26d59512a22a7634eb4edd28b4425ec1624405` (+ working tree, see `source-sha256.txt`)

Owner review is **not** requested for this phase. Canary rollout stays Aziz/Talal only.

## P0 closures

1. **Runtime access is fail-closed on `employees.app_access_enabled`.**
   `employee_app_context`, `rotate_employee_session` and `app_auth_activate` now share
   `_employee_app_runtime_access`. A cleared flag revokes the session with
   `revoked_reason='app_access_disabled'` and answers `401 app_access_revoked`; refresh
   refuses to rotate; a still-pending invite cannot redeem. `employee_app_access.py`
   retries the session revoke and reports `revoke_clean` / `revoke_error` /
   `sessions_still_active` instead of swallowing failures — access is blocked by the flag
   either way. Access policy storage, modes and invite semantics are unchanged.
2. **Deploy-time reconcile instead of runtime DDL.**
   `employee_app_access.reconcile_access_flag_for_live_sessions` enables exactly the
   employees holding a live session (only an HR grant can produce one), run by
   `wathefni-orchestrator/ops/migrate-employee-app-access-reconcile.sh` under the
   Wave 1-BR deploy advisory lock. Production run: `reconciled_count=0`,
   `live_sessions_without_flag=0`. Idempotent.
3. **Mobile tree typechecks.** `npx tsc --noEmit` is clean; `colors.canvas` and the four
   implicit-`any` payslip callbacks are fixed.
4. **Home never states a false fact.** `src/lib/moduleState.ts` gives every Home module its
   own `disabled|loading|error|ready` state; `HomeView` renders business copy only for
   `ready` and otherwise says the data is loading or unavailable. "Caught up" requires
   every contributing module to be factual.
5. **Source-neutral payslip authority copy.** Mode A (native authoritative) and Mode B
   (external import) both produce official PDFs, so employee copy now says the PDF comes
   from the authoritative released payroll record. Source authority stays in server
   metadata/audit. Downloaded PDFs are deleted from the cache in `finally` after sharing.
6. **Production diagnostics removed.** The auto-lock diagnostics panel is behind
   `EXPO_PUBLIC_LOCAL_AUTO_LOCK_DIAGNOSTICS`; PIN-enabled production users no longer see
   update IDs, employee key, gate reasons or timing internals.

## Release gate

`ops/employee-app-p1-release-gate.sh` — 19 gates in three classes. Anything skipped keeps
the verdict `INCOMPLETE` unless the skip is acknowledged, so a partial run can never read
as a qualification.

| class | where | result |
| --- | --- | --- |
| local (mobile toolchain + static/unit) | workstation | 12 passed, 0 failed |
| production DB (synthetic fixtures) | orchestrator host | 9 passed, 0 failed |
| staging DB (EMPAPPTESTCO harness) | orchestrator host | 1 passed, 0 failed |

New gate: `smoke-test-employee-app-runtime-access.py` (21 checks) and
`apps/wathefni-employee-mobile/scripts/composition-shapes-test.js` (28 checks) which
compiles and runs the real `employeeAppComposition.ts` across zero/one/two/four/full
entitlement shapes, onboarding states, deep-link admission and Home task derivation.

## Stale gates repaired (test-side, no product change)

- `smoke-test-employee-app-capabilities.py` asserted payslips stay disabled; Payroll Wave 3
  shipped them. Now asserts payroll enables payslips with view+download and that payslips
  stay `module_disabled` without the payroll module.
- `smoke-test-employee-app.py` never granted app access, so every invite was denied. It now
  goes through the canonical HR grant and scopes the rollout allowlist to its fixtures. Its
  fixture phones were 14 digits, so the Kuwait local-8 alias check could never match; they
  are canonical `965`+8 now. Confirmed staging-only (it creates and drops a company).
- `smoke-test-employee-payslips-p0_1.py` asserted a blocker key removed when Mode A shipped.
  It now asserts both sealed modes, synthetic-only, no invented payment date, and Mode A
  seal eligibility. Its cleanup LIKE pattern never matched its own decision notes, leaking a
  payroll period per run (15 residual); cleanup is tag-scoped and the period is chosen from
  a free month, with a savepoint so a failed create cannot poison the transaction.
- `smoke-test-employee-app-runtime-access.py` no longer sets `WATHEFNI_SCHEMA_APPLY`; the
  mega-DDL deadlocked against the live service. Migrations belong to deploy.

## Deployed

Production orchestrator restarted 05:59:20Z, `/health` 200.

| file | sha256 (host) |
| --- | --- |
| `app.py` | md5 `41f088a53be5061087b7b5278bd4463c` |
| `employee_app_access.py` | md5 `7b88b8759be0f118139b8b9745b47c68` |
| `payroll_payslip_wave3.py` | md5 `9fd41d792f5d3c0dd4dba9710e56bd25` |

Rollback: `ops/evidence/employee-app-p1-phase0-20260808T055747Z/ROLLBACK.sh`
(restores `/opt/wathefni/backups/employee-app-p0-20260808T055747Z`). The reconcile is not
rolled back: it only granted access to employees who already held a live session, and the
pre-repair code ignores the flag.

## Known residue (not a P0)

15 synthetic `payroll_periods` rows for WATHEFNI in 2032+ were left by earlier P0.1 runs
before the cleanup fix. They are `open`, synthetic-only gated, and no longer accumulate.

## Still frozen

Setup Console 1–5, Auth Wave 2 phases 0–5 (Phase 6 deferred), access-policy storage/modes,
invite semantics, no-SMS posture, Migration & Sync through P6.1, OCR/onboarding authority,
Bank ESS placement, Payroll Authority P1–P6 seals and release path, and
`employeeAppComposition.ts` as the single frontend composition derivation.
