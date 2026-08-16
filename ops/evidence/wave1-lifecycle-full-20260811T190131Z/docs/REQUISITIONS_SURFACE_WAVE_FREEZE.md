# Requisitions Surface Wave — FREEZE

**Status:** FROZEN — `REQUISITIONS_SURFACES_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/requisitions-surfaces-20260811T185808Z`  
**Contract:** `ops/REQUISITIONS_SURFACE_WAVE.md`  
**Backend authority:** `ops/REQUISITIONS_WAVE1_BACKEND_FREEZE.md` (untouched)

## Freeze rules

1. Do **not** change frozen `requisitions.py` SM / SoD / gate flags without a backend freeze amendment.
2. Surfaces stay thin: list/queue/detail/explain live in `requisitions_surfaces.py` only.
3. Mutations call frozen `create_requisition` / `transition_requisition` / `link_job_to_requisition` only.
4. Keep dark by default (process-scoped flags + company module). No systemd-global enable.
5. Manager/HR Mobile approve is capability-gated; SoD still enforced server-side.

## Proven

- EN/AR/RTL web framing
- RBAC `requisitions.read` / `manage` / `approve`
- Tenant isolation + module-off + concurrency conflict
- Works without `pre_hiring`
- No employee ESS requisitions page

Amendments require a dated note + re-qualify.
