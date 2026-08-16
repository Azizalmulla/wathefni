# Attendance Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp:** `20260804T071332Z`  
**Evidence:** `ops/evidence/attendance-page-refinement-wave1-prod-deploy-20260804T071332Z/`  
**Report:** `ops/ATTENDANCE_PAGE_REFINEMENT_WAVE1.md`

## Frozen surface

- Board-first Attendance with compact header, date chrome, attention strip
- Sole correction path: Ops request → dual review → separate Apply
- Board Resolve focuses Ops exception (employee + work date)
- Operations collapsed by default (Capture / Import / Export)
- No board Correct / Mark absent competing mutations
- Dual approval, row_version ConflictBanner, payroll-lock denial copy retained
- Arabic/RTL + mobile board/exception composition

## Frozen non-goals

- Punch ingest / device enablement
- New attendance permissions
- Payroll money impact
- Leave page (next wave)

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-attendance-page-refinement-wave1-20260804T071332Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-attendance-page-refinement-wave1-20260804T071332Z
```
