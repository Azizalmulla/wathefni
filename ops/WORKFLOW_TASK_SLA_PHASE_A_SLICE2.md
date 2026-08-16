# Workflow Tasks + SLA — Phase A Slice 2

**Status:** PHASE_A_SLICE2_FULL_PASS (unit + staging DB; invariants re-proved in Slice 3)  
**Charter:** `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md`  
**Code:** `wathefni-orchestrator/workflow_task_sla.py`  
**SQL:** `wathefni-orchestrator/ops/sql/workflow_task_sla_phase_a_v1.sql` + `v1b_invariants.sql`  
**Evidence:** `ops/evidence/workflow-task-sla-phase-a-20260811T152412Z` · re-prove in `ops/evidence/phase-a-slice3-20260811T153131Z`

## Modularity (preserved)

| Capability | Independence |
|---|---|
| Tasks | Works alone when `WATHEFNI_WORKFLOW_TASKS` + allowlist + company setting on |
| SLA clocks | Work alone for start/satisfy/cancel/breach accounting |
| Breach → `sla_breach` task | Only when **both** tasks + SLA company gates are on (OPTIONAL INTEGRATION) |
| Inbox SoT | Extends `hr_tasks` — no second inbox |

## Rollout (fail closed, not global)

1. `WATHEFNI_WORKFLOW_TASKS=on` + `WATHEFNI_WORKFLOW_TASKS_COMPANIES=CSV`
2. `WATHEFNI_WORKFLOW_SLA=on` + `WATHEFNI_WORKFLOW_SLA_COMPANIES=CSV`
3. `workflow_task_settings.enabled` / `workflow_sla_settings.enabled` (+ optional `reminders_enabled`)

Reminders in this slice emit `sla_reminder_due` audit events only (no live push).

## Locked invariants (Slice 2 contract)

1. One canonical open `hr_task` per `(company_code, task_type, subject_type, subject_id)`; retries dedupe.
2. `subject_type` + `subject_id` + `company_code` always required and tenant-scoped (fail closed).
3. SLA breach emitted once/idempotently per clock; repeated `tick` does not duplicate `sla_breach` tasks.
4. Satisfy/cancel after breach is deterministic and audited (`sla_post_breach_closure`).
5. `due_at` / SLA timestamps stored UTC; company-local presentation only at surfaces.
6. Tasks from approvals preserve `approval_instance_id` / subject linkage (`create_task_from_approval`).
7. Resolving a task never mutates the underlying business subject (`mutates_subject=false`).
8. Disabled Tasks/SLA leave existing domain workflows usable; legacy `hr_tasks` types remain insertable.
9. Audit-only reminders — no live push/channel delivery in Phase A.

## Rollback

Flags off → allowlist clear → company settings false → retain tables/rows.
