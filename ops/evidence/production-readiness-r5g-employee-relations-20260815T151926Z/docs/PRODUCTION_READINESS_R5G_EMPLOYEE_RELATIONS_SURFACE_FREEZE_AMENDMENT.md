# Production Readiness R5G — Employee Relations Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS`
**Phase:** R5G — Employee Relations Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5g-employee-relations-20260815T151926Z/`
**Amends:** R5A customer-facing Employee Relations enablement only. Wave 6 C4 domain authority stays frozen.

This amends R5A / R5F for **Employee Relations surfaces and Setup enablement**. Performance, Talent, Job Architecture, Learning, and Benefits enablement are unchanged. Remaining Wave 6 keys stay under the R5A honesty gate.

---

## What freezes with R5G

These are now binding contracts. Changing any of them requires a written amendment.

1. **Employee Relations is a product surface over C4 only.** HTTP, sealed HR Web, and thin HR Mobile are adapters. No second case / intake / investigation / evidence / finding / outcome schema. No client-owned canonical state.
2. **`customer_enableable("employee_relations")` is true** because `http_ready + hr_web_ready + mobile_ready` are true. `employee_surface_ready` and `manager_surface_ready` are false and **not required**. Setup remounts ER configuration (`Wave6EmployeeRelationsPoliciesCard`).
3. **Employee Relations is a commercial catalog SKU.** Key `employee_relations` (alias `er`) is in `module_catalog`. `people_surface=false`. No Employee App `app_surface_key`. Existing tenants are not auto-enabled.
4. **Submission ≠ allegation proven ≠ investigation ≠ finding/outcome ≠ employment mutation.** Intake creates a case/intake record, not a finding. Investigation does not imply a finding. A finding/outcome is not an employment mutation. ER must never silently terminate, suspend, discipline, transfer, or alter payroll/employment truth.
5. **Access is need-to-know.** Ordinary HR admin / HR operator / manager / payroll / Talent must not automatically gain ER case access. Access combines ER permission + case-level membership/assignment where required + specific sensitive-evidence authority. Direct URL/API access enforces the same rules.
6. **Empty assignment scope means zero cases**, never a company-wide fallback. Surface listing/detail/mutations are grant-scoped even for `er.manage` / C4 `er_admin`.
7. **Permissions stay separated.** `er.read` / `.manage` / `.investigate` / `.decide` / `.sensitive` / `.export`. Do not collapse everything into `hr_admin`. A user who can view a case does not automatically get sensitive evidence, investigator notes, outcome reasoning, or bulk export.
8. **Evidence is more sensitive than ordinary HR documents.** Retrieval is sealed. Raw storage/provider URLs never leak. A case viewer does not automatically see every evidence item. Access fails closed across API, file/blob retrieval, signed URLs, download, preview, export, logs, and Assistant.
9. **Notes stay confidential by class.** General chronology, investigator-only notes, sensitive/internal notes, and outcome reasoning are not interchangeable. Case-header visibility does not surface confidential notes.
10. **Findings and outcomes require governed authority.** Do not infer a finding from case status. Do not auto-create disciplinary or employment actions. No AI-generated finding or disciplinary decision.
11. **Wave 3 remains sole canonical employment lifecycle authority.** If an ER outcome requires an employment action, the path is ER outcome → explicit authorized handoff/change request → Wave 3 employment authority. The handoff is explicit, permissioned, idempotent, attributable, and historically linked to the ER case.
12. **Manager is not an ER role.** A line manager must not gain case access merely because the employee reports to them, they submitted information, or the case concerns their team. Participation through an explicitly scoped request/interview/action does not imply full case access.
13. **No Employee App ER case-management surface.** R5G does not invent employee transparency rules beyond frozen C4. Investigation notes, pre-disclosure findings, witnesses, sensitive evidence, and internal outcomes stay off the Employee App.
14. **HR Mobile stays thin and operational.** Authorized ER actors may see a privacy-safe Home/Inbox item, open a scoped summary, and perform a limited safe action. Heavy investigation/evidence authoring remains Web-first. Do not clone the full investigation workspace into mobile.
15. **Notifications use the canonical layer** (`flow=employee_relations`) with R4 module suppression and dedupe. Push/Inbox preview must not leak allegation, witness, or case narrative. Generic copy is required where necessary.
16. **Assistant remains read/explain only** and obeys the same confidentiality checks. It must never reveal a case to unauthorized users, summarize inaccessible evidence, expose witnesses or investigator notes, infer guilt/finding, create/update/close cases, or execute employment actions.
17. **Wave 5 may receive only explicitly safe typed ER facts.** Allegation / narrative / investigation-note / evidence free text stays out of HR Intelligence. No ER risk score, employee conduct score, or manager misconduct score.
18. **Export is separately permissioned** (`er.export`). Any export remains tenant-scoped, applies case/evidence permissions, avoids hidden fields, and preserves audit attribution. No unrestricted company-wide ER export.
19. **Module disable hides new surfaces, blocks new cases/actions, preserves confidential history, and suppresses new ER notifications.** Disabled workspace is `unavailable` with `counts=None`, not fake zeros. Disabled must never make historical cases visible through a generic HR fallback.
20. **Audit is immutable.** Case creation, access/assignment changes, evidence addition/access where appropriate, finding/outcome decisions, handoff creation, and governed closure/reopen record authenticated actor and timestamp. No silent destructive edits. Later org/manager/permission changes do not rewrite old case history; current permission still governs who may view that history.
21. **R4 truth states apply.** Distinguish no cases assigned, forbidden, module unavailable, error, and loading. Never translate 403 into “No employee relations cases”.
22. **R5A honesty remains** for Engagement, Comp Planning, and Workforce Planning. Domain `FULL_PASS` is still not customer enablement for those keys.
23. **Manager and Employee App ER workspaces are not enable gates** and are not shipped.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Employee Relations enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen.
8. R5E (`PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`) remains frozen.
9. R5F (`PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS`) remains frozen. Benefits surfaces and Setup enablement are unaffected.
10. Wave 6 C4 domain math, tables, and anti-duplication stay frozen.
11. Remaining Wave 6 domain authorities stay frozen and customer-unusable.
12. Env kill switch `WATHEFNI_EMPLOYEE_RELATIONS_C4` still wins over Setup enablement.
13. `PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `employee_relations_http.py` + `employee_relations_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web ER workspace + Setup ER card + thin HR Mobile ER routes must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.employee_relations` via `employee_relations_surfaces.sync_catalog_entitlement`.
* Do not remount remaining Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not auto-enable Employee Relations for existing tenants.
* Do not treat a Manager workspace or Employee App case surface as an ER enable gate.
* Do not begin R5H Engagement automatically.

## Owner review

R5G is complete and frozen. Stop.

Do not begin R5H Engagement automatically.
