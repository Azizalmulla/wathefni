# Attendance Wave 2F — Durable Capture-Ops Authority (local/staging)

**Stamp:** `20260802T105731Z`  
**Scope:** local/staging only — **no production deploy**, no customer device, no real punch ingest, no QR/GPS/kiosk.  
**Evidence root:** `ops/evidence/attendance-wave2f-durable-20260802T105731Z/`

## Verdict

| Gate | Result |
|------|--------|
| Staging durable Postgres capture-ops | **PASS** (smoke **41/0**) |
| Restart-safe state (store + HTTP host restart) | **PASS** |
| Checkpoint exactly-once + advance | **PASS** |
| Unknown mapping survives restart | **PASS** |
| Approve/reject/replay idempotent + concurrent fail-closed | **PASS** |
| Secrets absent from DB / evidence leak scan | **PASS** |
| Replay → Wave 1 authority exactly once + reconcile | **PASS** |
| Wrong-tenant / manager self / scope denied | **PASS** |
| Authenticated EN/AR desktop+mobile UI screenshots | **PASS** (staging session; Capture Ops panel visible) |
| Employees 360 + Onboarding freeze regressions | **PASS** (local **57/0** and **54/0**) |
| Production dark persistence deploy | **CONDITIONAL GO** (see below) |
| Customer read-only compatibility pilot | **NO-GO** |

## PostgreSQL schema & authority model

**Activation:** `WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres` (memory remains default for unit tests).

**Authority owner:** `PostgresCaptureStore` (`attendance_capture_postgres.py`), wired through `attendance_capture_ops.py` adapters. Wave 1 Attendance authority remains separate (`attendance_punches` / day projections); capture-ops reconciles via `attendance_capture_replay_ledger` ↔ punches.

### Tables

| Table | Role |
|-------|------|
| `attendance_capture_sites` | Tenant sites |
| `attendance_capture_devices` | Terminal SN ownership (cross-tenant SN denied) |
| `attendance_capture_connectors` | Connector registry + optimistic `row_version` |
| `attendance_capture_credentials` | **Fernet sealed_ref only** (no password/token columns) |
| `attendance_capture_health` | Current connector health |
| `attendance_capture_health_events` | Lag/offline/recovery history |
| `attendance_capture_checkpoints` | Durable resume checkpoint (duplicate = no-op) |
| `attendance_capture_mappings` | Device-user → employee mapping |
| `attendance_capture_quarantine` | Quarantine records |
| `attendance_capture_remediation` | Open/approved/rejected remediation + `row_version` |
| `attendance_capture_idempotency` | Durable enqueue/action idempotency |
| `attendance_capture_audit_events` | Immutable audit (trigger) |
| `attendance_capture_replay_ledger` | Append-only exactly-once replay (trigger) |

### Concurrency & integrity

- Optimistic concurrency on connectors and remediation (`stale_row_version` fail-closed).
- Mapping approve is single-transaction (FOR UPDATE + mapping upsert + status bump).
- Replay reserves ledger row (`pending` → `accepted`); duplicate source_event_id short-circuits.
- Audit/replay mutations blocked unless `wathefni.allow_capture_cleanup=1` (staging cleanup only).

## Migration / rollback contract

| Script | Contract |
|--------|----------|
| `wathefni-orchestrator/ops/migrate-attendance-capture-wave2f.sh` | Requires `WATHEFNI_ENV≠production`, `ACK_DB≠wathefni`; applies DDL; asserts tables + immutability triggers; asserts no plaintext secret columns |
| `wathefni-orchestrator/ops/rollback-attendance-capture-wave2f.sh` | Staging/local only; refuses residual non-`ATTW2F*` rows unless `FORCE_DROP=1`; drops Wave 2F tables under cleanup GUC |

Staging migrate evidence: `remote/tests/migrate.out` → `MIGRATE_OK`.

Staging systemd drop-in (staging service only):  
`/etc/systemd/system/wathefni-orchestrator-staging.service.d/attendance-capture-wave2f.conf`  
Flags: `CAPTURE_OPS=on`, `CAPTURE_STORE=postgres`, **`CAPTURE_INGEST=off`**, authority synthetic-only.

## Restart & concurrency evidence

| Proof | Artifact |
|-------|----------|
| Smoke (process-new store instance) | `remote/tests/qualify-staging-smoke.out` — **41 pass / 0 fail** |
| Machine-readable | `remote/tests/qualification-staging.json` |
| HTTP host restart | `remote/tests/restart-http-proof.out` — `RESTART_HTTP_PROOF_OK` (sites/remediation counts preserved; `store_mode=postgres`) |
| Concurrent approve | smoke: exactly one success; other `stale_row_version` / `item_not_open` |
| Checkpoint | health-synced write + duplicate no-op + advance; survives new store instance |
| Leak scan | `remote/tests/leak-scan.json` — **ok** |

## Authenticated UI screenshots

Staging dashboard-dist updated **staging-only** (backed up under `dashboard-dist.bak-wave2f-*`) to include Capture Ops panel. Screenshots minted via owner session against `127.0.0.1:8011`:

- `screenshots/capture-ops-en-desktop.png` / `en-mobile.png`
- `screenshots/capture-ops-ar-desktop.png` / `ar-mobile.png` (RTL + Arabic copy)
- Mapping-tab extras: `capture-ops-mapping-{en,ar}-{desktop,mobile}.png`
- `screenshots/manifest.json` — `authenticated: true`, `fixture_screenshots: false`, `store_mode: postgres`

## Freeze regressions

| Suite | Result |
|-------|--------|
| `smoke-test-employees360-freeze-regression.py` | **57 passed, 0 failed** (`tests/freeze-employees360.out`) |
| `smoke-test-onboarding-freeze-regression.py` | **54 passed, 0 failed** (`tests/freeze-onboarding.out`) |

## Remaining blockers

1. **Production not migrated** — Wave 2F schema/drop-in must not be applied to `wathefni` until an explicit production dark persistence change window.
2. **`CAPTURE_INGEST` must stay off** — approve maps only in UI; replay to authority is lab-gated; real punches still banned.
3. **No customer device / BioTime LAN** — registry ownership + sealed creds proven synthetically only.
4. **Screenshot seed POST intermittently returns 401** from the Playwright helper process (GET overview OK; restart-proof seed OK). Workaround: fall back to durable rows already present. Does not affect authority proofs.
5. **Customer read-only compat pilot** still needs: approved customer, read-only network path, secrets ops runbook live, and ingest remaining off — not started.

## GO / NO-GO

### Production dark persistence deployment
**CONDITIONAL GO** — allowed only as a follow-on change that:
- migrates capture-ops tables on production DB under an explicit ACK,
- sets `CAPTURE_STORE=postgres` + `CAPTURE_OPS=on` with **`CAPTURE_INGEST=off`**,
- keeps authority synthetic-only / no real clocking,
- does **not** connect a customer device.

Not executed in this wave.

### Future customer read-only compatibility pilot
**NO-GO** — durable store is ready on staging, but customer connectivity, read-only compat acceptance, and operational secret handling for a real tenant are not proven. Remain on synthetic/lab until a dedicated pilot wave.

## Hard bans observed

- No production Wave 2F deploy of ingest or device connectivity
- No real punch ingestion
- No QR / GPS / kiosk enablement
- Frozen Employees 360 / Onboarding / pre-hire surfaces unchanged (freeze green)
