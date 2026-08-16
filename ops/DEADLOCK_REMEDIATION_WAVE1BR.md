# Migration Wave 1-B Abort + Deadlock Remediation Wave 1-BR

## Immediate containment (production)

| Item | Result |
|---|---|
| Canary process | Already absent on host at abort time; local qualify wrapper terminated |
| Orchestrator restart | **Not performed** |
| Unrelated workers | **Not terminated** |
| Batch `70679db7-62c7-4de0-b09d-dd5560d7eb66` | Already absent (cleaned by canary teardown after SSH death); rollback returned `batch_not_found` |
| Active residual | **0** (batches/rows/chunks/apps/docs/deferred/queue/iso tenants/stage dirs) |
| Evidence preserved | `ops/evidence/migration-wave1b-abort-20260804T0158Z/` + deadlock qualify log |

Deadlock evidence retained under `ops/evidence/migration-wave1b-abort-20260804T0158Z/deadlock/`.

## Root cause

Runtime DDL competed with migration DML:

- migration worker: `INSERT INTO candidates` / `applications`
- orchestrator/runtime: `CREATE TABLE IF NOT EXISTS hr_turns` / `inbound_cv_intake.ensure_schema`
- result: relation-lock cycle + repeated `DeadlockDetected` (514 failed rows on stalled 10k were deadlock import failures)

Retries alone are not an acceptable fix.

## Runtime DDL call sites removed from normal execution

Converted to **validate-only** unless `WATHEFNI_SCHEMA_APPLY=1`:

| Module | Change |
|---|---|
| `schema_contract.py` | New apply/require contract, fail-closed, advisory lock `770911001`, counters |
| `inbound_cv_intake.py` | `apply_schema` / `require_schema`; `ensure_schema` gated |
| `inbound_cv_processing.py` | same |
| `durable_email_ingress.py` | same |
| `inbound_cv_adapters.py` | hot paths call `require_schema` only |
| `migration_wave1_cv_foundation.py` | same; migrate script uses `apply_schema` |
| `app.ensure_schema` | runtime: `require_core_runtime_schema` (includes `hr_turns`); DDL only under APPLY + deploy advisory lock |

## Replacement deployment migration

- `wathefni-orchestrator/ops/migrate-schema-wave1br.sh`
- ACK-gated (`ACK_STAGING_SCHEMA_WAVE1BR` / `ACK_PRODUCTION_SCHEMA_WAVE1BR`)
- Sets `WATHEFNI_SCHEMA_APPLY=1`
- Serialized with `pg_advisory_lock(770911001)`
- Applies inbound/durable/migration schemas, then validates core relations including `hr_turns`
- Workers/API must boot with APPLY unset; missing schema fails closed with `SchemaNotMigratedError`

## Staging proof (`20260804T021928Z`)

Evidence: `ops/evidence/migration-wave1br-deadlock-remediation-20260804T021928Z/`

| Proof | Result |
|---|---|
| No runtime DDL | `apply_calls=0` |
| Startup validate | zero schema mutations |
| Missing schema fail-closed | `schema_not_migrated:...wave1br_missing_relation_probe_zzz` |
| Concurrent core/1k + sibling noise | completed; `apply_calls=0`; no deadlock exhaustion |
| Inject / DLQ / replay / rollback | replayed=1; residual zero |
| Queue residual | active migration extraction = 0 |

## Gates

| Gate | Verdict |
|---|---|
| STAGING_DEADLOCK_REMEDIATION_WAVE1BR | **GO** |
| PROD deploy remediation | **NO-GO** — awaiting owner approval |
| Rerun Migration Wave 1-B from preflight | **NO-GO** — awaiting owner approval after production remediation deploy |
| Migration Wave 2 | **NO-GO_NOT_STARTED** |

Production was not remediated and Wave 1-B was not resumed.

## Production deploy

See `ops/DEADLOCK_REMEDIATION_WAVE1BR_PRODUCTION_DEPLOY.md`.

**PROD_DEADLOCK_REMEDIATION_WAVE1BR = GO**  
**RERUN_MIGRATION_WAVE1B_FROM_PREFLIGHT = GO** (execution requires separate owner approval; not started here)

