# Calendar Wave 2 — Post-Hire Projections (Production)

**Stamp:** `20260805T005000Z`  
**Bundle:** `CalendarShell-CLAOP6Nc.js`  
**Doc:** `ops/CALENDAR_WAVE2_POSTHIRE_PROJECTIONS.md`  
**Status:** LIVE — all five sources enabled for `WATHEFNI`

## Deploy order + smoke

| # | Source | Flag | Smoke |
|---|---|---|---|
| 1 | `employee_start` | `…_EMPLOYEE_START=on` | 4 events · `SMOKE_OK` |
| 2 | `onboarding_deadline` | `…_ONBOARDING=on` | 81 events · `SMOKE_OK` |
| 3 | `approved_leave` | `…_LEAVE=on` | 2 events · `SMOKE_OK` |
| 4 | `compliance_expiry` | `…_COMPLIANCE=on` | 1 event · `SMOKE_OK` |
| 5 | `company_events` | `…_COMPANY_EVENTS=on` | 3 holidays (range must include Jan–Feb 2026) · `SMOKE_OK` |

Final: **93** projections · `FINAL_SMOKE_OK` · `UX_PRESERVED_OK`

## Rollback

`/opt/wathefni/backups/production-pre-calendar-wave2-projections-20260805T005000Z/ROLLBACK.sh`

Also mirrored at `ops/evidence/calendar-wave2-posthire-projections-prod-deploy-20260805T005000Z/ROLLBACK.sh`
