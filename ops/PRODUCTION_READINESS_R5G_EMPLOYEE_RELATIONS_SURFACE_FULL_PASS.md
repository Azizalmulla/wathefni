# PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS`
**Phase:** R5G — Employee Relations Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r5g-employee-relations.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r5g-employee-relations-20260815T151926Z/`
**Prior freeze:** `PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS` (accepted; stays frozen)

**Scope:** Turn frozen Wave 6 C4 Employee Relations into a usable product: HTTP adapter → sealed HR Web workspace → thin HR Mobile alerts/actions for authorized ER actors. Commercial SKU `employee_relations`. Do not begin R5H Engagement.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** (named 4 files / 39 tests) |
| Employee composition | **69 checks** — no Employee App ER case workspace |
| Local R5G unit contracts | **89 passed, 0 failed** (`R5G_EMPLOYEE_RELATIONS_SURFACE_UNIT_PASS`) |
| Local R5F unit regression | **92 passed, 0 failed** (`R5F_BENEFITS_SURFACE_UNIT_PASS`) |
| Local R5E unit regression | **78 passed, 0 failed** (`R5E_LEARNING_SURFACE_UNIT_PASS`) |
| Local R5D unit regression | **70 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_UNIT_PASS`) |
| Local R5C unit regression | **62 passed, 0 failed** (`R5C_TALENT_SURFACE_UNIT_PASS`) |
| Local R5B unit regression | **56 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_UNIT_PASS`) |
| Local R5A unit regression | **151 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_UNIT_PASS`) |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB journeys A–G + HTTP security | **87 passed, 0 failed** (`R5G_EMPLOYEE_RELATIONS_SURFACE_DB_PASS`, tenant `R5G7A4629`) |
| R5F staging DB regression | **75 passed, 0 failed** (`R5F_BENEFITS_SURFACE_DB_PASS`) |
| R5E staging DB regression | **74 passed, 0 failed** (`R5E_LEARNING_SURFACE_DB_PASS`) |
| R5D staging DB regression | **81 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_DB_PASS`) |
| R5C staging DB regression | **63 passed, 0 failed** (`R5C_TALENT_SURFACE_DB_PASS`) |
| R5B staging DB regression | **62 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_DB_PASS`) |
| R5A staging DB regression | **30 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_DB_PASS`) |
| Live deployed staging service | **19 passed, 0 failed** (ER namespaces no longer `capability_not_released`; Engagement / Comp Planning / WFP still fail-closed) |
| Waves 1–6 unit freezes + C1–C7 + C5/C6 + authority contracts | **green** (all rc=0) |
| R2 security unit + staging DB | **green** / **69/0** `R2_SECURITY_FULL_PASS` |
| R3 data-safety unit + staging DB | **green** / **18/0** `R3_DATA_SAFETY_FULL_PASS` |
| R4 truth-in-UI unit + staging DB | **green** / **9/0** `R4_TRUTH_IN_UI_DB_PASS` |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R5G blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no broad rollout. Stop here. **Do not begin R5H Engagement automatically.**

---

## 2. Capability readiness after R5G

`capability_readiness.py` Employee Relations flags:

| Flag | Value |
|---|---|
| `domain_authority_ready` | ✅ |
| `http_ready` | ✅ |
| `hr_web_ready` | ✅ |
| `employee_surface_ready` | ❌ (not required) |
| `manager_surface_ready` | ❌ (not required) |
| `mobile_ready` | ✅ |
| `customer_enableable` | **true** |
| `customer_visible` | **true** |

Employee Relations **is** a catalog SKU (`employee_relations` in `MODULE_BY_KEY`, alias `er`). `people_surface=false` — ER is not on people 360. Empty domain allowlist now admits entitled companies via `employee_relations_runtime_allowlist_admits`. Env kill switch `WATHEFNI_EMPLOYEE_RELATIONS_C4=off` still wins.

Performance, Talent, Job Architecture, Learning, and Benefits remain `customer_enableable=true`. Remaining Wave 6 keys stay unreleased (`engagement`, `comp_planning`, `workforce_planning`).

Customer-facing Setup remounts `Wave6EmployeeRelationsPoliciesCard` (`#classic-wave6-employee-relations`) after Benefits. Engagement / Comp Planning / Workforce Planning cards stay omitted.

Existing tenants are **not** auto-enabled. Setup / catalog entitlement must be turned on per company.

A general Manager ER workspace and an Employee App ER case-management surface are **not** required and were not shipped. Managers are fail-closed unless given an explicit scoped contribution grant.

---

## 3. What shipped

### Canonical authority (unchanged)

Adapters only over frozen C4 (`employee_relations_c4.py`):

- case → intake → triage → investigation → evidence → finding/outcome → closure
- assignments / access participants
- notes (including investigator-only)
- evidence metadata / sealed retrieval
- findings and outcomes
- explicit Wave 3 employment-change handoff
- immutable history / audit

Preserved: **submission ≠ allegation proven ≠ investigation ≠ finding/outcome ≠ employment mutation**. ER never silently terminates, suspends, disciplines, transfers, or alters payroll/employment truth. No client-owned canonical state. No AI-generated finding or disciplinary decision. No ER risk / conduct / misconduct score.

Surface listing, detail, and mutations are **grant-scoped**. Empty assignment scope returns zero cases, never a company-wide fallback. C4 `er_admin` global bypass is not used by the product surface.

### HTTP

Namespaces: `/dashboard/employee-relations/...`, `/dashboard/posthire/employee-relations/...` (alias), `/dashboard/mobile/employee-relations/...`

No `/app/employee-relations` Employee App namespace.

Families: workspace summary, case list, case detail, intake, triage, assignments/grants, investigation notes, evidence metadata/access, findings, outcomes, closure, history/audit, export, Assistant (read/explain), explicit employment-change handoff, scoped contribution, thin mobile queue/summary/acknowledge.

Registered **after** Benefits / `employee_app_context`. Company / actor from authenticated context only. No `X-Company-Code` write authority. Entitlement is `require_entitlement(..., "employee_relations")` plus `er.*` — not `employee_relations.read`.

Permissions (owner / hr_admin / hr_manager only): `er.read` / `.manage` / `.investigate` / `.decide` / `.sensitive` / `.export`. Manager / team_manager / viewer fixtures have none.

### HR Web

First-class sealed Employee Relations workspace: Overview, Cases, Case Detail (intake / timeline / participants / investigation / evidence / findings / outcome / closure), My Work, History / Audit. Setup deep-link `#classic-wave6-employee-relations`. R4 `ResourceState`. EN+AR+RTL. Failed load / 403 must not render “No employee relations cases”.

### HR Mobile

Thin operational surface for authorized ER actors only: Home/Inbox/priority item, scoped case summary, assigned action, acknowledge, deep-link to Web for investigation/evidence authoring. Sensitive evidence stays Web-first. Notification / queue copy is privacy-safe (`Employee Relations action requires your attention`).

### Manager / Employee

No ordinary Manager ER workspace. Dashboard ER routes return 403 for managers. A line manager does not gain case access because the employee reports to them, they submitted information, or the case concerns their team. Explicit scoped contribution does not imply full case access.

No Employee App ER case-management surface.

---

## 4. Qualification proved

- Canonical frozen C4 authority only; no second ER model
- Real HTTP + sealed HR Web workspace + thin HR Mobile operational surface
- Ordinary HR admin without `er.*` cannot list/read a case
- Case-level need-to-know: investigator assigned to Case A cannot automatically access Case B
- Empty assignment ≠ company-wide fallback
- Intake ≠ finding; investigation ≠ outcome; outcome ≠ employment mutation
- Explicit Wave 3 employment-change handoff; `applied=false`; idempotent replay of the same case+outcome
- Employment remains unchanged until Wave 3 authority executes an authorized change
- Evidence permission is separate from case view; unauthorized participant cannot retrieve sensitive evidence
- Raw provider URL never returned; retrieval is sealed (`authorized_path` only)
- Investigator notes hidden from view-only participants
- Manager has zero ER case access by default; scoped contribution is not full case access
- Mobile: authorized actor sees privacy-safe queue/summary; unauthorized mobile principal fails closed
- Assistant is read/explain only; unauthorized denied; mutation forbidden; authorized metadata only
- Wave 5 forbids allegation/narrative free text; typed safe facts only; no ER scoring
- Export requires `er.export` separately from case view
- Module composition: ER only; ER + Performance OFF; Talent OFF; Payroll OFF; Benefits OFF; Engagement OFF; ER + Wave 3 employment authority
- Module-off: new intake/actions blocked, nav/workspace `unavailable` with `counts=None`, historical cases retained, notifications suppressed, no generic-HR leakage
- Notifications use the canonical layer (`flow=employee_relations`) with privacy-safe copy and R4 module suppression
- Error ≠ empty (403 is not “No employee relations cases”)
- Historical reconstruction after later assignment/org/permission changes
- Tenant isolation + direct-object IDOR blocked
- EN journey + AR / RTL copy
- R2–R5F regressions green; Waves 1–6 authorities green

---

## 5. What this stamp does not authorise

- R5H Engagement (or Compensation Planning, Workforce Planning)
- Automatic enablement of Employee Relations for existing tenants
- Broad production rollout beyond Aziz / Talal canary
- Treating this stamp as `PRODUCTION_READY`
- A second ER model, ordinary Manager ER workspace, or Employee App ER case-management surface
- Treating intake as a proven allegation, investigation as a finding, or an ER outcome as an employment mutation
- Silent termination / suspension / discipline / transfer / payroll change
- Company-wide case listing from empty assignment scope
- Collapsing `er.*` into `hr_admin`
- Assistant mutation, evidence summarization beyond the caller’s grants, or Wave 5 free-text ingestion
- ER risk / conduct / misconduct scores
- Unrestricted company-wide ER export
- Cloning the full investigation/evidence workspace into HR Mobile

---

## 6. Evidence

`ops/evidence/production-readiness-r5g-employee-relations-20260815T151926Z/`

| Inventory | File |
|---|---|
| API | `inventories/api-inventory.md` |
| Surfaces | `inventories/surface-inventory.md` |
| Authority mapping | `inventories/authority-mapping.md` |
| Permission matrix | `inventories/permission-matrix.md` |
| E2E journeys A–G | `inventories/e2e-journeys.md` |
| Web / App / Mobile convergence | `inventories/web-app-mobile-convergence.md` |
| Module-off | `inventories/module-off-proof.md` |
| EN / AR | `inventories/en-ar-proof.md` |
| Historical | `inventories/historical-proof.md` |
| Security negatives | `inventories/security-negatives.md` |
| Regressions | `inventories/regressions.md` |
| Blockers | `inventories/blockers.md` |
| Safe debt | `inventories/safe-debt.md` |
