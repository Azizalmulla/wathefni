# Employee Migration Foundation P0–P2

**Stamp:** `20260805T144609Z`  
**Mode:** create-only · no messages · no auto-onboarding · no existing-employee updates  
**Company allowlist:** `WATHEFNI`  
**Flag:** `WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION=on`

## What shipped

| Piece | Detail |
|---|---|
| Module | `wathefni-orchestrator/employee_migration_foundation.py` |
| Schema | `employee_import_batches` · `employee_import_rows` · `employee_source_mappings` |
| Wave4 fix | `manager_phone` → resolve hub key → `apply_assignment_change(manager_employee_key=…)` |
| UI | Preview totals · exception CSV download · optional ID columns documented |

## Schema

### `employee_import_batches`
- `batch_id`, `company_code`, `domain=employee_roster`
- `content_sha256`, `idempotency_key` (unique per company)
- `source_system`, `totals` jsonb `{create,skip,conflict,invalid}`
- statuses: `draft|previewed|committing|committed|partial|failed|rolled_back`

### `employee_import_rows`
- Per-row status: `will_create|skipped|conflict|invalid|created|failed|rolled_back`
- Optional `external_employee_id`, `payroll_id`, `source_system`
- Stamps `employee_key` on create

### `employee_source_mappings` (reusable multi-system)
- `(company_code, source_system, external_employee_id)` unique when active
- `(company_code, source_system, payroll_id)` unique when active
- Supports multiple HRIS/payroll systems per employee later without hub column sprawl

## Routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/dashboard/posthire/employees/import` | Preview (`dry_run=true`) or commit; foundation when flag on |
| `GET` | `/dashboard/posthire/employees/import-batches` | Import history |
| `GET` | `/dashboard/posthire/employees/import-batches/{batch_id}` | Batch detail |
| `GET` | `/dashboard/posthire/employees/import-batches/{batch_id}/exceptions.csv` | Exception export |
| `POST` | `/dashboard/posthire/employees/import-batches/{batch_id}/rollback` | Rollback created hub rows (`idempotency_key` required) |

Form extras on import: `source_system`, `idempotency_key`, `batch_id` (confirm).  
`start_onboarding` is ignored on the foundation path.

## Import states

**Batch:** `previewed` → `committing` → `committed` | `partial` | `failed` → `rolled_back`  
**Row preview:** `will_create` / `skipped` / `conflict` / `invalid`  
**Row commit:** `created` / `skipped` / `failed` (conflicts/invalids unchanged)  
**Totals:** `create` · `skip` · `conflict` · `invalid` (legacy `counts.created|skipped|needs_review|failed` preserved)

## Behavior invariants

- Existing employees: **never updated** (skip or conflict)
- No WhatsApp/email invites during import
- No automatic onboarding seed
- Alias-aware phone matching preserved
- Deterministic replay via `(company_code, idempotency_key)` derived from content hash + source_system

## Qualification (prod smoke)

`smoke-test-employee-migration-foundation.py` → `OK employee migration foundation local smoke`

| Check | Result |
|---|---|
| Repeated file import | Pass (replayed) |
| Duplicate employee | Pass (skip) |
| Conflicting name/phone | Pass (conflict) |
| Malformed rows | Pass (invalid) |
| Foreign tenant isolation | Pass |
| Partial/idempotent commit | Pass |
| Exception export | Pass |
| Rollback/recovery | Pass |
| Manager phone matching | Pass |
| No auto-onboarding | Pass |

## Rollback

```bash
/opt/wathefni/backups/production-pre-employee-migration-foundation-20260805T144609Z/ROLLBACK.sh
```

## Remaining P3 blockers

1. **Controlled update mode** — field refresh for existing employees (email/title/dept) behind explicit confirm + conflict report; never rewrite `employee_key`
2. **Source-mapping merge UX** — when external_id already maps to a different employee_key
3. **Bulk invite-after-import** — still must stay separate HR handoff (not auto)
4. **Leave opening balances / documents / shifts** — explicitly deferred
5. **ERP/SFTP connectors** — deferred; source_mappings ready to attach
6. **Migration Center UI** — history API exists; full Center still later
7. **Dashboard create-org-migration-batch client** — Wave4 API exists; thin upload still missing

Do **not** enable update-mode or invite-on-import without owner change-control.
