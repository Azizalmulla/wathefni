# Migration & Sync P4 — Opening Balances + Current-State Cutover

| Field | Value |
|---|---|
| Stamp | `20260807T101417Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Contract | `employee_migration_sync_p4_cutover` @ `4.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P4_CUTOVER.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p4-20260807T101417Z/ROLLBACK.sh` |
| Dashboard | `PostHire-XWDMcYyG.js` (P3 onboarding labels + P4 opening preview) |

## Proven

| Check | Result |
|---|---|
| Leave opening balance (ledger adjustment, no leave requests) | PASS |
| Payroll/current-value authority (staged + masked; never approved/effective) | PASS |
| Compliance expiry/current-state (imported/unverified staging) | PASS |
| Current assignment + shift template planning (no shift_assignments) | PASS |
| Missing values ≠ zero/false | PASS |
| Repeated import idempotent | PASS |
| Newer Wathefni leave activity wins | PASS |
| Rollback preserves superseded / native activity | PASS |
| P3 onboarding labels in live dashboard bundle | PASS |
| P1–P3 regression smokes | PASS |

## Remaining gaps

- P5 connectors · P6 leavers — not started
- Auth Wave 2 Phase 6 — not started
- Payroll draft contract creation may be refused under synthetic-only gates; values still stage with `authority=imported`
- Org assignment history insert is best-effort when Wave 4 schema/columns differ; hub `raw_json.department` stamp used when no `employees.department` column
- Live HR walk of Migration Sync preview UI not owner-stamped this session
