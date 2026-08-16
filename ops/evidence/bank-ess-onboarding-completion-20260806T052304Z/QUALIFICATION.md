# Bank ESS + onboarding completion — live production qualification

Run: `qual-20260806T052441Z` · production host, live HTTP against
`http://127.0.0.1:8010` (uvicorn), synthetic canaries only.

## Result

| domain | cases | proven | failed | partial | skipped |
|---|---|---|---|---|---|
| Bank ESS | 43 | 43 | 0 | 0 | 0 |
| Onboarding completion | 27 | 27 | 0 | 0 | 0 |

Per-case table: `findings/matrix-table.md`. Raw run: `findings/live-qualification-matrix.json`.

## How it was run

- Employee paths: real HTTP with minted employee sessions (`/app/bank`, `/app/onboarding`).
- HR paths: real HTTP with a minted dashboard session for the seeded owner, so
  `dashboard_context` permission resolution is the one under test. Resolved
  permission probe: 61 permissions, `employees.manage=true`.
- Backend invariants: asserted directly against Postgres (sealed proposals,
  authority-layer separation, notification dedup, audit events, tenant scoping).
- Fixtures: three synthetic canaries (`WATHEFNI-96554970{01,02,03}`) matching the
  ESS synthetic phone + name prefixes. No real employee bank data was created:
  the real-bank allowlist stayed empty and the runner refuses to start otherwise.

## Regression suites (production host, all green)

`test-onboarding-completion-contract` · `smoke-test-onboarding-lifecycle-wave2a` ·
`smoke-test-onboarding-freeze-regression` · `smoke-test-employees360-freeze-regression` ·
`smoke-test-onboarding-wave2` · `smoke-test-posthire-dashboard` ·
`smoke-test-onboarding-doc-validation-parity` · `smoke-test-employee-profile` ·
`smoke-test-employee-roster` · `smoke-test-onboarding-seeding` (38/38) ·
`smoke-test-posthire-mutation-integrity` · `smoke-test-summary-counts` ·
`smoke-test-onboarding-civil-id-dual-side` · `smoke-test-onboarding-capture-quality` ·
`smoke-test-employee-wave5-ess` (41/41) · `smoke-test-employee-wave5b-safety` (31/31)

## Defects found and fixed during qualification

1. **ESS optimistic concurrency broken by completion recompute.** The legacy
   mirror bumped `employees.updated_at`, which ESS uses as its hub concurrency
   token. Because bank approval now syncs the onboarding item, any checklist
   movement made unrelated in-flight employee requests fail `stale_data`. Caught
   by `smoke-test-employee-wave5-ess`. Fixed: derived counters no longer touch
   `updated_at`.
2. **Employee app never exposed the canonical completion state.** The projection
   computed it; the endpoint dropped it. Fixed, and the cross-surface check now
   fails on a missing value instead of silently ignoring it.
3. **Projections could not report `reopened`.** They recomputed without completion
   history, so they would disagree with the HR completion endpoint after a
   reopen. Fixed by threading the persisted `first_completed_at` into both
   projections.
4. **Orphaned bank evidence blobs.** Deleting an evidence row left the private
   file on disk. Fixed with a purge path (`purge_bank_evidence_bytes`, including
   an orphan sweep) plus `ON DELETE CASCADE` from all four bank tables to
   `employees`, and stale rows from other suites were cleaned.
5. **Canary cleanup could silently roll back.** A missing table aborted the whole
   cleanup transaction, leaving prior deletes undone and poisoning the next run.
   Fixed with per-table savepoints and a pre-run clean slate.
6. **Schema-drift assumption.** `recompute()` selected an `owner_group` column
   that does not exist in production. Fixed by introspecting available columns.
7. **Masked bank projection changed shape.** Sealed proposals moved masked values
   under `display`, which would have blanked older HR surfaces. Fixed by
   mirroring masked values at the top level with `<field>__masked`.

## Canary cleanup

Post-run invariants (`findings/post-run-invariants.txt`):

```
canary_employees      0
canary_qual_items     0
bank_verified_total   0
bank_effective_total  0
bank_evidence_total   0
completion_snapshots 51   (real employees — canonical product state)
accepted_docs_real    3   (Aziz's real accepted documents, untouched)
```

Private evidence directory: 0 files remaining.

## UI layer (code + contract qualification, `20260806T153212Z`)

See `findings/ui-qualification.md`.

| check | result |
|---|---|
| Employee mobile capability foundation (incl. bank + completion contracts) | GREEN |
| HR `BankReviewPanel` + `OnboardingCompletionStrip` unit tests | 18 cases PASS |
| Dashboard Vitest full suite | 83 files / 451 tests PASS |
| Dashboard production build | PASS |
| New UI file lint | 0 errors |
| Live dashboard UI deploy of this stamp | **not done** (dirty tree with unrelated WIP) |
| Live device / OTA bank walk | **not done** |

## Verdicts

| domain | verdict | why |
|---|---|---|
| Bank ESS | `partially proven` | Backend live 43/43 + regressions green · employee/HR UI implemented and contract-proven · live UI bundle + device paths not stamped |
| Onboarding completion | `partially proven` | Backend live 27/27 + canonical contract on all surfaces · UI strip contract-proven · live UI bundle + device paths not stamped |
| Auth Wave 2 readiness | `blocked` | Gate requires fully production-qualified Bank ESS + onboarding across backend, HR and employee paths — see `ops/AUTH_WAVE2_READINESS_DECISION.md` |

## Pre-existing findings, out of scope, not regressions

- `smoke-test-employee-app.py` fails on the controlled-rollout allowlist gate
  because the test never sets `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST`. With the
  gate relaxed it passes 28/28. Stale test, unrelated to this work.
- `smoke-test-onboarding-dashboard.py` expects `_onboarding_start_executor` to
  return `feature_disabled` for an unknown employee while the HR-mutate flag is
  off; it resolves the employee first and returns `employee_not_found`. It still
  fails closed. The ordering lives in `action_registry.py`, untouched here.
