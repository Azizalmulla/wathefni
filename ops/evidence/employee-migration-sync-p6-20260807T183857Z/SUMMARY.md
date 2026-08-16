# Migration & Sync P6 — Leavers + Lifecycle Sync

| Field | Value |
|---|---|
| Stamp | `20260807T183857Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Contract | `employee_migration_sync_p6_leavers` @ `6.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P6_LEAVERS.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p6-20260807T183857Z/ROLLBACK.sh` |
| Dashboard | `PostHire-DPVwAU00.js` |

## Lifecycle authority / policy

External signals are not automatic authority. Per-connection `lifecycle_policy`:

- **Default termination:** `review_required`
- Trusted source may set `auto_apply`
- `ignore` records only

Normalize → match → policy → `employee_migration_lifecycle_events` → hub `active|left` + Auth Wave 2 revoke (`offboarded` / `reactivated_via_invite`). No hard-delete. No parallel engine.

## Proven

| Check | Result |
|---|---|
| Trusted-source termination auto-apply | PASS |
| Default review-required → Needs Review | PASS |
| Termination preserves employee/history | PASS |
| Active app session revoked (`offboarded`) | PASS |
| App eligibility blocked for `left` | PASS |
| Stale/native authority blocks override | PASS |
| Conflicting systems → Needs Review | PASS |
| Repeated lifecycle idempotent | PASS |
| Rehire preserves identity / no duplicate | PASS |
| Paused/disconnected cannot apply | PASS |
| P1–P5.2 regressions | PASS |

## Remaining gaps

- Full multi-vendor lifecycle disagreement UX (beyond Needs Review ledger) can deepen later
- Optional archive of employment periods as first-class `employee_employments` rows not required for P6 hub `active|left`
- Reminder/scheduling workers not universally employment-gated (app + projections already gated)
- **Do not auto-start further Migration & Sync phases**
- Auth Wave 2 Phase 6 — not started
