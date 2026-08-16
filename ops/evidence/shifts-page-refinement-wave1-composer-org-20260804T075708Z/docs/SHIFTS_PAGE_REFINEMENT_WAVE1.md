# Shifts Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T074315Z`  
**Evidence:** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Freeze:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle:** `/var/www/wathefni-dashboard/assets/PostHire-YNtC8Unb.js`  
**Backup:** `/opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** |
| Freeze Shifts Wave 1 | **GO / FROZEN** |
| Backend / freeze reopen / payroll money | **NO-GO** (not done) |

## IA correction

| Before | After |
|---|---|
| 8 peer tabs | **Schedule / Requests / Planning** |
| Duplicated inner Shifts h1 | Removed (shell owns title) |
| Delivery-failure strip on Shifts | Excluded |
| Honesty/lab chips on first paint | Collapsed under Planning readiness |
| Free-text branch/site/team filters | Governed org-unit selects |
| Competing primaries | One primary: **Schedule a shift** |
| Loud Refresh | Ghost icon |
| Thin empty text | Empty state + Schedule CTA |

## Pre-green verification

| Check | Result |
|---|---|
| Schedule default dominant surface | **PASS** |
| Requests holds swaps / availability / reconciliation | **PASS** |
| Planning holds templates / publish / enterprise / reminders | **PASS** |
| Mutation contracts preserved (`create`/`cancel`/`reschedule` + row concurrency) | **PASS** |
| Arabic / RTL + mobile day view | **PASS** |

## Smoke

`verify/smoke-prod.out` — `SHIFTS_WAVE1_SMOKE_OK`

## Residual issues

- Create/edit composer still accepts free-text org keys (governed filters cover the board query).
- If org units API is empty/disabled, branch/site/team selects show “All …” only until units exist.
- Full `tsc -b` still fails on unrelated CloseExport/Payslip/Statutory files; deploy used `vite build`.

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z
```

## Screenshots

`screenshots/shifts-{desktop,mobile}-{en,ar}.png`
