# Calendar event-card redesign — production deploy

**Stamp:** `20260731T202233Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Qualified local pack:** `ops/evidence/calendar-event-card-redesign-local-20260731T200100Z/` (+ reference-style correction)  
**Verdict:** **PASS**

## Production artifacts
| Artifact | Value |
|---|---|
| Dashboard chunk | `dashboard-Bznlhxsn.js` |
| Dashboard SHA-256 | `d610dfeb0f08bd07b04f0ba4b6d37f457a37df7878eb01c006bc38d2189f8697` |
| CalendarShell chunk | `CalendarShell-DunoP2L4.js` |
| CalendarShell SHA-256 | `0de0e2233755ba5857f7e575de391daf8220eda70f9a159ecbfe4aff4e089866` |

## Scope deployed
Reference-led Calendar event cards + supporting grid hierarchy only:
- Top-aligned content, compact rounded cards
- Warm stone / yellow / blue / pink semantic pastels
- Timezone-aware start–end labels with `(+1d)` / `(+يوم)`
- Duration-driven progressive disclosure
- Candidate/job context, channel/location indicators, participants
- Teams Join action; card click opens existing drawer
- Overlap lanes; stronger day grouping and soft grid dividers

## Preserved
- Real event start/end values and height math
- Scope switcher + event query wiring
- Permissions, drawer, create/edit flows
- Overview mini-calendar (`scope=mine`, no toggle)
- No orchestrator / data mutation

## Production gates

| Gate | Result |
|---|---|
| Health after | **200** |
| Dashboard after | **200** |
| Live 25h cancelled event shows cross-day (`09:00 AM – 10:00 AM (+1d)`, height 576) | **PASS** |
| Short / medium / long densities | **PASS** |
| Overlapping lanes readable | **PASS** |
| Teams Join opens meeting link (no drawer) | **PASS** |
| Card body opens existing details surface | **PASS** |
| EN/AR + RTL | **PASS** |
| Mobile day/agenda | **PASS** |
| Scope switching unchanged | **PASS** |
| Overview mine-only | **PASS** |
| Vitest Calendar/Overview | **PASS** 13/13 |
| Production build | **PASS** |
| Rollback verified (old → restore new) | **PASS** |

## Bad-data flag (no mutation)
`c3c3d8e7-dc0c-4fbd-9d57-8c91d1cc053b` — cancelled “online meeting with aziz” spans **25 hours** (Aug 1 09:00 → Aug 2 10:00 Asia/Kuwait). Likely test data; left intact. See `verify/BAD_DATA_FLAG.json`.

## Screenshots
- `screenshots/after/prod-calendar-en-desktop.png`
- `screenshots/after/prod-calendar-ar-rtl.png`
- `screenshots/after/prod-calendar-mobile.png`
- `screenshots/after/prod-calendar-empty-week.png`
- `screenshots/overview/prod-overview-my-calendar.png`
- `screenshots/rollback-check/prod-calendar-en-rolled-back.png`

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-calendar-event-card-redesign-20260731T202233Z`
- Local: `ROLLBACK.sh` / `RESTORE_NEW.sh`

## Evidence path
`/Users/azizalmulla/Desktop/claw/ops/evidence/calendar-event-card-redesign-deploy-20260731T202233Z`
