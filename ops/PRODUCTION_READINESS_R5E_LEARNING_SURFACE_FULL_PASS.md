# PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS`
**Phase:** R5E — Learning & Development Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r5e-learning.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r5e-learning-20260815T141719Z/`
**Prior freeze:** `PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS` (accepted; stays frozen)

**Scope:** Turn frozen Wave 6 C2 Learning & Development into a usable product: HTTP adapter → HR Web workspace → scoped Manager → Employee App. Commercial SKU `learning`. Do not begin R5F Benefits.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** |
| Employee composition | **67 checks** — Learning hub / catalog / certificates / session routes |
| Local R5E unit contracts | **78 passed, 0 failed** (`R5E_LEARNING_SURFACE_UNIT_PASS`) |
| Local R5D unit regression | **70 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_UNIT_PASS`) |
| Local R5C unit regression | **62 passed, 0 failed** (`R5C_TALENT_SURFACE_UNIT_PASS`) |
| Local R5B unit regression | **56 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_UNIT_PASS`) |
| Local R5A unit regression | **156 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_UNIT_PASS`) |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB journeys A–F + HTTP security | **74 passed, 0 failed** (`R5E_LEARNING_SURFACE_DB_PASS`, tenant `R5EC348CC`) |
| R5D staging DB regression | **81 passed, 0 failed** (`R5D_JOB_ARCHITECTURE_SURFACE_DB_PASS`) |
| R5C staging DB regression | **63 passed, 0 failed** (`R5C_TALENT_SURFACE_DB_PASS`) |
| R5B staging DB regression | **62 passed, 0 failed** (`R5B_PERFORMANCE_SURFACE_DB_PASS`) |
| R5A staging DB regression | **30 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_DB_PASS`) |
| Live deployed staging service | **17 passed, 0 failed** (Learning namespaces no longer `capability_not_released`; Benefits / Comp Planning / WFP still fail-closed) |
| Waves 1–6 unit freezes + C1–C7 + C5/C6 + authority contracts | **green** (all rc=0) |
| R2 security unit + staging DB | **green** / **69/0** `R2_SECURITY_FULL_PASS` |
| R3 data-safety unit + staging DB | **green** / **18/0** `R3_DATA_SAFETY_FULL_PASS` |
| R4 truth-in-UI unit + staging DB | **green** / **9/0** `R4_TRUTH_IN_UI_DB_PASS` |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R5E blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no broad rollout. Stop here. **Do not begin R5F Benefits automatically.**

---

## 2. Capability readiness after R5E

`capability_readiness.py` Learning flags:

| Flag | Value |
|---|---|
| `domain_authority_ready` | ✅ |
| `http_ready` | ✅ |
| `hr_web_ready` | ✅ |
| `manager_surface_ready` | ✅ |
| `employee_surface_ready` | ✅ |
| `mobile_ready` | ❌ (not required) |
| `customer_enableable` | **true** |
| `customer_visible` | **true** |

Learning **is** a catalog SKU (`learning` in `MODULE_BY_KEY`, aliases `learning_development` / `l_and_d`). Empty domain allowlist now admits entitled companies via `learning_runtime_allowlist_admits`. Env kill switch `WATHEFNI_LEARNING_C2=off` still wins.

Performance, Talent, and Job Architecture remain `customer_enableable=true`. Remaining Wave 6 keys stay unreleased (`benefits`, `employee_relations`, `engagement`, `comp_planning`, `workforce_planning`).

Customer-facing Setup remounts `Wave6LearningPoliciesCard` (`#classic-wave6-learning`) after Job Architecture. Benefits / ER / Engagement / Comp Planning / Workforce Planning cards stay omitted.

Existing tenants are **not** auto-enabled. Setup / catalog entitlement must be turned on per company.

HR Mobile has **no** required Learning admin surface.

---

## 3. What shipped

### Canonical authority (unchanged)

Adapters only over frozen C2 (`learning_development_c2.py`):

- Catalog items / programs / offerings (sessions)
- Assignments, requests, approvals, enrollments
- Attendance metadata, evidence-backed completion, certifications
- Mandatory generation (idempotent `obligation_key`)
- Development fulfillment links that never silently close Wave 4 C3

Preserved: **assignment ≠ enrollment ≠ attendance ≠ completion ≠ certification**. Overdue is derived, not automatic failure. Course completion is not competency verification. No client-owned canonical state.

### HTTP

Namespaces: `/dashboard/learning/...`, `/dashboard/posthire/learning/...` (alias), `/app/learning/...`

Families: workspace, catalog, programs, assignments, requests / decide, sessions / enroll / attendance, completions, certificates, mandatory / generate, development-links, history, team.

Registered **after** `employee_app_context`. Company / actor from authenticated context only. No `X-Company-Code` write authority.

Permissions: `learning.read` / `.manage` / `.assign` / `.approve`. Managers get read + scoped assign + approve. Catalog authoring, completion verification, and certification administration require `learning.manage`.

### HR Web

First-class Learning workspace: Overview, Catalog, Assignments, Sessions, Certifications, Requests & Approvals, History. Setup deep-link `#classic-wave6-learning`. R4 `ResourceState`. EN+AR+RTL. Failed tab load ≠ “No learning assigned” / “No certificates” / “No requests”.

### Manager

Scoped team status, assign where policy permits, approve/reject requests. Empty canonical org scope returns empty lists (`company_wide=false`). No company-wide Learning visibility by default.

### Employee App

Entitlement-aware My Learning: required / assigned / upcoming / completed, catalog + request, session detail, certificates / expiry / renewal display. No HR administration. Employee cannot enumerate another employee's history.

---

## 4. Qualification proved

- Canonical C2 Learning authority only; no second schema
- Real HTTP + HR Web workspace + employee surface + scoped manager surface
- Catalog and programs work independently of an external LMS
- Assignment ≠ enrollment; enrollment ≠ completion; attendance ≠ completion
- Completion is evidence-backed; employee cannot self-complete mandatory learning unless self-attestation is explicit
- Certification ≠ completion; expiry is derived; renewal issues a new certificate; prior certificate remains historical
- Mandatory generation is idempotent; overdue ≠ automatic failure / non-compliance / termination
- Requests governed: request ≠ approval ≠ enrollment; rejection requires a reason
- Manager scope fail-closed
- Performance optional; Learning completion may attach fulfillment evidence and does **not** silently close the C3 development action
- Talent optional; no auto-HiPo, no learning Talent score
- Job Architecture optional; no Learning-specific job/grade hierarchy
- No duplicate skills / competency authority; course completion ≠ verified competency
- Learning usable with Performance OFF + Talent OFF + JA OFF
- Module-off: new work blocked, history / assignments / completions / certificates retained, notifications suppressed, workspace `unavailable` with `counts=None`
- Notifications use the canonical layer (`flow=learning`) and R4 module suppression
- Error ≠ empty; tenant isolation; employee isolation
- Historical reconstruction after later policy / catalog changes
- EN journey + AR / RTL copy
- R2–R5D regressions green; Waves 1–6 authorities green

---

## 5. What this stamp does not authorise

- R5F Benefits (or ER, Engagement, Comp Planning, Workforce Planning)
- Automatic enablement of Learning for existing tenants
- Broad production rollout beyond Aziz / Talal canary
- Treating this stamp as `PRODUCTION_READY`
- A second Learning model, LMS player, or skills / competency authority
- Silent close of Wave 4 development actions
- Auto-HiPo / potential / readiness / learning-based Talent score
- Treating overdue mandatory learning as failure, non-compliance, or a disciplinary outcome
- Employee self-declaration of mandatory completion without explicit self-attestation policy
- HR Mobile Learning administration
- External LMS / provider integration as a prerequisite

---

## 6. Evidence

`ops/evidence/production-readiness-r5e-learning-20260815T141719Z/`

| Inventory | File |
|---|---|
| API | `inventories/api-inventory.md` |
| Surfaces | `inventories/surface-inventory.md` |
| Authority mapping | `inventories/authority-mapping.md` |
| Permission matrix | `inventories/permission-matrix.md` |
| E2E journeys A–F | `inventories/e2e-journeys.md` |
| Web / App convergence | `inventories/web-app-mobile-convergence.md` |
| Module-off | `inventories/module-off-proof.md` |
| EN / AR | `inventories/en-ar-proof.md` |
| Historical | `inventories/historical-proof.md` |
| Security negatives | `inventories/security-negatives.md` |
| Regressions | `inventories/regressions.md` |
| Blockers | `inventories/blockers.md` |
| Safe debt | `inventories/safe-debt.md` |
