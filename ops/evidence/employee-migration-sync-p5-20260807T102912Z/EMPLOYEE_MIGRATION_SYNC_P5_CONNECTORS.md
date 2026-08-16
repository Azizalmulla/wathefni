# Employee Migration & Sync P5 — Real Connected Systems

Contract: `employee_migration_sync_p5_connectors` @ `5.0.0`  
Builds on frozen P1–P4. **Same** batch/row/provenance/Needs-review + 3-layer field model.

## Architecture

```
External HRIS/ERP/API/SFTP/file feed
        │  connector contract (kind-specific fetch)
        ▼
employee_migration_connections (+ sealed secrets)
        │
        ▼
employee_migration_sync_runs  (cursor, counts, status, errors)
        │  materialize CSV bytes
        ▼
preview_or_replay_import → commit_import_batch
        │
        ▼
canonical Wathefni records (P1–P4 authority unchanged)
```

Wathefni remains canonical once a batch is accepted. Connectors never write hub
employees, bank-effective, verified identity, or leave/payroll authority directly.

## Connector kinds (common contract)

| Kind | Role in P5 |
|---|---|
| `deterministic_canary` | Safe WATHEFNI qualification connector (fixture + watermark) |
| `scheduled_csv` | Scheduled/file-style feed contract (config path or inline fixture) |
| `api_stub` | Placeholder for future vendor API connectors |
| `sftp_stub` | Placeholder for future SFTP connectors |

Vendor-specific SAP/Oracle adapters plug in as new kinds without forking the pipeline.

## Sync-run model

Each run records: connection · trigger (`manual`/`scheduled`/`retry`) · started/finished ·
cursor before/after · records fetched · create/update/unchanged/review/failed ·
status · error summary · linked `batch_id`.

Retries are idempotent via content sha + foundation batch replay.

## Authority

All P2/P4 rules apply. External data never silently overwrites higher-authority
native Wathefni state. Missing fields ≠ delete unless the connector contract
explicitly guarantees deletion semantics (P5 default: not supplied). Lifecycle
deletion signals are **captured only** — P6 owns deactivation policy.

## Security

- Credentials in `employee_migration_connection_secrets` (Fernet; never in API/UI)
- Company isolation + `employees.manage`
- Audit connect / configure / pause / resume / disconnect / manual sync
- Sensitive preview values stay masked via existing import preview

## Boundaries

No invitations · no auto-onboarding outside P3 · no auto-deactivation · no Bank ESS bypass · no P6 · no Auth Wave 2 Phase 6.
