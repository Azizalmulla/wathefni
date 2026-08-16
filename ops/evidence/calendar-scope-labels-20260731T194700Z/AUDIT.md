# Calendar scope switcher — audit + local verify

**Verdict: PASS (local)** — labels/tooltips/visibility wired; scope drives `GET /dashboard/calendar/events?scope=`; Overview stays `mine` only.

## Backend predicates (`calendar_projections.py`)

| Scope | Inclusion |
|---|---|
| **mine** | Actor is owner, organizer, or attendee; or creator of a private event; or owner of `personal_block`. |
| **team** | Mine (T1) ∪ team/company-visible events bound to actor org scopes (T2) ∪ rare unbound team + `calendar.manage` (T3). Requires org memberships unless actor has `calendar.company`. |
| **company** | Requires `calendar.company`. Non-private, non-hidden events (plus always includes mine). |

`team_scope_meta.show_team_switch` = **only when actor has org scope memberships** (not merely company oversight).

## Frontend

- Labels: My calendar / Hiring team / Company calendar (+ AR)
- Tooltips via `title` on each scope control
- Hiring team hidden without meaningful team scopes (`has_team_scope` / scopes[])
- Company calendar hidden unless `canCompany` (`calendar.company`)
- `eventsParams.scope` → `useCalendarEventsQuery` query key/URL
- Overview: `useCalendarOverviewQuery(..., 'mine')` — no scope toggle

## Tests

`npx vitest run src/components/CalendarShell.test.tsx src/components/OverviewCalendarPanel.test.tsx` → 11 passed
