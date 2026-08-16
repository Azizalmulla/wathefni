# Wathefni Calendar — C3 Implementation

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260729T144605Z`  
**Evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c3/20260729T144605Z/`  
**Authority:** C0 (+ A1), C1 kickoff, C1/C2 implementation (+ C2 durability amendment)  
**Scope:** Shared conflict authority · Team projection · full day/week/month UX · Overview ≤5 · mobile + Arabic/RTL  
**Preserves:** Waves 1–6, Calendar C1–C2, Google operator coexistence  
**Tenants with `calendar` enabled:** **0** (no broad enablement; controlled evidence only via disposable smoke tenants)

---

## Verdict

**PASS.** C3 delivers the core Calendar product experience on the C1/C2 spine without starting C4+ (notifications, RSVP delivery, reminder workers, Google v2, Microsoft, recurrence, resources). Health **200** after deploy and after rollback/restore. C1 **53/0**, C2 **37/0**, durability **22/0**, Wave 6 **PASS**, C3 smoke **41/0**.

---

## C3 PASS/FAIL matrix

| # | Requirement | Result |
|---|---|---|
| 1 | Shared conflict service (attendee/organizer/leave/shift/hours/interview) | **PASS** |
| 2 | Required vs optional attendees distinguishable | **PASS** |
| 3 | Leave/shift soft warnings unless company policy hardens | **PASS** |
| 4 | Interview + Calendar use same conflict authority | **PASS** |
| 5 | Privacy-safe conflict payloads | **PASS** |
| 6 | Override requires `calendar.conflict_override` + reason + audit | **PASS** |
| 7 | Without override → 409 `scheduling_conflict`, draft preserved | **PASS** |
| 8 | Interview-linked edits still require Interview authority | **PASS** |
| 9 | Team projection via OrgScopeAdapter / opaque scopes | **PASS** |
| 10 | Team switch hidden without scope and without company oversight | **PASS** |
| 11 | Company oversight no-team guidance | **PASS** |
| 12 | Day / Week / Month UX (week default desktop) | **PASS** |
| 13 | My / Team / Company + filters + details drawer | **PASS** |
| 14 | Manual create/edit/cancel with conflict preview + OCC | **PASS** |
| 15 | Overview mini month + ≤5 upcoming + View full calendar | **PASS** |
| 16 | Mobile agenda-first | **PASS** |
| 17 | Arabic / RTL bilingual conflict/empty states | **PASS** |
| 18 | Bounded date-range queries (≤92 days) | **PASS** |
| 19 | Perf: 200-event seed query ~22ms | **PASS** |
| 20 | Cross-tenant isolation | **PASS** |
| 21 | C1/C2/durability + Wave 6 regression | **PASS** |
| 22 | Google operator behavior unchanged | **PASS** |
| 23 | No broad production enablement | **PASS** (0 enabled) |

---

## Exact files changed

| File | Change |
|---|---|
| `wathefni-orchestrator/calendar_conflicts.py` | **New** — shared conflict authority + override audit |
| `wathefni-orchestrator/calendar_projections.py` | Team inclusion, overview ≤5, bounded ranges, filters |
| `wathefni-orchestrator/calendar_store.py` | Conflict gate on create/update; override + OCC preserved |
| `wathefni-orchestrator/interview_service.py` | Schedule/reschedule via shared conflicts + override |
| `wathefni-orchestrator/app.py` | Overview, team-scopes, conflict preview routes; override fields |
| `wathefni-orchestrator/smoke-test-calendar-c3.py` | **New** — C3 proofs + perf |
| `apps/wathefni-dashboard/src/components/CalendarShell.tsx` | Full day/week/month + Team + drawer + composer + RTL |
| `apps/wathefni-dashboard/src/components/OverviewCalendarPanel.tsx` | **New** — Overview mini calendar ≤5 |
| `apps/wathefni-dashboard/src/App.tsx` | Wire CalendarShell + Overview panel |
| `apps/wathefni-dashboard/src/lib/api.ts` | Team/overview/conflict client APIs |
| `ops/WATHEFNI_CALENDAR_C3_IMPLEMENTATION.md` | This document |
| Dashboard asset | `dashboard-BcHI7NLC.js` deployed to `/var/www/wathefni-dashboard/` |

---

## Shared conflict service

**Module:** `calendar_conflicts.py`

Checks (tenant-scoped overlap):

| Check | Severity default |
|---|---|
| Attendee double-book (`calendar_attendees` ∩ non-cancelled/completed events) | **Blocking** (optional → warning) |
| Organizer double-book | **Blocking** |
| Approved leave overlap | **Warning** (blocking only if company `calendar.leave_overlap_blocking`) |
| Assigned shift overlap | **Warning** (policy-hardenable) |
| Company working hours (event timezone) | **Warning** |
| Live interview candidate/panel (folded from `find_schedule_conflicts`) | **Blocking** |

Structured conflict item: `type`, `affected_ref`, `start_at`/`end_at`, `severity`, `blocking`, privacy-safe `message` / `message_ar`, optional `attendee_role`.

**Override:** `override_conflicts=true` + non-empty `override_reason` + `calendar.conflict_override` → append-only `calendar_event_audit.action=conflict_override`. Without permission/reason → `409 scheduling_conflict` with `draft_preserved=true`.

**Interview cutover:** `schedule_interview` / `reschedule_interview` call `require_no_blocking_conflicts` (no separate Interview-only conflict path). Interview-linked Calendar PATCH of authority fields still returns `interview_authority_required`.

---

## Team Calendar

- Inclusion rules T1–T3 from C0 §2.3 in `include_in_team_calendar`.
- Adapter-only: projections never `FROM manager_scopes`.
- APIs: `GET /dashboard/calendar/events?scope=team`, `GET /dashboard/calendar/team-scopes`.
- UI: Team switch when `show_team_switch`; scope selector when multiple memberships; no-team guidance for company oversight.

---

## Full Calendar page

Desktop week default; Day/Week/Month; Today + prev/next; My/Team/Company; type/status/mine-only filters; time grid; compact cards; attendee dots; status chips; create/edit drawer (controlled form — no drag/drop to avoid unsafe OCC/conflict bypass); interview-managed banner routes to Interviews.

Manual types: meeting, personal_block, deadline, out_of_office, other — with PeoplePicker attendees, external guest email, visibility, timezone, all-day, location, meeting URL, conflict preview.

---

## Overview

`GET /dashboard/calendar/overview` — mini month busy days + **max 5** upcoming; My default; optional Company for `calendar.company`. Panel does not replace My Work / Company Work queues.

---

## Mobile + Arabic

Mobile (`max-width: 900px`): agenda-first day grouping (week grid not primary).  
Arabic: `dir=rtl`, bilingual empty/error/conflict copy in shell + overview + conflict messages.

---

## Performance

| Metric | Result |
|---|---|
| Seed 200 company events | **0.153s** |
| Bounded company projection (2-day window, n=200) | **0.022s** |
| Hard range cap | **92 days** (`range_too_large` / store window) |

Evidence: `perf.txt`, `c3-smoke.txt`.

---

## Screenshots

Under `…/screenshots/` (design-fidelity HTML captures of shipped UX; live Calendar nav remains gated until a tenant enables `calendar`):

| File | Surface |
|---|---|
| `c3-week.png` | Desktop week + details drawer |
| `c3-month.png` | Month · Company |
| `c3-day.png` | Day agenda |
| `c3-scopes.png` | My / Team / Company + no-team guidance |
| `c3-overview.png` | Overview ≤5 panel |
| `c3-mobile-rtl.png` | Mobile Arabic RTL agenda |
| `calendar-c3-preview.html` | Source fixture |

---

## Production smoke / regressions

| Suite | Result |
|---|---|
| `smoke-test-calendar-c3.py` | **41 PASS / 0 FAIL** |
| `smoke-test-calendar-c1.py` | **53 PASS / 0 FAIL** |
| `smoke-test-calendar-c2.py` | **37 PASS / 0 FAIL** |
| `smoke-test-calendar-c2-durability.py` | **22 PASS / 0 FAIL** |
| `smoke-test-multi-user-wave6-final.py` | **PASS** |
| Health after deploy / rollback / restore | **200** |

---

## Migration / rollback

**Migration:** No new required tables. Additive use of existing C1 audit + C2 outbox. Conflict service is code-only.

**Rollback proven:** restore `app.py`, `calendar_store.py`, `calendar_projections.py`, `interview_service.py` from `*.before`; remove `calendar_conflicts.py`; restart → health **200**. Restore C3 `*.after` → health **200** (`restore.marker.txt`).

Dashboard rollback: redeploy prior `dashboard-*.js` asset if needed.

---

## Remaining for C4+ (do not start)

- Notifications (`calendar_conflict`, invites)
- RSVP delivery / tokenized guest flows
- Reminder workers
- Google v2 company sync / Microsoft
- Recurrence editor
- Resources / room finder
- Drag-resize with safe OCC (deferred; C3 uses controlled forms)

**Stop after C3. Do not begin C4.**
