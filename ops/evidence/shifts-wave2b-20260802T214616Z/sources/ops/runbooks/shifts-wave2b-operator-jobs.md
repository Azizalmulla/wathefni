# Shifts Wave 2B — operator jobs runbook (synthetic-only)

**Scope:** production WATHEFNI · `WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1` · markers **SHW2B** / **965530***  
**Never run against real employees.** Jobs filter synthetic subjects and use advisory locks.

## Kill switches

| Switch | Effect |
|---|---|
| `WATHEFNI_SHIFTS_INTEGRITY_JOBS=0` | Disables reminder drain + lifecycle/leave recon jobs |
| Remove Wave 2B systemd drop-in + restart | Disables Wave 2 integrity features |
| `WATHEFNI_SHIFTS_INTEGRITY_WAVE2=0` | Disables Wave 2 module path |

## Job schedule (canary / operator-driven)

| Job | Lock key | Suggested cadence | Bound |
|---|---|---|---|
| Reminder drain | `820260201` | every 5–15 min (manual/`run-shifts-wave2b-jobs.sh reminder`) | `limit≤200` |
| Lifecycle reconciliation | `820260202` | after employment fact changes / hourly | `limit≤200` |
| Leave reconciliation | `820260203` | after leave approvals / hourly | `limit≤200` |

Overlapping runs: `pg_try_advisory_lock` → second runner returns `job_lock_held` (no concurrent work).

## Commands (on VPS, production env loaded from service)

```bash
cd /opt/wathefni/orchestrator
bash ops/run-shifts-wave2b-jobs.sh reminder --limit 50
bash ops/run-shifts-wave2b-jobs.sh lifecycle --limit 100
bash ops/run-shifts-wave2b-jobs.sh leave --limit 100
bash ops/run-shifts-wave2b-jobs.sh terminal-failures
```

## Terminal failure visibility

- Table: `shift_reminder_queue` where `status='terminal_failed'`
- API/scan dry_run returns `terminal_failures`
- Investigate `last_error`, fix delivery, then re-enqueue only for synthetic shift windows

## Safety rules

1. Jobs must not cancel/delete assignments — recon **flags only**.
2. Resolution requires audited `acknowledge` or `cancel` (`reconcile_cancel`).
3. Reminder drain must not claim/send for non-synthetic employees under synthetic-only.
4. Keep `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off`.
5. No Payroll money / Leave balance mutation.
