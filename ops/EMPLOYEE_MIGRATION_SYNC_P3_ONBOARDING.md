# Employee Migration & Sync P3 — Existing-Employee Onboarding Migration

Contract: `employee_migration_sync_p3_onboarding` @ `3.0.0`  
Builds on frozen P1 foundation path + P2 3-layer field model.  
**Canary verdict:** PASS · stamp `ops/evidence/employee-migration-sync-p3-20260807T095819Z/`

## Dispositions

| Disposition | Hub `onboarding_status` | HR needs-onboarding queue | Employee app | Reminders |
|---|---|---|---|---|
| `already_onboarded_externally` | `migrated_external` | Excluded | No checklist; message that onboarding completed outside Wathefni | Suppressed |
| `onboarding_history_imported` | `imported_history` | Excluded | No checklist; history stored as migrated provenance | Suppressed |
| `onboarding_not_applicable` | `not_applicable` | Excluded | No checklist | Suppressed |
| `needs_wathefni_onboarding` | `not_started` (or started if explicit) | Included | Normal workflow only after deliberate start | Normal |
| `unknown_insufficient_evidence` | `not_started` | Included (decide) | No fake completion | Normal |

Missing / “active employee” alone → **unknown** (never invents completed).

## Canonical mapping fields

`onboarding_migration_disposition`, `onboarding_status`, `onboarding_completed_at`, `onboarding_history`, `onboarding_start_after_import`

History rows land in `employee_onboarding_migration_history` with `wathefni_verified=false`.

## Authority

- Default import still does **not** start onboarding or send invites.
- Explicit `onboarding_start_after_import=true` + `needs_wathefni_onboarding` may call canonical `start_onboarding`.
- Native Wathefni assignment/checklist activity sets `native_superseded` and wins over imported settled state.
- `recompute()` short-circuits settled migrations until superseded.
- Rollback removes batch migration stamps but preserves native-superseded rows / activity.

## Tables

- `employee_onboarding_migration`
- `employee_onboarding_migration_history`
