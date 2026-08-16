# Attendance Wave 1C — Production PostgreSQL Authority Synthetic Canary

**Stamp:** `20260802T023448Z`  
**Local evidence:** `ops/evidence/attendance-wave1c-prod-canary-20260802T023106Z/`  
**Remote evidence:** `/opt/wathefni/production-evidence/attendance-wave1c-prod-canary/20260802T023448Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-attendance-wave1c-20260802T023448Z/`

## Scope kept

- Real employee clocking disabled (authority synthetic-only)
- Device import, QR, GPS, kiosk disabled (`WATHEFNI_ATTENDANCE_IMPORT=off`)
- Legacy `attendance_records` path unchanged for real employees
- Authority enabled only for WATHEFNI + strict synthetic key/phone allowlist
- Employees 360, Onboarding, pre-hiring, Wave D unchanged (freeze regressions green)

## Pre-deploy

| Item | Value |
|---|---|
| `app.py` SHA | `e6b670f958f18d32a572a2ae47e80f17e4e397c1b907eadea1f0e3e94cdc6222` |
| `attendance_import.py` SHA | `8565761d1238fe2699fb7e5e02cb8b7d9422b3aa090f117e6fe5383907d1461f` |
| Authority modules | absent |
| WATHEFNI attendance rows | 42 (all `demo_seed=wathefni_v1`) |
| `attendance_punches` | null (not created) |
| Import flag | off / unset |
| Pool | set conservatively to `WATHEFNI_DB_POOL_MAX=8` at deploy |

Backup SHA256SUMS and `ROLLBACK.sh` written under the backup path. Fingerprint CSV of all 42 rows captured.

## Deploy

Surgical patch of production `app.py` + modules:

| File | SHA256 |
|---|---|
| `app.py` | `e4b8643f9d8b2551b6fbc23604bb97ab6089260d1f15336faf6c372c741c63c3` |
| `attendance_authority_wave1.py` | `b556f349e1f1b77cf3363010cadca40efbf160474b928542b2c7aaeab88df5c9` |
| `attendance_authority_postgres.py` | `28fd2cde37d7f4751589839a0a4e4fc20887fb4386ec129c019bea9ec1332203` |
| `attendance_authority_hooks.py` | `834f5220b5ca6b0443794af8ab5db5d072c9a4d45a52589b64b3df28ba41260f` |

### Flags (drop-in `zz-attendance-wave1c-synthetic-canary.conf`)

```
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,W1C-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_DB_POOL_MAX=8
```

### Schema / immutability

- Tables: `attendance_punches`, `attendance_day_projections`, `attendance_payroll_snapshots`, `attendance_authority_events`, `attendance_compat_drift`, `attendance_corrections`
- Triggers: `trg_attendance_punches_immutable`, `trg_attendance_payroll_snapshots_immutable`
- Cleanup/test GUCs absent from normal `app.py` paths (canary check PASS)

## Synthetic canary — PASS 47/0

Synthetic IDs (cleaned after):

| Field | Value |
|---|---|
| employee_key | `WATHEFNI-ATTW1C-926c95ec` |
| phone | `965524926c95` |
| tag | `926c95ec` |
| punch_in | `fa5306ef-bb69-4cf4-bad4-dae991fe5835` |
| projection_id | `376be87d-d4c4-4eb8-8edd-b83de124d89f` |
| snapshot_id | `66d1c355-3ef3-48ea-a61e-63d5af6f2106` |

Proved: normal day (480m), overnight 22:00–06:00, checkout after midnight, multi-session, paid/unpaid breaks, duplicate + concurrent punches (6 threads → 1 created), restart persistence via new store, exact projection rebuild, absence vs late punch race, correction request/approve/reject/dispute, manager self-correction denial, approved leave + safe reversal, payroll snapshot reconcile exact, snapshot/punch immutability, legacy drift quarantine, tenant isolation, manager scope.

### Restart / concurrency

- Restart: projection `376be87d-…` survived new `PostgresAuthorityStore` with worked_minutes=480 and punch_in present
- Concurrent: 6 races → single punch id `c08ebcba-b8f9-4153-b118-4000bd85de96` (1 created / 5 duplicates)

### Payroll reconciliation

- Approved day snapshot → exact Payroll reconcile PASS
- Snapshot immutable PASS; punch append-only PASS
- `snapshot_id=66d1c355-3ef3-48ea-a61e-63d5af6f2106`

### Drift report (synthetic)

```
matched=1 drift_count=1 quarantined=1
kind=field_mismatch
authority status=completed vs legacy status=absent
silent_overwrite=False
```

### Cleanup

- Synthetic punches/projections cleaned (authority tables at 0 after cleanup)
- Demo rows 42/42 fingerprint unchanged
- Four real employees still present
- Legacy path untouched for reals

## Backup / rollback proof

Executed `ROLLBACK.sh` against production backup:

- Live `app.py` SHA restored to `e6b670f9…` (exact match to backup)
- Attendance authority modules removed
- Drop-in removed; ATTENDANCE flags cleared
- Health OK after rollback
- Then redeployed Wave 1C dark canary; freezes re-run green

## Freeze regressions (final)

- Employees 360: **57 passed, 0 failed**
- Onboarding: **54 passed, 0 failed**

Note: missing freeze doc/rule artifacts on prod ops/`.cursor` were restored from repo (pre-existing gap vs prior wave evidence); not caused by authority code.

## Final production state

- Authority on, synthetic-only, WATHEFNI company allowlist, postgres store
- Import off; pool max 8
- Real employees denied by allowlist
- 42 legacy demo rows intact; authority synthetic tables empty post-cleanup
- Real clocking / QR / GPS / kiosk / employee-app clocking **not** enabled
- Attendance UI **not** redesigned

## Separate verdicts

See `VERDICT.txt`.
