# Employee App Phase 4.3 — Leave request history backend

**Stamp:** `20260809T013329Z`  
**Verdict: PASS**

## Scope (this phase only)

Backend scale gap #3: add `GET /app/leave/history` so older leave requests (beyond `/app/leave` ~50) can be paged with keyset cursors and optional status/date/year filters. **Leave root UI unchanged. No deeper history UI. No balance/enforcement changes. No cancel-authority changes. No Home changes. No mobile OTA.**

## Contract

| Field | Meaning |
| --- | --- |
| `GET /app/leave/history` | Requires `leave` feature |
| `limit` | `1..50`, default `30` |
| `cursor` | Opaque keyset (`start_date`, `leave_id`) |
| `date_from` / `date_to` | Optional ISO bounds on `start_date` |
| `year` | Optional `2000..2100`; intersects with date bounds |
| `status` | Optional filter; allowlisted canonical statuses only |
| `ordering` | `start_date_desc` (`start_date DESC, leave_id DESC`) |
| `has_more` / `next_cursor` | Honest page continuation |
| `requests[]` | Same fields as `/app/leave` rows (no invented balance/policy) |
| Invalid cursor | `400 invalid_cursor` |
| Invalid range | `400 invalid_range` |
| Invalid status | `400 invalid_status` |
| Invalid date_* | `400 invalid_date_from` / `invalid_date_to` |

`/app/leave` remains the Leave root projection (still ≤50 rows; balances honesty flags unchanged). Cancel stays on `POST /app/leave/{id}/cancel`.

## What shipped

- `app.py` — cursor encode/decode, `_employee_leave_history_page`, `GET /app/leave/history`
- Smoke — `smoke-test-employee-app-leave-history.py` (24/24)
- Mobile — none (backend-only phase)

## Deploy

| Field | Value |
| --- | --- |
| Host | `root@76.13.63.68` |
| Backup | `/opt/wathefni/backups/production-pre-employee-leave-history-20260809T013329Z` |
| Rollback | that backup’s `ROLLBACK.sh` / evidence `ROLLBACK.sh` |
| Health | active · `/health` 200 (:8010) |
| Mobile OTA | none (backend only) |

## Smoke

| Check | Result |
| --- | --- |
| Multi-page keyset, no dupes, 55/55 reachable | **PASS** |
| Older-than-50-cap + status/year filters | **PASS** |
| Employee + tenant isolation | **PASS** |
| Empty / invalid cursor / range / status / date | **PASS** |
| `/app/leave` still ≤50 + honesty flags | **PASS** |

## Not in this phase

- Leave history UI / “View all history”
- Raising the `/app/leave` hard cap
- Balance enforcement / payroll / allowlist broadening
- Schedule or Payslips changes
