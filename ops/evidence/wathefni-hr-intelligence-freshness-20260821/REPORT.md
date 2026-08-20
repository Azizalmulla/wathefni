# WATHEFNI HR Intelligence automatic freshness — production qualification

**Stamp:** `20260820T213939Z`  
**Verdict:** PASS  
**Rollback:** `/opt/wathefni/backups/wathefni-hr-intelligence-freshness-20260820T213312Z/ROLLBACK.sh`  
**Worker:** `wathefni-hr-intelligence-projection.timer` (every 1 minute, oneshot)  
**HR Web Wave 5:** not started

## Model

Canonical domain write → existing domain event / ledger / audit table → tenant-scoped idempotent outbox → C2–C5 projection upserts. No second SoT, no frontend rebuild polling, no database CDC.

## Event sources wired

| Source | Existing tables tailed | Projection |
|---|---|---|
| Employees / workforce | `employee_lifecycle_events`, `employees.updated_at` | C2 employment periods |
| Recruiting | `application_lifecycle_events`, `applications.updated_at` | C3 applications / requisitions |
| Attendance | `attendance_authority_events`, `attendance_day_projections` | C4 attendance days |
| Leave | `leave_ledger` (append-only SoT) | C4 leave ledger facts |
| Shifts | `shift_assignments` | C4 shift assignments (hours from start/end only) |
| Performance / OKRs | `performance_goals_c1_audit`, `perf_okr_alignment_events` | C5 objectives / KRs |
| Talent / succession | `talent_profile_c5_audit`, `talent_succession_c6_audit` | C5 profiles / roles / nominations |

First live drain after flags: workforce 232, recruiting 161, attendance 267, leave 56, shifts 1278, performance 11, talent 9 — all `done`, zero dead-letters.

## Freshness guarantees

- Per-company / per-family `data_as_of`, lag, pending/failed counts, `guaranteed_current`.
- KPI evaluate / overview / bootstrap attach this blob. Stale or error overlay is never labelled current.
- SLA default 180s. Pending outbox within SLA is not guaranteed current.
- Payroll money family is always `unavailable` / not current (`payroll_not_sealed`).
- Missing employment dates are skipped, never invented.
- Missing shift hours are skipped, never assumed as 8h.

## Reconciliation / rebuild

- Outbox retries with exponential backoff; dead-letter after 8 attempts. Per-item savepoints so one SQL failure cannot abort the batch.
- Periodic reconcile (default 15 min) re-enqueues current SoT identities.
- Controlled full rebuild: `hr-intelligence-projection-worker.py --rebuild COMPANY [--family workforce]`.
- Worker exit 0 after a completed pass; retryable item failures stay in the outbox.

## Production tests

Local: `smoke-test-hr-intelligence-projection.py` 29/29. C2 74/74. C6 56/56.

Live WATHEFNI canary (`HINTL-FRESH-20260820T213939Z`):

- Bootstrap freshness present, `no_frontend_rebuild`, EN + AR overview.
- Canonical employee + leave_ledger writes → incremental drain → `workforce.headcount.active_heads` 9 → 10.
- Evaluate carries `data_as_of`. Drill includes the canary. Trend/segment/overview HTTP 200.
- Payroll money remains unavailable.
- Missing-date outbox item skipped, not failed.
- Rebuild path ok. Canary closed and headcount restored to 9. No leftover canary rows.

Evidence: `ops/evidence/wathefni-hr-intelligence-freshness-20260821/QUALIFICATION.json`

## Remaining gaps

- Headcount still only includes dated actives (74 `active` hub rows vs 9 dated). Dates are not fabricated.
- Payroll money KPIs stay unavailable until Wathefni-authoritative sealed periods exist.
- Synthetic recruiting canary was not inserted (applications require a `candidates` row). Recruiting freshness is proved from 161 live application events, not a throwaway application.
- Attendance / shifts / performance / talent were not given isolated canary writes (would pollute authority SoT). They are proved by live event ingest + current freshness.
- Preboarding / probation intelligence remains unavailable while those SKUs are off.
- Talent aggregates remain suppressed below min cohort n=5.
