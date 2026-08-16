# PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS`
**Phase:** R5J — Workforce Planning Product Surface (final R5 surface slice)
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r5j-workforce-planning.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r5j-workforce-planning-20260815T165705Z/`
**Prior freeze:** `PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS` (accepted; stays frozen)

**Scope:** Turn frozen Wave 6 C7 Workforce Planning into a usable product: HTTP adapter → HR Web planning workspace. Commercial SKU `workforce_planning`. Job Architecture is a hard dependency and is already customer-enableable. Recruiting, Compensation Planning, and Talent remain optional. No Employee App surface. No HR Mobile surface. Manager demand/review/submit is optional/scoped. Do not begin R6.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** (named 4 files / 39 tests) |
| Employee composition | **71 checks** — no Workforce Planning employee tile / HR Mobile workspace |
| Local R5J unit contracts | **112 passed, 0 failed** (`R5J_WORKFORCE_PLANNING_SURFACE_UNIT_PASS`) |
| Local R5I unit regression | **108 passed, 0 failed** (`R5I_COMPENSATION_PLANNING_SURFACE_UNIT_PASS`) |
| Local R5H unit regression | **97 passed, 0 failed** (`R5H_ENGAGEMENT_SURFACE_UNIT_PASS`) |
| Local R5G unit regression | **89 passed, 0 failed** (`R5G_EMPLOYEE_RELATIONS_SURFACE_UNIT_PASS`) |
| Local R5F unit regression | **92 passed, 0 failed** (`R5F_BENEFITS_SURFACE_UNIT_PASS`) |
| Local R5E unit regression | **78 passed, 0 failed** (`R5E_LEARNING_SURFACE_UNIT_PASS`) |
| Local R5D unit regression | **70 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_UNIT_PASS`) |
| Local R5C unit regression | **62 passed, 0 failed** (`R5C_TALENT_SURFACE_UNIT_PASS`) |
| Local R5B unit regression | **56 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_UNIT_PASS`) |
| Local R5A unit regression | **146 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_UNIT_PASS`) |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB journeys A–I + HTTP security | **94 passed, 0 failed** (`R5J_WORKFORCE_PLANNING_SURFACE_DB_PASS`, tenant `R5J9C6EE6`) |
| R5I staging DB regression | **74 passed, 0 failed** (`R5I_COMPENSATION_PLANNING_SURFACE_DB_PASS`) |
| R5H staging DB regression | **87 passed, 0 failed** (`R5H_ENGAGEMENT_SURFACE_DB_PASS`) |
| R5G staging DB regression | **87 passed, 0 failed** (`R5G_EMPLOYEE_RELATIONS_SURFACE_DB_PASS`) |
| R5F staging DB regression | **75 passed, 0 failed** (`R5F_BENEFITS_SURFACE_DB_PASS`) |
| R5E staging DB regression | **74 passed, 0 failed** (`R5E_LEARNING_SURFACE_DB_PASS`) |
| R5D staging DB regression | **81 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_DB_PASS`) |
| R5C staging DB regression | **63 passed, 0 failed** (`R5C_TALENT_SURFACE_DB_PASS`) |
| R5B staging DB regression | **62 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_DB_PASS`) |
| R5A staging DB regression | **30 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_DB_PASS`) |
| Live deployed staging service | **15 passed, 0 failed** (Workforce Planning enableable; namespaces no longer `capability_not_released`; unreleased keys empty) |
| Waves 1–6 unit freezes + C1–C7 + C5/C6 + R5I + authority contracts | **green** (all rc=0) |
| R2 security unit + staging DB | **green** / **69/0** `R2_SECURITY_FULL_PASS` |
| R3 data-safety unit + staging DB | **green** / **18/0** `R3_DATA_SAFETY_FULL_PASS` |
| R4 truth-in-UI unit + staging DB | **green** / **9/0** `R4_TRUTH_IN_UI_DB_PASS` |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R5J blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no broad rollout. Stop here. **Do not begin R6 automatically.**

---

## 2. Capability readiness after R5J

`capability_readiness.py` Workforce Planning flags:

| Flag | Value |
|---|---|
| `domain_authority_ready` | ✅ |
| `http_ready` | ✅ |
| `hr_web_ready` | ✅ |
| `employee_surface_ready` | ❌ (not required) |
| `manager_surface_ready` | ✅ (optional scoped demand / review / submit) |
| `manager_surface_required` | ❌ |
| `mobile_ready` | ❌ (not required) |
| `depends_on` | `job_architecture` (hard) |
| `customer_enableable` | **true** (JA is also enableable) |
| `customer_visible` | **true** |

Workforce Planning **is** a catalog SKU (`workforce_planning` in `MODULE_BY_KEY`, aliases `workforce`, `wfp`). `people_surface=false`. `app_surface_key=None`. Audience `hr`. Empty domain allowlist now admits entitled companies via `workforce_planning_runtime_allowlist_admits` **only after** the JA hard runtime gate. Env kill switch `WATHEFNI_WORKFORCE_PLANNING_C7=off` still wins. Explicit `WATHEFNI_WORKFORCE_PLANNING_COMPANIES=COMPANY` still blocks OTHER.

Job Architecture remains `customer_enableable=true` and is the hard dependency. If JA is unavailable, Workforce Planning is unavailable — never guessed from raw employee titles. Historical plans remain reconstructable.

Performance, Talent, Learning, Benefits, Employee Relations, Engagement, and Compensation Planning remain `customer_enableable=true`. `UNRELEASED_CAPABILITY_KEYS` is now **empty**. This is the final R5 surface slice.

Customer-facing Setup remounts `Wave6WorkforcePlanningPoliciesCard` (`#classic-wave6-workforce-planning`) after Compensation Planning.

Existing tenants are **not** auto-enabled. Setup / catalog entitlement must be turned on per company, and JA must already be enabled for that company.

An Employee App or HR Mobile Workforce Planning workspace is **not** required and was not shipped.

---

## 3. What shipped

### Canonical authority (unchanged)

Adapters only over frozen C7 (`workforce_planning_c7.py`):

- planning cycles
- actual / frozen baseline snapshot
- workforce plans
- demand
- planned positions / headcount
- scenarios
- assumptions
- projected headcount
- planned workforce cost
- workforce gaps
- scenario comparison
- approvals
- explicit execution / handoff
- actual-vs-plan references
- historical versions

Preserved:

- **actual workforce ≠ baseline ≠ workforce plan ≠ scenario ≠ approved execution**
- **baseline ≠ live actual workforce**
- **planned position ≠ actual position**
- **approved workforce demand ≠ approved requisition ≠ posted job ≠ candidate ≠ hire**
- **planned cost ≠ payroll result ≠ payment**
- **approval ≠ actual workforce change**

No second workforce planning model. No frontend forecasting authority. No hidden AI forecast. No universal `workforce_health_score`. No hidden FX. KWD explicit; unsupported currency fails `currency_unsupported_no_fx`.

### HTTP

Namespaces: `/dashboard/workforce-planning/...`, `/dashboard/posthire/workforce-planning/...` (alias)

No `/app/workforce-planning`. No `/dashboard/mobile/workforce-planning`.

Families: workspace, cycles/plans, baseline, demand, planned positions/headcount, scenarios, assumptions, headcount projections, planned workforce cost, gap views, scenario comparison, approvals, execution/handoff, actual-vs-plan, history/version, export, Assistant (read/explain), manager (scoped).

Registered **after** Compensation Planning / `employee_app_context`. Company / actor from authenticated context only. No `X-Company-Code` write authority. Entitlement is `require_entitlement(..., "workforce_planning")` plus `workforce_planning.*`.

Permissions: `workforce_planning.read` / `.manage` / `.plan` / `.cost` / `.approve` / `.execute` / `.export` / `.manager`. Owner / hr_admin / hr_manager full set includes all. Manager / team_manager fixtures have **`workforce_planning.manager` only**. Viewer has none.

### HR Web

First-class Workforce Planning workspace: Overview, Plan, Scenarios, Demand, Cost, Approvals, Execution, History. Setup deep-link `#classic-wave6-workforce-planning`. R4 `ResourceState`. EN+AR+RTL. KWD formatting. Failed load / 403 must not render “No workforce gap” or “0 planned hires”. Manager role loads `/dashboard/workforce-planning/manager` only and is refused the administration workspace.

### Manager (optional)

Scoped demand proposal / review / submit where configured. Empty manager scope = zero rows, never company-wide. No company-wide plans, restructuring data, salary/cost-sensitive information, or final execution authority.

---

## 4. Qualification proved

- Frozen C7 authority only; no second workforce planning model; no frontend forecast
- Real HTTP + HR Web workspace; no Employee App / HR Mobile surface
- JA hard dependency: enable blocked until JA is on; JA off → workspace `unavailable` / `counts=None`, not a guessed title catalog
- No planning-only duplicate Job Profile / Grade / Level catalog
- Baseline is an explicit frozen as-of snapshot of canonical actual; later actual change does not rewrite it
- Actual ≠ baseline ≠ plan ≠ scenario ≠ approved execution
- Planned headcount never enters Wave 5 actual headcount / hires / exits / payroll
- Planned position ≠ actual position / vacancy / employment
- Demand is explicit: growth, replacement, vacancy, reduction, role-mix; replacement requires a reason
- Assumptions are versioned; Wave 5 turnover is context, not prediction authority
- Projection is backend-authoritative, deterministic, and reproducible (`2 + 3 − 1 = 4`)
- Planned / estimated workforce cost is labeled as such; not finalized payroll cost
- KWD explicit; USD create is 422 `currency_unsupported_no_fx`
- Compensation Planning optional: WFP works Comp OFF; when ON it may consume bands as cost context only and must not start a cycle or change salary
- Talent optional: WFP works Talent OFF; no duplicate skills truth; no universal workforce/talent score
- Recruiting OFF: approved demand remains approved/unexecuted and exportable
- Recruiting ON: explicit authorized handoff → exactly one linked DRAFT requisition; no auto-approve / auto-post / auto-candidate / auto-hire; retry does not duplicate
- Approval lifecycle preserved; approved scenarios are immutable / versioned
- Actual-vs-plan queries canonical actual; does not copy employees into a WFP SoT
- Wave 5 planning facts stay on the planning plane; no second analytics engine
- Sensitive permissions: ordinary HR without `workforce_planning.*` is 403, not empty-plans
- Manager admin workspace 403; empty manager scope is zero rows / not company-wide
- Export requires `workforce_planning.export`
- Tenant isolation blocks foreign plan IDs
- Unauthenticated workspace is not public
- Disable hides workspace (`counts=None`), preserves history, suppresses new notifications, does not delete linked requisitions
- Notifications use the canonical layer (`flow=workforce_planning`) with generic copy (no confidential restructuring/cost)
- Assistant mutations (create scenario / change assumptions / approve / handoff / forecast) forbidden
- EN journey + AR / RTL copy; KWD formatting
- R2–R5I regressions green; Waves 1–6 authorities green; C7 unit green

---

## 5. What this stamp does not authorise

- R6 or later Production Readiness phases
- Automatic enablement of Workforce Planning for existing tenants
- Broad production rollout beyond Aziz / Talal canary
- Treating this stamp as `PRODUCTION_READY`
- A second workforce planning / forecasting / headcount model
- An Employee App or HR Mobile Workforce Planning workspace
- Treating a plan, scenario, approval, or handoff as an actual workforce change
- Treating planned headcount as Wave 5 actual headcount
- Treating a planned position as an actual vacancy, employment, or payroll row
- Auto-posting, auto-creating candidates, or auto-hiring from approved demand
- Hidden FX / invented exchange rates
- Hidden AI forecast or a universal `workforce_health_score`
- Starting a Compensation Planning cycle or changing salary from WFP
- Company-wide manager plan / cost visibility from empty manager scope
- Collapsing `workforce_planning.*` into ordinary `hr_admin` without the specific permission
- Assistant mutation of plans, assumptions, approvals, or requisitions
- Reversing executed downstream Recruiting / employment / payroll changes on disable

---

## 6. Evidence

`ops/evidence/production-readiness-r5j-workforce-planning-20260815T165705Z/`

| Inventory | File |
|---|---|
| API | `inventories/api-inventory.md` |
| Surfaces | `inventories/surface-inventory.md` |
| Authority mapping | `inventories/authority-mapping.md` |
| Permission matrix | `inventories/permission-matrix.md` |
| E2E journeys A–I | `inventories/e2e-journeys.md` |
| Web / App / Mobile convergence | `inventories/web-app-mobile-convergence.md` |
| Module-off | `inventories/module-off-proof.md` |
| EN / AR | `inventories/en-ar-proof.md` |
| Historical | `inventories/historical-proof.md` |
| Security negatives | `inventories/security-negatives.md` |
| Regressions | `inventories/regressions.md` |
| Blockers | `inventories/blockers.md` |
| Safe debt | `inventories/safe-debt.md` |
