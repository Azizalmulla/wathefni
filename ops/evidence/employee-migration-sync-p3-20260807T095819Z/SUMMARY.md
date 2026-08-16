# Migration & Sync P3 — Existing-Employee Onboarding Migration

| Field | Value |
|---|---|
| Stamp | `20260807T095819Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Contract | `employee_migration_sync_p3_onboarding` @ `3.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P3_ONBOARDING.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p3-20260807T095819Z/ROLLBACK.sh` |

## Proven

| Check | Result |
|---|---|
| Already-onboarded externally → `migrated_external`, no fresh checklist | PASS |
| History imported with migrated provenance (`wathefni_performed` false) | PASS |
| Unknown / empty source → no fake completion | PASS |
| Explicit Needs Wathefni + start flag can start canonical workflow | PASS (`explicit start attempted=True`) |
| Repeated import idempotent | PASS |
| Newer Wathefni activity supersedes imported state | PASS |
| Rollback does not erase native-superseded activity | PASS |
| P2 regression | PASS |
| P1 foundation regression | PASS |

## Fix in this stamp

Repeated `ensure_sql` under `WATHEFNI_SCHEMA_APPLY=1` re-wrote the schema ledger in the same transaction. PostgreSQL `now()` is transaction-stable, so the second insert hit the ledger PK, was swallowed by best-effort ledger code, and left the txn aborted — so onboarding migration never applied. Fixed `_record_ledger` with savepoint + `ON CONFLICT DO NOTHING`, plus onboarding schema ready-flag and native-activity savepoint probes.

## Remaining gaps (not P3 blockers)

- P4 opening balances · P5 connectors · P6 leavers — not started
- Auth Wave 2 Phase 6 — not started
- Dashboard `MigrationSyncShell` onboarding disposition line is in repo; confirm production dashboard build includes it if HR preview UX is reviewed live
- Employee-facing copy for migrated statuses should stay plain language (no internal disposition codes)
