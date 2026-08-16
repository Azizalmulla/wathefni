# Leave Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T072450Z`  
**Evidence:** `ops/evidence/leave-page-refinement-wave1-prod-deploy-20260804T072450Z/`  
**Freeze:** `ops/LEAVE_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle:** `/var/www/wathefni-dashboard/assets/PostHire-HPcJNRf5.js`  
**Backup:** `/opt/wathefni/backups/production-pre-leave-page-refinement-wave1-20260804T072450Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** |
| Freeze Leave Wave 1 | **GO / FROZEN** |
| Backend authority / payroll money changes | **NO-GO** (not done) |

## Pre-green verification

| Check | Result |
|---|---|
| Queue-first cream Leave board + attention strip | **PASS** |
| One primary action via `leavePrimaryAction` + More secondaries | **PASS** |
| Dual initiate and dual confirm separate from Approve | **PASS** |
| `expected_row_version` on decide mutations | **PASS** |
| Unpaid honesty + balances `enforced=false` messaging | **PASS** |
| E360 leave mutates demoted → Open in Leave | **PASS** |
| Mobile / Arabic RTL (`dir` + AR copy) | **PASS** |

## Smoke

`verify/smoke-prod.out` — `LEAVE_WAVE1_SMOKE_OK`

## Residual issues

- Leave list API does not yet enrich `dual_control_status` / `dual_action_id` on pending rows; Confirm dual-control is wired and shows when those additive fields are present (or in drawer). Start dual remains available for `needs_review` / `expired_stale`.
- Full `tsc -b` still fails on unrelated CloseExport / Payslip / Statutory workspaces; deploy used `vite build` (same pattern as prior UI waves).

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-leave-page-refinement-wave1-20260804T072450Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-leave-page-refinement-wave1-20260804T072450Z
```

## Screenshots

`screenshots/leave-{desktop,mobile}-{en,ar}.png`
