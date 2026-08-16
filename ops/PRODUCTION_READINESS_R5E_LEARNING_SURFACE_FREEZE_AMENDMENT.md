# Production Readiness R5E — Learning Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`
**Phase:** R5E — Learning & Development Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5e-learning-20260815T141719Z/`
**Amends:** R5A customer-facing Learning enablement only. Wave 6 C2 domain authority stays frozen.

This amends R5A / R5D for **Learning surfaces and Setup enablement**. Performance, Talent, and Job Architecture enablement are unchanged. Remaining Wave 6 keys stay under the R5A honesty gate.

---

## What freezes with R5E

These are now binding contracts. Changing any of them requires a written amendment.

1. **Learning is a product surface over C2 only.** HTTP, HR Web, Manager, and Employee App are adapters. No second catalog / assignment / enrollment / completion / certification schema. No client-owned canonical state.
2. **`customer_enableable("learning")` is true** because `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready` are true. `mobile_ready` is false and **not required**. Setup remounts Learning configuration (`Wave6LearningPoliciesCard`).
3. **Learning is a commercial catalog SKU.** Key `learning` (aliases `learning_development`, `l_and_d`) is in `module_catalog`. Existing tenants are not auto-enabled.
4. **Assignment ≠ enrollment ≠ attendance ≠ completion ≠ certification.** A due-date transition does not fabricate completion. Attendance metadata is not completion. Course completion is not certification.
5. **Completion is evidence-backed.** Provenance (source, timestamp, verifier/provider, evidence reference) stays on the completion. Employees cannot declare mandatory / required learning complete unless company or item policy explicitly allows self-attestation.
6. **Mandatory generation is idempotent.** Re-evaluating a policy must not create duplicate assignments for the same `obligation_key`. Mandatory source stays explicit. Past due is derived overdue — not failed, non-compliant, terminated, or disciplinary unless another explicit authority says so.
7. **Request ≠ approval ≠ enrollment.** Rejection requires a reason and history. Manager approval is server-scoped from canonical org authority. Empty manager scope is fail-closed and not company-wide.
8. **Certifications are their own governed issuance.** Issued / effective / expiry / renewal history are preserved. Expiry does not erase the historical certificate. Renewal issues a new record linked with `renewal_of`.
9. **Sessions are server-authoritative.** Capacity / concurrency are enforced on enroll. Registered/enrolled ≠ attended ≠ completed.
10. **Performance remains independently healthy.** Learning may attach fulfillment evidence to a Wave 4 C3 development action. It must **never** silently close that action. Performance continues to work with Learning OFF. Learning continues to work with Performance OFF.
11. **Talent remains independently healthy.** When Talent is ON, Learning may read permitted skill-gap / development / interest context. It must not auto-designate HiPo, change potential or readiness, or invent a learning-based Talent score. Learning works Talent OFF.
12. **Job Architecture remains independently healthy.** When JA is ON, Learning may reference profiles / grades / levels / canonical skills for targeting. It must not create a Learning-specific job/grade hierarchy. Learning works JA OFF.
13. **No duplicate skills / competency authority.** A learning completion may be evidence. Course completion is not automatically verified competency unless the canonical competency authority says that evidence is sufficient.
14. **External LMS / provider integration is not required.** Wathefni's internal Learning product works independently.
15. **Module disable hides new surfaces, blocks new Learning work, preserves history, and suppresses new Learning notifications.** Assignments, completions, certificates, and audit remain reconstructable.
16. **Notifications use the canonical layer** (`flow=learning`) with R4 module suppression and dedupe. No second Learning inbox.
17. **Permissions stay separated.** `learning.read` / `.manage` / `.assign` / `.approve` / employee self. Employees cannot enumerate another employee's learning history. Tenant isolation is server-authoritative.
18. **R4 truth states apply.** Failed load must not look like “No learning assigned”, “No certificates”, or “No requests”. Disabled Learning returns `unavailable` with `counts=None`, not fake zeros.
19. **R5A honesty remains** for Benefits, ER, Engagement, Comp Planning, and Workforce Planning. Domain `FULL_PASS` is still not customer enablement for those keys.
20. **HR Mobile Learning admin is not an enable gate** and is not shipped.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Learning enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen. JA surfaces and Setup enablement are unaffected.
8. Wave 6 C2 domain math, tables, and anti-duplication stay frozen.
9. Remaining Wave 6 domain authorities stay frozen and customer-unusable.
10. Env kill switch `WATHEFNI_LEARNING_C2` still wins over Setup enablement.
11. `PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `learning_http.py` + `learning_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Learning workspace + Setup Learning card + Employee App Learning routes must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.learning` via `learning_surfaces.sync_catalog_entitlement`.
* Do not remount remaining Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not auto-enable Learning for existing tenants.
* Do not treat HR Mobile as a Learning enable gate.
* Do not begin R5F Benefits automatically.

## Owner review

R5E is complete and frozen. Stop.

Do not begin R5F Benefits automatically.
