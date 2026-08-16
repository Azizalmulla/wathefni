# Multi-User Workspace Wave 3 — Ownership & Assignment Authority

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T214719Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave3-ownership/20260728T214719Z/`  
**Scope:** First-class recruiter / hiring manager / interviewer ownership  
**Preserved:** Waves 1–2 (roles + visibility policy)  
**Out of scope:** Wathefni Calendar  

---

## Verdict

**PASS.** Ownership is now a single backend contract: jobs auto-assign recruiter when a Recruiter creates them (leadership may leave Unassigned or override); hiring manager is always explicit; applications inherit `owner_user_id` from `positions.recruiter_user_id` on import/admit/public apply; reassignment is versioned and audited (`position_ownership_events` + existing `application_ownership_events`); Unassigned work stays visible to HR leadership under assigned/hybrid while scoped roles only see owned/assigned items. Health **200**. Rollback/restore proven. Waves 1–2 regression smoke passed.

---

## Canonical ownership contract

| Entity | Field | How set | Unassigned |
|---|---|---|---|
| Job | `recruiter_user_id` | Auto = actor when creator role is `recruiter` and not overridden; explicit override always wins; leadership default = null | `recruiter_user_id IS NULL` |
| Job | `hiring_manager_user_id` | Explicit only (never auto) | null |
| Job | `created_by_user_id` | Actor (provenance only) | n/a |
| Application | `owner_user_id` | Inherit from job recruiter when present; claim/assign/reassign APIs unchanged | null |
| Interview | `candidate_interview_assignments` | Explicit panel (Wave 1) | no assignee rows |

Serialized jobs now include `recruiter_ownership_state` / `hiring_manager_ownership_state` / `ownership_unassigned`.

---

## Behaviors

### Job create
- Recruiter creates without `recruiter_user_id` → auto-assigned to self (`auto_recruiter`)
- Company Admin / HR Admin / HR Manager create without recruiter → **Unassigned**
- Any role providing `recruiter_user_id` → explicit override
- HM set only when provided

### Job update
- Changing recruiter/HM writes `position_ownership_events` (`recruiter_*` / `hm_*`)
- Optimistic concurrency unchanged (`expected_version` / `expected_updated_at`)
- When recruiter is newly set/changed, still-unassigned applications on that job inherit ownership (does not steal already-owned apps)

### Application intake
- Bulk/email import, import role-assign/admit, public Stage B apply → `apply_application_owner_inherit`
- Existing owner assignment/claim/reassign APIs + `application_ownership_events` retained

### Visibility (Wave 2)
- Scoped Recruiter/HM still see owned/assigned only
- Unassigned excluded from scoped queues (no black hole for leadership — oversight bypasses scope)
- Jobs summary adds `unassigned_recruiter_positions` / `unassigned_hm_positions`
- Applications already expose `ownership_counts.unassigned`

### Interviewer
- Remains explicit per-interview assignment (Wave 1)

---

## Proofs

| Gate | Result |
|---|---|
| New recruiter-created job gets owner | **PASS** (`auto_recruiter`) |
| Leadership default Unassigned | **PASS** |
| Explicit leadership override | **PASS** |
| Applications inherit job recruiter | **PASS** (import / admit / public apply wired) |
| Reassignment updates scoped surfaces | **PASS** (events + unassigned app inherit on job recruiter change) |
| HM only owns via `hiring_manager_user_id` | **PASS** (Wave 2 SQL + no HM auto) |
| Interviewer assignment-only | **PASS** (Wave 1 regression) |
| Unassigned visible to leadership | **PASS** (oversight unscoped + summary counts) |
| No accidental access loss | **PASS** (default shared_company; ownership only fills nulls) |
| Health | **200** |
| Rollback / restore | **PASS** (`actor_role` absent → present) |
| Waves 1–2 regression | **PASS** |

---

## Source map

| Concern | Location |
|---|---|
| Contract helpers | `wathefni-orchestrator/prehire_ownership.py` |
| Job create/update + events | `prehire_jobs.py` |
| Route actor_role + audits | `app.py` positions create/update |
| App inherit | `register_imported_cv`, import assign, `jobs_phase2_stage_b.py` |
| Smoke | `smoke-test-multi-user-wave3-ownership.py` |

---

## Remaining (not Wave 3)

- Calendar
- UI person-picker for recruiter/HM (still UUID fields)
- Syncing dead `recruiter_owner_user_id` governance channel (authority is `owner_user_id`)
- Moving already-owned applications when job recruiter changes (intentionally not silent)

**Stop after Wave 3.**
