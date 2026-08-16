# EMF P3 — Needs review queue semantics

**Stamp:** `20260805T180801Z`  
**Contract:** `employee_migration_foundation_p0p3` / `1.1.2`

## Bug

Repeated previews/imports created duplicate active Needs review cards for the same identity (e.g. Salem name conflict). Invalid and intra-file duplicate rows were mixed into the active queue.

## Fix (list-time; ledger preserved)

Active queue is now:

- **One card per unresolved employee/source identity**
- Newer matching conflict **supersedes** older unresolved copies
- **Approved/resolved** identity rows clear the active card immediately
- **Invalid** and **intra-file duplicate** rows stay in History / exception CSV only
- Quiet “From {filename}” on cards — no row IDs / technical clutter
- Ledger rows are **never deleted**; History / batch detail still shows every attempt

## Deploy

- Orchestrator: `/opt/wathefni/orchestrator/employee_migration_foundation.py` (contract `1.1.2`, `active_review_queue_deduped`)
- Dashboard: calm Needs review copy live (`Each person appears once` / quiet `From {filename}`)
- Canary: `WATHEFNI` only

## Smoke

`smoke-test-employee-migration-foundation-p3-review-queue.py` → `OK employee migration foundation P3 review queue smoke`

| Check | Result |
|---|---|
| 3 preview retries → 1 active card | Pass |
| Leave unresolved → still 1 card | Pass |
| Ledger keeps ≥3 conflict copies | Pass |
| Approve → active card gone | Pass |
| Older conflict rows retained | Pass |
| Batch detail retains needs_review | Pass |
| Invalid / in-file dup not in queue | Pass |

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-review-queue-20260805T180801Z/ROLLBACK.sh`
