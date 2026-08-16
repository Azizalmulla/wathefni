# Wathefni Calendar — C1 Implementation

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260729T040224Z`  
**Evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c1/20260729T040224Z/`  
**Authority:** `ops/WATHEFNI_CALENDAR_C0_SPEC.md` (+ Amendment A1), `ops/WATHEFNI_CALENDAR_C1_KICKOFF.md`  
**Scope:** C1 event spine only — **no C2 Interview integration**  
**Preserves:** Multi-User Waves 1–6; current Interview + Google operator-calendar behavior unchanged  

---

## Verdict

**PASS.** Canonical first-party Calendar event spine is live behind opt-in module key `calendar` (disabled by default for existing tenants: **0** enabled). My + Company projections, ACL detail levels, OCC/409, audit, org-scope adapter isolation, and a minimal gated Calendar shell are in place. Interview routes and `GOG` helpers unchanged. Health **200**. Rollback/restore proven. C2 not started.

---

## C1 PASS/FAIL matrix

| # | Requirement | Result |
|---|---|---|
| 1 | Module key `calendar` in catalog; disabled by default | **PASS** — `ENABLED_CALENDAR_TENANTS=0` |
| 2 | Permissions on existing role authority | **PASS** — C0 §3.2 matrix on `ROLE_PERMISSIONS` / `KNOWN_DASHBOARD_PERMISSIONS` |
| 3 | Core schema + indexes + unused recurrence/resource/outbox | **PASS** — 10 `calendar_*` tables, 28 indexes |
| 4 | `OrgScopeAdapter` + `ManagerScopesOrgAdapter` + factory | **PASS** — `calendar_org_scope.py` |
| 5 | ACL/projections never query `manager_scopes` | **PASS** — smoke import/SQL guard |
| 6 | Manual timed events + personal blocks CRUD | **PASS** |
| 7 | Reminder is not a timed/busy event | **PASS** — rejected create |
| 8 | Interview-linked authority edits → `interview_authority_required` | **PASS** |
| 9 | OCC `expected_version` + Wave 5 409 envelope | **PASS** |
| 10 | Append-only `calendar_event_audit` (+ admin audit on mutate) | **PASS** |
| 11 | Detail levels `full\|limited\|busy_only\|hidden` | **PASS** |
| 12 | My + Company projections; candidate busy_only | **PASS** |
| 13 | Busy-only leaks no title/attendees/guests/source/candidate | **PASS** |
| 14 | Minimum APIs with date window + gates | **PASS** |
| 15 | Minimal gated Calendar shell + nav | **PASS** — asset `dashboard-TyZt3SK0.js` |
| 16 | Cross-tenant isolation | **PASS** |
| 17 | Active workflow-link uniqueness | **PASS** |
| 18 | Waves 1–6 regression | **PASS** — wave4/5/6 smokes |
| 19 | No Interview enqueue/worker / Google behavior change | **PASS** — C2 deferred |
| 20 | Migration + rollback evidence | **PASS** — see below |

---

## Files changed

### Backend (orchestrator)

| File | Change |
|---|---|
| `wathefni-orchestrator/module_catalog.py` | Add `calendar` module (`order=28`, opt-in); alias `wathefni_calendar` |
| `wathefni-orchestrator/app.py` | Calendar permissions on roles; `ensure_calendar_schema`; thin Calendar routes + request models |
| `wathefni-orchestrator/calendar_schema.py` | **New** — DDL for events/attendees/guests/links/org_scopes/audit (+ reminders/resources/outbox unused) |
| `wathefni-orchestrator/calendar_org_scope.py` | **New** — Protocol, `ManagerScopesOrgAdapter`, factory |
| `wathefni-orchestrator/calendar_acl.py` | **New** — detail levels + busy_only serialization |
| `wathefni-orchestrator/calendar_store.py` | **New** — create/update/cancel, OCC, attendees/guests/scopes/links/audit |
| `wathefni-orchestrator/calendar_projections.py` | **New** — My + Company projections |
| `wathefni-orchestrator/smoke-test-calendar-c1.py` | **New** — C1 safety proofs |
| `wathefni-orchestrator/smoke-test-module-catalog.py` | 13 → 14 modules; calendar opt-in checks |
| `wathefni-orchestrator/smoke-test-multi-user-wave4-personal-work.py` | Calendar routes expected in C1 |
| `wathefni-orchestrator/smoke-test-multi-user-wave5-concurrency.py` | Same |
| `wathefni-orchestrator/smoke-test-multi-user-wave6-final.py` | Same + calendar permission checks |

### Frontend (dashboard)

| File | Change |
|---|---|
| `apps/wathefni-dashboard/src/App.tsx` | `calendar` page + nav gate (`module=calendar` + `calendar.read`) |
| `apps/wathefni-dashboard/src/components/CalendarShell.tsx` | **New** — minimal agenda shell |
| `apps/wathefni-dashboard/src/lib/api.ts` | Calendar list/detail/create/update/cancel client |

### Ops

| File | Change |
|---|---|
| `ops/WATHEFNI_CALENDAR_C1_IMPLEMENTATION.md` | This document |

---

## APIs (C1)

| Method | Path | Gate |
|---|---|---|
| `GET` | `/dashboard/calendar/events?scope=mine\|company&start=&end=` | `calendar` + `calendar.read` (+ `calendar.company` for company scope) |
| `GET` | `/dashboard/calendar/events/{id}` | `calendar` + `calendar.read` + ACL |
| `POST` | `/dashboard/calendar/events` | `calendar` + `calendar.manage` |
| `PATCH` | `/dashboard/calendar/events/{id}` | `calendar` + `calendar.manage` + OCC |
| `POST` | `/dashboard/calendar/events/{id}/cancel` | `calendar` + `calendar.manage` + OCC |

Date windows required; max 92 days.

---

## Migration evidence

- Stamp: `20260729T040224Z`
- `ensure_calendar_schema` applied on production Postgres
- Tables created:  
  `calendar_events`, `calendar_attendees`, `calendar_guests`, `calendar_event_links`, `calendar_event_org_scopes`, `calendar_event_audit`, `calendar_reminders`, `calendar_resources`, `calendar_resource_bookings`, `calendar_link_outbox`
- Indexes: **28** (see `schema.indexes.txt`)
- Enabled tenants for `calendar`: **0** (dark / opt-in)

### Rollback

1. **Code:** restore `app.py.before` + `module_catalog.py.before`; quarantine `calendar_*.py`; restart orchestrator — proven (`health.rollback.code.txt` = 200).  
2. **Dashboard:** restore `wathefni-dashboard.before` — proven (`asset.rollback.txt` = `dashboard-BtTY4HND.js`), then restore C1 (`asset.restore.txt` = `dashboard-TyZt3SK0.js`).  
3. **Schema:** optional destructive SQL in `schema.rollback.sql` (not executed permanently; tables retained, module remains off).  
4. **Restore:** C1 code + dashboard restored; `health.restore.code.txt` = 200; service `active`.

---

## Test results

| Suite | Result |
|---|---|
| `smoke-test-calendar-c1.py` (prod + DB) | **53 PASS / 0 FAIL** |
| `smoke-test-multi-user-wave5-concurrency.py` | **PASS** |
| `smoke-test-multi-user-wave6-final.py` | **PASS** |
| `smoke-test-module-catalog.py` (local) | **28 PASS** (14 modules) |
| Health after deploy / restore | **200** |

Key DB proofs in `c1-smoke.db.txt`: cross-tenant empty get, stale OCC 409, link uniqueness 409, `interview_authority_required`, candidate company projection `busy_only`.

---

## Remaining for C2

- Interview → Calendar **durable outbox enqueue** after interview commit  
- Outbox **worker** + idempotent `ensure_calendar_event`  
- Live interview create/reschedule/cancel/complete → linked calendar event  
- Panel attendees sync from interview assignments  
- Dual-write / coexistence with current Google operator calendar until C5  
- Agenda reads preferring native linked events  
- **Do not** start Team UI polish, Overview widget, notifications, RSVP, reminder worker, or Google channel v2 in C2 beyond what Interview linking requires  

---

## Explicitly not in C1 (confirmed excluded)

Full week/month UX · Team switch product · Overview ≤5 · Notifications · RSVP · Reminder worker · Google sync migration · Recurrence/resources product · Free/busy polish  

**Stop after C1.**
