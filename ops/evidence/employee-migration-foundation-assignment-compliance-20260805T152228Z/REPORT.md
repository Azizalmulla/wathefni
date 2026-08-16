# EMF — Assignment history + compliance seed correction

**Stamp:** `20260805T152228Z`  
**Batch repaired:** `5f09ba60-b9a7-4df1-a129-701e5f1ece34`

## Audit truth (before)

| Check | Finding |
|---|---|
| Fahad manager in `employees.raw_json` | Yes → Noura `WATHEFNI-96550010001` |
| Fahad `employee_org_assignment_history` | **Empty** |
| Fahad Wave2 `employee_assignments.manager_employee_key` | **null** |
| Root cause | Import stamped hub JSON only; `UPDATE employee_assignments WHERE employee_key` is invalid (no such column) |
| Compliance after import | Auto-seeded `civil_id`+`passport` `missing` via `seed_compliance=True` when company has compliance module; unspecified category defaults to both types |
| Unknown Manager | Unset (`manager_unresolved=true`) — correct |

## Correction (smallest)

1. Foundation commit: `seed_compliance=False` (no auto gap campaign on existing-workforce import)
2. Resolved manager → Wave4 `apply_assignment_change(change_type=migration)` (canonical history + Wave2 projection)
3. Repair route + one-shot repair for committed batch: managers into history; remove auto-seeded missing civil_id/passport

## After repair

| Person | Manager history | Wave2 manager | Compliance missing |
|---|---|---|---|
| Fahad | migration → Noura | Noura | none |
| Unknown Manager Test | none | null | none |

Repair counts: managers_applied=5 · compliance_missing_removed=14

## Rollback

`/opt/wathefni/backups/production-pre-emf-assignment-compliance-20260805T152228Z/ROLLBACK.sh`

## Still deferred (not broadened)

- Nationality/role-aware compliance campaign UX
- HR-approved migration reconciliation campaign before reminders
- Passport applicability by nationality
