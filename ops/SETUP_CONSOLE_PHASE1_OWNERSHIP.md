# Setup Console Phase 1 — Canonical configuration ownership + deep links

**Status:** Implemented locally; qualify on canary before broad rollout.  
**Scope:** Ownership cleanup, deep links, Employee App policy write consolidation, module disable semantics contract.  
**Out of scope:** Visual redesign, Phase 2 Setup payroll forms, Employee App P1, Auth Wave 2 Phase 6.

## Verdict

**PASS** (Phase 1 — ownership + deep links + Employee App policy write consolidation)

Evidence:
- Canary: `ops/evidence/setup-console-phase1-20260808T015639Z` (21/0 incl. live ownership + tenant-scoped policy)
- Local source smoke: `ops/evidence/setup-console-phase1-20260808T015644Z` (29/0)

Run `python3 wathefni-orchestrator/smoke-test-setup-console-phase1.py` (optionally with live Setup credentials). Evidence lands under `ops/evidence/setup-console-phase1-*`.

## Configuration ownership map

| Setting | Canonical owner | Ops surface | Notes |
|---|---|---|---|
| Company identity (name/country/tz/currency) | Setup Console `#classic-profile` | — | |
| Module entitlements | Setup Console `#classic-modules` | — | |
| Employee App on/off | Setup Console `#classic-modules` | Employees (read-only when off + Configure link) | PostHire cannot toggle |
| Employee App who-can-use policy | Setup Console `#classic-app-access` | Employees per-person only | PostHire company policy PATCH refused |
| Per-employee app eligibility / revoke | Employees | — | |
| Channel / company WhatsApp policy | Setup Console `#classic-channels` | — | |
| HR personal WhatsApp login | Settings → Account | Setup may seed Owner identity | |
| Company payroll setup | Setup Console `#classic-payroll-setup` | Payroll (read-only summary + Configure link) | Phase 2A forms live |
| Payroll runs / reviews | Payroll | — | |
| Team invites (day-to-day) | Settings → Team | Setup Owner seed only | |
| Connected systems | Setup control + Migration & Sync | Settings integrations (connectors) | |

## Module disable semantics (standard)

- Stop new future activity  
- Hide navigation / surfaces  
- Fail-close module APIs  
- Preserve historical records + audit  
- **Do not** delete data  
- **Do not** silently cancel/mutate existing records  

**Known exception:** `employee_app` — disable revokes sessions and supersedes open invites (explicit lifecycle); history retained.

Contract: `wathefni-orchestrator/setup_console_phase1_ownership.py` and `GET /dashboard/superadmin/setup/ownership`.

## Changes made

### Backend
- Setup routes: `GET/PATCH .../setup/companies/{code}/employee-app-access`, `GET .../setup/ownership`
- Phase 2B (frozen separately): durable who-can-use (`everyone` / `departments` / `employees`) with preview + batch reconcile — see `ops/SETUP_CONSOLE_PHASE2B_EMPLOYEE_APP_ACCESS.md`
- PostHire `PATCH .../app-access/policy` refuses company-level policy writes (`company_app_access_owned_by_setup_console`)
- `set_company_app_access_policy(..., allow_module_toggle=False)` for Setup/PostHire callers
- Launch readiness deep links → `#classic-*` anchors + `/dashboard?page=...`

### Frontend
- Ownership map + helpers: `src/lib/setupConsoleOwnership.ts`
- `ConfigureInSetupBanner` / ops links
- Setup Classic: ownership card, Employee App access policy card, payroll placeholder, section anchors, hash scroll
- Settings integrations + Payroll / Employees: Configure-in-Setup banners

## Phase 2 gaps (do not start automatically)

1. ~~Move company payroll policy/forms from Payroll into Setup~~ → **Done in Phase 2A**
2. Roles/permissions canonical Setup UI (beyond Owner seed)
3. Attendance / Leave / Shifts / Documents / Compliance / Onboarding **company policy** forms in Setup
4. Integrations catalog UX in Setup control (without duplicating Migration & Sync connectors)
5. Broader EN/AR polish on new Classic cards
6. Full live multi-tenant isolation matrix beyond smoke
7. Phase 2A follow-ons: working calendar UI, PIFSS wage-base editors, allowlist-in-Setup

## Qualification checklist

- [ ] Canonical owner documented for every audited setting  
- [ ] No conflicting duplicate writes for Employee App company policy  
- [ ] Deep links route to Classic anchors / ops pages  
- [ ] Tenant-scoped policy responses  
- [ ] Permissions: Setup superadmin vs HR PostHire  
- [ ] Module disable semantics contract + employee_app exception  
- [ ] Historical data retained after disable (employee_app sessions closed, rows kept)  
- [ ] EN/AR banners where added  
