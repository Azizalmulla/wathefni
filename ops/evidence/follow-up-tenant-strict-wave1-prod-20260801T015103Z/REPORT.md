# Wave 1 STRICT — Production Deploy

**Verdict: PASS**  
**Stamp:** `20260801T015103Z`  
**Wave 2:** not started

## What shipped
1. Ownership migration applied (`--ack-db=wathefni`): **32 backfilled**, **0 ambiguous**, **690 quarantined**
2. Strict predicate deployed: `ode.company_code = a.company_code`
3. New inserts require resolvable `company_code` (`company_code_required`)

## Backup
| Item | Path |
|------|------|
| Contained backup | `/opt/wathefni/backups/production-pre-follow-up-tenant-strict-wave1-20260801T015103Z` |
| Daily backup | `/opt/wathefni/backups/daily/20260801T015146Z` (SUCCESS) |
| DB dump | `db.dump` |
| Pre code | `app.py.pre`, `prehire_overview.py.pre` |
| Pre ODE CSV | `ode-null-or-wave1-pre.csv` |

## Migration
| Class | Count |
|-------|------:|
| backfill_unambiguous_application | 32 |
| quarantine_ambiguous_multi_tenant | 0 |
| quarantine_orphan_no_application | 690 |

## Proofs (live)
| Check | Result |
|-------|--------|
| WATHEFNI follow-up | **2 people / 4 applications** |
| Null-company qualify | **0** |
| Cross-tenant same app_key | **blocked** |
| Sent/recovered excluded | confirmed |
| Write-path requires company | **true** |
| Health | **ok** |
| Tenant-safety smoke | **PASS** |

## Rollback (verified, not executed)
| Type | Script | Verification |
|------|--------|--------------|
| Code | `/opt/wathefni/backups/production-pre-follow-up-tenant-strict-wave1-20260801T015103Z/ROLLBACK_CODE.sh` | Restores pre SHAs; present + executable |
| Migration | `/opt/wathefni/backups/production-pre-follow-up-tenant-strict-wave1-20260801T015103Z/ROLLBACK_MIGRATION.sh` | `BEGIN` restore then `ROLLBACK`; txn briefly restored 722 nulls; live remains 690 null / 32 backfilled |
| Full DB | `pg_restore --clean --if-exists -d wathefni db.dump` | dump validated at backup |

## Evidence
- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/follow-up-tenant-strict-wave1-prod-20260801T015103Z`
- Remote: `/opt/wathefni/production-evidence/follow-up-tenant-strict-wave1/20260801T015103Z`
