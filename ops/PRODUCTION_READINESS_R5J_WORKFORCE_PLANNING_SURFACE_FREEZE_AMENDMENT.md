# Production Readiness R5J — Workforce Planning Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS`
**Phase:** R5J — Workforce Planning Product Surface (final R5 surface slice)
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5j-workforce-planning-20260815T165705Z/`
**Amends:** R5A customer-facing Workforce Planning enablement only. Wave 6 C7 domain authority stays frozen.

This amends R5A / R5I for **Workforce Planning surfaces and Setup enablement**. Performance, Talent, Job Architecture, Learning, Benefits, Employee Relations, Engagement, and Compensation Planning enablement are unchanged. `UNRELEASED_CAPABILITY_KEYS` is now empty.

---

## What freezes with R5J

These are now binding contracts. Changing any of them requires a written amendment.

1. **Workforce Planning is a product surface over C7 only.** HTTP and HR Web are adapters. No second workforce planning / forecasting schema. No client-owned canonical state. No frontend projection formulas.
2. **`customer_enableable("workforce_planning")` is true** because `http_ready + hr_web_ready` are true **and** Job Architecture is customer-enableable. Employee App and HR Mobile are **not required**. Manager demand/review/submit is optional (`manager_surface_required=false`, `manager_surface_ready=true`). Setup remounts Workforce Planning configuration (`Wave6WorkforcePlanningPoliciesCard`).
3. **Workforce Planning is a commercial catalog SKU.** Key `workforce_planning` (aliases `workforce`, `wfp`) is in `module_catalog`. `people_surface=false`. `app_surface_key=None`. Audience `hr`. Existing tenants are not auto-enabled.
4. **Job Architecture is a hard dependency.** Enable fails if JA is off. Runtime gate fails if JA is unavailable. The workspace is then `unavailable` with `counts=None` — never a guessed title catalog. Historical plan data remains reconstructable.
5. **WFP uses canonical JA Job Profile / Grade / Level only.** No planning-only duplicate role/grade catalog.
6. **`actual workforce ≠ baseline ≠ workforce plan ≠ scenario ≠ approved execution`.** Baseline is an explicit frozen as-of snapshot of canonical actual (employment / org / positions where applicable / JA mapping). Once frozen for a planning version, later actual changes must not rewrite it.
7. **Workforce Planning is never actual headcount authority.** Planned headcount, positions, hires, exits, and reductions must never enter Wave 5 actual workforce metrics. Distinct `truth_plane` semantics stay in force.
8. **Planned position ≠ actual position.** A planned position must not appear as an employee vacancy, create employment, enter payroll, or enter actual Wave 5 headcount.
9. **Demand is explicit.** Growth / new headcount, replacement, vacancy, reduction, and role-mix change are typed facts with org/location, JA profile/grade/level, quantity, period, reason/type, owner, and provenance. Do not infer replacement or growth from numbers alone.
10. **Scenarios are versioned and independent.** Editing Scenario B must not mutate baseline, actual workforce, or Scenario A. Approved scenarios must not be silently edited in place; revisions create a new version.
11. **Assumptions are explicit and versioned.** Expected hires/exits, start dates, salary/cost assumptions, hiring lead time, role mix, and other configured drivers. Never silently convert historical Wave 5 turnover into a forecast.
12. **Projection math is backend-authoritative, deterministic, reproducible, and explainable.** No hidden AI forecast. No frontend-only formulas.
13. **Planning periods come from Setup.** Monthly / quarterly / annual / fiscal horizon as configured. Do not invent period logic in the client.
14. **Planned workforce cost is planned / estimated, not finalized payroll cost.** `planned cost ≠ payroll result ≠ payment`. KWD explicit. No hidden FX. Unsupported currency fails `currency_unsupported_no_fx`.
15. **Compensation Planning is optional.** When enabled, WFP may consume governed bands/ranges and planning assumptions as cost context. It must not start a compensation cycle, create a raise, or modify salary. WFP works with Compensation Planning OFF.
16. **Recruiting is optional.** Approved demand → explicit authorized handoff → linked DRAFT requisition only. `approved workforce demand ≠ approved requisition ≠ posted job ≠ candidate ≠ hire`. Never auto-approve, auto-post, auto-create a candidate, or auto-hire. WFP is a complete planning product with Recruiting OFF (`approved/unexecuted` / exportable / externally executed).
17. **Handoff is idempotent.** Retry, double-click, partial failure, cancel, and quantity changes must not create duplicate requisitions. Preserve lineage: workforce demand ↔ handoff ↔ draft requisition.
18. **Talent is optional.** When enabled, WFP may use authorized skills / capability gaps / readiness as context. It must not duplicate skills truth, infer capability automatically, or create a universal workforce/talent score. WFP works with Talent OFF.
19. **Gaps are definition-driven.** Planned demand vs projected supply, role quantity deficit, or an explicit capability gap. No universal `workforce_health_score` or hidden AI score.
20. **Scenario comparison validates compatibility** of baseline, period, currency, and definition/version. Never compare incompatible scenarios as if they were equivalent.
21. **Approval lifecycle stays C7-authoritative** (`draft → submitted → approved → execution_ready → closed`, plus rejected). `approval ≠ actual workforce change`.
22. **Actual-vs-plan queries canonical actual workforce truth.** Do not copy actual employees into a new Workforce Planning SoT. A current actual number and a historical baseline are different concepts.
23. **Wave 5 integration stays planning-plane only.** Planning facts may feed frozen Wave 5 Intelligence as planning facts. No second analytics/evaluator engine. Planned headcount must never contaminate actual headcount, hires, exits, or payroll.
24. **Manager participation is scoped and fail-closed.** Empty manager scope = zero rows, never company-wide. Managers do not automatically receive company-wide plans, restructuring data, salary/cost-sensitive information, or final execution authority. Server enforcement required.
25. **Workforce plans are confidential.** Explicit permissions for planning read, planner, cost-sensitive view, approver, execution/handoff, and manager scope. Employee App must have no WFP surface and no future-plan leakage.
26. **Assistant is read/explain only.** It may explain authorized scenarios, assumptions, gaps, and comparisons. It may not create scenarios, change assumptions, approve plans, create requisitions, or execute hiring/reduction actions. No AI planning authority.
27. **Notifications use the canonical layer** (`flow=workforce_planning`) with R4 module suppression and dedupe. Copy is generic and must not leak confidential restructuring/cost information to unauthorized recipients.
28. **Module disable hides new planning work, preserves history, suppresses new notifications, and does not delete linked requisitions or reverse executed downstream changes.** Disabled / JA-unmet workspace is `unavailable` with `counts=None`.
29. **R4 truth states apply.** Distinguish no plans, no demand, zero gap, unavailable, forbidden, error, and loading. Never translate 403 or API failure into “No workforce gap” or “0 planned hires.”
30. **R5A honesty is now empty of unreleased Wave 4/6 surface keys.** Domain `FULL_PASS` is still not customer enablement by itself; this carve-out is the surface + Setup enablement for Workforce Planning only.
31. **Employee App and HR Mobile Workforce Planning are not enable gates** and are not shipped.
32. **R5 is complete as a surface program.** Do not begin R6 automatically.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Workforce Planning enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen.
8. R5E (`PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`) remains frozen.
9. R5F (`PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS`) remains frozen.
10. R5G (`PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS`) remains frozen.
11. R5H (`PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS`) remains frozen.
12. R5I (`PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS`) remains frozen. Compensation Planning surfaces and Setup enablement are unaffected.
13. Wave 6 C7 domain math, tables, projection, SOD, comparison, and anti-duplication stay frozen.
14. Env kill switch `WATHEFNI_WORKFORCE_PLANNING_C7` still wins over Setup enablement.
15. `PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `workforce_planning_http.py` + `workforce_planning_surfaces.py` registered **after** `employee_app_context` / Compensation Planning (not inside a swallowed early import).
* HR Web Workforce Planning workspace + Setup Workforce Planning card must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.workforce_planning` via `workforce_planning_surfaces.sync_catalog_entitlement`, and C7 enable must still require JA enabled for that company.
* Do not auto-enable Workforce Planning for existing tenants.
* Do not treat an Employee App or HR Mobile Workforce Planning workspace as an enable gate.
* Do not begin R6 automatically.

## Owner review

R5J is complete and frozen. This is the final R5 surface slice. Stop.

Do not begin R6 automatically.
