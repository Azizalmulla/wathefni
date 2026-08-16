# Production Readiness R8 — Delivery Safety Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R8_DELIVERY_SAFETY_FULL_PASS`
**Phase:** R8 — Observability / CI / Migration Safety
**Date:** 2026-08-16
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R8_DELIVERY_SAFETY_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r8-delivery-safety-20260816T002217Z/`
**Amends:** R1 P1-23, P1-24, and the migration-framework gap. R2–R7 remain frozen.

---

## What freezes with R8

These are now binding contracts. Changing any of them requires a written amendment.

1. **First-party error reporting** is the production sink. HR Web and Setup Console POST `/dashboard/telemetry/error`. HR Mobile (standalone and employee HR co-bundle) POST `/dashboard/mobile/telemetry/error`. Employee App POSTs `/app/telemetry/error`. Backend unhandled exceptions are recorded. A required third-party crash SaaS is not part of this freeze.
2. **Client payloads are redacted before persist.** R2 `safe_detail` remains authoritative for secret keys. R8 additionally redacts emails, phone numbers, and `password=` / `token=` assignments in free text. Raw stacks with request data are not the ingest contract.
3. **Structured logs** use `observability.structured_log` and must not write secrets. R2 denial telemetry is hooked into that logger; the R2 denial table remains the security audit.
4. **`/health` is liveness only.** It must not call `ensure_schema()` and must not publish `legacy_dashboard_token_auth`.
5. **`/ready` is readiness.** It includes the delivery snapshot (migrations, recent error counts, failed-job visibility) and returns HTTP 503 when forward migrations are not ok.
6. **Forward migrations** live in `wathefni-orchestrator/migrations/` as numbered SQL. History is `wathefni_forward_migrations`. Apply only with `WATHEFNI_SCHEMA_APPLY=1`. Runtime never DDL. Checksums and contiguous versions are required. Drift detection is mandatory before calling a schema ready.
7. **Rollback is restore-from-backup**, documented in `wathefni-orchestrator/ops/RESTORE_RUNBOOK.md` §4b. Do not invent down-SQL for domain tables.
8. **CI** (`.github/workflows/delivery-safety.yml`) must run the R8/R7/R2 unit suites and the relevant mobile client suites on pull requests. It must not SSH to the VPS.
9. **Deploy gate** is `ops/gate-wathefni-deploy.sh`. Broken R8/R7/R2 unit suites must not casually ship. Historical `ops/deploy-*.sh` files stay as-is; new deploys invoke the gate.
10. **Failed-job visibility** reads existing job tables. R8 does not invent a second queue.
11. **R8 does not reopen** Wave 4 C1–C6, PT1–PT7, or R2–R7 except a genuine correctness/security blocker.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen, including `safe_detail` and rate-limit policy shape. `client_error_report` is additive.
2. R3–R7 remain frozen.
3. Wave 1-BR runtime DDL ban remains frozen.
4. `PRODUCTION_READINESS_R8_DELIVERY_SAFETY_FULL_PASS` is **not** `PRODUCTION_READY`.

## Owner review

R8 is complete and frozen. **Stop here. Do not begin R9 automatically.**
R9 (live permission and tenant-isolation probing) starts only after owner review.
