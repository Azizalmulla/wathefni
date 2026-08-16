# Deadlock Remediation Wave 1-BR

Date stamp: `20260804T021928Z`
Scope: staging proof only — no production remediation deploy, no Wave 1-B resume

## Containment (production abort)

See `ops/evidence/migration-wave1b-abort-20260804T0158Z/` — stalled 10k aborted; residual zero proved; orchestrator not restarted.

## Root cause

Runtime schema DDL (`CREATE TABLE IF NOT EXISTS hr_turns` / `inbound_cv_intake.ensure_schema`) competed with migration DML (`INSERT INTO candidates/applications`), producing relation-lock cycles and repeated deadlocks.

## Runtime DDL call sites converted (validate-only unless `WATHEFNI_SCHEMA_APPLY=1`)

- `schema_contract.py` — apply/require contract, advisory lock, fail-closed
- `inbound_cv_intake.ensure_schema` → apply/require
- `inbound_cv_processing.ensure_schema` → apply/require
- `durable_email_ingress.ensure_schema` → apply/require
- `inbound_cv_adapters` — `require_schema` only on hot paths
- `migration_wave1_cv_foundation.ensure_schema` → apply/require
- `app.ensure_schema` — validate core runtime tables; DDL only under apply flag + deploy advisory lock

## Replacement deployment migration

- `ops/migrate-schema-wave1br.sh` — ACK-gated, sets `WATHEFNI_SCHEMA_APPLY=1`, advisory lock `770911001`, applies schemas before workers resume

## Staging proof results

- no runtime DDL: `NO_RUNTIME_DDL_OK` in tests/proofs.out
- missing schema fail-closed: `FAIL_CLOSED_OK`
- concurrent migration DML + sibling workers: `CONCURRENCY_MIGRATION_OK`
- inject/retry/replay/rollback + residual zero: `RESIDUAL_ZERO_OK`

## Gate

**STAGING_DEADLOCK_REMEDIATION_WAVE1BR = GO**

**PROD deploy remediation = NO-GO** until owner approval  
**Rerun Migration Wave 1-B = NO-GO** until owner approval after production remediation deploy
