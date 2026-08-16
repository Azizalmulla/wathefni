# PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS`
**Phase:** R6 — Setup Self-Service Completeness
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r6-setup-self-service.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r6-setup-self-service-20260815T173558Z/`
**Prior freeze:** `PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS` (accepted; R5A–R5J stay frozen)

**Scope:** Make Wathefni configurable by a company administrator without a developer editing environment variables, database rows, or legacy hidden configuration. Customer-facing policy → Setup. Environment → secrets, infrastructure, kill switches, and deployment allowlists only. Setup must never say a capability is enabled when runtime cannot use it. Do not begin R7.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** (named 5 files / 46 tests) |
| Employee composition | **71 checks** |
| Local R6 unit contracts | **63 passed, 0 failed** (`R6_SETUP_SELF_SERVICE_UNIT_PASS`) |
| Local R5J–R5A unit regressions | **112 / 108 / 97 / 89 / 92 / 78 / 70 / 62 / 56 / 146** — all 0 failed |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB journeys A–G + HTTP security | **42 passed, 0 failed** (`R6_SETUP_SELF_SERVICE_DB_PASS`, tenants `R6AF1BAF5` / `R6BF1BAF5`) |
| R5J–R5A staging DB regressions | **94 / 74 / 87 / 87 / 75 / 74 / 81 / 63 / 62 / 30** — all 0 failed |
| Live deployed staging service | **7 passed, 0 failed** (WFP/Comp/JA still enableable; unreleased empty; company and operator Setup not public) |
| Waves 1–6 + Intelligence C1–C6 + R2–R5J + authority contracts | **green** (all rc=0) |
| R2 security unit + staging DB | **green** / **69/0** `R2_SECURITY_FULL_PASS` |
| R3 data-safety unit + staging DB | **green** / **18/0** `R3_DATA_SAFETY_FULL_PASS` |
| R4 truth-in-UI unit + staging DB | **green** / **9/0** `R4_TRUTH_IN_UI_DB_PASS` |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R6 blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no broad rollout. Stop here. **Do not begin R7 Mobile Keyboard / Native Safety automatically.**

---

## 2. R1 items closed in R6

| ID | Close |
|---|---|
| **P1-1** | Wave 5 HR Intelligence now has Setup ownership (`Wave5HrIntelligencePoliciesCard`, `setup_console_wave5_policies.py`). Enablement, `min_cohort_n` (upward only), fiscal month, nationality/other demographics, manager analytics, export permission, and optional KPI publish are company-admin configurable over frozen C1 + C6. No second evaluator. |
| **P1-2** | Dual-gating UX is honest. Setup consumes one effective state. Stored ON + kill switch / allowlist / JA unmet is never customer-facing **Enabled**. Remaining Wave 6 cards no longer say “Enabled for this company (env gate still required)”. Empty Intelligence allowlist now admits when `analytics` is catalog-enableable (same invert as R5 Wave 4/6). Explicit `COMPANIES=X` still blocks OTHER. Kill switches still win. |
| **P1-3** | Catalog/composition already listed shipped R5 modules. R6 does not force Job Architecture into a billable SKU. JA remains a platform foundation. Analytics remains the commercial Intelligence SKU. `UNRELEASED_CAPABILITY_KEYS` stays empty. |
| **P1-18** | Leave / Attendance / Onboarding have one canonical customer-policy authority each. Extra cards may display the same store; they must not write a conflicting store. |

R1 P1-5 (HR Mobile Tasks actions) remains **R7**. R6 reviewed the env-only customer-behavior class, not the mobile Tasks wiring.

---

## 3. One effective capability state

Canonical product:

`product released × deployment available × company entitled/configured × principal permitted`

| Effective state | Customer-facing state (R5A vocabulary) | Meaning |
|---|---|---|
| `enabled_usable` | `enabled` | Released, deployable, entitled, permitted, and actually usable |
| `available_disabled` | `disabled` | Available in this deployment but company has not turned it on |
| `unavailable_deployment` | `unavailable` | Kill switch / staged allowlist / infrastructure gate |
| `dependency_unmet` | `dependency_unmet` | Compensation Planning or Workforce Planning without company JA |
| `not_entitled` | `disabled` | Company not entitled |
| `not_permitted` | `not_permitted` | Ordinary HR / missing `settings.manage` |
| `not_released` | `not_released` | Capability not customer-enableable |

`capability_readiness` remains authoritative for `customer_enableable`, `domain_authority_ready`, `http_ready`, and required-surface readiness. Setup does not invent a second availability system.

Public deployment reasons never include `WATHEFNI_*` names or secrets.

---

## 4. What shipped

### Effective state + honesty

- `setup_console_effective_state.py` — one resolver consumed by Setup GET/PATCH annotation
- `capability_readiness.annotate_policy_payload` — never reports `customer_facing_state=enabled` when runtime is blocked
- `SetupEffectiveStateBanner` on Wave 5, delivery, JA, Learning, Benefits, ER, Engagement, Comp, WFP

### Wave 5 Intelligence Setup

- `setup_console_wave5_policies.py` over frozen C1 Registry + C6 surfaces
- Commercial key `analytics`
- Syncs `company_modules.analytics`
- Disable preserves history (cohort / publications / definitions retained)
- Empty `WATHEFNI_HR_INTELLIGENCE_*_COMPANIES` admits after R6 when analytics is catalog-enableable
- `WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1` and `WATHEFNI_ANALYTICS_KILL` remain Class A kill switches

### Policy convergence

- Leave: `leave_policies` canonical; Wave 2 `enforced` writes through
- Attendance: ops overlay vs Wave 2 ingest vs payroll pay-mode — one store per concern
- Onboarding: `company_settings.onboarding.auto_start_on_hire` canonical; `onboarding_setup.auto_seed_on_hire` write-through
- `WATHEFNI_ONBOARDING_SEED` stays Class A infrastructure

### Notifications / delivery

- Customer `notification_preset` (`frontline` / `office` / `conservative`) via Setup
- Push remains a deployment gate; Setup shows availability, never provider secrets
- Existing channel cards remain the channel-policy UI

### Company-admin Setup HTTP

- `GET/PATCH /dashboard/setup/company/module-policies[/{module_key}]`
- Company from authenticated dashboard context only
- Requires `settings.manage`
- Ordinary HR → 403 `not_permitted`
- Client `X-Company-Code` cannot expand authority
- Comp/WFP enable without company JA → **409** `dependency_unmet`
- Failed save without audit reason is not 200
- Existing `record_admin_audit` records Setup policy writes

### Catalog / dependencies

- Job Architecture remains a platform foundation, not a separately billable SKU
- Compensation Planning and Workforce Planning require company-enabled JA
- Setup does not silently auto-enable an unrelated commercial module
- Existing tenants are not auto-enabled for Intelligence or any new policy

---

## 5. Required E2E A–G

| Journey | Result |
|---|---|
| **A** Fresh company — Setup writes Leave / Attendance / Onboarding / notification preset; no env edit | **PASS** |
| **B** Analytics kill switch → Setup `unavailable_deployment`, not Enabled; unblock resolves | **PASS** |
| **C** Comp without JA governed (API + HTTP 409); enable JA; Comp can then be enabled explicitly. WFP without JA governed | **PASS** |
| **D** Leave enforced, onboarding auto-start, attendance grace resolve to one canonical store | **PASS** |
| **E** Intelligence enable + cohort + fiscal via Setup; downward cohort forbidden; no env edit | **PASS** |
| **F** Disable Intelligence preserves cohort history; re-enable restores | **PASS** |
| **G** Ordinary HR 403; tenant B does not inherit A preset; header cannot write B; company admin cannot use operator Setup for B | **PASS** |

Harness SQL is used only to create isolated disposable tenants for cleanup. Customer policy after bootstrap is Setup API only.

---

## 6. Qualification minimum

| Proof | Status |
|---|---|
| R5A readiness contract preserved | **PASS** |
| One effective module state | **PASS** |
| No Setup Enabled / runtime unavailable lie | **PASS** |
| Wave 5 Setup ownership exists | **PASS** |
| Intelligence privacy policy configurable | **PASS** |
| Customer policy no longer env-only where inappropriate | **PASS** |
| Legitimate kill switches remain deployment-only | **PASS** |
| Job Architecture represented as platform foundation | **PASS** |
| Compensation → JA dependency honest | **PASS** |
| WFP → JA dependency honest | **PASS** |
| Leave / Attendance / Onboarding ownership converged | **PASS** |
| Duplicate stores removed or non-authoritative | **PASS** |
| Notification/channel customer settings correctly owned | **PASS** |
| Clean company configurable without SQL/env/Python for policy | **PASS** |
| Disable semantics preserve history | **PASS** |
| Re-enable restores correctly | **PASS** |
| Setup writes audited (existing audit architecture) | **PASS** |
| Setup permissions enforced server-side | **PASS** |
| Tenant isolation | **PASS** |
| Failed save ≠ successful-looking switch | **PASS** |
| EN + AR/RTL critical Setup journeys touched by R6 | **PASS** |
| R2–R5J regressions green | **PASS** |
| Waves 1–6 frozen authority regressions green | **PASS** |

---

## 7. Explicitly out of scope / not authorised

- R7 Mobile Keyboard / Native Safety, or any later Production Readiness phase
- New HCM modules or reopening R5 surfaces except a genuine correctness/security blocker
- Rewriting Leave calculations, Attendance truth, Onboarding lifecycle, Performance/Talent authority, Wave 5 evaluator math, or Wave 6 domain models
- Moving secrets / provider credentials / infrastructure kill switches into Setup
- Making Job Architecture a separately billable SKU
- Auto-enabling Intelligence or any module for existing tenants
- Broad production rollout beyond Aziz / Talal canary
- Treating this stamp as `PRODUCTION_READY`
- A second analytics / evaluator / audit system
- Full product-wide Arabic audit (remains R11)

---

## 8. Evidence

`ops/evidence/production-readiness-r6-setup-self-service-20260815T173558Z/`

| Inventory | File |
|---|---|
| Configuration ownership | `inventories/configuration-ownership-matrix.md` |
| Env classification | `inventories/env-classification-matrix.md` |
| Duplicate-policy resolution | `inventories/duplicate-policy-resolution.md` |
| Capability / effective state | `inventories/capability-effective-state-matrix.md` |
| Dependency proof | `inventories/dependency-proof.md` |
| Clean-company no-developer E2E | `inventories/clean-company-e2e.md` |
| Tenant / permission negatives | `inventories/tenant-permission-negatives.md` |
| EN / AR | `inventories/en-ar-proof.md` |
| Regressions | `inventories/regressions.md` |
| Blockers | `inventories/blockers.md` |
| Safe debt | `inventories/safe-debt.md` |
