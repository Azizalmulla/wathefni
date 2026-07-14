# HR-1 — Capability Matrices

Derived on every `/dashboard/mobile/me` from modules + backend-current permissions + manager scope health.
Features without a safe mobile endpoint stay `enabled: false` with `reason: feature_disabled`.

## HR workspace

| Feature | Modules | Permissions | Actions when enabled | Notes |
| --- | --- | --- | --- | --- |
| `hr_tasks` | any post-hire | any of leave/attendance/onboarding/compliance/shifts/payroll `.read` | `read` | Aggregate inbox signal |
| `leave_approvals` | `leave` | `leave.read` / `leave.decide` | `read`, `approve`, `reject` | |
| `onboarding_review` | `onboarding` | `onboarding.read` / `onboarding.manage` | `read`, `review` | |
| `document_review` | onboarding or compliance | matching read/manage | `read`, `review` | |
| `attendance_exceptions` | `attendance` | `attendance.read` / `attendance.manage` | `read`, `resolve` | |
| `today_shifts` | `shifts` | `shifts.read` | `read` | |
| `shift_swap_decisions` | `shifts` | `shifts.manage` | `read`, `approve`, `reject` | |
| `employee_search` | n/a | **grant-only** `employees.read` | `read` | Not inferred from role |
| `employee_quick_profile` | n/a | **grant-only** `employees.read` | `read` | |
| `delivery_alerts` | any post-hire | matching `.read` set | `read` | |

Manager with `configuration_error` / blocked scope: **all HR features disabled** (`manager_scope_missing` or `manager_scope_conflict`).

### Representative roles (full modules on)

| Role | leave_approvals | employee_search (no grant) | employee_search (with grant) |
| --- | --- | --- | --- |
| owner | read+approve+reject | off | on |
| hr_manager | read+approve+reject | off | on |
| manager (scoped) | read+approve+reject | off | on if granted |
| manager (missing/conflict) | off | off | off |
| recruiter | off (no post-hire perms) | off | off |
| hiring_manager | read (+ decide if role has it) | off | on if granted |
| viewer | read | off | on if granted |

## Recruiting workspace

| Feature | Permissions | Actions | Notes |
| --- | --- | --- | --- |
| `candidate_rankings` | `prehire.read` | `read` | `advisory: true` |
| `candidate_summary` | `prehire.read` | `read` | |
| `candidate_evidence` | `prehire.read` | `read` | Concerns remain visible at data endpoints |
| `candidate_cv` | `prehire.read` | `view`, `preview`, `download` | HR-0 audit retained on data path |
| `candidate_shortlist` | `candidate.manage` | `shortlist` | Registry policy |
| `candidate_reject` | `candidate.decide` | `reject` | `confirmation_required: true` |
| `candidate_hire` | `candidate.decide` | `hire` | `confirmation_required: true` |
| `interview_status` | `prehire.read` or `interview.manage` | `read` | |
| `interview_notes` | `interview.manage` | `read`, `write` | |
| `candidate_communication_status` | `candidate.manage` or `prehire.read` | `read` | |

### Explicitly unavailable (disabled)

`new_candidate_push`, `interview_reschedule`, `kanban_stage_management`, `bulk_import`, `job_pipeline_configuration`, `ai_scoring_configuration`.

Requires `pre_hiring` module. No legacy `ai-recruiter/` endpoints.

### Representative roles

| Role | rankings | shortlist | hire/reject |
| --- | --- | --- | --- |
| owner / hr_manager | on | on | on (+ confirmation) |
| recruiter | on | on | off |
| hiring_manager | on | off | off |
| viewer | on | off | off |
| manager | off (no prehire perms) | off | off |

## Owner workspace

| Field | HR-1 value |
| --- | --- |
| `enabled` | `false` |
| `features` | `{}` |
| `reason` | `feature_disabled` |

Owner users still receive HR/recruiting capabilities via those namespaces when granted. Setup Console, cross-company ops, and provisioning stay out of Wathefni HR.
