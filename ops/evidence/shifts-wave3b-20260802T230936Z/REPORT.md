# Shifts Wave 3B — production synthetic UX canary

**Stamp:** `20260802T230936Z`  
**Evidence:** `ops/evidence/shifts-wave3b-20260802T230936Z/`  
**Staging gate:** `ops/evidence/shifts-wave3b-staging-create-20260802T225846Z/` (**GO**)  
**Module:** `shifts_wave3_controlled.py` **v3.1.0**

## Scope
Production WATHEFNI synthetic-only UX canary for Calendar-aligned Shifts workspace.  
Markers: **SHW3B** / **965531***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Timers / integrity jobs **disabled** (`WATHEFNI_SHIFTS_INTEGRITY_JOBS=0`).

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 3 UX | **GO** |
| Controlled HR scheduling | **NO-GO** (allowlists empty; real mutations blocked) |
| Scoped manager scheduling | **NO-GO** (allowlists empty; real mutations blocked) |
| Talal read-only scheduling view | **NO-GO** (not separately qualified; mutate path blocked) |
| Real reminders | **NO-GO** (`WATHEFNI_SHIFTS_REAL_REMINDERS=0`) |
| Broad employee-app rollout | **NO-GO** |

## Staging create-path (mandatory before prod)
- Plural `POST /dashboard/posthire/actions` → **405**
- Canonical `POST /dashboard/posthire/shifts` → **200**
- Browser composer: same-day, split (2 authority rows), overnight; UI↔API↔DB; residual **0**
- Gate: **STAGING_CREATE_PATH_GO**

## Production canary results
- Dashboard serve fix: set `WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist` and sync legacy `/opt/wathefni/apps/wathefni-dashboard/dist` (was serving stale `dashboard-BtTY4HND.js`)
- Deploy #1 → API canary #1: **31 passed, 0 failed** (`real_fps_unchanged`)
- Browser #1: **11 passed, 0 failed** (composer creates + residual zero + EN desktop + AR mobile RTL shots)
- Rollback: **ROLLBACK_OK**
- Redeploy #2 → API canary #2: **31 passed, 0 failed** (`real_fps_unchanged`)
- Browser #2: **11 passed, 0 failed**
- Screenshots: `screenshots/browser/{browser1,browser2}/` (14 PNGs)

## Regressions (prod)
- Wave 3 UX: **43 passed, 0 failed**
- Wave 1: **90 passed, 0 failed**
- Wave 2: **82 passed, 0 failed** (SHW2 / 965529 markers restored for frozen-module smoke; jobs kill switch remains **0** in service env; dry-run scan exercised in-process only)
- Freezes: E360 **57/0**, Onboarding **54/0**, Attendance **22/0**, Leave **34/0**

## Residual / gates held
- SHW3B residual: assignments **0**, employees **0**
- Real fingerprints unchanged across both API canaries
- WATHEFNI only · Wave 1/2 synthetic-only markers retained · empty HR/manager allowlists · real mutation gate on · real reminders off · integrity jobs 0 · CAPTURE_INGEST off

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · No templates/recurring/rotations/publishing/open shifts/PAM.

## Gate result
**PROD_SYNTHETIC_WAVE3_UX_GO**
