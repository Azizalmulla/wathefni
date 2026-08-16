# EMF P3 — Migration & Sync flow clarity

**Stamp:** `20260805T161521Z`  
**Scope:** Import flow UX + route-order fix (no redesign)

## Fixes

### Approve name change
- Immediate success banner + toast
- Same batch/row context retained
- Row leaves **Needs review** → **Will be updated** with **Approved** mark
- Counts refresh from server response
- Explicit: **Confirm import is still required**
- Never surfaces “We couldn't find that employee” after approval (route-order root cause + friendly fallback)

### Auto preview
- Choosing a file runs preview automatically
- Loading: **Checking your file…**
- Result buckets appear when ready
- Confirm enabled only after preview finishes
- Manual control becomes **Refresh preview**

### Calm messages
- File selected
- Preview complete / refreshed
- Review approved (confirm still required)
- Import confirmed
- Undo completed

### Root cause of false employee 404
`GET /employees/import-batches` and `GET /employees/import-review` were registered **after** `GET /employees/{employee_key}`, so FastAPI treated `import-batches` / `import-review` as employee keys.

Foundation import routes are now registered **before** the employee detail route.

## Smoke

`smoke-test-employee-migration-foundation-p3-flow-clarity.py` → `OK employee migration foundation P3 flow clarity smoke`

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-flow-clarity-20260805T161521Z/ROLLBACK.sh`
