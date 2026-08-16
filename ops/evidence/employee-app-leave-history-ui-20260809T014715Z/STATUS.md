# Employee App Phase 5.2 — Leave History UI

**Stamp:** `20260809T014715Z`  
**Verdict: PASS**

## Scope (this phase only)

Wire Leave → dedicated leave history over existing `GET /app/leave/history`. **Leave root unchanged except a single “View all history” entry under Recent history.** No Schedule changes. No Home changes. No backend changes. No balance invention.

## Route / UX

| Surface | Behavior |
| --- | --- |
| Leave root | Recent history section → **View all history** → `/leave/history` (link always present under that section) |
| `/leave/history` | Back, title, year chips (`All` + last 5 years), status chips (`All` / cancelled / rejected / completed / approved) |
| Rows | Compact `ListRow`: type, dates, status, reason; newest first |
| Pagination | `has_more` → **Load older requests** with opaque `cursor` |
| Cancel | Only when `can('leave','cancel')` **and** status is `requested`\|`approved` — terminal rows never cancel |

## What shipped

- `LeaveHistoryView.tsx` + `app/leave/history.tsx`
- Type `LeaveHistoryResponse`
- Route registry + stack screen
- EN/AR copy
- Capability + density gates

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `c4249469-8c13-4d47-a053-ded2149dc3f3` · runtime `0.1.0` · no native build |
| Rollback | `c12f398e-68a6-4c77-8781-6315d2402a92` (attendance history UI) via evidence `ROLLBACK.sh` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/c4249469-8c13-4d47-a053-ded2149dc3f3 |

## Smoke

| Check | Result |
| --- | --- |
| tsc | PASS |
| capability foundation | GREEN |
| density + hierarchy | PASS (99) |
| year/status contract | PASS |
| i18n EN/AR keys | match |

## Not in this phase

- Leave root redesign / filter chrome on root
- Date-range picker UI (year + status only)
- Balance/accrual display on history
- Home-style cards
