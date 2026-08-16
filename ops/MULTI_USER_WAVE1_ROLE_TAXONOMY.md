# Multi-User Workspace Wave 1 — Role Taxonomy & Least-Privilege Authority

**Date:** 2026-07-28 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T210539Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave1-role-taxonomy/20260728T210539Z/`  
**Scope:** Distinct production roles + least-privilege authority  
**Out of scope:** Wathefni Calendar, unrelated page redesigns, custom Wave-2 RBAC cutover  

---

## Verdict

**PASS.** Company Admin, HR Admin, HR Manager, Recruiter, Hiring Manager, Interviewer, Payroll Operator, and Viewer are distinct backend roles with unambiguous keys/labels. `hr_admin` no longer aliases to Owner. Interviewer is assignment-scoped. Payroll Operator cannot access candidates. Existing `owner` users remain Company Admin with unchanged Owner powers. No DB role rewrites; no privilege escalation. Health **200**. Rollback/restore proven.

Employee App users remain on `/app/*` (separate). Team Manager (`manager`) is retained for live `manager_scopes` (not removed).

---

## Canonical keys and labels

| Product role | Backend key | Label | Notes |
|---|---|---|---|
| Company Admin | `owner` | Company Admin | Existing owners stay on this key; `company_admin` / `admin` alias → `owner` |
| HR Admin | `hr_admin` | HR Admin | **No longer aliases to owner** |
| HR Manager | `hr_manager` | HR Manager | Operational HR; no settings/users/audit |
| Recruiter | `recruiter` | Recruiter | Unchanged authority |
| Hiring Manager | `hiring_manager` | Hiring Manager | Unchanged authority |
| Interviewer | `interviewer` | Interviewer | **New**; assignment-scoped |
| Payroll Operator | `payroll_operator` | Payroll Operator | **New**; payroll-only |
| Viewer | `viewer` | Viewer | Unchanged |
| Team Manager (compat) | `manager` | Team Manager | Kept for manager_scopes |
| Employee App user | n/a | — | Separate `/app/*` surface |

---

## Permission matrix (Wave 1)

| Capability | Company Admin | HR Admin | HR Manager | Recruiter | Hiring Manager | Interviewer | Payroll Operator | Viewer |
|---|---|---|---|---|---|---|---|---|
| Company settings (`settings.manage`) | Yes | Yes | No | No | No | No | No | No |
| User management (`users.manage`) | Yes | **No** | No | No | No | No | No | No |
| Jobs read | Yes | Yes | Yes | Yes | Yes | No | No | Yes |
| Jobs create/edit | Yes | Yes | Yes | Yes | No | No | No | No |
| Jobs publish/close | Yes | Yes | Yes | No | No | No | No | No |
| Candidate read | Yes | Yes | Yes | Yes | Yes | **No** | **No** | Yes |
| Candidate manage/import | Yes | Yes | Yes | Yes | No | No | No | No |
| Candidate decide | Yes | Yes | Yes | No | No | No | No | No |
| Interview read (list) | Company | Company | Company | Company | Company | **Assigned only** | No | Company |
| Interview manage / feedback | Full | Full | Full | Full | Full | **Assigned feedback/notes/review only** | No | No |
| Assessment manage | Yes | Yes | Yes | Yes | No | No | No | No |
| Assessment publish | Grant-only | Grant-only | Grant-only | Grant-only | Grant-only | Grant-only | Grant-only | Grant-only |
| Offers send | Yes | Yes | Yes | Yes | No | No | No | No |
| Offers approve | Yes | Yes | Yes | No | Yes | No | No | No |
| Reports export | Yes | Yes | Yes | Yes | Yes | No | No | No |
| Payroll read/manage/export | Yes | Yes | Yes | No | read/manage subset* | No | **Yes (all three)** | read |
| Audit (`audit.read`) | Yes | Yes | **No** | No | No | No | No | No |
| Post-hire | Full | Full | Full | None | Manager subset | None | Payroll only | Read-ish |

\*Hiring Manager keeps existing `_POSTHIRE_PERMS_MANAGER` (no `payroll.export`).

Permissions remain **backend-authoritative** via `dashboard_effective_permissions_for_user`. Frontend invite/role UI and nav consume effective permissions / role keys only.

---

## Interviewer assignment scope

1. List + agenda SQL/filter: actor must appear on `candidate_interview_assignments` (`assignee_user_id` / email / phone).
2. `require_interview_record` + video file GET enforce the same fail-closed check.
3. Presentation `allowed_actions` narrowed to `{write_notes, view_feedback, review_video}`.
4. Company-wide ops blocked: schedule, reschedule, assign, status update, send-video-invitation, transcript retry.

---

## Migration safety

| Rule | Result |
|---|---|
| Existing `owner` rows unchanged | **PASS** — production counts: `owner=2`, `viewer=2`; no role UPDATEs |
| Literal `hr_admin` rows | **0** in production (none demoted unexpectedly) |
| No automatic privilege escalation | **PASS** — code-only taxonomy; no grant inserts |
| Owners keep Company Admin powers | **PASS** — `users.manage` / settings / audit retained on `owner` |
| HR Manager least-privilege tighten | Intentional **reduction** only (`settings.manage`, `audit.read` removed) — not escalation |
| Tenant isolation / sessions / audit history | Unchanged substrate |
| EN/AR + RTL | Labels updated; layout/locale untouched |

---

## Frontend

- `ROLE_LABELS_UI` lists all Wave 1 invite/change roles (Team Manager kept).
- Nav gated by effective permissions (Payroll Operator → payroll; Interviewer → interviews; Settings requires settings/users manage; Activity requires audit.read).

---

## Proofs

| Gate | Result |
|---|---|
| Company Admin ≠ HR Admin | **PASS** (`owner` ⊃ `hr_admin`; only owner has `users.manage`) |
| HR Admin cannot manage users | **PASS** |
| Interviewer assignment-scoped + action-narrowed | **PASS** (smoke + live helpers) |
| Payroll Operator cannot access candidates | **PASS** (no `prehire` / `candidates` / `candidate.*`) |
| Existing Owner users remain Owner | **PASS** (`owner=2`, key unchanged) |
| No user gains permissions during migration | **PASS** (no DB role/grant mutations) |
| Health | **200** (`http://127.0.0.1:8010/health`) |
| Rollback / restore | **PASS** — dashboard `BcGPtRfR` ↔ `BlTBX1nQ`; `hr_admin` alias `owner` ↔ `hr_admin` |
| Unrelated mutations | **PASS** — only role taxonomy, interview scope gates, nav permission filters, smoke/docs |

Dashboard asset after Wave 1: `dashboard-BlTBX1nQ.js`.

Smoke: `wathefni-orchestrator/smoke-test-multi-user-wave1-roles.py` (ALL PASSED on production after restore).

---

## Rollback / restore

| Step | Result |
|---|---|
| Dashboard → before | asset `dashboard-BcGPtRfR.js`; health 200 |
| Dashboard → after | asset `dashboard-BlTBX1nQ.js`; health 200 |
| `app.py` → before | `normalize_hr_role("hr_admin")` → `owner`; health 200 |
| `app.py` → after | `normalize_hr_role("hr_admin")` → `hr_admin`; Wave1 smoke PASS; health 200 |

Artifacts: `app.py.before|after`, `wathefni-dashboard.before|after`, `asset.*.txt`, `alias.*.txt`, `wave1-smoke*.txt`, `live-proof.json`, `migration-role-counts.json`, `health.*`.

---

## Source map

| Concern | Location |
|---|---|
| Aliases / labels / permissions | `wathefni-orchestrator/app.py` `ROLE_ALIASES`, `ROLE_LABELS`, `ROLE_PERMISSIONS` |
| Interviewer scope helpers | `interview_assignment_scope_sql`, `require_interview_assignment_scope`, `require_interview_company_operator`, `narrow_interview_allowed_actions_for_role` |
| Interview list/agenda/record gates | `dashboard_interviews_payload`, agenda endpoint, `require_interview_record`, video GET |
| Invite UI labels / nav | `apps/wathefni-dashboard/src/App.tsx` `ROLE_LABELS_UI`, `availableNavItems` |
| Smoke | `smoke-test-multi-user-wave1-roles.py`, updated `smoke-test-company-activity.py` |

---

## Remaining (explicitly not Wave 1)

- Wathefni Calendar
- Soft-scoping Hiring Manager / Recruiter to owned jobs/candidates by default
- Retiring Team Manager or mapping it into Hiring Manager
- Billing product surface (Company Admin ownership conceptually includes it; no separate billing ACL module yet)
- Populating `assignee_user_id` on every historical panel row (email/phone match still works)

**Stop after Wave 1.**
