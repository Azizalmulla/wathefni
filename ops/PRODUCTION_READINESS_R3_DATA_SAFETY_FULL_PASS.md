# PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`
**Phase:** R3 — Production Data Safety (remediation, scoped)
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Qualify:** `ops/qualify-production-readiness-r3-data-safety.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R3_DATA_SAFETY_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r3-data-safety-20260812T175202Z/`

**Scope:** R1 P0-6 (production-targeting seed/matrix scripts), implicit/default WATHEFNI tenant fallback, and production-capable demo/fixture paths. No R4 Truth-in-UI work. No R5 Wave 4/6 surface work. R2 stays frozen.

---

## 1. Result

| Gate | Result |
|---|---|
| Local unit contracts (no DB) | **61 passed, 0 failed** (`R3_DATA_SAFETY_UNIT_PASS`) |
| Staging database paths, isolated synthetic tenants | **18 passed, 0 failed** (`R3_DATA_SAFETY_FULL_PASS`) |
| Live deployed staging service | **5 passed, 0 failed** |
| Script inventory (no live `setdefault(..., "production")`) | **1064 live scripts; 0 unsafe production defaults** |
| Waves 1–6 unit freezes + authority contracts + R2 security + internal-auth | **green** (R2 unit 84/0, R2 staging DB 69/0, internal-auth 10/0, Waves 1–6 product-acceptance all 0 failed) |
| Open R3 blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no rollout. Stop here for owner review. Do not begin R4 automatically.

---

## 2. What changed

### Reusable safety primitive

`wathefni-orchestrator/production_data_safety.py` (`CONTRACT_VERSION = r3-data-safety-v1`) is the only fixture/ops guard. Scripts do not invent their own production fallback.

| Helper | Contract |
|---|---|
| `require_explicit_environment()` | Missing `WATHEFNI_ENV` → `REFUSE TO RUN [environment_required]`. Never defaults to production. |
| `require_non_production_target()` | `production` / `prod` / `live`, DB name `wathefni`, marker `wathefni-production-isolation-v1`, or `postgres.env` → hard block. |
| `require_non_production_ack()` | Requires `WATHEFNI_DATA_SAFETY_ACK=non-production`. There is no `--force`. |
| `require_fixture_tooling()` | Env + non-production target + ack + explicit synthetic company. |
| `require_non_production_ops()` | Mutating canary/ops tooling: same production hard-block + ack; WATHEFNI is not inferred. |
| `require_production_maintenance(operation=...)` | Named operation + `WATHEFNI_PRODUCTION_MAINTENANCE_ACK=I_UNDERSTAND_THIS_MUTATES_PRODUCTION`. Separate from fixture tooling. |
| `require_company_code()` | Missing company raises `MissingCompanyCode`. Never substitutes WATHEFNI. |
| `require_destructive_scope()` / `scoped_delete_company_modules()` | Named tenants only. Wildcards refused. |
| `refuse_protected_identities()` | Aziz `WATHEFNI-96599338566` and Talal `WATHEFNI-96550252254` cannot be mutated by fixture tooling. |
| `synthetic_connectors_allowed()` | Off unless `WATHEFNI_SYNTHETIC_CONNECTORS=1` and the company is synthetic or explicitly allowlisted. |

`DataSafetyError.reason` is the machine code. It does not use `SystemExit.code` (that attribute is the exit payload).

### P0-6 — seed/fixture/matrix scripts fail closed

Live `ops-seed-*-visual-fixture.py` and `ops-seed-wave1-visual-canary.py`:

* no `setdefault("WATHEFNI_ENV", "production")`
* `activate_fixture_tooling_from_argv()` / `require_fixture_tooling()` before mutating
* `--company` + `--ack-non-production` (or the matching env vars)
* missing env / production-shaped target / missing company → refuse

`kuwait-pilot-document-journey-production-matrix.py` and `candidates-c01-production-matrix.py` now call `require_fixture_tooling` (synthetic `KWDOC*` / `C01*` tenants). They cannot run against production even though the filenames still say production.

Mutating `canary-prod-*.py` scripts call `require_non_production_ops()`. Setting `WATHEFNI_ENV=production` is a hard block, not a warning.

### Destructive operation protection

Fixture/matrix `DELETE FROM company_modules` is scoped `WHERE company_code = ANY(%s)` after `require_destructive_scope`. Wildcard tenants are refused. The unscoped `DELETE FROM company_modules` class is detected by `looks_like_unscoped_company_modules_delete`.

### Implicit WATHEFNI company authority removed

`app.py` `require_company_code()` wraps the primitive and returns HTTP 400 `company_required`. Tenant-sensitive helpers no longer use `company_code or "WATHEFNI"`. Missing company does not route into the Wathefni canary tenant. An explicit `"WATHEFNI"` still resolves when named.

### Production demo-build guard

Employee-mobile:

* `src/hr/features/demoProductionGuard.ts` — production release (env marker, baked extra, or updates channel `production`/`canary`) ignores demo flags at runtime.
* All seven demo gates (Hiring, Attendance, Shifts, Onboarding, Documents, Tasks, Delivery Alerts) use `readDemoFlag()`.
* `hiringComposition.ts` ignores `forceDemo` unless `demoAllowedInThisBuild()`.
* `app.config.js` `assertDemoFlagsSafe()` throws if a production release bakes any `EXPO_PUBLIC_HR_*_DEMO=1`.
* `eas.json` production profile sets `EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE=1`.

HR mobile design-preview stays available in development and is off when the production-release marker is `1`.

### Synthetic connectors

`employee_migration_connectors.create_connection` returns 403 `synthetic_connector_forbidden` unless the isolated test capability is on. The kinds catalog marks `deterministic_canary` `available` only then. `MigrationSyncShell` hides “Connect canary source” unless `available === true`. Migration smokes enable the flag in-process only.

### Test identities

WATHEFNI, Aziz, Talal, and synthetic prefixes remain valid qualification assets. They are not a default production tenant, bootstrap employee, missing-company fallback, or customer-visible fixture.

### Clean-company bootstrap

Setup Console create still inserts only `companies` + `company_settings` (timezone/currency). Qualification re-proves a fresh staging company has no employees, messages, leave, payroll, modules, or other fixture tables from `CLEAN_BOOTSTRAP_ABSENT_TABLES`.

### Genuine production maintenance (separated)

These are not fixture escapes:

* `ops/optional-module-boundary-production-matrix.py` — existing `WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1` **plus** `require_production_maintenance(operation="optional-module-boundary-matrix")`
* `ops/correct-production-noor-esraa-identity.py`
* `ops/unified-inbound-cv-legacy-binding-backfill.py`

---

## 3. Qualification matrix (required proofs)

| Proof | How |
|---|---|
| Seed with no environment refuses | unit + subprocess `ops-seed-inbox-visual-fixture.py` |
| Seed pointed at production-shaped target refuses | unit + subprocess |
| Seed with explicit staging synthetic tenant works | staging DB `require_fixture_tooling(R3SYNTH…)` |
| Destructive matrix cannot delete another tenant's `company_modules` | staging DB scoped delete |
| Missing company code fails closed | unit + `app.require_company_code` + live process |
| Missing company cannot resolve to WATHEFNI | unit + live |
| Explicit legitimate tenant still resolves | unit + live |
| Production mobile build cannot activate fabricated HR queues | `app.config.js` bake-fail + runtime guard |
| Development preview remains usable | node load of `app.config.js` with demo=1 and no production marker |
| Clean company bootstrap contains no fixtures | staging DB insert matching Setup Console |
| Fixture identity cannot leak into a clean tenant | staging DB |
| Destructive retries remain scoped | `require_destructive_scope` on named companies only |
| R2 security regressions remain green | `smoke-test-r2-security.py` + staging `smoke-test-r2-security-db.py` |
| Waves 1–6 frozen regressions remain green | product-acceptance smokes + authority contracts + internal-auth |

---

## 4. Deleted / retained fixture tooling

**Deleted behaviour (not the files):** silent production defaults, inferred WATHEFNI company, unscoped module wipes, production demo flags that can bake into a release, UI-accessible synthetic connectors in production workspaces.

**Retained:**

* Visual fixture seeds, behind `require_fixture_tooling`
* Staging matrices (`KWDOCSTG*`, `C01STG`), behind the same guard
* Historical `ops/evidence/**` copies (frozen artifacts, not live tooling)
* Read-oriented production screenshot/qualify scripts: explicit `WATHEFNI_ENV` required, no production `setdefault`, not a seed path
* Design-preview / demo gates for development builds

---

## 5. Safe debt

1. Filenames such as `*-production-matrix.py` and `canary-prod-*.py` still say production. The guard refuses production. Rename is cosmetic and out of R3 scope.
2. Some staging matrices still `setdefault` staging secret/workspace paths after `WATHEFNI_ENV` is required. That never infers production.
3. Read-oriented `*-ui-prod.py` / screenshot scripts require explicit env but are not hard-blocked from a production-shaped target, because they are not fixture writers. A later pass can split them into a read-only class.
4. `ops/evidence/**` retains historical `setdefault(..., "production")` copies. Do not copy those back into live `ops/` or `wathefni-orchestrator/`.
5. Bank visual fixture still mentions WATHEFNI employee allowlist strings; the company itself is env-driven and guarded.
6. HR mobile has no production EAS profile today; the preview guard is marker-based for when one exists.
7. Staging schema did not have `payroll_runs` / `payslips` / `onboarding_items` / `attendance_days` / `shifts` during bootstrap proof; those checks were skipped. Every listed table that exists was empty for the fresh company.

---

## 6. Blockers

None. Live qualification is green. R3 is frozen for owner review.

---

## 7. What this does not do

* Does not reopen R2 unless a genuine security regression is found.
* Does not start R4 Truth-in-UI.
* Does not implement the R5 hybrid Wave 4/6 decision.
* Does not authorise production customer rollout.
