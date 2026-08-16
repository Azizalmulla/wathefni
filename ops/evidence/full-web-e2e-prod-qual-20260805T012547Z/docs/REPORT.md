# Wathefni Full Web E2E & Production Qualification

**Stamp:** `20260805T012547Z`  
**Verdict:** **PASS** (qualification only — no product redesign; harness false-positive fixed; attendance smoke script restored on VPS)  
**Host:** `https://api.wathefni.ai` · health `127.0.0.1:8010` **200**  
**Primary tenant:** `WATHEFNI` owner session (minted for read-only qual)  
**Bundles:** `PostHire-BBh-0pcx.js` · `CalendarShell-KlPj_qBg.js` · `dashboard-BnPdHXAl.js`  
**Evidence:** `ops/evidence/full-web-e2e-prod-qual-20260805T012547Z/`

## Suite counts

| Suite | Passed | Failed | Total |
|---|---:|---:|---:|
| Freeze pack (8 scripts, VPS venv) | 8/8 | 0 | 8 |
| API live gates | 21 | 0 | 21 |
| UI live gates (EN/AR × desktop/mobile + deep links) | 87 | 0 | 87 |
| Posthire page UI prod smokes | 10/10 | 0 | 10 |
| Vitest contracts | 18 | 0 | 18 |
| Mutation integrity smoke | PASS | 0 | — |
| Calendar projections unit smoke | PASS | 0 | — |

## Route-by-route PASS/FAIL

| Route | Verdict | Notes |
|---|---|---|
| Overview | **PASS** | UI×4 + summary API |
| Jobs | **PASS** | UI×4 + positions API |
| Candidates | **PASS** | UI×4 + applications API |
| Interviews | **PASS** | UI×4 + interviews API |
| Assessments | **PASS** | UI×4 + assessments API; orphan `/assessments/queue` now **410** fail-closed |
| Ranking | **PASS** | UI×4 |
| Calendar | **PASS** | UI×4 + events API; Wave 2 projections flags on; freeze markers intact |
| Employees / Profile 360 | **PASS** | UI×4 + list/profile API; deep link `?employee=` PASS; Add overlay scroll-lock PASS |
| Organization | **PASS** | UI×4 (`workforce`) |
| Needs Attention | **PASS** | UI×4 + action-inbox API |
| Onboarding | **PASS** | UI×4 + API; deep link PASS |
| Attendance | **PASS** | UI×4 + API + Wave1 UI prod smoke |
| Leave | **PASS** | UI×4 + API + Wave1 UI prod smoke |
| Shifts | **PASS** | UI×4 + API + Wave1 UI prod smoke |
| Payroll | **PASS** | UI×4 + API + Wave1 UI prod smoke (read/honesty markers only) |
| Analytics | **PASS** | UI×4 + API + page smoke |
| Compliance | **PASS** | UI×4 + API + page smoke |
| Alerts & Delivery | **PASS** | UI×4 + notifications API + page smoke |
| Activity | **PASS** | UI×4 + API + page smoke |
| Settings | **PASS** | UI×4 (EN re-probed after harness fix) + import/settings API + page smoke |
| Cross-cutting | **PASS** | Invalid token 401; foreign company 403; back/forward; RTL AR desktop/mobile |

Canonical matrix: `matrix/RESULTS.md`

## Critical defects found and fixed

| Item | Severity | Action |
|---|---|---|
| Settings EN UI gate false-positive (`Sign in` copy matched login-wall heuristic) | P3 harness | Tightened probe; Settings EN desktop/mobile **PASS** on re-probe |
| Attendance Wave1 UI prod smoke missing on VPS orchestrator dir | P3 ops packaging | Copied `smoke-test-attendance-wave1-ui-prod.py` → VPS; **ATTENDANCE_WAVE1_SMOKE_OK** |

No product UX redesign, backend contract, payroll mutation, hiring-authority, or tenant-isolation defect required a deploy.

## Deferred blockers (do not block mobile kickoff)

1. **Live money / payroll mutations** — not re-executed (by design). Payroll page smoke validates honesty/gates only. Prior payroll freeze packs remain authoritative.
2. **Live hiring mutations / Graph Teams create-cancel / outbound mail allow-deny** — cited prior prehire E2E + Wave D freezes; not re-mutated this run.
3. **Broad employee-app / ESS / lifecycle synthetic-only** — Employees 360 freeze still limits real employee-app to Talal allowlist; mobile work must respect that.
4. **Local macOS freeze of onboarding script** needs `psycopg2` for `import app`; VPS pack is the authoritative freeze evidence.

## Production stamp

`20260805T012547Z`

Harness: `ops/full-web-e2e/run-ui-qual.cjs`, `ops/full-web-e2e/run-api-qual.py`

## Tests & smoke evidence

- `tests/freeze-pack-vps.out` → `FREEZE_PACK_VPS_OK`
- `verify/api-qual.out` → `API_SUMMARY pass=21 fail=0`
- `verify/ui-qual.out` + `verify/ui-results.json` → `87/87` after Settings re-probe
- `verify/settings-reprobe.out`
- `verify/posthire-ui/prod-page-smokes.out` + `attendance-smoke.out`
- `tests/vitest-contracts.out` · `mutation-integrity.out` · `calendar-projections.out`
- `verify/as02-orphan.out` → queue route **410**
- Screenshots under `screenshots/{en,ar}-{desktop,mobile}/`

## Rollback

No dashboard/orchestrator product deploy in this stamp.  
If attendance smoke script on VPS must be removed: delete `/opt/wathefni/orchestrator/smoke-test-attendance-wave1-ui-prod.py`.  
Prior product rollbacks remain:

- Profile closure: `/opt/wathefni/backups/production-pre-employee-profile-360-closure-20260805T010809Z/ROLLBACK.sh`
- Calendar Wave 2: `/opt/wathefni/backups/production-pre-calendar-wave2-projections-20260805T005000Z/ROLLBACK.sh`

## Final GO / NO-GO — begin employee iOS/Android app work

| Decision | Result |
|---|---|
| Full web E2E / production qualification | **GO / PASS** |
| Begin employee iOS/Android app work | **GO** under existing Employees 360 / ESS freeze boundaries (Talal allowlist canary; synthetic-only gates; no payroll money authority in app v1 without a new owner wave) |
| Broad real employee-app GA | **NO-GO** until ESS/lifecycle allowlist expansion is separately approved |
| Reopen frozen web UX / module authority | **NO-GO** without owner change-control |
