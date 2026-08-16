# Employee App Phase 4.1 — Payslips history pagination

**Stamp:** `20260809T011927Z`  
**Verdict: PASS**

## Scope (this phase only)

Backend scale gap #1: replace the silent `/app/payslips` ~24 hard cap with honest keyset pagination (`has_more` + `next_cursor`). Minimal mobile wire: **Load earlier payslips** under the existing year-grouped list. **No Payslips redesign. No Home changes. No Schedule/Leave history APIs yet.**

## Contract

| Field | Meaning |
| --- | --- |
| `GET /app/payslips?limit=1..50&cursor=` | Default `limit=24` (first page unchanged for old clients) |
| `has_more` | Another page exists |
| `next_cursor` | Opaque keyset token (`period_end`, `created_at`, `payslip_id`) |
| Invalid cursor | `400 invalid_cursor` |
| Order | `period_end DESC, created_at DESC, payslip_id DESC` |

`list_employee_released_payslips(...)` remains a list wrapper for Home (`limit=12`).

## What shipped

- `payroll_payslip_wave3.py` — `list_employee_released_payslips_page` + cursor encode/decode
- `app.py` — `/app/payslips` accepts `limit`/`cursor`, returns `has_more`/`next_cursor`
- Mobile — accumulates pages; year groups + in-year `PAYSLIP_PAGE` unchanged; `payslips.loadEarlier`
- Smoke — `smoke-test-employee-payslips-pagination.py` (11/11)

## Deploy

| Field | Value |
| --- | --- |
| Host | `root@76.13.63.68` |
| Backup | `/opt/wathefni/backups/production-pre-employee-payslips-pagination-20260809T011927Z` |
| Rollback | that backup’s `ROLLBACK.sh` / evidence `ROLLBACK.sh` |
| Health | active · `/health` 200 |
| Mobile OTA | `41afc0af-2aa8-46dd-911e-c94d17941ed1` · runtime `0.1.0` · no native build |
| Mobile rollback | prior canary `f151fbb5-f174-47bc-9c78-4f45c1af5c2f` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/41afc0af-2aa8-46dd-911e-c94d17941ed1 |

## Smoke

| Check | Result |
| --- | --- |
| Pagination contract (cursor, pages, HTTP 400, has_more) | **PASS** |
| density + capability + tsc | PASS / GREEN |

## Not in this phase

- Schedule date-range / attendance history API
- Leave request history beyond ~50
- Dedicated deeper Payslips history screen / redesign
