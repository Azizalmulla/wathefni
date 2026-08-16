# Employee Migration & Sync P6 — Leavers + Lifecycle Sync

Contract: `employee_migration_sync_p6_leavers` @ `6.0.0`  
Builds on frozen P1–P5.2. **Same** Connected Systems sync_run → foundation pipeline. No separate lifecycle engine.

## Authority / policy design

External lifecycle data is a **signal**, not automatic authority.

Per-connection `config.lifecycle_policy`:

| Key | Values | Default |
|---|---|---|
| `termination` | `review_required` · `auto_apply` · `ignore` | **`review_required`** |
| `reactivation` | same | `review_required` |
| `default` | same | `review_required` |

Missing source status/date = **not supplied** (never assume termination).

## Normalize → disposition → apply

```
connector lifecycle_signals
  → normalize (terminated/resigned/inactive/suspended/ended/reactivated/rehired)
  → match employee (source_system + external_id)
  → policy route
  → employee_migration_lifecycle_events (ledger)
  → auto_apply OR Needs review OR ignore/blocked
  → hub employment_status active|left + Auth Wave 2 revoke
```

Dispositions surfaced to HR: Termination proposed · Reactivation proposed · Will apply · Needs review · Ignored by policy · Unchanged · Applied · Blocked (authority).

## Apply effects (no hard-delete)

- Hub `employment_status` → `left` / `active`
- Preserve employee row + history (payroll/leave/attendance/docs untouched)
- Terminate: `revoked_reason=offboarded` (app → account inactive, not generic session expired)
- Rehire: `revoked_reason=reactivated_via_invite` (fresh activation required; **no auto-invite**)
- Provenance stamped on `raw_json.employee_migration_lifecycle`

## Conflict rules

- Newer Wathefni activity / `lifecycle_native_authority` blocks stale source termination
- Conflicting connected systems → Needs review
- Unmatched identity → Needs review
- Paused/disconnected connections cannot sync/apply

## Boundaries

No Auth Wave 2 Phase 6 · no hard-delete · no silent historical mutation · no auto-invite on rehire
