# Employee App Phase 1 — Activation Inbox noise

**Stamp:** `20260809T003705Z`  
**Verdict: PASS**

## Goal

Stop `app_activation` messages from flooding the employee Inbox on resend / new code, while keeping older rows for audit and leaving other notification types untouched.

## What shipped

### Backend (`wathefni-orchestrator`)

- `deliver_app_activation_code` now:
  - uses invite-scoped `dedupe_key` (`app_activation:{employee_key}:{invite_id}`) so each delivery remains an audit row
  - after a successful insert, marks prior `app_activation` rows `metadata.inbox_hidden=true` (keeps newest)
- `_employee_inbox_rows` (powers `/app/notifications` + Home unread):
  - omits `inbox_hidden` rows
  - for `app_activation`, projects **only the newest** non-hidden row (fixes existing floods without waiting for a new send)
- `_remediate_app_activation_inbox_projection` for canary cleanup
- `employee_app_invitation._deliver_code` passes `invite_id` through

### Frontend (`wathefni-employee-mobile`)

- `SYSTEM_ACTIVITY_FLOWS` includes `app_activation` so read activation rows land under Account activity (not Earlier)
- No new Inbox tabs; no visual redesign beyond correct grouping

## Deploy

| Field | Value |
| --- | --- |
| Host | `root@76.13.63.68` |
| Service | `wathefni-orchestrator.service` · active · health/ready 200 · `/app/notifications` 401 |
| Backup | `/opt/wathefni/backups/production-pre-employee-app-activation-inbox-20260809T003705Z` |
| Rollback | `<backup>/ROLLBACK.sh` |
| Post sha256 app.py | `7a1a49edcf82fa7fdd134b5318021da145d3d8422ced2b2ec921ca3587f5865c` |
| Post sha256 employee_app_invitation.py | `01163d7f12d775af50847a03db5a8bb2455c1d98a87fd84be18d03ac38437c41` |

## Smoke

`smoke-test-employee-app-activation-inbox.py` with `WATHEFNI_LIVE_INBOX=1` (service process environ + venv):

| Check | Result |
| --- | --- |
| Source contract (supersede after send, projection filters) | PASS |
| Pure projection: activation flood → newest only; payroll unaffected | PASS |
| Aziz `WATHEFNI-96599338566`: 20 stored activations → 19 hidden, 1 projected | PASS |
| Aziz inbox after: `flows={app_activation:1, shift:1, leave_decision:1, onboarding:1, compliance:1}` unread=1 | PASS |
| Talal: 0 activations; 32 shift rows unchanged | PASS |

## Unread honesty

Home / `/app/notifications` unread is the count of **projected** rows only. Hidden activation rows no longer inflate the badge. Non-activation unread (e.g. Talal’s shift rows) is unchanged.

## FE OTA

Canary OTA `428d1000-80cb-4f36-83d5-f399af1b85bf` — map `app_activation` into Account activity.

## Not done (out of scope)

- Inbox tabs / density redesign
- Marking hidden rows as read (unnecessary for projection)
- Changing shift/leave/payroll delivery
