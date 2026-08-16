# EMF P3 — Material name identity guard

**Stamp:** `20260805T160200Z`  
**Contract:** `employee_migration_foundation_p0p3` / `1.1.1`  
**Fixture:** `wathefni_p3_safe_updates_test.xlsx`

## Gap

External ID match treated a materially different name (`Different Salem Name` → `Salem Aldosari`) as **Will be updated**, including auto name change.

## Fix

- External ID remains the strongest match (employee key + source mapping unchanged).
- Email / job title / department / start date / manager still auto-update when identity is clear.
- **Materially different name → Needs review** (whole row; not auto-applied).
- Minor normalization (case, spacing, `Al-` / `Al `), token-order/subset, and known aliases remain safe.
- HR can **Approve name change** on the review row (preview only) → moves to Will be updated; Confirm then applies. Does not change `employee_key` or break mappings.

## Exact-file preview (live WATHEFNI)

| Person | Outcome |
|---|---|
| Lulwa Alshammari | Will be added |
| Fahad Alenezi | Will be updated (email, job title) |
| Mariam Almulla | Will be updated (manager) |
| Noura Almutairi | Will be skipped |
| Different Salem Name | Needs review (material name; mapped to Salem via ERP-EMP-1006) |

**Totals:** Added 1 · Updated 2 · Skipped 1 · Needs review 1

Smoke: `OK employee migration foundation P3 name-identity guard smoke`

## Route

`POST /dashboard/posthire/employees/import-batches/{batch_id}/rows/{row_id}/approve-name-change`

## Rollback

`/opt/wathefni/backups/production-pre-emf-p3-name-guard-20260805T160200Z/ROLLBACK.sh`
