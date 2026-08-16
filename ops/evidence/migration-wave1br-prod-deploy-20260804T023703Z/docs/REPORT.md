# Migration Wave 1-BR — Production Deadlock Remediation Deploy

Stamp: `20260804T023703Z`  
Scope: production remediation deploy only — **no** Migration Wave 1-B qualification this step

## Deployment

- Backup: `/opt/wathefni/backups/production-pre-migration-wave1br-20260804T023703Z/`
- Rollback: `BACKUP/ROLLBACK.sh` (path proven; not executed — remediation left live)
- Modules deployed: `schema_contract.py`, `app.py`, `inbound_cv_intake.py`, `inbound_cv_processing.py`, `inbound_cv_adapters.py`, `durable_email_ingress.py`, `migration_wave1_cv_foundation.py`, `ops/migrate-schema-wave1br.sh`
- Evidence: `ops/evidence/migration-wave1br-prod-deploy-20260804T023703Z/`

## Schema migration

- ACK: `ACK_PRODUCTION_SCHEMA_WAVE1BR=YES`
- `WATHEFNI_SCHEMA_APPLY=1` for migrate only
- Advisory lock: `770911001`
- Result: `MIGRATE_SCHEMA_WAVE1BR_OK`
- Post-migrate fail-closed validate: `apply_calls=0` require path
- Ledger: `wathefni_schema_migrations` row `wave1br.bundle` / `wave1br-runtime-ddl-ban-v1`
- Restart with `WATHEFNI_SCHEMA_APPLY` **unset**

## Runtime zero-DDL proof

- `apply_calls=0`
- Forbidden `apply_schema` blocked (`schema_apply_forbidden`)
- Core/`hr_turns`/inbound/durable/migration require_schema green
- Fail-closed missing-relation probe OK

## Confirmations

| Check | Result |
|---|---|
| Services healthy | OK |
| Live CV/email queues | 0 active impact |
| Migration residue / iso tenants | 0 |
| Sibling freezes | all green |
| CV hybrid authority | `production_authority` |
| GPT auto OCR fallback | `off` |

## Gates

**PROD_DEADLOCK_REMEDIATION_WAVE1BR = GO**

**RERUN_MIGRATION_WAVE1B_FROM_PREFLIGHT = GO** (separate owner approval required to execute)

**Wave 1-B core/1k/10k not run in this step.**
