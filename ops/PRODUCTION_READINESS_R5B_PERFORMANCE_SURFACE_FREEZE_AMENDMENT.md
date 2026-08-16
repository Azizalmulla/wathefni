# Production Readiness R5B — Performance Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`
**Phase:** R5B — Performance Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5b-performance-20260815T123626Z/`
**Amends:** R5A customer-facing Performance enablement only. Wave 4 domain authorities stay frozen.

This amends R5A for **Performance surfaces and Setup enablement**. Talent and Wave 6 remain under the R5A honesty gate.

---

## What freezes with R5B

These are now binding contracts. Changing any of them requires a written amendment.

1. **Performance is a product surface over C1–C4 only.** HTTP, HR Web, Manager, Employee App, and thin HR Mobile are adapters. No second goal/review model. No frontend formulas for progress, KR rollup, review status, or final rating.
2. **`customer_enableable("performance")` is true** because `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready + mobile_ready` are all true. Setup remounts Performance policy enablement (`Wave4PerformancePoliciesCard`, `scope="performance"`).
3. **Talent stays false / hidden.** `customer_enableable("talent")` remains false. Talent is not a catalog SKU. Reserved Talent HTTP stays 404 `capability_not_released`. A high Performance rating is not HiPo.
4. **Launch snapshots freeze participant / form / config.** Later org, manager, or template edits must not silently rewrite an active or historical cycle.
5. **Rating layers stay distinct:** self, manager, 360 evidence, pre-calibration, calibrated, sealed final. Sealed results are not silently editable.
6. **360 confidentiality is server-enforced.** Anonymous identity must not leak to the employee. Minimum-response / privacy thresholds stay in C2. No client-side anonymity.
7. **Manager scope is fail-closed.** Empty `manager_scopes` is an empty list, not company-wide access. Managers do not gain cycle admin or calibration unless explicitly authorized.
8. **HR Mobile stays thin.** Queue + detail + submit only. Calibration administration and cycle configuration stay Web-first.
9. **Performance works with Talent OFF, competencies OFF, and Learning unreleased.** Learning completion ≠ development completion.
10. **Disabled Performance** removes nav, blocks new work, preserves history, fails deep links cleanly, and suppresses new Performance notifications via R4.
11. **R5A honesty remains.** Domain `FULL_PASS` is still not customer enablement for any other Wave 4/6 key. Only Performance left the unreleased set.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A (`PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS`) remains frozen, except the Performance enablement carve-out above.
5. Wave 4 C1–C4 domain math, tables, and anti-duplication stay frozen.
6. Wave 6 domain authorities stay frozen and customer-unusable.
7. Env kill switches (`WATHEFNI_PERFORMANCE_*`) still win over Setup enablement.
8. `PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `performance_http.py` + `performance_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Performance workspace + Setup Performance card must ship with that backend.
* Employee App + HR Mobile cobundle JS (OTA-eligible) must ship the Performance routes.
* Do not remount Talent or Wave 6 Setup cards without flipping that key's `customer_enableable`.

## Owner review

R5B is complete and frozen. Stop.

Do not begin R5C Talent automatically.
