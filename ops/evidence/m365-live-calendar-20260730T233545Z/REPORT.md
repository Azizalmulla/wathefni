# Microsoft Graph live calendar — post-propagation matrix

**Stamp:** `20260730T233545Z`  
**Check UTC:** `2026-07-30T23:35:20Z`  
**Assigned at:** `2026-07-30T22:12:23Z`  
**Elapsed since assign:** **1h 22m 57s**  
**Overall:** **PARTIAL PASS** — calendar create/reschedule/cancel/AU-deny green; **Teams join link still FAIL**

No permissions or configuration were changed for this run.

## Propagation recheck (first)

| Field | Value |
|---|---|
| Mailbox | `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` |
| Result | **PASS** `HTTP 201` |
| Event id | present |
| Cleanup | delete ok |

## `prove-m365-live-calendar.py`

| Proof | Result |
|---|---|
| Cert token mint | **PASS** |
| Outlook create | **PASS** (201, event id + webLink) |
| Teams meeting join URL | **FAIL** (`has_join_url=false`; create returns `isOnlineMeeting=false`) |
| Reschedule (PATCH same id) | **PASS** |
| GET after update | **PASS** |
| Cancel | **PASS** (204) |
| Idempotent second cancel | **PASS** (404) |
| Outside-AU deny (`wathefni-rbac-deny-probe@…`) | **PASS** (403) |
| Provider-failure Wathefni intact | **FAIL** (`application_environment_missing_or_invalid` — local app env, not Graph) |

Summary from script: `passed=7 failed=2`

## Extended Teams / interview matrix

| Check | Result | Notes |
|---|---|---|
| Teams interview create (Graph event + `isOnlineMeeting`) | **PARTIAL** | Event created; online meeting **not** materialized |
| Attendee consistency | **PASS** | 2 attendees present on event |
| Timezone consistency | **PASS** | `Asia/Kuwait` round-trip on create/reschedule |
| Join link | **FAIL** | `onlineMeeting.joinUrl` null; `/users/{upn}/onlineMeetings` → **403** `Missing required permissions` |
| Invitation email delivery | **UNVERIFIED** | Attendees attached; Sent Items read → **403** (no Mail authority under current RBACfA-only setup) |
| Reschedule | **PASS** | |
| Cancel | **PASS** | |
| Audit trail (provider event lifecycle) | **PASS** for Graph create→patch→delete; Wathefni DB audit probe blocked by app env |
| Outside-AU denial | **PASS** | 403 `ErrorAccessDenied` |
| Assistant workflow (schedule executor + Teams Graph path) | **PARTIAL** | `_schedule_interview_executor` present and Microsoft-aware; equivalent Graph path creates event but **no Teams join URL** — cannot mark Assistant Teams complete |

### Token / permission observation (unchanged config)

- App-only token `roles` / `scp`: **null** (expected for RBACfA-only; Exchange role not in JWT)
- Calendar event CRUD in AU: **works**
- Direct Online Meetings API: **403 Missing required permissions** (not granted; per instructions not changed)

## Evidence

- Prod: `/opt/wathefni/production-evidence/wathefni-calendar-c6b/m365-live-20260730T233545Z/`
- Local: `ops/evidence/m365-live-calendar-20260730T233545Z/`
- Helper / Assistant probes under `remote/interview-helper/`, `remote/assistant-schedule/`

## Verdict

**Calendar RBAC propagation: PASS.**  
**Full Teams interview matrix: FAIL / incomplete** until Teams online-meeting creation returns a join URL (current blocker is Online Meetings permission / Teams online meeting materialization — not calendar create 403).
