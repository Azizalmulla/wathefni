# PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS`
**Phase:** R5A — Wave 4/6 Capability Honesty Gate
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (P0-1)
**Qualify:** `ops/qualify-production-readiness-r5a-capability-honesty.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r5a-capability-honesty-20260812T183621Z/`

**Scope:** If a capability has no usable HTTP + product surface, a customer must not be able to enable it. No Performance / Talent / Wave 6 product surfaces were built. R2, R3, and R4 stay frozen. Wave 4/6 domain authorities stay frozen.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** |
| Local unit contracts (no DB) | **205 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_UNIT_PASS`) |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB preserve + refuse enable | **30 passed, 0 failed** (`R5A_CAPABILITY_HONESTY_DB_PASS`) |
| Live deployed staging service | **26 passed, 0 failed** (health 200; reserved namespaces 404 `capability_not_released`) |
| Waves 1–6 unit freezes + C1–C7 + authority contracts | **green** (all rc=0, 0 failed) |
| R2 security unit + staging DB | **84/0 unit, 69/0 DB** |
| R3 data-safety unit + staging DB | **61/0 unit, 18/0 DB** |
| R4 truth-in-UI unit + staging DB | **40/0 unit, 9/0 DB** |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R5A blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no rollout. Stop here for owner review. **Do not begin R5B** until owner approval.

---

## 2. What changed

### One readiness contract

`wathefni-orchestrator/capability_readiness.py` is the reusable answer to “Can this company use this module right now?”

| Flag | Meaning |
|---|---|
| `domain_authority_ready` | Frozen Wave 4/6 domain library exists |
| `http_ready` | Real HTTP adapter exists |
| `hr_web_ready` | HR Web product surface exists |
| `employee_surface_ready` | Employee App surface exists (when the charter requires it) |
| `manager_surface_ready` | Manager surface exists (when the charter requires it) |
| `mobile_ready` | HR Mobile surface exists (only when genuinely required) |
| `customer_enableable` | All charter-promised surfaces for that module are ready |

`customer_enableable` is **not** inferred from a domain `FULL_PASS` stamp. For all nine surface-less capabilities it is currently **false**.

Catalog SKUs (Waves 1–3, Wave 5 `analytics`, Employee App, etc.) stay customer-enableable. The nine unreleased keys are intentionally **absent** from `MODULE_CATALOG`.

### Customer-facing Setup

Setup Console **omits** enable cards for:

Performance, Talent, Job Architecture, Learning & Development, Benefits, Employee Relations, Engagement, Compensation Planning, Workforce Planning.

Card files are retained for later unhide. Waves 1–3 Setup cards remain mounted. Wave 5 Intelligence is unchanged.

HTTP Setup PATCH to `wave4_*` / `wave6_*` returns **409** `capability_not_customer_enableable` and does not mutate rows. Bulk module save of those keys returns the same 409.

GET still returns stored policy, including `stored_enabled`, with `usable: false` and `customer_facing_state: not_released`.

### Existing enabled rows

Python/domain enablement still writes overlays and `*_company_settings` for internal qualification. Staging proved a stored `enabled=true` Performance overlay and Job Architecture settings row survive the customer refuse path. Runtime remains env + allowlist gated. Stored enabled never becomes customer-usable.

### Fail-closed future HTTP

Reserved namespaces return **404** `capability_not_released` and do not import domain libraries:

`/dashboard/performance`, `/dashboard/posthire/talent`, `/dashboard/talent`, `/dashboard/job-architecture`, `/dashboard/learning`, `/dashboard/benefits`, `/dashboard/employee-relations`, `/dashboard/engagement`, `/dashboard/compensation-planning`, `/dashboard/workforce-planning`, plus matching `/app/...` paths.

`/dashboard/posthire/intelligence` is not stolen.

---

## 3. Qualification proved

- Normal customer cannot enable Performance, Talent, or any Wave 6 module
- Backend/domain state is preserved
- Internal gated qualification remains possible (env allowlist + domain enable)
- No empty Wave 4/6 Setup enable control
- Waves 1–3 modules still enable normally
- Wave 5 Intelligence remains mounted and catalog-enableable as `analytics`
- R2–R4 regressions green
- Waves 1–6 authority regressions green

---

## 4. R5B → R5J surface delivery order

Do **not** start these until owner approval. Each slice unhides Setup only when `customer_enableable` becomes true for that key.

| Slice | Capability | HTTP adapter | HR Web | Manager surface | Employee App | HR Mobile | Setup unhide condition |
|---|---|---|---|---|---|---|---|
| **R5B** | Performance | `/dashboard/performance` + `/app/performance` | Goals, cycles, reviews, calibration, competencies | Team goals, review queue, check-ins | Own goals, self-review, check-ins, development | **Required** — thin manager queues only; not heavyweight calibration admin | `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready + mobile_ready` |
| **R5C** | Talent | `/dashboard/posthire/talent` + `/app/talent` (never recruiting `talent_pool`) | Profiles, Talent Review, HiPo, succession, optional 9-box | Nominate successors; authorized team signals | Limited self-profile | Not an enable gate (thin read only; not large 9-box admin) | `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready` |
| **R5D** | Job Architecture | `/dashboard/job-architecture` | Setup + catalog authoring (primary) | Thin read of assigned grade/role — not required to enable | Not required | Not required (no heavyweight authoring) | `http_ready + hr_web_ready`. Platform capability, not a separate SKU, but must not show a dead enable switch |
| **R5E** | Learning & Development | `/dashboard/learning` + `/app/learning` | Catalog / admin | Scoped assign | Employee learning self-service **required** | Not an enable gate (thin) | `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready` |
| **R5F** | Benefits | `/dashboard/benefits` + `/app/benefits` | Plans / admin | Not required (private detail fail-closed) | Enrollment **required** | Not required | `http_ready + hr_web_ready + employee_surface_ready` |
| **R5G** | Employee Relations | `/dashboard/employee-relations` | Sealed ER workspace **required** | **Not** an ER surface (manager ≠ ER) | Not required for enable | **Required** — thin alerts to authorized ER actors only | `http_ready + hr_web_ready + mobile_ready` |
| **R5H** | Engagement | `/dashboard/engagement` + `/app/engagement` | Survey admin | Threshold-gated aggregates **required** | Participation **required** | Not an enable gate | `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready` |
| **R5I** | Compensation Planning | `/dashboard/compensation-planning` | Planning worksheets **required** | Optional recommend — not an enable gate | Not (no company admin) | Not (not heavyweight) | `http_ready + hr_web_ready` **and** Job Architecture `customer_enableable` (HARD C1) |
| **R5J** | Workforce Planning | `/dashboard/workforce-planning` | Planning **required** | Not required | Not | Not an enable gate (thin) | `http_ready + hr_web_ready` **and** Job Architecture `customer_enableable` (HARD C1) |

R5D before R5I/R5J is required by the Wave 6 JA hard contracts. Performance before Talent matches the owner-listed order and keeps post-hire talent distinct from recruiting `talent_pool`.

---

## 5. What this stamp does not authorise

- Building any Wave 4/6 product surface
- Broad production rollout
- Treating domain `FULL_PASS` as customer enablement
- Remounting Setup cards without flipping `customer_enableable` for that module
- Changing R2 / R3 / R4 frozen contracts
