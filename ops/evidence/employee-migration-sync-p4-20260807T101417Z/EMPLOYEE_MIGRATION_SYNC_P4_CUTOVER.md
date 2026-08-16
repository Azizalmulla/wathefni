# Employee Migration & Sync P4 — Opening Balances + Current-State Cutover

Contract: `employee_migration_sync_p4_cutover` @ `4.0.0`  
Builds on frozen P1–P3. Same batch/row/provenance/Needs-review + 3-layer field model.

## Principle

Prefer **authoritative opening / current-state values + provenance** over fake historical
transactions. Missing source data = **not supplied** (never invent zero / expired / inactive).

## Authority policy

| Domain | Import writes | Never does | Authority ladder |
|---|---|---|---|
| **Leave** | Opening balance as `leave_ledger` `adjustment` (`observe_only`) + balance recompute | Fabricate leave requests / accrual history | `imported` → HR verifies → Wathefni-authoritative |
| **Payroll** | Staging row + optional **draft** compensation contract (`source_kind=import`) | Approve, payroll-effective, bypass synth/security gates | `imported` draft ≠ approved |
| **Assignment** | Current org slice (`change_type=migration`) when safe | Fabricate `shift_assignments` / attendance | `imported`; conflict → Needs review |
| **Shifts** | Template/code staging only | Dated shift events | `imported` planning metadata |
| **Compliance** | Expiry/current-state staging (`unverified`) | Auto-seed campaigns / mark reviewed | `imported` until Wathefni verifies |

## Provenance (every opening row)

`source_system` · `batch_id` · `row_id` · `external_employee_id` · `cutover_date` ·
`imported_at` · `authority` (`imported` \| `verified` \| `wathefni_authoritative`)

## Preview dispositions

`will_apply` · `unchanged` · `needs_review` · `not_supplied`

Sensitive payroll values are **masked** in preview.

## Safety

- No invitations / messages
- No automatic onboarding outside P3 explicit path
- Re-imports idempotent per `(employee, domain, field_key, batch)`
- Newer native Wathefni activity → `native_superseded`; import does not roll back
- Rollback removes batch-stamped opening rows / ledger adjustments / draft contracts created by the batch; preserves superseded native state
