# Safe debt (not blockers)

- Alignment tree UI is progressive (on request). Deep multi-level indent beyond two levels is not a default spreadsheet.
- `list_cycle_objectives` membership lookup is per-row (N+1). Acceptable for PT1 canary volume.
- C3 check-in creation is best-effort; `perf_okr_updates` remains the OKR thread if C3 is off.
- `index_ref` `xmax = 0` insert detection is PostgreSQL-specific; uniqueness still guarantees idempotency.
- Employee App update thread is simple text; confidence input is Setup-gated and not shown as a default progress control.
- No native rebuild required (JS/Python overlay only). OTA-eligible for the Employee App.
- Trajectory labels remain uncomputed (PT6).
- Configurable Talent models remain unbuilt (PT2).
