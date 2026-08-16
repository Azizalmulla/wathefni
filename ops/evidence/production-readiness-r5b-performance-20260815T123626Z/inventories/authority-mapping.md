# R5B authority mapping

HTTP and clients are adapters. No second Performance model. No frontend formulas for objective progress, KR rollup, review status, or final rating.

| Product concept | Canonical library | Persistence | Adapter |
|---|---|---|---|
| Objectives / goals | `performance_goals_c1` | `perf_objectives` + history | `/objectives`, `/app/performance/objectives` |
| Measures | `performance_goals_c1` | `perf_measures` | `/measures` |
| Key Results | `performance_goals_c1` | `perf_key_results` | `/objectives/{id}/key-results` |
| Progress / rollup | `compute_progress`, `objective_rollup`, `record_progress` | `perf_progress` | `/progress` — decorative `progress_pct` rejected |
| Review cycles | `performance_reviews_c2` | `perf_cycles` | `/cycles` |
| Launch snapshot | `snapshot_frozen` on launch | cycle snapshot JSON | `/cycles/{id}/launch`, `/cycles/{id}/snapshot` |
| Self review | C2 layer `self` | `perf_reviews` | submit with reviewer role self |
| Manager review | C2 layer `manager` | `perf_reviews` | submit with reviewer role manager |
| 360 input | C2 `get_360_aggregate` | assignments + responses | `/360`, employee submit when assigned |
| Competency evidence | `performance_feedback_c3` | versioned framework / mappings | `/competencies` — honest empty when OFF |
| Check-ins / feedback | C3 | `perf_check_ins` | `/check-ins`, `/feedback` |
| Development actions | C3 (`require_learning` default false) | plans + actions | `/development` |
| Calibration | `performance_calibration_c4` | sessions + adjustments | `/calibration` |
| Pre-calibration outcome | C4 distinct from calibrated | session items | session detail |
| Calibrated outcome | C4 adjust | session items | `/calibration/{id}/adjust` |
| Sealed final | C2 `close_cycle` + C4 lock | sealed rows | `/cycles/{id}/close`, `/calibration/{id}/lock` |

## Frozen rules preserved

- Launch snapshots participant / form / config truth. Later org / manager / template edits do not rewrite an active or historical cycle (`attempt_mutate_launched_setup` rejected).
- Distinct ratings never collapse into one mutable field: self, manager, 360 evidence, pre-cal, calibrated, sealed final.
- Sealed / finalized ratings cannot be silently edited.
- Competencies independently configurable. Performance works with competencies OFF.
- Learning completion ≠ development completion. `require_learning` / `require_talent` default false.
- `strip_talent()` removes `hipo`, `potential`, `nine_box`, succession, Talent score from every HTTP payload.
- High final Performance rating does not imply HiPo.

## Runtime gate

Commercial key: `performance`. Triple gate: env flag + allowlist + company settings.

After R5B, empty allowlist + `customer_enableable` admits via `performance_runtime_allowlist_admits`. Kill switch and `WATHEFNI_PERFORMANCE_*_C{1-4}` still win.
