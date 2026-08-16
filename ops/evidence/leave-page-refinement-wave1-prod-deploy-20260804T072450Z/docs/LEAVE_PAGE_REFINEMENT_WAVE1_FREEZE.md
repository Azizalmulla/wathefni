# Leave Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp:** `20260804T072450Z`  
**Evidence:** `ops/evidence/leave-page-refinement-wave1-prod-deploy-20260804T072450Z/`  
**Report:** `ops/LEAVE_PAGE_REFINEMENT_WAVE1.md`

## Frozen surface

- Queue-first Leave with Active / History filters and compact attention strip
- One derived primary row action (`approve` / `start_dual` / `confirm_dual` / `cancel` / `view_details`)
- Secondary decide actions under **More** / detail drawer
- Dual initiate and dual confirm remain separate from Approve
- Decide mutations keep `leave_id` + `expected_row_version`
- Balances stay non-binding (`enforced=false`); unpaid money owned by Payroll copy only
- Employee 360 Leave section is context + **Open in Leave** (no Approve/Decline)

## Frozen non-goals

- Backend leave gates / allowlists
- Balance enforcement (`enforced=true`)
- Payroll money calculation changes
- Inventing new leave statuses

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-leave-page-refinement-wave1-20260804T072450Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-leave-page-refinement-wave1-20260804T072450Z
```
