# Production Readiness R5I — Compensation Planning Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS`
**Phase:** R5I — Compensation Planning Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5i-compensation-planning-20260815T163045Z/`
**Amends:** R5A customer-facing Compensation Planning enablement only. Wave 6 C6 domain authority stays frozen.

This amends R5A / R5H for **Compensation Planning surfaces and Setup enablement**. Performance, Talent, Job Architecture, Learning, Benefits, Employee Relations, and Engagement enablement are unchanged. Remaining Wave 6 key (`workforce_planning`) stays under the R5A honesty gate.

---

## What freezes with R5I

These are now binding contracts. Changing any of them requires a written amendment.

1. **Compensation Planning is a product surface over C6 only.** HTTP and HR Web are adapters. No second compensation / salary / payroll schema. No client-owned canonical state. No frontend compensation math.
2. **`customer_enableable("comp_planning")` is true** because `http_ready + hr_web_ready` are true **and** Job Architecture is customer-enableable. Employee App and HR Mobile are **not required**. Manager recommend is optional (`manager_surface_required=false`, `manager_surface_ready=true`). Setup remounts Compensation Planning configuration (`Wave6CompensationPlanningPoliciesCard`).
3. **Compensation Planning is a commercial catalog SKU.** Key `comp_planning` (aliases `compensation_planning`, `compensation`) is in `module_catalog`. `people_surface=false`. `app_surface_key=None`. Audience `hr`. Existing tenants are not auto-enabled.
4. **Job Architecture is a hard dependency.** Enable fails `ja_must_be_enabled` if JA is off. Runtime gate fails `ja_hard_dependency_unmet` if JA is unavailable. The workspace is then `unavailable` with `counts=None` — never a guessed worksheet. Historical cycle data remains reconstructable.
5. **Bands belong to Compensation Planning, not Job Architecture.** They attach to canonical JA grade / optional level. `grade ≠ salary band`. `salary range ≠ employee salary`. No compensation-specific grades or shadow role catalog. Being outside a range does not automatically change pay.
6. **Cycle launch freezes the snapshot.** Eligible employees, employment context, JA profile/grade/level, compensation basis, policy, budget, and band/range version are pinned. Later employment, salary, org, JA, or policy edits must not silently rewrite the active/historical cycle.
7. **Eligible ≠ entitled to increase.** Eligibility only means the employee participates in the planning population. No automatic raise.
8. **Budget math is backend-authoritative.** Allocation, utilization, and over-budget state are server-side. Over-budget follows configured policy (`warn` / `hard_block` / `exception_approval`). No frontend-only enforcement.
9. **Recommendation ≠ approval ≠ finalization ≠ salary application.** Capture amount/%, rationale, actor, timestamp, source, history. Calibration inserts a new `calibrated` layer; the original recommendation remains historically visible.
10. **Performance and Talent are optional advisory context only.** A sealed rating or HiPo / potential / succession flag must never automatically determine salary, bonus, or adjustment. Compensation Planning works with Performance OFF and Talent OFF.
11. **Manager participation is scoped and fail-closed.** Empty manager scope = zero rows, never company-wide. Managers do not gain company-wide salary visibility, peer-manager budgets, HR calibration, final approval, or Talent-sensitive data. Server enforcement required.
12. **SOD is enforced.** Distinct authority for recommend / calibrate / approve / finalize / handoff. Same actor cannot approve their own recommendation. HR admin does not silently bypass C6 SOD.
13. **Finalized ≠ applied.** Finalization seals the planning decision and must not mutate employee salary, employment terms, or payroll.
14. **Handoff is explicit, idempotent, attributable, and effective-date aware.** `handoff created ≠ salary changed ≠ payroll applied ≠ paid`. Comp never sets `employment_mutated_by_comp` or `payroll_paid`. Replay of the same `(company, cycle, decision, target)` returns the existing package.
15. **Payroll is optional.** The full plan/finalize flow works with Payroll OFF. With Payroll ON, use explicit handoff only. Payroll remains sole execution authority. “Payment file acknowledged” is not paid.
16. **Employment authority stays outside Comp.** A cycle must not create shadow employment records. Any effective salary/employment change uses existing canonical employment / payroll authority.
17. **KWD explicit. No hidden FX.** Unsupported currency fails `currency_unsupported_no_fx`. Do not invent exchange-rate logic.
18. **Compensation data is highly sensitive.** Ordinary HR access does not imply `comp_planning.*`. Export is separately permissioned (`comp_planning.export`) and cannot bypass manager scope or SOD.
19. **Notifications use the canonical layer** (`flow=compensation_planning`) with R4 module suppression and dedupe. Copy is generic and must not leak salary values unless the recipient/surface is explicitly authorized.
20. **Module disable hides new workspace/work, preserves historical cycles, suppresses new notifications, and does not reverse applied downstream changes.** Disabled / JA-unmet workspace is `unavailable` with `counts=None`.
21. **R4 truth states apply.** Distinguish no eligible employees, no recommendations yet, forbidden, unavailable, error, and loading. Never translate 403 or API failure into “No compensation changes.”
22. **R5A honesty remains** for Workforce Planning. Domain `FULL_PASS` is still not customer enablement for that key.
23. **Employee App and HR Mobile Compensation Planning are not enable gates** and are not shipped.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Compensation Planning enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen.
8. R5E (`PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`) remains frozen.
9. R5F (`PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS`) remains frozen.
10. R5G (`PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS`) remains frozen.
11. R5H (`PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS`) remains frozen. Engagement surfaces and Setup enablement are unaffected.
12. Wave 6 C6 domain math, tables, SOD, budget, finalize, and anti-duplication stay frozen.
13. Remaining Wave 6 domain authority (Workforce Planning) stays frozen and customer-unusable.
14. Env kill switch `WATHEFNI_COMP_PLANNING_C6` still wins over Setup enablement.
15. `PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `compensation_http.py` + `compensation_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Compensation Planning workspace + Setup Compensation Planning card must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.comp_planning` via `compensation_surfaces.sync_catalog_entitlement`, and C6 enable must still require JA enabled for that company.
* Do not remount the Workforce Planning Setup card without flipping that key's `customer_enableable`.
* Do not auto-enable Compensation Planning for existing tenants.
* Do not treat an Employee App or HR Mobile Compensation Planning workspace as an enable gate.
* Do not begin R5J Workforce Planning automatically.

## Owner review

R5I is complete and frozen. Stop.

Do not begin R5J Workforce Planning automatically.
