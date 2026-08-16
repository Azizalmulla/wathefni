# Shifts Wave 2 — Schedule Integrity (staging)

**Stamp:** `20260802T212437Z`  
**Scope:** local/staging only — no production deploy, no real-employee mutation enablement, no UI redesign, no templates/recurring/rotations/publishing/open shifts/PAM, no Payroll money, no Leave balance mutation.

**Verdict:** Staging Wave 2 prove-out **GO**. Production synthetic Wave 2 canary **NO-GO** until a separate authorized canary pack (Wave 2B) is requested.

---

## Models

### Version / history model
- Current-row authority remains `shift_assignments`.
- Immutable append-only history in `shift_assignment_versions` (`version_no`, `is_current`, `effective_at`, `superseded_at`, `reason_code`, `snapshot`, `lineage`, `previous_employee_key`).
- Assignment pointer columns: `current_version_no`, `schedule_reason_code`, `lineage_json`.
- Reason codes: `created`, `rescheduled`, `cancelled`, `reassigned_swap`, `reassigned_manual`, `reconcile_ack`, `reconcile_cancel`, …
- Proven: multi-reschedule history (≥3 versions), one current row, priors superseded, stale `expected_updated_at` → 409.

### Availability + swap state models
- Availability: existing `employee_availability_requests` (`requested` → `approved`/`rejected`) via Wave 2 `decide_availability` (idempotent replay).
- Conflict modes on create/reschedule (`shift_integrity_settings.availability_conflict_mode`): `warn` | `require_ack` | `block`.
- Swap: existing `shift_swap_requests`; approve path gates overlap, lifecycle, leave; records `reassigned_swap` versions with `previous_employee_key` + lineage (`swap_id`, from/to keys).
- Proven: request/decide/ack/block/warn; swap approve/reject/replay; overlap/lifecycle/leave denial; employee lineage preserved.

### Attendance linkage contract
- Wave 2 `match_shift_for_attendance` (read-only; never mutates Attendance or Shifts authority rows).
- Deterministic: exact `shift_id` → match; else same-day + prior-day overnight candidates.
- Overnight: window may cover next calendar day punch.
- Split: date-only with multiple same-day rows → `ambiguous_shift_match` (fail closed); punch time selects covering window.
- Wired into `active_shift_for_attendance` when Wave 2 enabled.

### Reminder delivery model
- Durable `shift_reminder_queue` with `idempotency_key` (shift_id|date|start|end), statuses `pending|claimed|sent|failed|terminal_failed|cancelled`.
- Claim uses `FOR UPDATE SKIP LOCKED`; retry/backoff via `next_attempt_at`; terminal failures listed for ops.
- Reschedule cancels pending + enqueues new key; duplicate enqueue is no-op.
- Proven: retry without duplicate delivery; terminal failure visibility on dry_run scan.

### Seasonal policy model
- `shift_seasonal_policies`: `ramadan` | `midday_restriction` | `custom`.
- Configurable `effective_start`/`effective_end`, optional `site_key`/`branch_key`, `enforcement_mode` default **warn** (block only when configured).
- Site-scoped policies apply only when assignment site matches.
- Proven: Ramadan effective-date warn; midday site match/miss; optional block deny on create.

### Reconciliation model
- `shift_reconciliation_flags`: `lifecycle_fact_change` | `approved_leave_conflict` (also availability/seasonal types reserved).
- Jobs **flag only** — never silent cancel/delete.
- Resolution requires audited `acknowledge` or `cancel` (`reconcile_cancel` soft-cancel + version).
- Hub employment fallback on key-only stubs (swap/recon paths).
- Proven: lifecycle + leave flags; no silent cancel; ack + audited cancel.

---

## Gate / honesty

| Control | Value |
|---|---|
| Env gate | `WATHEFNI_SHIFTS_INTEGRITY_WAVE2` (default on when `WATHEFNI_ENV≠production`) |
| Module version | `2.0.0` |
| Wave 1 dependency | `WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1` |
| `payroll_money` | false |
| `leave_balances_mutated` | false |
| Owns | planned intervals only |
| Does not own | worked time (Attendance), leave decisions, overtime/money (Payroll) |

Migrate script refuses `WATHEFNI_ENV=production` and `ACK_DB=wathefni`.

---

## Tests and evidence

| Suite | Result |
|---|---|
| Wave 2 smoke (`smoke-test-shifts-schedule-integrity-wave2.py`) | **82 / 0** |
| Wave 1 regression smoke | **90 / 0** |
| Employees 360 freeze | **57 / 0** |
| Onboarding freeze | **54 / 0** |
| Attendance freeze | **26 / 0** |
| Leave freeze | **35 / 0** |
| Staging migrate | `SHIFTS_W2_MIGRATE_OK` on `wathefni_staging` |
| Staging health | `wathefni-orchestrator-staging` active `:8011` |

Evidence root: `ops/evidence/shifts-wave2-20260802T212437Z/`

Source SHAs (local tree at qualify):
- `shifts_schedule_integrity_wave2.py` `8f79189923dfe04c3e338677a730a84e6a12a1affc089d41b9e47db65f007321`
- `shifts_authority_wave1.py` `0f26fa3c65e4a81976f4ddec4ee515a4b66727d6d9e72599d81ca66ad7582593`
- `smoke-test-shifts-schedule-integrity-wave2.py` `ebc3ebfd497843bac44e66b956c1aadb422ecdcbdc902f1ce27218929bf02656`
- `app.py` `85acc3f015c7176da7f2c74bbf54239b6884bcf3ea49487ecc015f86b72cf470`

---

## Remaining blockers (before prod synthetic Wave 2 canary)

1. **No authorized Wave 2B prod canary pack yet** (SYNTHETIC_ONLY markers, rollback, residual cleanup, dual-run evidence).
2. **Prod still runs Wave 1B synthetic posture** — Wave 2 must not flip prod gates without explicit canary auth.
3. **Operator jobs not cron-wired** — lifecycle/leave reconciliation and reminder drain are callable; production schedule/ops runbook not yet defined.
4. **Dashboard/UI** not updated for availability ack chips, seasonal warnings, recon queue, or reminder terminal board (API/backend only this wave).
5. **Templates / recurring / publish / rotations / open shifts / PAM** intentionally out of scope.
6. **Real-employee / HR / manager / Talal schedule integrity rollout** remains NO-GO until separate auth after synthetic canary.

---

## GO / NO-GO

| Decision | Status |
|---|---|
| Staging Wave 2 schedule integrity | **GO** |
| Production deploy of Wave 2 | **NO-GO** (not requested; migrate refuses prod) |
| Production **synthetic** Wave 2 canary | **NO-GO** pending separate Wave 2B authorization |
| Real-employee schedule integrity | **NO-GO** |
| Templates / recurring / publish / rotations | **NO-GO** (out of scope) |

**Bottom line:** L0 assignment model is operationally reliable on staging for history, availability, swaps, Attendance matching, reminders, seasonal warn foundations, and non-destructive reconciliation. Ready for a future synthetic prod canary only after explicit Wave 2B auth — not enabled here.
