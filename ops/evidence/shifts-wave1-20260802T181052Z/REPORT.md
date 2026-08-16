# Shifts Wave 1 — Authority, safety & overnight foundation

**Stamp:** `20260802T181052Z`  
**Evidence:** `ops/evidence/shifts-wave1-20260802T181052Z/`  
**Mode:** local/staging only — **no production deploy**  
**Prior:** Wave 0 prod truth; Wave 0B Kuwait rostering research  

---

## Verdict

| Gate | Result |
|---|---|
| Staging qualify (migrate + smoke) | **GO** — 63/63 |
| Employees 360 / Onboarding / Attendance / Leave freezes | **GO** — all green |
| WATHEFNI-only production synthetic canary | **NO-GO** (ready to plan; not authorized this wave) |

**Staging Shifts Wave 1 foundation: GO.**  
**Production canary: NO-GO** until an explicit deploy wave with `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1`, orphan quarantine executed under change-control, and a synthetic-only canary script.

---

## Canonical L0 assignment model

Authority remains **`shift_assignments`** (one row = one planned work window) + soft-cancel (`status='cancelled'`) + append-only **`shift_events`**.

| Field | Role |
|---|---|
| `company_code`, `employee_key` | Tenant + subject (employee must exist) |
| `shift_date`, `start_time`, `end_time` | Planned window clocks |
| `ends_next_day` | Persisted overnight flag (`end <= start`) |
| `break_minutes` | Optional unpaid/paid break metadata (not money) |
| `site_key`, `branch_key`, `team_key`, `position_key`, `role` | Optional scope refs |
| `idempotency_key` | Create idempotency (unique per company) |
| `row_version` / `updated_at` | Concurrency tokens |
| `status` | `scheduled` \| `cancelled` (history preserved) |

**Boundaries (unchanged):** Shifts = scheduled hours only · Attendance = worked time · Leave = leave · Payroll = money.

---

## Overnight & split-shift contract

**Overnight (Attendance-identical):**  
`attendance_authority_wave1.shift_window` / `shifts_authority_wave1.shift_window` — if `end_time <= start_time`, end timestamp += 1 day. Example: `2026-08-11 22:00` → `2026-08-12 06:00`. Persisted as `ends_next_day=true`. Configurable `allow_overnight` (default **enabled**).

**Split shifts:** Multiple **non-overlapping** L0 rows on the same `shift_date` (e.g. 09:00–13:00 + 14:00–18:00). Overlap detection is interval-based across same-day, split, and overnight neighbour dates — not same-`shift_date` SQL only.

**Rest days:** `rest_weekdays` on `shift_authority_settings` (default Friday=`4`). **Not** hard-coded as the only legal rest day.

---

## Lifecycle & leave-conflict policy

**Lifecycle gates** (when Wave 1 applies to subject): block `terminated` / `left`, `suspended`, `future_start`, `notice_period` on create.

**Leave-conflict modes** (`leave_conflict_mode`):

| Mode | Create behaviour |
|---|---|
| `block` | Hard deny on approved leave overlap |
| `require_ack` (default) | Deny unless `ack_leave_conflict` / `allow_leave_conflicts` |
| `cancel_shift` | On leave approve with explicit cancel flag — soft-cancel conflicting shifts + event `cancelled_for_leave` |

---

## Orphan disposition report

**Prod orphans (Wave 0 — not touched this wave):**

| employee_key | shift_date | Disposition |
|---|---|---|
| `WATHEFNI-96552263564` | 2026-08-11 | **Deferred** — quarantine mechanism proven on staging; prod execution needs canary/deploy wave |
| `WATHEFNI-96552202357` | 2026-08-11 | Deferred |
| `WATHEFNI-96596552203` | 2026-08-11 | Deferred |

**Mechanism:** `shift_orphan_quarantine` + soft-cancel; restore re-schedules when allowed. Staging proved: quarantine → restore blocked while still orphan → force-restore → re-scheduled → re-quarantine cleanup.

---

## Exact fixes

| Area | Change |
|---|---|
| Module | `wathefni-orchestrator/shifts_authority_wave1.py` |
| Create | Unknown employee fail-closed; lifecycle; overnight columns; break/site metadata; idempotency; leave-conflict |
| Overlap | Overnight-aware `shift_conflicts` via Wave 1 |
| Time range | `extract_shift_time_range` allows overnight when Wave 1 + `allow_overnight` |
| Cancel | Soft-cancel + idempotent by `shift_id`; events append-only |
| Swap | Hard-ban self-approve/reject; decide races on `status='requested'` |
| Dashboard reschedule | Overnight allowed; `expected_updated_at` concurrency on UPDATE; leave ack |
| Leave approve | Optional cancel conflicting shifts |
| Client | `rescheduleShift` sends `expected_updated_at`; overnight UI allowed; `PosthireShiftRow.updated_at` |
| Schema | `shift_authority_settings`, `shift_orphan_quarantine`, assignment columns |
| Gates | WATHEFNI company default; synthetic markers `SHW1` / phone `965528*` |

---

## Tests & evidence

- Smoke: `smoke-test-shifts-authority-wave1.py` → **63/63** on staging  
- Qualify: `wathefni-orchestrator/ops/qualify-shifts-wave1-staging.sh`  
- Migrate: `ops/migrate-shifts-authority-wave1.sh` + `ops/sql/shifts_authority_wave1_v1.sql`  
- Freezes: Employees 360 57, Onboarding 54, Attendance 26, Leave 35 — all pass  
- Artifacts under `ops/evidence/shifts-wave1-20260802T181052Z/`

Proven on staging: orphan reverse quarantine, unknown fail-closed, lifecycle terminated, concurrent reschedule one winner, idempotent create/cancel, overnight 22–06, split two assignments, overlaps, break/site metadata, tenant mismatch, leave ack, Attendance overnight parity, no Leave/Payroll money mutation symbols.

---

## Remaining blockers

1. **No production deploy** this wave — orphans still live in prod.  
2. **Dashboard dist** not rebuilt/deployed; API concurrency is live on staging; client source is fixed locally.  
3. **Self-swap** ban is unit + code-wired; no end-to-end swap fixture in smoke (swaps unused in prod Wave 0).  
4. **Notice-period / future-start** depend on hub + `employee_employments` data quality.  
5. Templates / recurring / rotations / publish / open shifts / PAM / broad employee-app — intentionally out of scope.

---

## GO / NO-GO — WATHEFNI production synthetic canary

**NO-GO now.** Staging foundation is ready. A future canary wave may proceed only with:

- Explicit owner authorization to sync orchestrator to prod  
- `WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1`  
- `WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI`  
- `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1`  
- Audited quarantine of the three prod orphans (reversible)  
- Synthetic-only create/cancel/overnight smoke on prod  
- Freeze regressions still green  

Until then: **do not deploy; do not touch real employee shifts.**
