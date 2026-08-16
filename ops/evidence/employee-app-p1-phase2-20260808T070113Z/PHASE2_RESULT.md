# Employee App P1 — Phase 2: unified read-only Schedule

Stamp: `20260808T070113Z` · branch `authority-cutover` · base commit `cf26d59`
Deployed `app.py` sha256 `347b2f4058551fa5a36b5fb2fb22f8c17ba5298e68584fc8217fbbb2400246ba`
(identical to the local tree — see `source-stamp.txt`).

Owner review is **not** requested. This is an internal wave step.

## What shipped

### 1. `/app/workday` — a read-only projection, not a new authority

The employee has one workday. Shifts and Attendance are two backend modules, and the app
was exposing that boundary as two separate screens: the expected schedule on one, the
recorded attendance on another, with the employee left to reconcile them. `/app/workday`
combines what those modules already store into one day-centred read:

- today's expected schedule beside today's recorded attendance
- upcoming schedule (next 30 days, excluding today)
- recent records and the window summary the Attendance module already computes

It **creates no authority**. There is no employee clocking, no attendance correction, no
payroll input, and no new status vocabulary. Every value is the owning module's stored
value, passed through verbatim — lateness, early leave, notes and status are read, never
recomputed. The response carries an explicit `read_only` block (`employee_clocking`,
`attendance_correction`, `payroll_effect` all false) plus the EN/AR statement that HR
records the schedule and the attendance.

Pairing is by the canonical `shift_id` the attendance record already carries. A record
with no matching shift becomes its own entry rather than being guessed onto a shift, and
a shift with no record keeps `recorded: null` so the surface can say the record is
missing instead of inventing one.

### 2. Unavailable authority stays informational

Each authority reports its own read state (`disabled` / `error` / `ready`) and carries
`null` when it has nothing truthful to say, reusing the Phase 1 per-module savepoint
helper. So:

- Attendance off → the Schedule surface still works from Shifts alone, and never renders
  "nothing recorded" as a fact
- a failed Attendance read → `error`, no value, and the Shifts read still completes on
  the same transaction (and vice versa)
- today with no rows → the message depends on which authorities were actually read, so
  "No shift scheduled today" is only ever said when Shifts was read successfully

The shared read helper was renamed `_home_module_read` → `_module_read` with a `surface`
label, because it now serves two surfaces and was logging every Schedule failure as a
Home failure.

### 3. One Schedule surface, one launcher

- New tab `app/(tabs)/schedule.tsx` + `src/features/schedule/ScheduleView.tsx`
- Deleted `app/(tabs)/shifts.tsx` and `app/attendance.tsx` — the split surfaces are gone,
  along with `ShiftsView` / `AttendanceView`
- The tab and the Home tile appear when **either** entitlement is present; Shifts and
  Attendance no longer produce two Home destinations for the same day
- Route registry `RouteSpec.feature` now accepts a tuple for a combined destination.
  `/(tabs)/schedule` is admitted by `shifts` OR `attendance` and still refused without
  both. The pre-Schedule paths (`/shifts`, `/(tabs)/shifts`, `/attendance`) are explicit
  aliases, so links in older builds and in-flight notifications land on the new surface
  instead of dead-ending
- Attendance check-in/out are instants; they render in Kuwait wall-clock time via
  `formatClockTime`, so a travelling employee's device time zone cannot shift their day

EN + AR copy added for every new string; the keysets still match exactly.

## Gates

Local (`local-gates.txt`) — 12 passed, 0 failed, DB classes skipped by host:

```
mobile typecheck (tsc --noEmit) · mobile PIN crypto selftest
mobile entitlement composition shapes (54 checks) · auth wave 2 phases 1–5 unit
mobile capability + composition contract · backend modules compile
employee app capability contract
```

Production host (`prod-gates.txt`) — 12 passed, 0 failed, mobile toolchain classes
skipped by host:

```
employee app runtime access enforcement · employee app home projection contract
employee app workday projection contract  ← new
employee app access eligibility matrix · employee app invitation + delivery
employee payslips P0 · employee payslips P0.1 official PDF
employee↔HR sync hardening · employee app session/self-scope regression
```

`workday-projection.txt` holds the 33 per-check results of the new contract, proving on
real production fixtures (synthetic employees only; Aziz/Talal untouched): the refusal
without either authority, either authority alone, both together, pairing by `shift_id`,
unpaired records kept separate, today excluded from the recent list, cancelled shifts and
out-of-window rows never presented, both single-authority failure isolations, the
read-only declaration, and locale echo/fallback.

The two release-gate runs together are the full qualification; neither host can run both
classes, and each prints PARTIAL rather than PASS so a partial run cannot be mistaken for
a complete one.

## Frozen foundations untouched

Auth Wave 2 phases 0–5, Payroll Authority / Payslip Wave 3, Migration & Sync, and the
Setup Console entitlement contract were not reopened. Shifts and Attendance keep their
existing endpoints and response shapes: `_employee_shift_rows` and
`_employee_attendance_rows` gained an opt-in `detailed` projection, so `/app/shifts/*`
and `/app/attendance` return exactly what they returned before.

## Not done, deliberately

No employee clocking, no attendance correction request, no schedule acknowledgement, no
payroll effect. Those are separate product decisions and none is authorized.

## Rollback

`ROLLBACK.sh` restores the previous `app.py` from
`/opt/wathefni/backups/employee-app-p1-workday-20260808T070000Z`. Backend-only and no
schema or data change, so nothing needs unwinding. A client already on the new build
would lose `/app/workday` and show the Schedule surface's error state until the JS is
also rolled back; the mobile change is JS-only, so that is an OTA revert, not a rebuild.
