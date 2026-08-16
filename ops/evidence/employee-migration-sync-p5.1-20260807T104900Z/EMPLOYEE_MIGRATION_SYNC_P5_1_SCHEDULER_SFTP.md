# Employee Migration & Sync P5.1 — Scheduler + real SFTP

Contract: `employee_migration_sync_p5_1_scheduler_sftp` @ `5.1.0`  
Builds on frozen P1–P5. **Same** foundation preview/commit pipeline — no second apply engine.

## Scheduler architecture

```
systemd timer (1 min)
  → migration-connector-scheduler-worker.py
  → claim_due_connections (FOR UPDATE SKIP LOCKED + sync_lock_until)
  → run_sync(trigger=scheduled)   # identical path to Sync now
  → deterministic next_sync_at / retry_after backoff
```

- Due = `status=active` · `schedule_enabled` · `next_sync_at<=now` · lock expired · `retry_after` cleared
- Paused / disconnected never claimed
- Missed runs catch up **once** (advance from now + cadence), no stampede
- Transient failures: exponential backoff on `retry_after` without duplicate apply

## SFTP / file-feed

```
External HR export → SFTP drop
  → list (pattern) · stability window · sha256 identity
  → download → CSV/XLSX parse → foundation preview/commit
  → processed_files ledger (never re-apply same content)
```

- Password and/or private key sealed via P5 secrets table
- Host-key fingerprint required in production (canary may set allow flag)
- Source files immutable by default; optional `archive_remote_dir` only
- One bad file among good → partial + explicit `files_failed`
- Remote delete ≠ employee delete (P6)

## Boundaries

`api_stub` remains stub · no P6 · no Auth Wave 2 Phase 6 · no invites / auto-onboarding / auto-deactivation
