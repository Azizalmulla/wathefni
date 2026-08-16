# Workflow Approvals — Phase A Slice 1

**Status:** PHASE_A_SLICE1_FULL_PASS (unit + staging DB)  
**Charter:** `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md` v0.2  
**Code:** `wathefni-orchestrator/workflow_approvals.py`  
**SQL:** `wathefni-orchestrator/ops/sql/workflow_approvals_phase_a_v1.sql`  
**Smoke:** `wathefni-orchestrator/smoke-test-workflow-approvals-phase-a.py`  
**DB prove:** `wathefni-orchestrator/smoke-test-workflow-approvals-phase-a-db.py`  
**Qualify:** `ops/qualify-workflow-approvals-phase-a-staging.sh`  
**Evidence:** `ops/evidence/workflow-approvals-phase-a-20260811T152111Z`

## Rollout flag (fail closed)

All three required:

1. `WATHEFNI_WORKFLOW_APPROVALS=on`
2. `WATHEFNI_WORKFLOW_APPROVALS_COMPANIES=<CSV company codes>` (empty = nobody)
3. `workflow_approval_settings.enabled=true` for that company

Schema may be present on boot; **no product subjects** bind until later slices.

## Rollback

1. Set `WATHEFNI_WORKFLOW_APPROVALS=off`
2. Remove company from allowlist
3. `UPDATE workflow_approval_settings SET enabled=false WHERE company_code=…`
4. Retain tables; do not DROP
5. Legacy offer/leave dual-control unchanged

## Out of scope this slice

- Requisitions / Preboarding UI
- SLA clocks
- Migrating existing offer/leave approvals onto this engine
- HTTP public API surface (authority module only)
