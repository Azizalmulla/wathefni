# Migration & Sync P5.1 — Scheduler + real SFTP

| Field | Value |
|---|---|
| Stamp | `20260807T104900Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Contract | `employee_migration_sync_p5_1_scheduler_sftp` @ `5.1.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P5_1_SCHEDULER_SFTP.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p5_1-20260807T104900Z/ROLLBACK.sh` |
| Dashboard | `PostHire-B2-S5cGs.js` |

## Scheduler architecture

```
systemd timer (1 min)
  → migration-connector-scheduler-worker.py
  → claim_due_connections (FOR UPDATE SKIP LOCKED + sync_lock_until)
  → run_sync(trigger=scheduled)  # same P5 pipeline as Sync now
  → next_sync_at = now + cadence | retry_after backoff on transient failure
```

Paused/disconnected never claimed. Missed runs catch up once (no stampede).

## Real SFTP proof

In-process paramiko SFTP test server → `sftp` connector → foundation preview/commit.

| Check | Result |
|---|---|
| Initial file sync | PASS |
| Second new file incremental | PASS |
| Duplicate same file → no re-apply | PASS |
| Source update classification | PASS |
| Unknown/custom fields retained | PASS |
| Scheduled execution without manual | PASS |
| Missed-run/restart recovery | PASS |
| Pause prevents execution | PASS |
| Transient failure retries/backoff | PASS |
| Malformed file explicit + recoverable | PASS |
| Sync-run history | PASS |
| P1–P5 regressions | PASS |

## Remaining gaps

- `api_stub` still stub (no vendor SAP/Oracle without customer requirement)
- Full cron expressions limited to interval / simple `*/N` / hourly / daily (interval_minutes is primary)
- Credential Fernet falls back to sealed plainhex when mailbox key unset
- Optional remote archive is opt-in; default never mutates customer source files
- P6 leavers / Auth Wave 2 Phase 6 — not started
