# Attendance Wave 1B — PostgreSQL persistence and authority cutover

**Stamp:** `20260802T022646Z` (staging qualify)  
**Mode:** Local engineering + staging DB qualification. **No production deploy.**  
**DB:** `wathefni_staging` only.

## Verdict

| Gate | Result |
|---|---|
| Staging PG qualification | **PASS 43/0** |
| Local E360 freeze | **PASS 57/0** |
| Local Onboarding freeze | **PASS 54/0** |
| Wave 1 memory suite | **PASS** |
| Migrate → rollback → remigrate | **PASS** |
| Production deploy | **NOT DONE** |
| Real clocking / device / QR / GPS / kiosk | **NOT ENABLED** |
| **WATHEFNI-only production synthetic canary** | **NO-GO** (staging proven; production modules/schema not deployed) |

---

## 1. PostgreSQL schema and adapter design

### Tables (Wave 1 + 1B)
| Table | Role |
|---|---|
| `attendance_punches` | Append-only ledger; `UNIQUE (company_code, source, source_event_id)` |
| `attendance_day_projections` | Versioned day authority; partial unique current `(company, emp, date, shift_key)` |
| `attendance_corrections` | request → approved/rejected/disputed |
| `attendance_payroll_snapshots` | Immutable approved payroll payloads |
| `attendance_authority_events` | Durable audit (punch/project/correct/snapshot/rebuild) |
| `attendance_compat_drift` | Quarantine for authority↔legacy mismatches |

### Guards
- Triggers forbid punch UPDATE/DELETE and snapshot payload mutation.
- Synthetic cleanup only via `SET LOCAL wathefni.allow_authority_cleanup = '1'`.
- `shift_key` (`''` when null shift) prevents duplicate null-shift authority.

### Adapter
`PostgresAuthorityStore` (`attendance_authority_postgres.py`):
- Same interface as Wave 1 in-memory store
- `pg_advisory_xact_lock` per employee-day for concurrent punches/absence/corrections
- `INSERT … ON CONFLICT DO NOTHING` for punch idempotency
- `SELECT … FOR UPDATE` on current projection before versioning
- Thread-local cursor nesting so append → project → approve is one transaction when wrapped in `employee_day_transaction`

### Store selection
```
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres|memory
# default: postgres when AUTHORITY on, else memory
```

---

## 2. Migration and rollback contract

| Script | Contract |
|---|---|
| `ops/migrate-attendance-authority-wave1b.sh` | Refuses `WATHEFNI_ENV=production` and `ACK_DB=wathefni`. Applies Wave 1+1B DDL. |
| `ops/rollback-attendance-authority-wave1b.sh` | Refuses non-synthetic residuals (`company_code NOT LIKE ATTW1%`). Drops Wave 1B additive objects/triggers. Optional `ROLLBACK_DROP_BASE=1` drops base tables. |

Proven on staging: **MIGRATE_OK → qualify → ROLLBACK_OK → REMigrate_OK**.

---

## 3. Reconciliation report

Authority projections vs legacy `attendance_records`:

- Compare status / check_in / check_out / late / early_leave
- **Never silently overwrite** conflicting legacy rows
- Mismatches → `attendance_compat_drift` with `status=quarantined`

Staging proof:
- matched ≥ 1
- drift detected and quarantined
- conflicting legacy `absent` row preserved while authority showed completed

Artifact: `remote/final/reconcile/reconcile-checks.json`

---

## 4. Tests proved (staging `wathefni_staging`)

| Scenario | Result |
|---|---|
| Data survives reconnect / optional systemd restart | PASS |
| Duplicate + concurrent idempotent punches | PASS |
| Overnight + multi-session + unpaid break calc | PASS |
| Exact rebuild from immutable punches | PASS |
| Correction/dispute history + audit events survive restart | PASS |
| Approved snapshot immutable + payroll reconcile exact | PASS |
| Compat drift quarantined (no silent overwrite) | PASS |
| Flag-off legacy gate | PASS |
| Tenant isolation | PASS |
| E360 + Onboarding freeze (local evidence) | PASS |
| Wave 1 memory suite | PASS |

---

## 5. Remaining risks

1. **Staging orchestrator `app.py` not yet cut over** to Wave 1B modules in the running service tree — qualification used `/tmp` PYTHONPATH overlay. Production/staging service deploy still required before live flag use.
2. **Connection pool pressure** under high concurrency — mitigated by shared store + advisory locks; keep `WATHEFNI_DB_POOL_MAX` sized for workers.
3. **Compat mirror dual-write** still needed until clients read projections natively.
4. **Legacy overnight bug** remains on flag-off path.
5. Cleanup GUC must never be set in production app code paths.

---

## 6. GO / NO-GO — WATHEFNI-only production synthetic canary

**NO-GO for executing a production synthetic canary in this wave.**

Reasons:
- Wave 1B code/schema were **not** deployed to production (explicitly banned).
- Staging persistence is proven; that is the exit for Wave 1B.
- A future canary wave may be **GO** only after: production backup → schema migrate on allowlisted synthetic company → deploy modules → `WATHEFNI_ATTENDANCE_AUTHORITY=on` with `…_COMPANIES=<synthetic only>` → `STORE=postgres` → no real clocking/import/QR/GPS/kiosk → kill-switch + rollback drill.

---

## 7. Files

| Path | Change |
|---|---|
| `attendance_authority_postgres.py` | New PG adapter, reconcile, rebuild, Wave 1B DDL |
| `attendance_authority_wave1.py` | Day transactions; PG service selection; schema includes 1B |
| `smoke-test-attendance-authority-wave1b-staging.py` | Staging qualification |
| `ops/migrate-attendance-authority-wave1b.sh` | Safe migrate |
| `ops/rollback-attendance-authority-wave1b.sh` | Safe rollback |

Remote evidence: `/opt/wathefni/staging-evidence/attendance-wave1b-postgres-20260802T022646Z`  
Local evidence: `ops/evidence/attendance-wave1b-postgres-20260802T021813Z`
