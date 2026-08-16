# Production Readiness R6 — Setup Self-Service Completeness Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS`
**Phase:** R6 — Setup Self-Service Completeness
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r6-setup-self-service-20260815T173558Z/`
**Amends:** Setup configuration ownership, effective-state honesty, Wave 5 empty-allowlist admit, and company-admin Setup HTTP. Frozen domain authorities stay frozen.

This amends R1 P1-1 / P1-2 / P1-3 / P1-18 and the remaining customer-facing env-only class. R5A–R5J surface enablement stays frozen. `UNRELEASED_CAPABILITY_KEYS` stays empty.

---

## What freezes with R6

These are now binding contracts. Changing any of them requires a written amendment.

1. **Customer-facing policy/configuration lives in Setup.** Environment may hold secrets, infrastructure, kill switches, and staged-rollout allowlists only.
2. **`capability_readiness` remains the only customer-enableable contract.** Do not weaken `domain_authority_ready`, `http_ready`, required surface readiness, or `customer_enableable`. Setup consumes that truth; it does not invent a second availability system.
3. **One effective capability state** is `product released × deployment available × company entitled/configured × principal permitted`. States: `enabled_usable`, `available_disabled`, `unavailable_deployment`, `dependency_unmet`, `not_entitled`, `not_permitted`, `not_released`.
4. **R5A `customer_facing_state` vocabulary is preserved** on the happy path (`enabled` when usable). R6 never reports `enabled` when runtime cannot use the capability. Richer state lives in `effective_state`.
5. **Setup must never say Enabled while an invisible env gate blocks execution.** Prefer **Enabled** or **Unavailable in this deployment** with a non-sensitive reason. Never expose env names or secrets.
6. **Wave 5 Setup owns customer Intelligence policy** over frozen C1 + C6. Commercial key `analytics`. Configurable: enablement, `min_cohort_n` (upward only), fiscal month, nationality/other demographics, manager analytics, export permission, optional KPI publish. No second evaluator, KPI catalog, or analytics authority.
7. **Wave 5 empty allowlist admits** after R6 when `analytics` is catalog-enableable (`hr_intelligence_runtime_allowlist_admits` / slice `slice_allowlist_admits`). Explicit `COMPANIES=X` still blocks OTHER. `WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1` and `WATHEFNI_ANALYTICS_KILL` still win. This is empty-allowlist semantics only — evaluator/KPI math is unchanged.
8. **Job Architecture remains a platform foundation**, not a separately billable SKU, even though it is customer-enableable.
9. **Compensation Planning and Workforce Planning require company-enabled Job Architecture.** Setup prevents invalid enablement (HTTP 409 `dependency_unmet`) and shows `dependency_unmet`. Never silently auto-enable an unrelated commercial module.
10. **Leave canonical customer policy is `leave_policies`.** Wave 2 `leave.enforced` writes through. Module overlays are optional display/ops only.
11. **Attendance has one store per concern:** ops overlay, Wave 2 ingest flags, payroll pay-mode. Cards may display the same store; they must not invent a third answer.
12. **Onboarding customer auto-start is `company_settings.onboarding.auto_start_on_hire`.** Phase 3B `auto_seed_on_hire` writes through. `WATHEFNI_ONBOARDING_SEED` remains infrastructure, not customer policy.
13. **Customer notification preset is Setup-owned** (`frontline` / `office` / `conservative`). Push enablement and provider credentials remain deployment / integration configuration.
14. **Company-admin Setup HTTP** is `/dashboard/setup/company/module-policies*`. Company comes from authenticated context only. Requires `settings.manage`. Ordinary HR is `not_permitted`. Client `company_code` cannot expand authority. Platform operator routes remain `/dashboard/superadmin/setup/companies/{code}/...`.
15. **Disable contract stays frozen:** stop new work, hide normal surfaces, block governed APIs, preserve history. Re-enable restores preserved history. Do not delete historical domain state.
16. **Setup writes use the existing audit architecture** (`record_admin_audit` / action_results). Actor, time, previous/new value for module enable/disable, sensitive policy, notification/channel policy, and Intelligence privacy thresholds. Do not invent a second audit system.
17. **R4 truth states apply to Setup:** saved, validation error, forbidden, runtime unavailable, conflict/dependency, server failure. Failed save must not leave a switch visually ON.
18. **R6-touched Setup journeys are bilingual EN/AR** (module enablement, policies, dependencies, Intelligence, notifications, errors, unavailable states). R11 still performs the full product-wide Arabic audit.
19. **Assistant remains out of Setup mutation authority.**
20. **Existing tenants are not auto-enabled** for Intelligence or any newly Setup-owned policy.
21. **R6 is configuration convergence only.** Do not rewrite Leave calculations, Attendance truth, Onboarding lifecycle, Performance/Talent authority, Wave 5 evaluator math, or Wave 6 domain models.
22. **Do not begin R7 automatically.**

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A–R5J remain frozen. No new HCM modules. Do not reopen R5 surfaces except a genuine correctness/security blocker.
5. Wave 1–6 domain authorities remain frozen.
6. Provider secrets (`EXPO_ACCESS_TOKEN`, WhatsApp, and other integration credentials) stay out of Setup.
7. `WATHEFNI_EMPLOYEE_APP` and employee-key allowlists stay Class A rollout/kill switches. Company `employee_app` entitlement remains Setup-owned.
8. `WATHEFNI_PUSH_NOTIFICATIONS` stays Class A.
9. Wave 5 C1 default flag remains off as a kill switch. Do not flip the default to on as a “fix.”
10. `PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship the R6 Setup modules (`setup_console_effective_state.py`, `setup_console_wave5_policies.py`, `setup_console_env_classification.py`, `setup_console_policy_convergence.py`, `setup_console_delivery_policies.py`) with the updated `app.py` / `capability_readiness.py` / Intelligence empty-allowlist invert.
* HR Web Setup Console must ship the Wave 5 Intelligence card, delivery card, and effective-state banners.
* Do not auto-enable Intelligence or any module for existing tenants.
* Deployment secrets/gates may be pre-provisioned as infrastructure.
* Do not begin R7 automatically.

## Owner review

R6 is complete and frozen. Stop.

Do not begin R7 Mobile Keyboard / Native Safety automatically.
