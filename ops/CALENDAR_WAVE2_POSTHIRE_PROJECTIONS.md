# Calendar Wave 2 — Real Post-Hire Read-Only Projections

**Status:** LIVE · stamp `20260805T005000Z`  
**Freeze preserved:** `ops/CALENDAR_UX_PERMANENT_FREEZE.md` (UX/layout unchanged)  
**Module:** `wathefni-orchestrator/calendar_posthire_projections.py`  
**Evidence:** `ops/evidence/calendar-wave2-posthire-projections-prod-deploy-20260805T005000Z/`  
**Bundle:** `CalendarShell-CLAOP6Nc.js`

## Source mapping

| Source | Flag | Table / field | Event shape | Deep link |
|---|---|---|---|---|
| Employee start | `WATHEFNI_CALENDAR_PROJECTION_EMPLOYEE_START` | `employees.start_date` | all-day `other` / `employee_start` | `?page=employees&employee=` |
| Onboarding deadlines | `WATHEFNI_CALENDAR_PROJECTION_ONBOARDING` | `onboarding_items.due_date` | all-day `deadline` / `onboarding_deadline` | `?page=onboarding&employee=` |
| Approved leave | `WATHEFNI_CALENDAR_PROJECTION_LEAVE` | `leave_requests` | OOO / `approved_leave` | `?page=leave&leave=` |
| Compliance expiries | `WATHEFNI_CALENDAR_PROJECTION_COMPLIANCE` | `compliance_documents.expiry_date` | all-day `deadline` / `compliance_expiry` | `?page=compliance&employee=&document_type=` |
| Training / company events | `WATHEFNI_CALENDAR_PROJECTION_COMPANY_EVENTS` | `public_holidays` (no LMS yet) | all-day `meeting` / `training_company` | `?page=leave` |

Companies allowlist flag per source: `…_COMPANIES` (default `WATHEFNI`).  
Synthetic ids: `calproj-*` (never written to `calendar_events`).

## Filters / status rules

| Source | USE | EXCLUDE |
|---|---|---|
| Employee start | `start_date` in range; default employment active | `employment_status=left` |
| Onboarding | open assignment; item `due_date` in range | assignment `completed/cancelled/abandoned`; item `received/complete/completed/verified/waived/cancelled_onboarding/abandoned_employment_ended/retired_legacy` |
| Leave | `status=approved` only | requested / rejected / cancelled / withdrawn / … |
| Compliance | has `expiry_date` in range | `missing`, `archived`, `superseded`, `rejected` |
| Company holidays | seeded/approved `review_status` in range | `draft`, `pending_review`, `rejected`, `superseded` |

Payroll and shifts remain out of scope.  
Cancelled / rejected / archived / superseded records do not appear. Updates in owning modules invalidate Calendar via `invalidate.afterPostHireProjectionTouch`. Soft-keep + polling unchanged.

## Permissions

Actor needs `calendar.read` plus source permission:

| Source | Permission |
|---|---|
| Employee start | `employees.read` |
| Onboarding | `onboarding.read` |
| Leave | `leave.read` |
| Compliance | `compliance.read` |
| Company events | `calendar.read` |

Projections are read-only in Calendar (mutate → `projection_event_readonly`). Owning modules keep workflow authority. Clicking an event opens the owning record via `metadata.deep_link`.

## Production stamp

- **Stamp:** `20260805T005000Z`
- **Flags drop-in:** `/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-calendar-wave2-projections.conf` (all five sources `=on`, companies `WATHEFNI`)
- **Per-source smoke counts (WATHEFNI):** starts 4 · onboarding 81 · leave 2 · compliance 1 · company holidays 3 (holidays visible when range includes Jan–Feb 2026)
- **Combined:** 93 projections in window `2026-01-01` → `now+400d`

## Tests

- Local: `ops/smoke-test-calendar-posthire-projections.py` → `CALENDAR_POSTHIRE_PROJECTIONS_SMOKE_OK`
- Prod per-source: `ops/evidence/.../verify/smoke-*.out`
- Prod final: `ops/evidence/.../verify/production-smoke-final.out` → `FINAL_SMOKE_OK` + `UX_PRESERVED_OK`

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-wave2-projections-20260805T005000Z/ROLLBACK.sh
```

Restores pre-wave dashboard + orchestrator sources, removes/restores the projection drop-in, restarts orchestrator.
