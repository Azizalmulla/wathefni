# Attendance Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T071332Z`  
**Evidence:** `ops/evidence/attendance-page-refinement-wave1-prod-deploy-20260804T071332Z/`  
**Freeze:** `ops/ATTENDANCE_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle:** `/var/www/wathefni-dashboard/assets/PostHire-D7arwIkG.js`  
**Backup:** `/opt/wathefni/backups/production-pre-attendance-page-refinement-wave1-20260804T071332Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** |
| Freeze Attendance Wave 1 | **GO / FROZEN** |
| Begin Leave Wave 1 | **GO** (UI refinement; no wait) |

## Pre-green verification

| Check | Result |
|---|---|
| Board Resolve → Ops focus (employee + date) | **PASS** (source + deployed markers) |
| Absence Ops path (`kind===absence` → request sets completed) | **PASS** |
| Dual review and Apply separate | **PASS** (distinct handlers + confirm copy) |
| Payroll-locked cannot change (surfaces `payroll_period_locked`) | **PASS** |
| Row-version conflicts → ConflictBanner / stale copy | **PASS** |
| Operations collapsed by default (`operationsOpen=false`) | **PASS** |
| Mobile / Arabic RTL | **PASS** (dir + AR copy in bundle) |

## Smoke

`verify/smoke-prod.out` — `ATTENDANCE_WAVE1_SMOKE_OK`  
`verify/preflight-gates.out` — `PREFLIGHT_GATES_OK`

## Residual issues

- WATHEFNI `attendance_ops_exceptions` / `attendance_ops_cases` had **no open rows** at smoke time (empty company sample). Absence/dual-path proof is UI+code authority, not a live mutate exercise (intentionally non-mutating).
- Global `ACTION_CONFIRM` map still lists `mark_attendance_absent` / `correct_attendance_record` for non-board callers; Attendance page no longer wires them.

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-attendance-page-refinement-wave1-20260804T071332Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-attendance-page-refinement-wave1-20260804T071332Z
```

## Screenshots

`screenshots/attendance-{desktop,mobile}-{en,ar}.png`
