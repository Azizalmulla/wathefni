# EMF P3 — Review application flow (approve → apply)

**Stamp:** `20260805T184419Z`  
**Contract:** `employee_migration_foundation_p0p3` / `1.1.3`

## Bug

Name-change approval was batch-scoped but HR had no clear apply path on the original batch. Re-uploading created a new batch and the same conflict returned. Approved rows disappeared from Needs review without being applied.

## Fix

- Approve keeps the **original batch** actionable (`previewed` or `partial`)
- Confirming safe rows with remaining conflicts leaves the batch **partial** (not sealed)
- Approved rows stay in Needs review as **Approved** with **Apply approved change**
- Apply once on the same batch updates the employee, stamps audit fields, then clears the card
- Confirm import on the same batch still works as the alternate apply path
- Approval does **not** transfer to unrelated future batches
- Ledger rows are never deleted; History shows approval, application, actor, time, before/after

## Smoke

`smoke-test-employee-migration-foundation-p3-apply-flow.py` → `OK employee migration foundation P3 apply-flow smoke`

| Check | Result |
|---|---|
| Preview: 1 safe update + 1 name conflict | Pass |
| Confirm safe rows → batch partial; conflict unchanged | Pass |
| Approve keeps original batch; Approved card applyable | Pass |
| Re-upload does not inherit approval | Pass |
| Apply once → employee updated; queue cleared | Pass |
| History retains approval/application/actor/time/before-after | Pass |
| Idempotent second apply | Pass |

## Deploy

- Orchestrator: `employee_migration_foundation.py` + `apply-approved-name-change` route
- Dashboard: Apply approved change in Needs review / Import
- Canary: `WATHEFNI` only

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-apply-flow-20260805T184419Z/ROLLBACK.sh`
