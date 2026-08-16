# Shifts Wave 0 — production truth & architecture audit

**Stamp:** `20260802T174657Z`  
**Evidence:** `ops/evidence/shifts-wave0-prod-truth-20260802T174657Z/`  
**Mode:** read-only (no code/deploy/UI/frozen-module changes)  
**DB:** production `wathefni` · company module `shifts` = **enabled** for WATHEFNI  
**Canvas:** [shifts-wave0-production-truth](/Users/azizalmulla/.cursor/projects/Users-azizalmulla-Desktop-claw/canvases/shifts-wave0-production-truth.canvas.tsx)

---

## Objective verdict: **PARTIAL**

Shifts is **partially useful in production today** for basic same-day assignment create / list / cancel / reminders over dashboard, WhatsApp/action-registry, HR mobile (read + swap decisions), and Talal employee-app read — but it is **not a production-grade rostering product**.

There is **no** template/recurring/draft-publish/open-shift model, **overnight create is rejected**, dashboard **reschedule is broken** vs concurrency, **3 orphan future assignments** exist, and Attendance/Leave/lifecycle coupling is incomplete relative to frozen Attendance/Leave/E360 standards.

| Question | Answer |
|---|---|
| Production-ready end-to-end rostering product? | **No** |
| Safe to use for basic HR schedule assignments today? | **Yes, with limits** (same-day fixed windows; manual cleanup of orphans/leave clashes) |
| Architecturally weak relative to Attendance/Leave freezes? | **Yes** — assignment CRUD core is real; schedule authority/history/lifecycle are thin |

---

## Production truth (counts)

| Object | Count | Notes |
|---|---:|---|
| `shift_assignments` | **23** | WATHEFNI only |
| · scheduled | 20 | |
| · cancelled | 3 | soft-cancel only |
| · past / today / future | 20 / 0 / **3** | future all `2026-08-11` |
| `shift_events` | 28 | created 5 · notified 4 · reminder_sent 4 · notify_failed 4 · cancelled 3 · reminder_fail 3 · rescheduled 2 · cancel_notified 2 · objection 1 |
| `shift_swap_requests` / events | **0 / 0** | schema live, unused in prod |
| `employee_availability_*` | **0 / 0** | schema live, unused in prod |
| `shift_templates` / `schedules` / `open_shifts` / `schedule_drafts` | **absent** | not implemented |
| Split-day employee-dates | 0 | no AM+PM pairs in prod |
| Overnight (`end <= start`) scheduled | 0 | create API also rejects overnight |
| Overlapping scheduled pairs | 0 | |
| Duplicate exact windows | 0 | |
| Orphan `employee_key` | **3** | all future Aug 11 scheduled; no matching `employees` row |
| Cross-tenant | 0 | |
| Scheduled on approved leave date | **1** | Fouad `2026-05-11` shift vs approved sick leave |
| Attendance records with `shift_id` | **0 / 42** | demo attendance not linked to shifts |
| Location / role filled | 15 / 15 of 23 | |
| Reminders sent | 7 | |
| Timezone | Asia/Kuwait × 23 | |
| Module settings | `reminder_hours_before=2` | |
| Employee-app allowlist | Talal only | `WATHEFNI-96550252254` |
| Outbound | `shift` in `OUTBOUND_FLOWS` · templates **off** | |
| Dedicated `WATHEFNI_SHIFT*` flags | **none** | module row is the gate |

**By employee (historical + future):** Fouad 8 · mohammad 7 · Talal 5 · **3 orphan keys** (1 each, future). Brian (`96599411617`) has **0** shifts.

Source: `prod/truth.json`, `prod/anomaly-detail.json`.

---

## Architecture & data-flow map

```
Dashboard ShiftsPage / Assistant / WhatsApp tools
HR mobile (today + swap decide) / Employee app (read)
        │
        ▼
 action_registry + /dashboard/posthire/shifts* + /app/shifts/*
        │
        ▼
 app.create/list/cancel/reschedule + swap/availability helpers
        │
        ├─► shift_assignments   ← CANONICAL schedule authority
        ├─► shift_events        ← append-only audit (weak; no row_version)
        ├─► shift_swap_*        ← unused in prod
        ├─► employee_availability_* ← unused in prod
        │
        ├─► Attendance: optional shift_id FK; active_shift_for_attendance; absence scan
        ├─► Leave: leave_shift_conflicts on leave approve; no auto-cancel of shifts
        └─► Payroll: scheduled-hours read from assignments (boundary only; no money)
```

**Canonical vs derived**

| Concern | Canonical | Derived / observe |
|---|---|---|
| Who works when | `shift_assignments` (status scheduled/cancelled) | — |
| Audit | `shift_events` | outbound notification attempts |
| Swaps | `shift_swap_requests` (unused) | mutates assignment employee fields on approve |
| Availability | requests table (unused) | does not block create |
| Attendance day | authority/ops projections | may reference `shift_id` |
| Payroll hours | — | reads scheduled windows as input |
| Templates / publish | **none** | — |

---

## Shift & schedule state model

Observed assignment statuses: `scheduled` → `cancelled` (soft).  
No draft / published / locked / taken / open.

| Capability | Status |
|---|---|
| Fixed same-day window | **Implemented** (create requires `end > start` same date) |
| Flexible | **Missing** |
| Split (multi non-overlapping same day) | **Allowed by conflict logic**; **0** in prod |
| Overnight | **Create rejected**; leave/attendance layers can consume overnight rows if seeded |
| Templates / recurring / rotation / rest days / breaks | **Missing** |
| Team / branch / location as first-class assignment targets | Location/role are free-text columns only |
| Effective dating / assignment history versions | **Missing** (cancel+create; events only) |
| Draft schedule / publish | **Missing** |
| Open shifts | **Missing** |
| Employee availability decisions | Request+list only; **no decide API**; prod unused |
| Shift swaps | Code path exists; **0** prod rows; **no self-approve ban** |

---

## Permission & ownership matrix

| Actor | Read | Create/cancel/reschedule | Swap decide | Availability | Self-action |
|---|---|---|---|---|---|
| owner / hr_admin / hr_manager | yes (`shifts.read`) | yes (`shifts.manage`) | yes | request (auto-approved if HR) | N/A |
| scoped `manager` | scoped | scoped via `manager_scope_allows_employee` | scoped | yes | **swap self-approve not banned** |
| viewer | read | no | no | no | — |
| Employee app (Talal) | today + upcoming | no | no (WhatsApp objection only) | WhatsApp request only | cannot cancel own shift |
| HR mobile | today | no create | approve/reject | no | — |

Module gate: `company_modules.shifts.enabled`. No synthetic-only gate for shifts (unlike Leave/Attendance authority).

---

## Attendance, Leave, Payroll boundaries

| Boundary | Current behavior | Risk |
|---|---|---|
| **Attendance** | May attach `shift_id`; absence scan uses scheduled shifts; overnight calc exists in leave/attendance helpers | Prod attendance **0** linked; create cannot mint overnight that attendance canaries need |
| **Leave** | `leave_shift_conflicts` on leave approve; optional override | Shifts **not** auto-cancelled on approved leave; **1** historical clash (Fouad 2026-05-11) |
| **Payroll** | Scheduled hours consumed as input only | Must not invent money from shifts; no payroll-lock on schedule |
| **Lifecycle** | No terminate/suspend auto-cancel of future shifts | Orphans already prove identity drift |

---

## Critical risks & evidence

### P0 — production blockers before feature expansion

1. **Orphan future assignments (3)** — `WATHEFNI-96552263564`, `…96552202357`, `…96596552203` scheduled `2026-08-11` with no `employees` row (`prod/anomaly-detail.json`).
2. **Dashboard reschedule unreachable** — backend requires `expected_updated_at` (HTTP 422); `rescheduleShift` + `RescheduleShiftModal` omit it (`api.ts` ~1994, `PostHire.tsx` ~3433).
3. **No schedule authority comparable to frozen Leave/Attendance** — no synthetic-only, no dual-control, no lifecycle gate, no self-decision ban on swaps.

### P1 — correctness / integrity

4. **Overnight create blocked while Attendance/Leave overnight logic exists** — architectural split; real night shifts cannot be filed via product API.
5. **Approved leave vs still-scheduled shift** — Fouad sick `e3217e0e-…` on `2026-05-11` with scheduled shift `1f74e534-…`.
6. **Outbound notification fragility** — 4 `employee_notification_failed` + 3 `reminder_attempt_failed` vs 4 successes.
7. **Availability / swap workflows unused & incomplete** — no availability decide endpoint; swaps lack self-approval ban.
8. **Attendance linkage empty** — 0/42 records carry `shift_id`.

### P2 — product gaps (expected for Wave 0; do not build yet)

9. Templates, recurring patterns, rotations, rest days, breaks, open shifts, draft/publish, team/branch first-class assignment, EN/AR polish beyond basic employee i18n, effective-dated history.

---

## What should stay / move / remove / rebuild

| Keep | Move later | Do not build yet | Rebuild later if needed |
|---|---|---|---|
| `shift_assignments` as canonical row | Availability decide into registry | Templates / open shifts / publish | Overnight model (single multi-day interval vs two-date) |
| Soft cancel + `shift_events` | Employee swap UX into app (Talal-only) | Full rotation engine | Dashboard Shifts UX (after concurrency fix) |
| Kuwait TZ + same-day conflict check | Lifecycle cancel-future on terminate | Broad employee-app | — |
| Manager scope on manage | Leave→auto-handle conflicting shifts | Payroll money from shifts | — |
| Reminder scan (after reliability fix) | | | |

---

## Recommended phased plan

| Wave | Goal |
|---|---|
| **0 (this)** | Production truth + architecture — **done** |
| **1** | Authority & safety: orphan cleanup (audited), reschedule concurrency fix, self-swap ban, lifecycle/leave conflict policy, overnight create decision, smoke + staging qual — **no UI redesign** |
| **2** | Schedule integrity: history/effective updates, availability decide, swap prove-out, attendance link hygiene, reminder reliability |
| **3** | Controlled UX (E360/pre-hire chrome) for HR/manager week board — still no templates |
| **4** | Templates / recurring / publish only after Wave 1–3 freeze gates |

---

## Exact first implementation wave (Wave 1)

**Name:** Shifts Authority & Safety Hardening (local/staging → controlled prod canary)  
**In scope:**
1. Audited cleanup or quarantine of 3 orphan Aug-11 assignments  
2. Wire dashboard reschedule `expected_updated_at` (+ expose `updated_at` on `PosthireShiftRow`)  
3. `self_decision_denied` (or equivalent) on swap approve/reject  
4. Create-path gates: refuse unknown employee_key; optional refuse non-active employment_status  
5. Document overnight policy: either allow overnight create with Attendance-compatible encoding **or** explicitly keep reject and seed-only overnight for canaries  
6. Leave conflict policy: on leave approve, surface/require handling of conflicting scheduled shifts (cancel or acknowledge) — **without** changing frozen Leave money/enforcement  
7. Smokes: concurrency reschedule, orphan refuse, self-swap ban, overnight contract, leave×shift  

**Out of scope for Wave 1:** UI redesign, templates, open shifts, broad employee-app, Payroll money, weakening E360/Onboarding/Attendance/Leave freezes.

---

## Required tests & qualification

- Unit/smoke: `smoke-test-shift-management.py` (extend concurrency + self-swap)  
- Staging qualify script (read/write synthetic only; markers TBD, distinct from Leave `965527` / Attendance `965524`)  
- Prod canary: synthetic assignments only; assert real 20 historical + orphan disposition; no Attendance ingest; no Leave enforcement change  
- Freeze regressions: E360 / Onboarding / Attendance / Leave smokes green  
- Evidence pack + separate GO/NO-GO for: HR shifts use, manager scoped use, Talal app read, broad app, overnight, templates  

---

## What Wave 0 did not do

- No code changes, deploys, UI redesign, dark-feature enables  
- No mutation of `shift_assignments` or orphans  
- No changes to frozen Employees 360, Onboarding, Attendance, Leave, pre-hiring, or Wave D  

## Scripts / sources

- Read-only inventory captured in `prod/truth.json`  
- Anomaly detail in `prod/anomaly-detail.json`  
- Code authority: `wathefni-orchestrator/app.py` (schema ~1918+, create/conflict/swap ~18985–19699, dashboard reschedule ~69119+)  
- UI: `PostHire.tsx` ShiftsPage, `api.ts` `rescheduleShift`, employee `ShiftsView`
