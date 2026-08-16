# Shifts Wave 5 — draft/review/publish, open shifts, coverage (local/staging)

**Stamp:** `20260803T004110Z`  
**Evidence:** `ops/evidence/shifts-wave5-20260803T004110Z/`  
**Module:** `shifts_publish_wave5.py` **v5.0.0**  
**Scope:** local + staging only. **No production deploy. No real employees.**

## Schedule-period & version model
- `shift_schedule_periods`: date range, timezone, site/branch/team scope, `require_publish`, `row_version`
- `shift_schedule_versions`: immutable published lineage (`based_on` / `rollback_of`), fingerprint, review_diff, coverage_snapshot, publish idempotency key
- `shift_schedule_draft_rows`: draft-only planned rows; never operational until publish
- L0 provenance columns: `schedule_period_id`, `schedule_version_id`, `schedule_source`

## State machine
`draft` → `in_review` → `approved` → `published` (via publish endpoint)  
Also: back to `draft`, `cancelled`; prior published → `superseded` (non-destructive)

## Publish & rollback contract
- Advisory lock per company+period; optimistic `expected_row_version`; idempotency key
- Drafts never write Attendance/Leave/reminders/Payroll
- Publish materializes/promotes L0; unchanged cloned rows retarget provenance (no duplicate)
- Historical/started (`shift_date < today`) locked/skipped
- Rollback = new audited draft from prior published version → approve → publish
- Conflict bulk acknowledge/cancel on draft rows before publish
- Mid-publish commits avoid DDL deadlock with `create_fn` schema ensure

## Open-shift model
- Unassigned needs by date/time/role/site/branch/team; same-day + overnight
- Claim → scoped approve/reject; self-approval denied; one winner; losers rejected
- Direct HR/manager assign; gates via Wave 4 conflict evaluator (+ create_fn overlap) → canonical L0

## Coverage model
- Min staffing by role/team/branch/site + time band; effective dates; overnight windows
- Classes: covered | understaffed | overstaffed | unresolved_open_shift | unavailable_employee
- Default `warn`; `block` can stop publish. No money calculations.

## Permission / approval matrix
- HR owner: period CRUD, draft, review, publish, rollback, open-shift decide, coverage CRUD
- Manager scoped: draft/submit, scoped open-shift decide, coverage read
- Employee: claim only; self-approval false
- Simple companies: direct L0 with `require_publish=false`
- Medium/enterprise: `require_publish=true`

## UX architecture
- Calendar-aligned Shifts workspace: **Publish & coverage** tab when Wave 5 enabled
- Surfaces periods (draft/published status), open shifts, coverage rules without cluttering simple companies
- EN/AR copy + honesty banner; direct board assignment remains default path

## Test results
- Local Wave 5 honesty: YES (DB deferred — `LOCAL_DB_UNAVAILABLE`)
- Staging Wave 5: **62 passed, 0 failed** (`tests/staging-regressions.out`, confirmed `tests/wave5-rerun-after-w2-hygiene.out`)
- Staging W4: **54/0**
- Staging W1: **90/0** · W3 UX: **43/0**
- Staging W2: initially **81/1** due to leftover SHW2 Ramadan seasonal policies from prior waves (`ramadan outside effective dates quiet`); after SHW2 synthetic hygiene → **82/0**
- Freezes: E360/ONB/ATT/LEAVE green

## Unresolved blockers
- Production synthetic Wave 5 canary **not run** in this wave (staging-only by design)
- Advanced rotations / remote hitches / PAM / real reminders / Payroll money: out of scope
- Dashboard publish panel is read/list-first; full create/review/publish action UX can deepen later
- Staging W2 seasonal leftovers can flake regressions if prior SHW2 runs leave enabled Ramadan policies — hygiene before coexist proves

## GO/NO-GO — production synthetic Wave 5 canary
**Verdict: GO**

| Gate | Result |
|---|---|
| Staging Wave 5 prove | **YES** (62/0) |
| Wave 1–4 regressions | W1=YES W2=YES (post-hygiene) W3=YES W4=YES |
| Production synthetic canary (this wave) | **NOT RUN** — staging qualifies readiness only |
| Real employees / reminders / Payroll | **NO-GO** |

**Gate name:** `PROD_SYNTHETIC_WAVE5_PUBLISH_GO` — ready to plan a production *synthetic-only* Wave 5 canary (SHW5 / 965534*). Not an authorization for real employee publishing.
