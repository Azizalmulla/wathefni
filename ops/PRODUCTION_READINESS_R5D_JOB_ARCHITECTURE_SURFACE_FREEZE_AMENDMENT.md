# Production Readiness R5D — Job Architecture Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`
**Phase:** R5D — Job Architecture Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5d-job-architecture-20260815T134412Z/`
**Amends:** R5A customer-facing Job Architecture enablement only. Wave 6 C1 domain authority stays frozen.

This amends R5A / R5C for **Job Architecture surfaces and Setup enablement**. Performance and Talent enablement are unchanged. Remaining Wave 6 keys stay under the R5A honesty gate.

---

## What freezes with R5D

These are now binding contracts. Changing any of them requires a written amendment.

1. **Job Architecture is a product surface over C1 only.** HTTP and HR Web are adapters. No second family / function / profile / grade / level / career-edge schema. No client-owned canonical hierarchy.
2. **`customer_enableable("job_architecture")` is true** because `http_ready + hr_web_ready` are true. `manager_surface_ready`, `employee_surface_ready`, and `mobile_ready` are false and **not required**. Setup remounts JA configuration (`Wave6JobArchitecturePoliciesCard`).
3. **JA is a shared platform foundation, not a separately billable SKU.** It is absent from `module_catalog`. Setup exposes configuration honestly without forcing a commercial SKU narrative.
4. **JA is the sole Wave 6 grade/level authority.** Talent, Learning, Compensation Planning, and Workforce Planning must not create their own canonical grades or job-profile catalogs. Compensation Planning may later attach bands to JA grades; salary bands are out of R5D.
5. **Job Profile is a stable canonical object.** It is not silently derived from an employee's raw title. JA Job Profile ≠ Recruiting Job ≠ Requisition.
6. **Raw employment truth is preserved.** Mapping adds canonical structure. It does not destroy original title / grade / role wording. Historical records remain reconstructable.
7. **Auto-map only when deterministic and uniquely resolvable.** Ambiguous or unmatched values stay `unmapped_ambiguous` / `unmapped_none` for human review. No fuzzy or AI canonical mapping.
8. **Career edge ≠ employee eligibility.** A path does not mark anyone ready, eligible, or promotable. No automatic promotion recommendations. No AI eligibility score.
9. **Talent remains independently healthy.** Talent may optionally reference JA profiles / grades / levels / target roles. Existing Talent records are not rewritten merely because JA is enableable. `job_architecture_required` stays false. No Talent-specific role catalog.
10. **Recruiting remains independently healthy.** A requisition may point at a JA profile. The requisition remains recruiting truth. Editing a requisition does not rewrite the JA profile. Recruiting still functions without JA.
11. **JA is not a second employee or position authority.** Mapping changes architecture classification only. It does not silently promote, change salary, transfer organization, or alter employment status.
12. **Skills / competencies are references only.** No second skills authority. JA works with Talent / Performance / Learning OFF.
13. **Versioned / effective-dated semantics stay C1.** Renaming a grade or profile must not silently rewrite historical wording without trace. Historically referenced objects use retire / deactivate / supersede — not hard delete.
14. **Permissions stay separated.** `job_architecture.read` / `.manage` / `.mapping` / `.publish` / Setup-admin. Ordinary managers do not author. Employee App and HR Mobile have no required JA surface.
15. **R4 truth states apply.** Failed architecture load must not look like “No job profiles” or “No unmapped employees”. Disabled JA after historical mappings preserves raw values and returns `unavailable`, not fake zeros.
16. **R5I / R5J depend on this stamp but do not auto-enable.** Compensation Planning and Workforce Planning still need their own surface qualification.
17. **R5A honesty remains** for Learning, Benefits, ER, Engagement, Comp Planning, and Workforce Planning. Domain `FULL_PASS` is still not customer enablement for those keys.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Job Architecture enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen. Talent surfaces and Setup enablement are unaffected.
7. Wave 6 C1 domain math, tables, and anti-duplication stay frozen.
8. Remaining Wave 6 domain authorities stay frozen and customer-unusable.
9. Env kill switch `WATHEFNI_JOB_ARCHITECTURE_C1` still wins over Setup enablement.
10. `PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `job_architecture_http.py` + `job_architecture_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Job Architecture workspace + Setup JA card must ship with that backend.
* Do not remount remaining Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not add Job Architecture to `module_catalog` as a paid SKU.
* Do not treat Employee App or HR Mobile as a JA enable gate.
* Do not auto-enable Compensation Planning or Workforce Planning.

## Owner review

R5D is complete and frozen. Stop.

Do not begin R5E Learning automatically.
