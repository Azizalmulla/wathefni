# Setup Console Phase 2A — Payroll Setup Experience

**Status:** PASS (canary qualified)  
**Scope:** Replace payroll setup placeholder with P6 contract-driven company configuration in Setup Console.  
**Frozen:** Payroll Authority P1–P6 calc/seal/entitlement semantics unchanged. Phase 1 ownership frozen.  
**Out of scope:** Next Setup Console phase, Employee App P1, Auth Wave 2 Phase 6.

## Verdict

**PASS**

Evidence: `ops/evidence/setup-console-phase2a-*` (local + canary live).

## Setup Console Payroll IA

```
Payroll
├── Readiness (Setup incomplete | Needs attention | Ready for preview | Ready for authoritative | Ready for external)
├── Wathefni-owned (read-only statutory baseline / calc / sealing)
├── Required
│   ├── Mode: Wathefni Payroll | External Payroll
│   ├── Cycle + cut-off (monthly + optional day)
│   ├── Attendance → pay impact
│   ├── Company policy + compensation readiness (deep link to Employees)
│   ├── Approvals / SOD (SME defaults)
│   └── Wathefni authority level (explicit opt-in)
├── Optional (collapsed): lateness / absence / unpaid leave money flags
└── Advanced (collapsed): enterprise SOD; allowlist managed in Payroll ops
```

## Settings ownership map

| Setting | Owner | Notes |
|---|---|---|
| Payroll mode (native/external/parallel_shadow) | Setup Console | Guarded/audited mode switch |
| Frequency / cut-off | Setup (`setup_extras`) | Monthly default; cut-off 1–28 |
| Attendance payroll mode | Setup | UX mapped → `informational`/`required`/`ignored` |
| Approved company policy version | Setup | Creates P3 approved versions |
| Approval / SOD finalize policy | Setup | SME defaults + enterprise strict |
| Mode A entitlement opt-in | Setup | Blocked if payroll module off or external mode |
| Kuwait statutory rates/baseline | Wathefni (read-only) | Never company-editable |
| Compensation contracts | Employees (ops) | Readiness deep-links here |
| Allowlist (authoritative_allowlisted) | Payroll ops | After readiness |
| Runs / reviews / finalize / payslips | Payroll ops | Unchanged |
| Legacy hours policy editor | Retired from Payroll UI | Writes refused → Setup |

## Readiness UX

Uses `validate_payroll_readiness` via Setup GET/PATCH composer.

| State | When |
|---|---|
| Setup incomplete | Missing base mode/attendance |
| Needs attention | Blockers present |
| Ready for preview | Ready + preview entitlement (or ready without authoritative) |
| Ready for authoritative payroll | Ready + authoritative entitlement |
| Ready for external payroll | External mode without native blockers |

Every blocker: EN/AR message + how to fix + deep link. No raw Wave/P6 names in customer UI.

## Changes

### Backend
- `setup_console_payroll_phase2a.py` — get/patch composer over Wave1/P2/P3/P5/P6
- `GET/PATCH /dashboard/superadmin/setup/companies/{code}/payroll-setup`
- Additive `payroll_company_settings.setup_extras` jsonb
- PostHire company policy create + `set_payroll_policy` dashboard action → 422 owned by Setup

### Frontend
- `PayrollSetupCard` replaces placeholder
- Payroll timesheet policy + components policy create UIs → read-only + Configure in Setup
- Preview calc retained in Payroll

## Remaining Setup Console gaps (do not auto-start)

~~1. Richer optional: working calendar UI, PIFSS wage-base editors, variance thresholds UI~~ → **Phase 3A**  
~~2. Authoritative allowlist management inside Setup~~ → **Phase 3A**  
3. Roles/permissions Setup beyond Owner seed  
4. Leave/Attendance/Shifts/Docs/Compliance/Onboarding company-policy forms  
5. Broader multi-tenant isolation matrix beyond smoke  
6. Parallel shadow coexistence advanced UX polish  

See `ops/SETUP_CONSOLE_PHASE3A_PAYROLL_SETUP.md`.

## Qualification coverage

- SME Wathefni + informational  
- Attendance-driven policy  
- Enterprise SOD  
- External Mode B  
- Incomplete → actionable blockers  
- Statutory read-only  
- Mode switch audited/guarded  
- Temporary Payroll editors retired  
- Tenant 404 for unknown company  
- EN/AR/RTL on Setup payroll card  
