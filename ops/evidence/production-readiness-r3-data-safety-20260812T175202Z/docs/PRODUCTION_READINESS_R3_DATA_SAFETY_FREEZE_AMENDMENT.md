# Production Readiness R3 — Data Safety Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`
**Phase:** R3 — Production Data Safety
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Full pass:** `ops/PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r3-data-safety-20260812T175202Z/`

---

## What freezes with R3

These are now binding contracts. Changing any of them requires a written amendment, not a pull request.

1. **Missing environment refuses to run.** Fixture, seed, matrix, and mutating canary tooling must not default `WATHEFNI_ENV` (or equivalent) to production. Missing target configuration is `REFUSE TO RUN`, never production.
2. **One data-safety primitive.** New mutating ops/fixture tooling uses `wathefni-orchestrator/production_data_safety.py`. A script does not invent a parallel production fallback, `--force`, or inferred company.
3. **Fixture tooling is hard-blocked against production.** Production-shaped env, database name `wathefni`, isolation marker `wathefni-production-isolation-v1`, or `postgres.env` cannot be used by fixture/seed/matrix tooling.
4. **Explicit company, explicit non-production ack.** Mutating fixture tooling requires a named company and `WATHEFNI_DATA_SAFETY_ACK=non-production` (or `--ack-non-production non-production`). There is no default company and no `--force`.
5. **WATHEFNI is never inferred tenant authority.** Missing company context fails closed. It does not become the Wathefni canary tenant. An explicit `"WATHEFNI"` is still a valid named identity.
6. **Destructive fixture SQL is scoped.** `DELETE` / `TRUNCATE` / module reset / tenant-wide cleanup names the company. Wildcard tenant deletion is forbidden. Unscoped `DELETE FROM company_modules` does not return.
7. **Production maintenance is a separate door.** Genuine production mutation uses `require_production_maintenance(operation=...)` with `WATHEFNI_PRODUCTION_MAINTENANCE_ACK=I_UNDERSTAND_THIS_MUTATES_PRODUCTION`. That is not a fixture override.
8. **Production mobile builds cannot bake or honour HR demo queues.** Production release + any `EXPO_PUBLIC_HR_*_DEMO=1` is a build failure. Runtime also ignores demo flags when the production-release marker or production/canary update channel is set. Development preview may still opt in.
9. **Synthetic connectors are an isolated test capability.** Production users cannot create `deterministic_canary` (or other synthetic kinds) unless `WATHEFNI_SYNTHETIC_CONNECTORS=1` and the company is synthetic or explicitly allowlisted.
10. **Qualification identities stay in test assets.** WATHEFNI, Aziz (`WATHEFNI-96599338566`), Talal (`WATHEFNI-96550252254`), and synthetic prefixes are not a default production tenant, bootstrap employee, or customer-visible fixture.
11. **Clean company bootstrap stays clean.** Creating a company inserts `companies` + `company_settings` only. No fixture employees, fake leave, fake payroll, fake messages, or demo modules.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen. R3 does not reopen security contracts.
2. Waves 1–6 remain frozen as **domain authority**. Waves 4–6 remain not product-surface complete. The R5 hybrid decision is untouched.
3. All Wave 4/6 capability remains global-OFF and company-gated.
4. `PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no rollout.
5. R4 Truth-in-UI does not start from this amendment. Owner review is required first.

## Deployment prerequisites

* Staging and local fixture runs must export `WATHEFNI_ENV` and `WATHEFNI_DATA_SAFETY_ACK=non-production` plus an explicit synthetic `--company`.
* Canary-tenant fixture writes on non-production additionally need `WATHEFNI_ALLOW_CANARY_FIXTURES=1`.
* Employee-mobile production EAS builds must keep `EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE=1` and must not set demo flags.
* Synthetic connector smokes must set `WATHEFNI_SYNTHETIC_CONNECTORS=1` in-process only.
* Named production maintenance scripts need the matching `WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION` and ack. Optional-module boundary still also needs `WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1`.

## Rollback

Rolling back R3 means restoring previous `app.py` WATHEFNI fallbacks, removing `production_data_safety.py` hooks from ops scripts, and dropping the mobile demo production guard. That reinstates silent production seeding and missing-company routing into the canary tenant, so it is an incident action rather than a routine revert.

## Next

Owner review of this freeze. **Stop.** Do not begin R4 Truth-in-UI until the owner accepts R3.
