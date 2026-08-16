# Calendar scope labels — production deploy

**Stamp:** `20260731T194941Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Verdict:** **PASS**

## Production artifacts
| Artifact | Value |
|---|---|
| Dashboard chunk | `dashboard-Btr3JHJY.js` |
| Dashboard SHA-256 | `502f79217accc5ae20ffd4f1605a1cb338a3c344de4f2c1731b13c66cd1c9ba2` |
| CalendarShell chunk | `CalendarShell-McJD9Ux2.js` |
| CalendarShell SHA-256 | `9d3d626b22356e23559275f4e3b016e24e33202cd3fd928756b83e5d0e3d8659` |
| `calendar_projections.py` SHA-256 | `4189a8f28761a2060562d6e528b83ec16ab9352ce5bd84625835e76416271698` |

## Scope deployed
- Labels: **My calendar** / **Hiring team** / **Company calendar** (+ AR)
- Tooltips on each scope control
- Hiring team only with real org-scope membership (`has_team_scope` / scopes[])
- Company calendar only with `calendar.company`
- Invalid / unavailable scope snaps to My calendar
- Event query uses `scope=mine|team|company`
- Overview mini-calendar fixed to `scope=mine`, no toggle
- Backend `show_team_switch` = memberships only (not company oversight alone)
- **Not included:** Calendar event-card redesign

## Production gates

| Gate | Result |
|---|---|
| Health after | **200** |
| Dashboard after | **200** |
| Visible scopes change backend `scope=` query | **PASS** (mine ↔ company observed; team N/A — hidden) |
| Unauthorized scopes hidden | **PASS** (Hiring team hidden; `team-scopes`: `show_team_switch=false`, `has_team_scope=false`) |
| Company gated on `calendar.company` | **PASS** (visible + permission consistent) |
| Default / invalid state → My calendar | **PASS** (`aria-pressed=true` on My calendar) |
| EN/AR + RTL | **PASS** |
| Overview mini-calendar unchanged (`mine`, no toggle) | **PASS** |
| Vitest CalendarShell + Overview | **PASS** 11/11 |
| Rollback verified (old → restore new) | **PASS** |

## Screenshots
- `screenshots/after/prod-calendar-en-scopes.png`
- `screenshots/after/prod-calendar-en-scope-bar.png`
- `screenshots/after/prod-calendar-ar-scopes.png`
- `screenshots/overview/prod-overview-my-calendar.png`
- `screenshots/rollback-check/prod-calendar-en-rolled-back.png`

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-calendar-scope-labels-20260731T194941Z`
- Local: `ROLLBACK.sh` / `RESTORE_NEW.sh` in this evidence pack

## Evidence path
`/Users/azizalmulla/Desktop/claw/ops/evidence/calendar-scope-labels-deploy-20260731T194941Z`
