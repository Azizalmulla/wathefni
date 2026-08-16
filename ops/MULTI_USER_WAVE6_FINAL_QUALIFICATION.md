# Multi-User Workspace Wave 6 — Team Privacy, People Pickers & Final Qualification

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T232331Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave6-final/20260728T232331Z/`  
**Scope:** Team directory privacy + searchable people pickers + notification routing completion + final multi-user qualification  
**Preserved:** Waves 1–5 (roles, visibility, ownership, personal work, concurrency)  
**Out of scope:** Wathefni Calendar  

---

## Verdict

**PASS.** Team directory is privacy-tiered in the backend: collaboration users see name + role (+ status) only; peer emails/phones and effective permission matrices stay admin-gated. Ownership UIs use searchable company people pickers (no raw UUID fields for HR). Personal pre-hire assignment notifications route to assignees only with `audience` + `source` audit; company operational alerts stay company-level with no accidental personal broadcast. Final role matrix smoke covers Company Admin → Viewer. Health **200**. Rollback/restore proven. Waves 1–5 regression passed. No Calendar.

---

## 1. Team directory privacy

| View | Who | Payload |
|---|---|---|
| **Admin** | `users.manage` (Company Admin) or authorized HR Admin (`settings.manage` + `hr_admin`/`owner`) | Name, role, status, email, phone, WhatsApp linked, last active; **permissions / role_capabilities only with `users.manage`** |
| **Collaboration** | Everyone else | `user_id`, name, role, role_label, status — **no peer email/phone/permissions** |

- Invites + role capability matrices: `users.manage` only (Wave 1: HR Admin still cannot invite).
- Self row may include own contact fields even in collaboration view.
- Enforced in `GET /dashboard/team` via `prehire_team_directory.project_team_member` — not UI-only.

---

## 2. People pickers

| Purpose | Eligible active roles | Unassigned |
|---|---|---|
| `recruiter` | owner, hr_admin, hr_manager, recruiter | yes |
| `hiring_manager` | owner, hr_admin, hr_manager, hiring_manager, manager | yes |
| `interviewer` | owner, hr_admin, hr_manager, recruiter, hiring_manager, interviewer | no (assign flow) |
| `task_owner` | owner, hr_admin, hr_manager, recruiter, hiring_manager | yes |
| `approver` | owner, hr_admin, hr_manager, hiring_manager, manager | — |

- API: `GET /dashboard/team/people?purpose=&q=`
- Returns privacy-safe `name · role` labels — no emails/phones in picker rows.
- Frontend: `PeoplePicker` on job recruiter/HM and interview panel assign.
- Backend validates job ownership targets as active + role-eligible.
- Jobs list/workspace show `recruiter_name` / assigned label — not raw UUIDs.
- `hr_admin` added to recruiting eligibility (`RECRUITING_ROLES` + catalog SQL).

---

## 3. Notification routing completion

| Kind | Audience | Source examples |
|---|---|---|
| Personal work | `personal` | `application_owner_assignment`, `task_assignment`, `interview_assignment` |
| Company ops | `company` | `company_ops` / shared delivery alerts |

- `notify_hr_admins(..., source=, kind=)` always returns `audience`, `notification_scope`, `source`.
- `notify_prehire_personal_assignees` — **never** company-broadcasts (`fallback_company_broadcast=False`); unreachable assignees stay `audience=personal` with `target_count=0`.
- Wired on owner assign/reassign, task create/reassign, interview panel assign.
- Dashboard notification items include `source` alongside audience.
- Dedup by phone within a single fan-out.

---

## 4. Final qualification (roles)

| Role | Modules / authority (smoke + contract) |
|---|---|
| Company Admin (`owner`) | Full; `users.manage`; Company work |
| HR Admin | Full HR + settings/audit; **no** `users.manage`; admin directory view |
| HR Manager | Operational HR; Company work; no settings/users |
| Recruiter | Pre-hire operate; My work only; no company scope |
| Hiring Manager | Assigned/HM-scoped pre-hire |
| Interviewer | Assignment-scoped interview actions |
| Payroll Operator | Payroll only — no `prehire.read` |
| Viewer | Read-only pre-hire/jobs |

Preserved: shared/assigned/hybrid visibility (Wave 2), ownership (Wave 3), My/Company work (Wave 4), stale 409 concurrency (Wave 5), EN/AR + RTL via existing locale/`dir`.

---

## Proofs

| Gate | Result |
|---|---|
| Role sees correct modules/actions | **PASS** (role matrix smoke) |
| Shared / assigned / hybrid policies | **PASS** (Wave 2 regression) |
| My work / Company work | **PASS** (Wave 4 regression) |
| Reassignment / ownership | **PASS** (Wave 3 regression) |
| Stale edits cannot overwrite | **PASS** (Wave 5 regression) |
| Team directory privacy | **PASS** (`live-proof.json` collab hides email/permissions) |
| People picker eligible + no PII | **PASS** (labels only; route registered) |
| Personal notify no company broadcast | **PASS** (personal + miss target_count 0) |
| Company ops stay company-level | **PASS** |
| No Calendar | **PASS** |
| Health | **200** |
| Rollback / restore | **PASS** — dashboard `Byp5Hy6_` ↔ `BtTY4HND`; module absent (`False`) ↔ restored |
| Waves 1–5 regression | **PASS** |
| Unrelated mutations | **PASS** — directory/picker/notify wiring + FE pickers/team privacy only |

Smoke: `smoke-test-multi-user-wave6-final.py`  
Live: `live-proof.json`  
Dashboard asset: `dashboard-BtTY4HND.js`

---

## Source map

| Concern | Location |
|---|---|
| Privacy + picker contract | `wathefni-orchestrator/prehire_team_directory.py` |
| Team list + people API | `app.py` (`/dashboard/team`, `/dashboard/team/people`) |
| Notify routing + personal helper | `app.py` (`notify_hr_admins`, `notify_prehire_personal_assignees`) |
| Personal miss stays personal | `prehire_personal_work.resolve_notify_targets` |
| Job ownership validation / names | `prehire_jobs.py` |
| Recruiting eligibility | `candidate_collaboration.py` |
| PeoplePicker UI | `apps/wathefni-dashboard/src/components/PeoplePicker.tsx` |
| Jobs / interview / team UI | `JobsForm.tsx`, `App.tsx`, `JobWorkspace.tsx` |
| Smoke | `smoke-test-multi-user-wave6-final.py` |

---

## Remaining (not Wave 6)

- Calendar
- Richer task-owner picker surface in candidate collaboration UI (API purpose ready; jobs + interviewer wired)
- Expanding live non-owner role samples in WATHEFNI tenant

**Stop after Wave 6.**
