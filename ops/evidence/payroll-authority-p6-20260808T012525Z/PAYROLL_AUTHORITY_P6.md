# Payroll Authority P6 — Kuwait Production Readiness + Controlled Real-Money Enablement

**Status:** implemented (company entitlement model)  
**Version:** 1.0.0  
**Date:** 20260808  
**Depends on:** P1–P5 frozen · `KW_PUBLIC_BASELINE_v1.0.0`  
**Preserves:** preview_non_authoritative on calc rows · Mode B external · payment_processing=disabled · no invented payment_date · fail-closed statutory gates

---

## Production entitlement model

Replaces blanket global `SYNTHETIC_ONLY` as the Mode A production gate with company-level entitlement:

| State | Meaning |
|---|---|
| `disabled` | No Mode A money authority (default for tenants) |
| `preview_only` | Native calc/preview allowed; seal refused for non-synthetic |
| `authoritative_allowlisted` | Seal only for allowlisted employees (+ synthetic qualification fixtures) |
| `authoritative` | Company-wide Mode A seal (still requires readiness + finalize gates) |

- Explicit opt-in via `set_company_mode_a_entitlement` (actor + reason + audit)
- Never inferred from Payroll module enablement alone
- Synthetic fixtures remain valid for qualification (`ALLOW_SYNTHETIC_QUALIFICATION`)
- **WATHEFNI** is the first controlled company (`authoritative_allowlisted`)
- Not a global unlock for all tenants

---

## Payroll readiness contract

`validate_payroll_readiness` returns actionable issues (EN/AR + how_to_fix), not stack traces.

Required before authoritative entitlement:

- payroll mode (native / external / parallel_shadow)
- attendance payroll mode
- approved company payroll policy
- compensation structure (approved contracts)
- finalize/SOD policy
- Kuwait statutory baseline available (Wathefni-owned)

Setup Console schema (contract only): `ops/payroll_authority_p6_setup_console_schema_v1.json`

---

## Exception / variance

- Buckets: `ready` · `needs_review` · `blocked` · `changed_since_previous`
- Variance vs previous authoritative period is **advisory only** — never rewrites money
- Controlled overrides: policy/variance ack only — **never** clears statutory uncertainty

---

## Independent oracle

- Module: `payroll_authority_p6_oracle.py`
- Fixtures: `ops/payroll_authority_p6_oracle_fixtures_v1.json`
- Does not import P3 calc internals
- Qualification requires fixture residual = 0

---

## Module / SQL / APIs / smoke

- `wathefni-orchestrator/payroll_authority_production_p6.py`
- `wathefni-orchestrator/ops/sql/payroll_authority_production_p6_v1.sql`
- APIs under `/dashboard/posthire/payroll/authority-production/*`
- Smoke: `ops/smoke-test-payroll-authority-p6.py`

---

## Remaining gaps before unrestricted customer rollout

- Per-customer legal/ops onboarding beyond WATHEFNI canary
- Broader multi-tenant residual-zero evidence packs
- Setup Console UX implementation of the schema contract
- Payment/WPS still a separate program
- Counsel acknowledgement for company-specific statutory extensions

**Do not start:** Employee App P1 · broad Setup Console redesign · Auth Wave 2 Phase 6 · payment/WPS
