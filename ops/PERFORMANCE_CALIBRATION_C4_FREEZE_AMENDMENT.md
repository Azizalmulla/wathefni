# PERFORMANCE_CALIBRATION_C4_FREEZE_AMENDMENT

**Slice:** Wave 4 C4 — Rating Aggregation + Performance Calibration  
**Stamp:** `PERFORMANCE_CALIBRATION_DEV_FULL_PASS`  
**Status:** QUALIFIED / FROZEN after staging prove — stop for owner review before C5  
**Module:** `wathefni-orchestrator/performance_calibration_c4.py`  
**Flags:** `WATHEFNI_PERFORMANCE_CALIBRATION_C4` + `WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES` (empty = nobody)  
**Shared kill:** `WATHEFNI_PERFORMANCE_KILL`

## Frozen authority

C4 owns:

1. Versioned `perf_calc_policies` + deterministic `perf_pre_calibration_results` (replayable from frozen inputs)
2. Explicit missing/not-observed semantics (`exclude_from_denominator` | `block_finalization` | `neutral_default`)
3. Scale-snapshot aggregation (numeric/labeled/normalized) — no universal 1–5; later scale edits do not rewrite history
4. Calibration sessions (`draft→prepared→in_session→completed→locked|cancelled`) with frozen population
5. Append-only `perf_calibration_adjustments` (prior/new/actor/reason/version); distribution guidance vs hard constraint + audited exceptions
6. Separate layers: submitted evidence → pre_calibration_result → calibrated/final_result
7. Visibility: provisional hidden from employees by default; raw 360 stays redacted; sensitive permission gate
8. Lock/publish immutability + audited post-lock amendment only

## Explicit non-goals (do not reopen into C4)

- Talent potential / HiPo / 9-box / succession / retention risk / talent rankings  
- Assumed bell-curve / silent forced distribution  
- Reopening C1–C3 for safe debt  
- Assistant mutations  

## Next

C4 frozen and owner-accepted 2026-08-12. C5 may proceed; do not reopen C1–C4.
