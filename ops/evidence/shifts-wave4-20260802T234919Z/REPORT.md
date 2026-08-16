# Shifts Wave 4 — templates & recurring schedules (local/staging)

**Stamp:** `20260802T234919Z`  
**Evidence:** `ops/evidence/shifts-wave4-20260802T234919Z/`  
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
- Session advisory lock per company+recurrence; commit after classify so sibling `create_fn` connections can run ensure-DDL without deadlock
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

## Staging prove results
| Suite | Result | Evidence |
|---|---|---|
| Wave 4 smoke | **54/0** (`W4_RC=0`) | `tests/staging-w4-final.out` |
| Wave 3 UX | **43/0** (`W3_RC=0`) | `tests/staging-prior-waves-freezes.out` |
| Wave 1 | **90/0** (`W1_RC=0`) | same |
| Wave 2 | **82/0** (`W2_RC=0`) | same |
| E360 freeze | **57/0** | same |
| Onboarding freeze | **54/0** | same |
| Attendance freeze | **22/0** | same |
| Leave freeze | **34/0** | same |

Matrix covered on staging (synthetic SHW4 only): same-day + overnight + split templates; weekly / six-on-one-off / alternating; preview counts; idempotent + concurrent materialize; pause/resume/end; skip exception; cancel held; manual detach; template edit without silent L0 rewrite; no Attendance / Leave balance / Payroll mutation.

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · No rotations/publishing/open shifts/PAM · No draft/publish · No production deploy · No real allowlists · Timers/reminders unchanged

## Unresolved blockers (documented, not staging blockers)
- Production synthetic Wave 4 canary **not executed** in this wave (by design — separate authorized pack)
- Team/site/role resolution depends on org assignment / `raw_json` metadata; incomplete metadata → preview `skipped_target` / empty expand
- Concurrent materialize uses Postgres session advisory lock; multi-host OK only with shared DB (true for Wathefni)
- Enterprise rotations / coverage / publishing remain out of scope

## GO/NO-GO for production synthetic Wave 4 canary

Staging qualify is green on the full Wave 4 matrix plus W1–W3 and freeze regressions.

| Scope | Verdict |
|---|---|
| Production synthetic Wave 4 canary | **GO** (cleared to run when separately authorized; **not deployed / not executed here**) |
| Controlled real HR / manager enablement | **NO-GO** |
| Draft/publish / rotations / open shifts | **NO-GO** |
| Real reminders / timers | **NO-GO** |
| Broad employee-app | **NO-GO** |
| Production deploy of Wave 4 | **NO-GO** (out of scope this wave) |
