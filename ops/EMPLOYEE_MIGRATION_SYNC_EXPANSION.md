# Employee Migration & Sync Expansion

Canonical plan for bringing existing companies onto Wathefni without forcing
manual rebuild of HR data. **CSV/XLSX roster foundation remains the base** —
Connected Systems (P5) build on the same batch/row/provenance model.

## Audit snapshot (pre-P1)

| Area | Status |
|---|---|
| Foundation CSV/XLSX preview → confirm | **HAVE** (`employee_migration_foundation.py`) |
| Needs review · provenance · history · exception CSV · concurrency-safe rollback | **HAVE** |
| No invites / no auto-onboarding on foundation path | **HAVE** (create uses `seed_compliance=False`, `start_onboarding=False`) |
| Legacy `/employees/import` fallback when flag off | **WAS RISK** — could `seed_compliance=True` when compliance module on |
| Deep fields (civil ID, addresses, bank, docs, compliance evidence) | **MISSING** → P2 |
| Existing-employee onboarding migration states | **MISSING** → P3 |
| Leave/payroll/shift opening balances | **MISSING** → P4 |
| Connected systems / connectors / incremental sync | **DONE** → P5 (`20260807T102912Z`) |
| Leavers / lifecycle sync | **MISSING** → P6 |

## Architecture (proposed)

```
External source (CSV/XLSX | API | SFTP | vendor connector)
        │
        ▼
┌───────────────────────────────┐
│ Sync / Import Run             │  idempotent batch ledger
│  · source_system + run_id     │
│  · field mapping              │
│  · per-field authority policy │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│ Match                         │  external_id → phone → Needs review
│ Never name-alone              │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│ Apply or Needs review         │
│  · missing = not supplied     │
│  · never overwrite higher     │
│    Wathefni authority         │
│  · provenance on every write  │
└───────────────┬───────────────┘
                ▼
        Wathefni canonical ops record
```

Authority ladder (aligns with Bank ESS): **imported/proposed → verified in Wathefni → payroll-effective** where relevant.

## Phase map

| Phase | Intent | Status |
|---|---|---|
| **P1** | Foundation-only production path; kill legacy seed/onboarding risk | **DONE** |
| **P2** | Deep employee record migration + 3-layer field model + mapping profiles | **DONE** |
| **P3** | Existing-employee onboarding migration states | **DONE** (`20260807T095819Z`) |
| **P4** | Opening balances / current-state cutover | **DONE** (`20260807T101417Z`) |
| **P5** | Real Connected Systems (API/SFTP/connectors) | **DONE** (`20260807T102912Z`) |
| **P5.1** | Scheduler + real SFTP | **DONE** (`20260807T104900Z`) |
| **P5.2** | Connector secret hardening | **DONE** (`20260807T181334Z`) |
| **P6** | Leavers + lifecycle sync (no hard-delete) | **DONE** (`20260807T183857Z`) |
| **P6.1** | Live UI refresh after sync (no new realtime platform) | **DONE** (`20260807T185259Z`) — freeze here; do not auto-start further phases |

Do **not** start Auth Wave 2 Phase 6. Do **not** send activation invitations as a migration side effect.

## Exact P1 scope (implemented)

1. `/dashboard/posthire/employees/import` **only** calls the foundation path.
2. If foundation flag/company allowlist is off → **503 `migration_foundation_required`** (no legacy fallback).
3. `start_onboarding=true` → **422 `migration_onboarding_forbidden`** (not silently ignored).
4. Preserve preview → confirm, Needs review, provenance, history, exception CSV, concurrency-safe rollback.
5. Contract: `employee_migration_sync_p1_foundation_only` @ `1.2.0`.
6. Honesty flags: `production_path_foundation_only`, `legacy_import_disabled`, `no_invites`, `no_auto_onboarding`, `no_auto_compliance_seed_on_import`.

### Explicitly out of P1

Deep fields · onboarding history states · balances · connectors · leavers · Auth Wave 2 Phase 6.

## Canary

- Company: `WATHEFNI`
- Flag: `WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION=on`
- Allowlist: `WATHEFNI_EMPLOYEE_MIGRATION_FOUNDATION_COMPANIES=WATHEFNI`
- Smoke: `smoke-test-employee-migration-foundation.py`