# Employee App — Coordinated visual polish (except Home)

**Stamp:** `20260809T015936Z`  
**Verdict: PASS**

## Scope

JS-only visual system alignment across Schedule, Attendance History, Leave, Leave History, Payslips, Inbox, Documents, Profile, Bank, Request Leave, onboarding/actions, Settings/Privacy, and shared Loading/Empty/Error. **Home untouched.**

No architecture, backend, pagination, permission, or EN/AR/RTL behaviour changes.

## Main visual changes

| Area | Change |
| --- | --- |
| Shared | `PageBackButton`, `QuietEmpty`, demoted Loading/Empty/Error (surface panels, no lilac/bloom heroes) |
| Schedule | Upcoming → `ListRow`; empty/unavailable → surface notices; HR note demoted; selected-day entry Pastel kept |
| Leave / Inbox | Already row + `SectionHeader`; Leave balance remains the one olive Pastel |
| Payslips | Quiet empty; uppercase section headers; net uses `font.display`; detail butter Pastel kept |
| Documents | Quiet empty (no bloom); flat back |
| Profile | Identity Pastel kept; bloom watermark removed |
| Bank | Butter account Pastel kept; change/form cream Pastels → surface panels; subtitle `font.small` |
| Onboarding | Shared back + `SectionHeader`; cream reviewed → surface; lilac actions + progress Pastel kept; complete → surface |
| History screens | Shared back + `QuietEmpty` |
| Privacy | Help panels no longer force `minHeight: 180` |

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `dd05381d-b2a0-4d59-b0f9-117e71b4b0f7` · runtime `0.1.0` · no native build |
| Rollback | `c4249469-8c13-4d47-a053-ded2149dc3f3` via evidence `ROLLBACK.sh` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/dd05381d-b2a0-4d59-b0f9-117e71b4b0f7 |

## Smoke

| Check | Result |
| --- | --- |
| tsc | PASS |
| capability foundation | GREEN |
| density + hierarchy | PASS (99) |
| Home file | not edited |

## Not in this wave

- Home composition / copy / Pastels
- Native build
- Backend / capability / pagination contract changes
- Physical device visual QA (canary pull after OTA)
