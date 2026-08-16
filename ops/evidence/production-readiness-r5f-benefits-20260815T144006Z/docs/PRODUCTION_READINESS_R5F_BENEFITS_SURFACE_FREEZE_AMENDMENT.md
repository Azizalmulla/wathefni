# Production Readiness R5F — Benefits Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS`
**Phase:** R5F — Benefits Administration Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5f-benefits-20260815T144006Z/`
**Amends:** R5A customer-facing Benefits enablement only. Wave 6 C3 domain authority stays frozen.

This amends R5A / R5E for **Benefits surfaces and Setup enablement**. Performance, Talent, Job Architecture, and Learning enablement are unchanged. Remaining Wave 6 keys stay under the R5A honesty gate.

---

## What freezes with R5F

These are now binding contracts. Changing any of them requires a written amendment.

1. **Benefits is a product surface over C3 only.** HTTP, HR Web, and Employee App are adapters. No second plan / eligibility / enrollment / coverage / contribution schema. No client-owned canonical state.
2. **`customer_enableable("benefits")` is true** because `http_ready + hr_web_ready + employee_surface_ready` are true. `manager_surface_ready` and `mobile_ready` are false and **not required**. Setup remounts Benefits configuration (`Wave6BenefitsPoliciesCard`).
3. **Benefits is a commercial catalog SKU.** Key `benefits` (alias `benefits_administration`) is in `module_catalog`. `people_surface=false`. Existing tenants are not auto-enabled.
4. **Eligible ≠ enrolled ≠ coverage active ≠ provider confirmed ≠ payroll deducted.** Eligibility never creates coverage. Election is not coverage. Waiver is not ineligibility. Internal coverage is not provider confirmation. Contribution is not a deduction. Handoff is not payroll execution.
5. **A plan is a stable governed object.** Changes that affect historical meaning create a new version / effective period. Historical employees stay tied to the plan version they actually elected.
6. **Eligibility is server-authoritative** and evidence-based on canonical employment / dependent truth. Client-provided company or employee identity is never trusted. Client attributes cannot override server employment truth.
7. **Enrollment lifecycle stays the frozen C3 machine:** eligible → election/waiver → submitted → governed processing if required → coverage effective. Employee elect adapters never call `confirm_enrollment`.
8. **Waiver is explicit employee/governed truth** (plan, employee, effective period, reason where required, provenance, history). Waiver must not be interpreted as ineligibility.
9. **Dependents reuse Wave 3 canonical authority only.** Benefits may maintain coverage relationships to those dependents. No Benefits-specific dependent profile. Dependent exists ≠ eligible ≠ enrolled ≠ covered.
10. **Coverage is explicit** (plan/version, covered party, effective date, end date where applicable, status, provenance). Coverage is not inferred from an election alone. Historical periods remain reconstructable.
11. **Provider / member references show actual status.** Do not fabricate provider enrollment. Do not label an internal election “provider confirmed”. External insurer integrations are not required.
12. **Contributions surface canonical configured/estimated truth only.** Employee vs employer vs estimated/configured vs payroll handoff vs actual payroll deduction stay distinct. No frontend financial calculation authority. `paid_amount` stays unset by Benefits.
13. **Benefits works with Payroll OFF.** When Payroll is ON, Benefits may create the existing explicit handoff contract (`applied_to_payroll=false`). No Benefits action may silently mutate finalized payroll. Payroll remains sole execution authority.
14. **Kuwait-first scope stays administration depth only.** No invented statutory entitlement formulas, insurer adjudication, claims processing, or medical-policy legal conclusions unless already governed by explicit configured policy. Claims remain OUT.
15. **No general manager Benefits workspace.** Managers must not automatically see elections, dependents, contributions, or private coverage merely because they manage the employee. Any later manager visibility must be explicitly permissioned and minimal.
16. **Privacy is fail-closed.** Dependent information, member/provider identifiers, coverage details, and contribution details are sensitive. Employee sees self only. HR visibility is permission-controlled. No sensitive benefit data in logs.
17. **Module disable hides new surfaces, blocks new enrollment/actions, preserves historical coverage/elections, and suppresses new Benefits notifications.** Disabled workspace is `unavailable` with `counts=None`, not fake zeros.
18. **Notifications use the canonical layer** (`flow=benefits`) with R4 module suppression and dedupe. No second Benefits inbox.
19. **Permissions stay separated.** `benefits.read` / `.manage` / `.eligibility` / `.enroll` / `.sensitive` / employee self / Setup admin. HR without Benefits permission fails closed. Employees cannot enumerate another employee's Benefits.
20. **R4 truth states apply.** Failed load must not look like “No benefits”, “Not eligible”, or “No coverage” unless that is successful backend truth.
21. **R5A honesty remains** for Employee Relations, Engagement, Comp Planning, and Workforce Planning. Domain `FULL_PASS` is still not customer enablement for those keys.
22. **HR Mobile Benefits admin is not an enable gate** and is not shipped.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Benefits enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen.
8. R5E (`PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`) remains frozen. Learning surfaces and Setup enablement are unaffected.
9. Wave 6 C3 domain math, tables, and anti-duplication stay frozen.
10. Remaining Wave 6 domain authorities stay frozen and customer-unusable.
11. Env kill switch `WATHEFNI_BENEFITS_C3` still wins over Setup enablement.
12. `PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `benefits_http.py` + `benefits_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Benefits workspace + Setup Benefits card + Employee App Benefits routes must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.benefits` via `benefits_surfaces.sync_catalog_entitlement`.
* Do not remount remaining Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not auto-enable Benefits for existing tenants.
* Do not treat HR Mobile or a Manager workspace as a Benefits enable gate.
* Do not begin R5G Employee Relations automatically.

## Owner review

R5F is complete and frozen. Stop.

Do not begin R5G Employee Relations automatically.
