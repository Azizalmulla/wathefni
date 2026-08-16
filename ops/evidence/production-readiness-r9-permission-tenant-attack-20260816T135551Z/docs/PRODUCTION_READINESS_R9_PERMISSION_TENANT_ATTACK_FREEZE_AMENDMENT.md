# Production Readiness R9 — Permission / Tenant Attack Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FULL_PASS`
**Phase:** R9 — Live permission and tenant-isolation probing
**Date:** 2026-08-16
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r9-permission-tenant-attack-20260816T005018Z/`
**Amends:** R1 live permission/tenant-attack intent and P1-19. R2–R8 remain frozen.

---

## What freezes with R9

1. **Session company is the only tenant authority.** Mismatched `X-Company-Code` is `403 dashboard_company_forbidden`. Employee `/app` identity is the session employee only.
2. **Server fail-closed** on cross-tenant IDs, exports, documents, manager-scope escapes, employee enumeration, module-disabled access, and privileged mutation. UI hiding is not evidence.
3. **`employees.read` / `employees.manage` remain grant-only** and are never inferred from role.
4. **P1-19** `company_code` predicates on `employees` hub writes stay in place.
5. **The live attack harness** `smoke-test-r9-permission-tenant-attack-db.py` remains the R9 qualification oracle.
6. **R9 does not reopen** Waves 1–6, R2–R8, or PT1–PT7 except a genuine correctness/security blocker.
7. **R9 does not authorise store submission.** Physical RP, clean canary, and the store build gate remain separate.

## Owner review

R9 is complete and frozen. Continue the store-release program. Do not begin the HR Web UX redesign.
