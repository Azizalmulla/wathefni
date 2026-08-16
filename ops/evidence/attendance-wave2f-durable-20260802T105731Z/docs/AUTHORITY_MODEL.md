# Wave 2F Capture-Ops Authority Model

```
┌─────────────────────────────────────────────────────────────┐
│ Capture Ops API / UI (dark)                                 │
│  CAPTURE_OPS=on  CAPTURE_INGEST=off  STORE=postgres|memory  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ attendance_capture_ops adapters                             │
│  registry / queue / health / mapping                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   memory (tests)                    PostgresCaptureStore
                                              │
         ┌────────────────────────────────────┼────────────────────────┐
         ▼                                    ▼                        ▼
   sites/devices/connectors          health + events + checkpoints   remediation
   credentials.sealed_ref (Fernet)   (restart-safe)                  + idempotency
         │                                    │                        │
         │                                    │                        ▼
         │                                    │              approve/reject (row_version)
         │                                    │                        │
         │                                    │                        ▼
         │                                    │              replay_ledger (exactly-once)
         │                                    │                        │
         │                                    └───────────┬────────────┘
         │                                                ▼
         │                                   CapturePipeline.ingest_canonical
         │                                                │
         │                                                ▼
         │                                   Wave 1 Attendance Authority
         │                                   (attendance_punches, projections)
         │                                                │
         └──────── reconcile_with_authority() ◄───────────┘
```

Secrets never appear as plaintext columns; API responses use `[REDACTED]`.
