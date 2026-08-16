# Employee App Phase 5.1 — Attendance History UI

**Stamp:** `20260809T014321Z`  
**Verdict: PASS**

## Scope (this phase only)

Wire Schedule → dedicated attendance history over existing `GET /app/schedule/history`. **Schedule root + week strip unchanged except a single “View attendance history” entry.** No Leave history UI. No Home changes. No backend changes.

## Route / UX

| Surface | Behavior |
| --- | --- |
| Schedule root | After Recent record (when attendance is factual): **View attendance history** → `/schedule/history` |
| `/schedule/history` | Back, title, HR honesty line, month chip strip (`All` + last 6 months via `date_from`/`date_to`) |
| Rows | Compact chronological list, newest first: date, status, recorded times / late / notes; **EXPECTED line only when API `scheduled` is non-null** |
| Pagination | `has_more` → **Load older records** with opaque `cursor` |
| Entitlement | Attendance required; shifts-only Schedule shows no history entry |

## What shipped

- `AttendanceHistoryView.tsx` + `app/schedule/history.tsx`
- Types `ScheduleHistoryResponse` / `ScheduleHistoryRecord`
- Route registry + stack screen
- EN/AR copy
- Capability + density gates for history honesty

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `c12f398e-68a6-4c77-8781-6315d2402a92` · runtime `0.1.0` · no native build |
| Rollback | `41afc0af-2aa8-46dd-911e-c94d17941ed1` (payslips pagination) via evidence `ROLLBACK.sh` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/c12f398e-68a6-4c77-8781-6315d2402a92 |

## Smoke

| Check | Result |
| --- | --- |
| tsc | PASS |
| capability foundation | GREEN |
| density + hierarchy | PASS (98) |
| month bounds contract | PASS |
| i18n EN/AR keys | match |

## Not in this phase

- Leave history UI
- Schedule root / week-strip redesign
- Analytics or Home-style cards on history
