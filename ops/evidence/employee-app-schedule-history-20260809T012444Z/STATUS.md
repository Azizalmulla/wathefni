# Employee App Phase 4.2 — Schedule attendance history backend

**Stamp:** `20260809T012444Z`  
**Verdict: PASS**

## Scope (this phase only)

Backend scale gap #2: add `GET /app/schedule/history` so older attendance (beyond `/app/workday` ~30d) can be paged with keyset cursors and optional date bounds. **Schedule root UI + week strip unchanged. No history UI. No Leave history. No Home changes. No mobile OTA.**

## Contract

| Field | Meaning |
| --- | --- |
| `GET /app/schedule/history` | Requires `attendance` feature |
| `limit` | `1..50`, default `30` |
| `cursor` | Opaque keyset (`attendance_date`, `attendance_id`) |
| `date_from` / `date_to` | Optional ISO dates; `date_to` capped at today |
| `ordering` | `attendance_date_desc` (`attendance_date DESC, attendance_id DESC`) |
| `has_more` / `next_cursor` | Honest page continuation |
| `records[]` | `{ recorded, scheduled \| null }` — `scheduled` only when canonical `shift_id` resolves |
| Invalid cursor | `400 invalid_cursor` |
| Invalid range (`date_from > date_to`) | `400 invalid_range` |
| Invalid date_* | `400 invalid_date_from` / `invalid_date_to` |

`/app/workday` remains the Schedule root projection (window still 30 days).

## What shipped

- `app.py` — cursor encode/decode, `_employee_attendance_history_page`, `_employee_shifts_by_ids`, `GET /app/schedule/history`
- Smoke — `smoke-test-employee-app-schedule-history.py` (23/23)
- Mobile — none (backend-only phase)

## Deploy

| Field | Value |
| --- | --- |
| Host | `root@76.13.63.68` |
| Backup | `/opt/wathefni/backups/production-pre-employee-schedule-history-20260809T012444Z` |
| Rollback | that backup’s `ROLLBACK.sh` / evidence `ROLLBACK.sh` |
| Health | active · `/health` 200 (:8010) |
| Mobile OTA | none (backend only) |

## Smoke

| Check | Result |
| --- | --- |
| Multi-page keyset, no dupes, drains | **PASS** |
| Older-than-30d reachable + no fabricated scheduled | **PASS** |
| Employee + tenant isolation | **PASS** |
| Empty / invalid cursor / invalid range / date_from | **PASS** |
| `/app/workday` still 30d; ancient excluded from recent | **PASS** |

## Not in this phase

- Schedule history UI / “View attendance history”
- Leave request history pagination
- Any Schedule root or week-strip redesign
