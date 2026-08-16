# Employee Migration Foundation P3

**Stamp:** `20260805T154331Z`  
**Scope:** Safe existing-employee updates + simple Migration & Sync shell  
**Company allowlist:** `WATHEFNI`  
**Flag:** `WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION=on`  
**Contract:** `employee_migration_foundation_p0p3` / `1.1.0`

## What shipped

| Piece | Detail |
|---|---|
| Matching | 1) `source_system` + `external_employee_id` when supplied · 2) else tenant phone/alias · ambiguous/conflicting → Needs review · **never by name alone** |
| Safe updates | name, email, job title, department, start date, manager via Wave4 assignment history |
| Preview | Exact before/after field diffs · HR language totals · explicit confirm before write |
| Undo | Concurrency-safe: reverse a field only if current still equals batch `after` |
| UI | Employees → **Migration & Sync** · four sections: Import employees · Connected systems · Needs review · History |
| Preserved | Create-only for new people · no invitations/messages · no onboarding · no compliance seeding · no leave/docs/shifts/payroll · **no deactivation** |

## HR language (preview)

- Will be added
- Will be updated
- Needs review
- Will be skipped
- Will be deactivated *(shown as label only; always 0 / off in P3)*

## Totals

`create` · `update` · `skip` · `review` · `invalid` · `warnings` · `deactivate=0`

Legacy `counts.created|updated|skipped|needs_review|failed` preserved for older clients.

## Routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/dashboard/posthire/employees/import` | Preview / confirm (create + update) |
| `GET` | `/dashboard/posthire/employees/import-batches` | History |
| `GET` | `/dashboard/posthire/employees/import-batches/{id}` | Batch detail with changes |
| `GET` | `/dashboard/posthire/employees/import-batches/{id}/exceptions.csv` | Exception export |
| `POST` | `/dashboard/posthire/employees/import-batches/{id}/rollback` | Undo creates + concurrency-safe field revert |
| `GET` | `/dashboard/posthire/employees/import-review` | Needs review queue |

## Qualification (prod smoke)

`smoke-test-employee-migration-foundation-p3.py` → `OK employee migration foundation P3 local smoke`

| Check | Result |
|---|---|
| Preview create / update / review / name-alone create | Pass |
| Commit updates applied | Pass |
| Skip when unchanged | Pass |
| Concurrency-safe undo (post-batch email left alone; name restored; creates removed) | Pass |
| Honesty: no deactivation · never match by name alone | Pass |

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/ROLLBACK.sh`

Restores prior `employee_migration_foundation.py`, `app.py`, and dashboard dist.

## Ready for live review

Owner can open **Employees → Migration & Sync**, upload a file of known people, preview Will be added / Will be updated / Needs review / Will be skipped, confirm once, then undo from History if needed.

## Still deferred (not in P3)

- Connected systems / ERP connectors
- Deactivation from sync
- Compliance reconciliation campaigns
- Phone as an auto-update field
