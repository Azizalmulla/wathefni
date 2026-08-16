# EMF P3 — Canonical review Apply (Salem blocker)

**Stamp:** `20260805T194534Z`  
**Contract:** `employee_migration_foundation_p0p3` / `1.1.4`

## Root cause

Needs review could show **Approved** while Apply used a different (stale/superseded) `batch_id`+`row_id`. Approval lived on one ledger row; Apply checked another → raw `row_not_approved_pending_apply`. UI also treated `name_change_approved && will_update` as Apply-able even when `applyable` was false.

## Fix

- Queue returns `canonical_batch_id` / `canonical_row_id` — the exact approved-pending row
- Approved chip + Apply button only when `applyable === true` on that canonical row
- Apply resolves identity to the canonical approved-pending row when client ids are stale
- Already-applied → idempotent success; superseded → calm refresh copy (never raw codes)
- Applied activity clears newer sealed conflict cards from the active queue

## Smoke (live Salem `WATHEFNI-96550010006`)

`smoke-test-employee-migration-foundation-p3-salem-canonical-apply.py` → OK

| Check | Result |
|---|---|
| Approve on canonical row | Pass |
| Apply with stale ids resolves to canonical | Pass |
| Same employee_key retained | Pass |
| Queue cleared | Pass |
| History approval+apply+before/after | Pass |
| Idempotent second apply | Pass |

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z/ROLLBACK.sh`
