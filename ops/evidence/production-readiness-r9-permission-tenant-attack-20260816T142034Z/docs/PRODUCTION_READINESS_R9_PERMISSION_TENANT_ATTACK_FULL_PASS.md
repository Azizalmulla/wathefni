# PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FULL_PASS

**Status:** QUALIFIED / frozen — continue store-release program
**Stamp:** `PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FULL_PASS`
**Phase:** R9 — Live permission and tenant-isolation probing
**Date:** 2026-08-16
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r9-permission-tenant-attack.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r9-permission-tenant-attack-20260816T005018Z/`
**Prior freeze:** `PRODUCTION_READINESS_R8_DELIVERY_SAFETY_FULL_PASS` (R8 stays frozen)

**Scope:** Authenticate as Employee, Manager, HR, Payroll-sensitive, Performance/Talent-sensitive, ER-sensitive, and Setup/admin on an isolated two-tenant staging database. Probe cross-tenant IDs, direct APIs, exports, documents, manager-scope escapes, employee enumeration, module-disabled access, and privileged mutation. Server must fail closed. Add P1-19 `company_code` predicates on `employees` hub writes. Do not reopen frozen Wave 1–6 / R2–R8 / PT1–PT7 architecture.

---

## 1. Result

| Gate | Result |
|---|---|
| R9 unit contracts | **25 passed, 0 failed** (`R9_PERMISSION_TENANT_ATTACK_UNIT_PASS`) |
| Frozen R2 security unit | **84 passed, 0 failed** |
| Staging two-tenant live session attack | **48 passed, 0 failed** (`R9_PERMISSION_TENANT_ATTACK_DB_PASS`) |
| Tenants | `R9AC3A1F7` / `R9BC3A1F7` / `R9CC3A1F7` (leave module off on C) |
| Live staging `/health` | **200** |
| Live staging `/ready` | **200** · `status=ready` |
| Live unauthenticated dashboard surfaces | **401** |
| Live unauthenticated `/app/me` `/app/leave` | **503** `employee_app_disabled` — fail-closed (capability off on the live process) |
| Open R9 blockers | **none** |

Roles probed with real sessions (not UI hiding, not dependency overrides): Employee, Manager, HR, payroll_operator, viewer, owner. Cross-tenant IDs, `X-Company-Code` spoofing, exports, documents, manager-scope escapes, employee enumeration, module-disabled leave, and privileged mutation all failed closed.

This stamp is **not** store-submission-ready. R9 is frozen. The store-release program continues into the E2E harness, R10, R11, physical qualification, clean canary, and the store build gate.

---

## 2. R1 items closed in R9

| ID | Close |
|---|---|
| **P1-19** | `employees` hub writes now include `company_code` predicates (onboarding `raw_json`, onboarding received, related selects). Remaining unscoped writes are not on the `employees` hub. |
| **Live permission / tenant attack** | Two-tenant staging attack harness is permanent: `smoke-test-r9-permission-tenant-attack-db.py`. |

---

## 3. Qualification honesty

- Directory reads require explicit `employees.read` grants (grant-only; never inferred from role). The harness seeds those grants. UI hiding was not used as evidence.
- Manager scope requires `WATHEFNI_ORG_HIERARCHY=on` in the attack process. Fail-closed empty lists without it are not treated as a leak.
- Live staging systemd currently has the employee app capability off, so unauthenticated `/app/*` returns **503** `employee_app_disabled` rather than 401. That is fail-closed, not a public leak. Authenticated `/app` contracts were proven in-process with `WATHEFNI_EMPLOYEE_APP=on`.
- This does not claim production tenant attack, physical-device auth, or store submission.
