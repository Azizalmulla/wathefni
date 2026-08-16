# R1 verification log

Every headline claim in `ops/PRODUCTION_READINESS_R1_AUDIT.md` was spot-verified against source rather than
accepted from a scan or a subagent summary. This log records the exact checks and their results.

## P0-1 — Wave 4 / Wave 6 have no API and no surface

```
rg -n '@app\.(get|post|patch)\("/dashboard/[^"]*(job-architecture|learning|benefits|employee-relations|engagement|compensation|workforce-planning)' wathefni-orchestrator
→ 0 matches
```

```
rg -ln "performance_goals_c1|performance_reviews_c2|performance_feedback_c3|performance_calibration_c4|talent_profile_c5|talent_succession_c6" wathefni-orchestrator --glob '!smoke-test-*' --glob '!local-qualify-*'
→ each file matches only itself; no importer, no HTTP registration
```

```
rg -n "job_architecture_c1|learning_development_c2|benefits_administration_c3|employee_relations_c4|engagement_c5|compensation_planning_c6|workforce_planning_c7" wathefni-orchestrator --glob '!smoke-test-*' --glob '!*_c[1-7].py'
→ only setup_console_wave6_policies.py and wave6_hcm_expansion_product_c8.py
```

```
rg -l --glob '!**/setup-console/**' --glob '!**/*.test.*' -i "job.?architecture|employee.?relations|workforce.?planning|compensation.?planning|engagement.?survey|benefits.?enrollment" apps/wathefni-dashboard/src
→ 0 files
rg -li ... apps/wathefni-employee-mobile/{src,app}   → 0 files
rg -li ... apps/wathefni-hr-mobile/{src,app}          → 0 files
```

Dashboard `Page` union (`apps/wathefni-dashboard/src/types.ts:703-728`) = 25 pages, none Wave 4 or Wave 6.

HTTP module registration pattern confirmed at `app.py:45776-45808`, `47062-47074`, `76496-76539`
(`preboarding_http`, `probation_http`, `hr_intelligence_surfaces_http`, `requisitions_http`, `offer_routes`,
`assessment_ai_routes`, `tenant_control_wave3/4_routes`, `attendance_*_http`). No Wave 4/6 module appears.

Note: `tenant_control_wave4_routes.py` is Setup tenant-control "wave 4", unrelated to HCM Wave 4.

## P0-2 — Hardcoded HMAC secret fallbacks

Read `wathefni-orchestrator/app.py:33589-33611` directly. Confirmed literal fallbacks
`"wathefni-assessment-dev-secret"` and `"wathefni-video-interview-dev-secret"`, and `WATHEFNI_DATABASE_URL` used
as key material in both chains.

## P0-3 — No authentication rate limiting

Read `app.py:45664-45695` (`/dashboard/auth/login`) — no attempt counter, lockout, or cooldown.
Repo scan `security/rate-limiting.txt`: no rate-limit middleware exists. Only domain throttles found —
`operator_mobile.py:166-237` (mobile operator login lock), employee OTP 5-attempt lockout,
`jobs_phase2_stage_b.py:59-61`, reminder caps.

## P0-4 — Internal worker fail-open

Read `app.py:59036-59055`. Confirmed: when neither `WATHEFNI_INTERNAL_WORKER_TOKEN` nor
`WATHEFNI_INTERNAL_TOKEN` is set, the only remaining check is `client_host in {127.0.0.1, ::1, localhost}`.

## P1-19 — `employee_key`-only mutations

`security/idor-update-scope.txt` lists 15+ `UPDATE … WHERE employee_key=%s` sites with no `company_code`.
Downgraded from cross-tenant P0 to defence-in-depth P1 after confirming key construction at `app.py:73305`:
`employee_key = f"{company}-{phone_digits}"` — company-prefixed, therefore globally unique in practice.
Two sites (`73532`, `73605`) already include `AND company_code=%s`, showing the intended pattern.

## Keyboard safety

`surfaces/keyboard-coverage.txt`:
- `apps/wathefni-hr-mobile`: 3 files with `TextInput`, **0** files with `KeyboardAvoidingView` / `keyboardInsets`
  / `automaticallyAdjustKeyboardInsets`.
- `apps/wathefni-employee-mobile`: 12 files with `TextInput`, 7 with keyboard handling; the HR co-bundle screens
  (`LeaveApprovalView`, `SignInView`, `InterviewDetailView`, `HRPeopleDirectoryView`, `OperationalViews`) have none.

## Infrastructure

`infra/infra-inventory.txt`:
- No Alembic/Flyway. `CREATE TABLE IF NOT EXISTS` × 83, `ADD COLUMN IF NOT EXISTS` × 153 in `app.py`.
- No Sentry/Rollbar/Bugsnag anywhere (only an unrelated transitive `@opentelemetry/api` in lockfiles).
  Corroborated by `wathefni-orchestrator/ops/PHASE7E_E1B_PRIVACY_CHECKLIST.md:112` — "Crash reporter: CONFIRMED none wired".
- `/health` at `app.py:42142`, `/ready` at `42155`.
- Backups real: `wathefni-orchestrator/ops/{backup-wathefni.sh,wathefni-backup.service,wathefni-backup.timer,RESTORE_RUNBOOK.md,restore-drill.sh}` + `smoke-test-backup-restore.py`.
- `ls -a .github` → absent. No CI.

## Fake/demo data

`fake-data/expo-demo-flags.txt`: 7 HR demo gates in the employee-mobile binary
(`EXPO_PUBLIC_HR_{HIRING,ATTENDANCE,SHIFTS,ONBOARDING,DOCUMENTS,TASKS,DELIVERY_ALERTS}_DEMO`), all defaulting to
`'0'` in `app.config.js:58-71` but present as production code paths.
`fake-data/ops-seed-scripts.txt`: ops scripts with `setdefault("WATHEFNI_ENV", "production")`.

## Files in this evidence pack

| Path | Contents |
|---|---|
| `security/rate-limiting.txt` | Repo-wide rate-limit / throttle scan |
| `security/hardcoded-secret-fallbacks.txt` | Committed dev-secret fallbacks |
| `security/idor-update-scope.txt` | `UPDATE … WHERE employee_key/document_id` without company predicate |
| `security/debug-endpoints.txt` | debug / internal / seed / reset / replay / sweep routes |
| `fake-data/demo-gates.txt` | Demo/fixture/mock gates in non-test client source |
| `fake-data/expo-demo-flags.txt` | Build-time demo flags |
| `fake-data/math-random.txt` | `Math.random` in non-test client source |
| `fake-data/ops-seed-scripts.txt` | Seed/fixture scripts and their production defaults |
| `routes/route-inventory.txt` | Dashboard page union, employee + HR mobile route files, `APP_ROUTES` registry |
| `surfaces/keyboard-coverage.txt` | TextInput vs keyboard-handling coverage per app |
| `infra/infra-inventory.txt` | Migrations, error reporting, health, backups, CI, deploy artifacts |
| `en-ar/catalog-parity.txt` | Per-app EN/AR key counts and diffs; dashboard i18n mechanism |
| `permissions/ui-permission-gating.txt` | Nav permission keys and client-side role-string checks |
| `setup/setup-cards.txt` | Setup Console cards imported and mounted |
| `module-composition/entitlement-resolution.txt` | Module catalog keys and client composition helpers |
| `performance/perf-shapes.txt` | Uncapped `company_employees`, list virtualization coverage |

EN/AR parity was recomputed independently (flattened key diff, not key count alone):
`employee-mobile 1300/1300`, `employee-mobile-hr 222/222`, `hr-mobile 196/196`, zero missing keys in either
direction. The dashboard has no `i18n` directory at all.

Areas audited by source reading rather than by executable scan — permissions probing, module composition at
runtime, cross-surface convergence, and performance measurement — are recorded as unproven in §15 of the audit
report rather than represented by fabricated artefacts.
