# Multi-User Workspace Wave 4 — Personal Work Queues & Notifications

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T220422Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave4-personal-work/20260728T220422Z/`  
**Scope:** My work / Company work queues + assignee-routed notifications  
**Preserved:** Waves 1–3 (roles, visibility policy, ownership)  
**Out of scope:** Wathefni Calendar  

---

## Verdict

**PASS.** Shared company truth remains one Postgres cohort; every user now has a backend-authoritative **My work** queue of only what they are responsible for. HR leadership can switch to **Company work**. Overview priorities personalize by authenticated user. Notifications route personal alerts to assignees and keep shared operational alerts company-level. Tasks expose owner, due state, next action, and source. Reassignment flips responsibility immediately on refresh. Health **200**. Rollback/restore proven. Waves 1–3 regression smoke passed.

---

## Views

| View | Who | Filtering |
|---|---|---|
| **My work** (`scope=mine`) | All entitled pre-hire users (default) | Backend assignment: app owner, job recruiter/HM, interview panel, task assignee, approval phone |
| **Company work** (`scope=company`) | Oversight only (`owner` / `hr_admin` / `hr_manager`) | Full company work queue; 403 for non-oversight |

No frontend-only hide: the API refuses `company` for Recruiter / Hiring Manager / Interviewer / Viewer.

---

## My work contents

| Item | Source of assignment |
|---|---|
| Jobs I own | `positions.recruiter_user_id` / `hiring_manager_user_id` with active candidates |
| Candidates / applications assigned to me | Filtered company work-queue rows + `owner_user_id` / job ownership |
| Interviews assigned to me | `candidate_interview_assignments` |
| Assessments needing my action | Owned/assigned apps in assessment cohorts |
| Feedback I need to submit | Assigned interviews with incomplete feedback |
| Approvals assigned to me | `pending_actions.admin_phone` = actor phone |
| Overdue tasks / reminders | `application_recruiter_tasks` assigned + past due |

Every item includes: `owner`, `due_state` (`open` / `due_soon` / `overdue`), `next_action`, `source`, `entity_type`, `entity_id`, `audience`.

Dedup key: `(action_type, entity_id)` — no duplicate personal/company rows in a single response.

---

## Company work & shared alerts

- Company work uses the same canonical overview queue, labeled `audience=company` / `source=company_ops`.
- Shared operational alerts (assessment/interview delivery failures, compliance) stay **company-level** and are excluded from My work notification action items.
- Personal notification kinds: approvals for my phone, overdue tasks, interview feedback needed, screening completed on my owned apps.

---

## APIs

| Endpoint | Change |
|---|---|
| `GET /dashboard/prehire/overview/work-queue?scope=mine\|company` | Scoped queue + counts + enrichment |
| `GET /dashboard/prehire/overview/next-action?scope=mine\|company` | Personalized next action from My work by default |
| `GET /dashboard/prehire/notifications?scope=mine\|company` | Assignee-scoped deliveries + labeled action items |
| `notify_hr_admins(..., assignee_user_ids=, audience=)` | Routes to assignees when provided; else company broadcast |

---

## Frontend

- Overview section titles: **My work** / **Company work** (EN/AR + RTL via existing `dir`).
- Oversight toggle only when `can_view_company_work` / Wave 2 oversight.
- Priority cards use personalized `workQueue.counts` in My work mode.
- Each row shows Owner / Due / Next / Source.

Dashboard asset: `dashboard-CYN46WBx.js`.

---

## Audit

| Change | Audit trail |
|---|---|
| Job recruiter/HM reassignment | Wave 3 `position_ownership_events` |
| Application owner claim/assign/reassign | Existing `application_ownership_events` |
| Task create/resolve/reassign | `application_recruiter_tasks` + collaboration events |
| Interview panel assignment | Interview lifecycle assignment writes |
| Visibility / policy | Wave 2 settings audit unchanged |

Wave 4 does not invent a parallel ownership store — queues read Wave 3 authority.

---

## Proofs

| Gate | Result |
|---|---|
| Recruiter My work = own responsibility | **PASS** (smoke responsibility + ownership filter) |
| Hiring Manager via `hiring_manager_user_id` | **PASS** (smoke) |
| Interviewer via interview assignment | **PASS** (smoke) |
| HR leadership My ↔ Company switch | **PASS** (`can_view_company_work`; live owner company queue `audience=company`) |
| Unrelated users no personal alerts / no company scope | **PASS** (viewer `company` → 403; personal kinds labeled) |
| Reassignment moves responsibility | **PASS** (`reassignment-proof.json` responsibility flip; restored) |
| Shared alerts remain company-level | **PASS** (`shared_alerts_company`; delivery kinds `audience=company`) |
| Counts match rows | **PASS** (`counts.total == total`) |
| Health | **200** |
| Rollback / restore | **PASS** — dashboard `oEgG3EB7` ↔ `CYN46WBx`; module absent ↔ restored `mine` |
| Waves 1–3 regression | **PASS** |
| Unrelated mutations | **PASS** — personal work module + work-queue/notifications/notify wiring + Overview toggle only |
| Calendar | **Not built** |

Smoke: `smoke-test-multi-user-wave4-personal-work.py` (+ Waves 1–3 after restore).

---

## Source map

| Concern | Location |
|---|---|
| Queue builder | `wathefni-orchestrator/prehire_personal_work.py` |
| Routes + notify + notification action items | `app.py` |
| Overview My/Company UI | `apps/wathefni-dashboard/src/App.tsx` |
| API client / types | `lib/api.ts`, `types.ts` |
| Smoke | `smoke-test-multi-user-wave4-personal-work.py` |

---

## Remaining (not Wave 4)

- Calendar
- Richer live Recruiter/HM sample queues in WATHEFNI (few non-owner active users today; responsibility flip proven)
- UI person-picker for ownership (still UUID fields from Wave 3)
- Pushing every WhatsApp HR notify call site to pass assignees (helper ready; company broadcast remains default for shared ops)

**Stop after Wave 4.**
