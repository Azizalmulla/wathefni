# Production Readiness R5H — Engagement Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS`
**Phase:** R5H — Engagement Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5h-engagement-20260815T160244Z/`
**Amends:** R5A customer-facing Engagement enablement only. Wave 6 C5 domain authority stays frozen.

This amends R5A / R5G for **Engagement surfaces and Setup enablement**. Performance, Talent, Job Architecture, Learning, Benefits, and Employee Relations enablement are unchanged. Remaining Wave 6 keys stay under the R5A honesty gate.

---

## What freezes with R5H

These are now binding contracts. Changing any of them requires a written amendment.

1. **Engagement is a product surface over C5 only.** HTTP, HR Web, Manager aggregates, and Employee App participation are adapters. No second survey / pulse / analytics / recognition schema. No client-owned canonical state.
2. **`customer_enableable("engagement")` is true** because `http_ready + hr_web_ready + employee_surface_ready + manager_surface_ready` are true. `mobile_ready` is false and **not required**. Setup remounts Engagement configuration (`Wave6EngagementPoliciesCard`).
3. **Engagement is a commercial catalog SKU.** Key `engagement` (alias `surveys`) is in `module_catalog`. `people_surface=false`. `app_surface_key=engagement`. Existing tenants are not auto-enabled.
4. **Anonymous response ≠ identifiable employee response.** Anonymous batches store `employee_key IS NULL` and have no invitation↔batch join. Ordinary application authority cannot recombine who→what.
5. **Below the anonymity threshold, suppress — never guess.** Default `min_responses = 5`, configurable upward only. Suppressed cells send `scores=None` and `n=None`. Suppressed is not zero.
6. **Complementary suppression is server-side.** A large segment is suppressed when the complement is below `min_n`. Do not show total + large segment in a way that reveals a small complement.
7. **Participation ≠ answer mapping.** Invitation status may be listed. Answers stay in anonymous batches. Admin resolve of anonymous answers fail-closed. Export, logs, Assistant, and manager drilldown must not emit a respondent→answer map.
8. **HR admin does not automatically bypass anonymity.** `engagement.manage` / `.results` / `.export` do not unlock identifiable anonymous answers.
9. **survey result ≠ action plan ≠ ER case.** An action plan is not a disciplinary, performance, or employment action. Engagement must never auto-create ER cases or employment mutations.
10. **eNPS is backend-only and explicit.** Only `enps_scale` questions with a 0–10 scale. No frontend formula. An arbitrary 1–5 rating is not eNPS.
11. **Launch freezes survey version + audience.** Later wording / version changes do not rewrite a launched campaign’s pin. History remains reconstructable.
12. **Manager receives threshold-safe aggregates for authorized org scope only.** Empty or small manager scope is suppressed and never falls back to company-wide. Managers have no administration workspace. Manager fixture permission is `engagement.manager` only — not `.manage` / `.export`.
13. **Employee App is participation only.** Open surveys, detail, submit, submitted/closed. Employees must not see other answers, identities, restricted aggregates, or hidden action plans. Identified mode copy is explicit and distinct from anonymous.
14. **HR Mobile Engagement is not required and is not shipped.** Do not add `/dashboard/mobile/engagement`.
15. **Recognition remains OUT.**
16. **No universal engagement / flight-risk / sentiment score.** No hidden AI sentiment authority. Wave 5 may receive only safe typed aggregate facts — no raw anonymous free text.
17. **Assistant remains read/explain only.** Mutations, identify-respondent, expose-suppressed, and fake scores are forbidden. Authorized aggregates still obey suppression.
18. **Export is separately permissioned** (`engagement.export`). Export obeys suppression and never includes a respondent→answer map.
19. **Notifications use the canonical layer** (`flow=engagement`) with R4 module suppression and dedupe. Launch copy is generic (`An Engagement survey is open.`).
20. **Module disable hides new surfaces, blocks new campaigns, preserves history, and suppresses new Engagement notifications.** Disabled workspace is `unavailable` with `counts=None`, not fake zeros.
21. **R4 truth states apply.** Distinguish empty surveys, forbidden, module unavailable, error, and loading. Never translate 403 into “No surveys”.
22. **R5A honesty remains** for Compensation Planning and Workforce Planning. Domain `FULL_PASS` is still not customer enablement for those keys.
23. **HR Mobile Engagement is not an enable gate** and is not shipped.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A remains frozen, except the Engagement enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen.
6. R5C (`PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`) remains frozen.
7. R5D (`PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS`) remains frozen.
8. R5E (`PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`) remains frozen.
9. R5F (`PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS`) remains frozen.
10. R5G (`PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS`) remains frozen. Employee Relations surfaces and Setup enablement are unaffected.
11. Wave 6 C5 domain math, tables, anonymity, suppression, and anti-duplication stay frozen.
12. Remaining Wave 6 domain authorities stay frozen and customer-unusable.
13. Env kill switch `WATHEFNI_ENGAGEMENT_C5` still wins over Setup enablement.
14. `PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `engagement_http.py` + `engagement_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Engagement workspace + Setup Engagement card + Employee App participation routes must ship with that backend.
* Catalog save / Setup enable must sync `company_modules.engagement` via `engagement_surfaces.sync_catalog_entitlement`.
* Do not remount remaining Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not auto-enable Engagement for existing tenants.
* Do not treat an HR Mobile Engagement workspace as an enable gate.
* Do not begin R5I Compensation Planning automatically.

## Owner review

R5H is complete and frozen. Stop.

Do not begin R5I Compensation Planning automatically.
