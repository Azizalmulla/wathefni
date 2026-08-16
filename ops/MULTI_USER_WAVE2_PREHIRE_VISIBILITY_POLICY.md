# Multi-User Workspace Wave 2 — Pre-Hiring Visibility Policy

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T213243Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave2-visibility/20260728T213243Z/`  
**Scope:** Tenant pre-hiring visibility (`shared_company` / `assigned_only` / `hybrid`)  
**Preserved:** Wave 1 roles + Interviewer assignment scope  
**Out of scope:** Wathefni Calendar  

---

## Verdict

**PASS.** Existing tenants default to **`shared_company`** (no access loss). Leadership (`owner` / `hr_admin` / `hr_manager`) always retains company-wide oversight. Recruiters and Hiring Managers are scoped by ownership/assignment under `assigned_only` and hybrid detail. Interviewers remain Wave 1 assignment-only. Direct links, lists, exports, and overview queues enforce backend scope (not UI-only hiding). Health **200**. Rollback/restore proven.

---

## Policy model

Stored in `company_settings.settings.prehire_visibility_policy` (operator-managed key).  
Missing / unknown → **`shared_company`**.

| Policy | Summary counts | Detail lists / GET-by-id / search / exports / work-queue |
|---|---|---|
| `shared_company` | Company-wide | Company-wide (among entitled roles) |
| `assigned_only` | Scoped for Recruiter/HM | Scoped for Recruiter/HM |
| `hybrid` | Company-wide for Recruiter/HM | Assigned-only for Recruiter/HM |

**Always company-wide:** Company Admin (`owner`), HR Admin, HR Manager.  
**Always assignment-only (Wave 1):** Interviewer.  
**Viewer:** company-wide read (no ownership fields).  

No duplicated private copies — one shared Postgres cohort with SQL/Python filters.

---

## Assignment predicates (auditable)

| Role | Jobs | Candidates / applications |
|---|---|---|
| Recruiter | `recruiter_user_id` or `created_by_user_id` = actor | `owner_user_id` / governance `recruiter_owner_user_id` / jobs they own |
| Hiring Manager | `hiring_manager_user_id` = actor | Applications on those jobs |
| Interviewer | n/a (panel assignment) | n/a — interview assignment ACL only |

---

## Surfaces enforced

| Surface | Enforcement |
|---|---|
| Jobs list + summary | SQL visibility on positions |
| Job PATCH | `require_prehire_job_visibility` |
| Candidates list + search | SQL on applications |
| Application GET + mutations via `dashboard_application_or_404(..., context)` | 404 outside scope |
| Interviews list | ownership SQL + Wave 1 interviewer SQL |
| Interview record | application visibility after Wave 1 gate |
| Assessments list | attempt page scoped; hybrid keeps company-wide tab counts |
| Overview recent + work-queue | scoped detail rows |
| Reports export rows | filtered by app/job visibility |
| Bootstrap | exposes policy + effective scope meta |
| Settings UI | EN/AR policy selector (`settings.manage`) |

---

## APIs

- `GET /dashboard/prehire/visibility-policy`
- `PUT /dashboard/prehire/visibility-policy` (`settings.manage`, audited)
- Bootstrap fields: `prehire_visibility_policy`, `prehire_visibility_scope`, …

---

## Migration / safety

| Rule | Result |
|---|---|
| Default existing tenants | **shared_company** (WATHEFNI live default confirmed) |
| No accidental access loss | **PASS** — default unchanged |
| No privilege escalation | **PASS** — filters only narrow |
| Wave 1 roles intact | **PASS** (regression smoke) |
| Tenant isolation | Unchanged `company_code` gates |
| EN/AR + RTL | Settings labels + existing `dir` |

---

## Proofs

| Gate | Result |
|---|---|
| Recruiter in shared / assigned / hybrid | **PASS** (`live-proof.json`) |
| Hiring Manager assigned scope | **PASS** |
| Interviewer remains assignment-only | **PASS** |
| HR leadership oversight under assigned_only | **PASS** |
| Direct links / exports respect scope | **PASS** (backend gates) |
| Counts: hybrid summary company-wide, detail scoped | **PASS** (plan + assessments summary split) |
| No user gains access outside policy | **PASS** |
| Health | **200** |
| Rollback / restore | **PASS** — dashboard `BlTBX1nQ` ↔ `oEgG3EB7`; app helper absent ↔ `shared_company` |
| Unrelated mutations | **PASS** — visibility module + wires + Settings control only |

Dashboard asset: `dashboard-oEgG3EB7.js`.  
Smoke: `smoke-test-multi-user-wave2-visibility.py` (+ Wave 1 regression).

---

## Source map

| Concern | Location |
|---|---|
| Policy helpers | `wathefni-orchestrator/prehire_visibility.py` |
| Wiring | `app.py` (`company_prehire_visibility_policy`, list/detail/export gates) |
| Settings UI | `apps/wathefni-dashboard/src/App.tsx` Settings Account card |
| API | `apps/wathefni-dashboard/src/lib/api.ts` |

---

## Remaining (not Wave 2)

- Calendar
- Soft-scoping Viewer under assigned_only
- Pushing ownership SQL into every Overview SQL aggregate (hybrid keeps company-wide leadership summaries by design; assigned_only job summary is scoped)
- Auto-assigning `recruiter_user_id` / `owner_user_id` on create (operators must set ownership for assigned modes to be useful)

**Stop after Wave 2.**
