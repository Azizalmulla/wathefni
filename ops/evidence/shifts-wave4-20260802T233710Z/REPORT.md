# Shifts Wave 4 — templates & recurring schedules (local/staging)

**Stamp:** `20260802T233710Z`  
**Evidence:** `ops/evidence/shifts-wave4-20260802T233710Z/`  
**Module:** `shifts_templates_wave4.py` **v4.0.0**  
**Scope:** local + staging only. **No production deploy.**

## Template model
- Table `shift_templates`: named windows (same-day / overnight via `ends_next_day`), optional break/role/site/branch/team/position/location/timezone/notes
- Status `active|archived`; `planning_version` bumps on edit (never silently rewrites L0)
- Split schedules = two templates (two L0 authority rows)

## Recurrence / cycle model
- Table `shift_recurrences`: `weekly_weekdays`, `n_on_m_off` (six-on/one-off), `alternating_templates` (day/night weeks)
- Effective start/end, horizon default 90 / max 180
- Targets: employee | team | site | role
- Status: active | paused | ended

## Materialization / regeneration contract
- Preview classes: unchanged, newly_generated, updated_future, conflict, detached, cancelled_held
- Materialize writes `status=scheduled` L0 immediately (no draft/publish)
- Deterministic idempotency: `SHW4|{company}|{recurrence_id}|{employee}|{date}|{template}|{start}|{end}`
- Advisory lock per company+recurrence for concurrent authority
- Regen skips today/history; cancelled never auto-reappears; manual edit sets `regen_detached`

## Override / exception model
- `shift_recurrence_exceptions`: `skip` | `one_off_override` per date
- Manual reschedule/cancel of generated rows → `regen_detached=true`

## API / permission model
- Routes under `/dashboard/posthire/shifts/templates` and `.../recurrences` (+ preview/materialize/pause/resume/end/exceptions)
- Wave 3 real-mutation gate + SHW4 / 965532* synthetic markers
- Manual composer remains available without templates

## Complexity levels
| Level | Status |
|---|---|
| Simple (manual only) | Unchanged — default path |
| Medium (templates + weekly/cycle) | **This wave** |
| Enterprise (rotations/coverage/publish) | **Not built** |

## Test results
- Local Wave 4: NO (`tests/wave4-local.out`)
- Staging Wave 4: NO
- Staging W1: NO · W2: NO · W3 UX: NO
- Freezes: see `tests/freeze-*-local.out` and staging regressions

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · No rotations/publishing/open shifts/PAM · No draft/publish · No production deploy · No real allowlists · Timers/reminders unchanged

## Unresolved blockers
- Production synthetic Wave 4 canary not executed in this wave (by design)
- Team/site/role resolution depends on org assignment / raw_json metadata
- Enterprise rotations / coverage / publishing remain out of scope

## GO/NO-GO for production synthetic Wave 4 canary

| Scope | Verdict |
|---|---|
| Production synthetic Wave 4 canary | **NO-GO** |
| Controlled real HR / manager enablement | **NO-GO** |
| Draft/publish / rotations / open shifts | **NO-GO** |
| Real reminders / timers | **NO-GO** |
| Broad employee-app | **NO-GO** |

