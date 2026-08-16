# Shifts Wave 3A — Calendar foundation UX + live staging qualification

**Stamp:** `20260802T225214Z`  
**Evidence:** `ops/evidence/shifts-wave3a-20260802T225214Z/`  
**Module:** `shifts_wave3_controlled.py` **v3.0.0**  
**Dashboard:** Calendar-aligned `ShiftsWorkspace.tsx` + `shiftsUx.ts`  

**Scope:** UX direction lock to Wathefni Calendar + live staging API/UI prove.  
**Not done:** production deploy, real-mutation enablement, timer activation, templates/recurring/rotations/publishing/open shifts/PAM, broad employee-app, Payroll money.

---

## Verdicts

| Scope | Verdict |
|---|---|
| Staging Wave 3A Calendar-aligned UX + live API/UI | **GO** |
| HR controlled production scheduling | **NO-GO** |
| Scoped manager production scheduling | **NO-GO** |
| Talal employee-app mutations | **NO-GO** (read-only) |
| Real-employee reminders | **NO-GO** |
| Broad employee-app rollout | **NO-GO** |
| Production Wave 3 canary | **NO-GO** (not authorized) |
| Operator timers | **NO-GO** (disabled) |

---

## UX audit → refactor

### Foundation reused from Calendar (`CalendarShell.tsx`)
- Page hierarchy: eyebrow + title + icon + actions
- Unified toolbar `rounded-[1.35rem] border-line/70 bg-panel/90`
- Day/week pills on warm `#f3ebe0` with active `bg-wf-ink text-white`
- Chevron date nav + Today (RTL-aware chevron swap)
- Filter strip treatment
- Warm schedule canvas `#fbf7ee` / border `#ded3c1` / `rounded-[1.55rem]`
- Aside detail/composer (`xl:grid-cols-[minmax(0,1fr)_360px]`) instead of a foreign full-screen drawer system
- Loading / empty / error / honesty states
- EN/AR + `dir`/`lang` + mobile `max-width: 900px` day-first

### Scheduling adaptations (not a literal calendar copy)
- Roster rows = employees (site shown as secondary)
- Columns = dates in week view
- **Shift blocks** (`data-testid="shift-block"`) with Calendar semantic surfaces adapted for scheduled / conflicted / reconciliation / cancelled / overnight
- Overnight span marker into next day **without duplicating authority**
- Split same-day windows called out
- Availability / leave ack + audit reason on mutate
- Assignment history / lineage in aside
- Bulk scheduling readiness note reserved for later template/recurring waves
- **No** FullCalendar / react-big-calendar / Schedule-X / dhtmlx

### Screenshots (live staging `:8011`)
- Desktop week roster: `screenshots/shifts-wave3a-desktop-board.png`
- Desktop composer aside: `screenshots/shifts-wave3a-desktop-composer.png`
- Mobile RTL day-first: `screenshots/shifts-wave3a-mobile-rtl.png`

---

## Live staging API qualification (synthetic SHW2B/W3A)

Against `wathefni_staging` only:

| Check | Result |
|---|---|
| Wave 3 enrich on `GET /dashboard/posthire/shifts` | PASS |
| Honesty payload embedded (`payroll_money=false`, no templates) | PASS |
| Create day + overnight assignment | PASS |
| Overnight `ends_next_day` | PASS |
| History / lineage versions | PASS |
| Stale concurrency rejected | PASS |
| Reschedule with token | PASS |
| Soft-cancel with reason | PASS |
| Calendar-aligned dashboard dist markers | PASS |
| Residual cleanup zero | PASS |

**Suite:** `smoke-test-shifts-wave3a-live-staging.py` → **21 / 0**  
**UX smoke:** `smoke-test-shifts-wave3-ux.py` → **40 / 0** (local + staging)

Staging service drop-in (staging only): `WATHEFNI_SHIFTS_WAVE3=1`, `REAL_MUTATION_GATE=0` for synthetic prove, `REAL_REMINDERS=0`, Wave1/Wave2 flags retained. Production untouched.

---

## Freezes

| Suite | Result |
|---|---|
| Employees 360 | **57 / 0** (local) |
| Onboarding | **54 / 0** (local) |
| Attendance | **26 / 0** (local) |
| Leave | **35 / 0** (local) |
| Dashboard `tsc` + build | clean; PostHire chunk markers for shift-block / `#fbf7ee` / no generic schedulers |

Note: staging orch tree lacked `smoke-test-attendance-freeze-regression.py`; attendance freeze re-proven locally in this pack.

---

## Remaining blockers (unchanged production posture)

1. Production deploy of Wave 3 sources not authorized  
2. Named HR/manager allowlists empty for live real mutations  
3. Operator timers remain disabled  
4. Real reminder sending remains off  
5. Templates / recurring / rotations / publishing / open shifts / PAM still out of scope  
6. Dashboard seed via `POST /dashboard/posthire/actions` returned 405 in UI shot helper (shots still captured against live board; create path proven via domain/dashboard cancel-reschedule APIs)

---

## Bottom line

**Staging Wave 3A: GO** — Shifts workspace now shares Calendar product language with roster/schedule adaptations, and live staging API/UI qualification passed on `wathefni_staging` with residual-zero synthetic cleanup.  
All production enablement scopes remain **NO-GO**.
