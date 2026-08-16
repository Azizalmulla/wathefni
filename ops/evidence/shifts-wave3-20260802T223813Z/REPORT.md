# Shifts Wave 3 — controlled scheduling UX and real-operation readiness

**Stamp:** `20260802T223813Z`  
**Evidence:** `ops/evidence/shifts-wave3-20260802T223813Z/`  
**Module:** `shifts_wave3_controlled.py` **v3.0.0**  
**Dashboard:** `ShiftsWorkspace.tsx` + `shiftsUx.ts`  

**Scope:** staging-first UX + controlled allowlist model.  
**Not done:** production deploy, real-mutation enablement, timer activation, templates/recurring/rotations/publishing/open shifts/PAM, broad employee-app, Payroll money.

---

## Verdicts

| Scope | Verdict |
|---|---|
| HR controlled production scheduling | **NO-GO** (model ready; allowlists empty / gate fail-closed; not deployed) |
| Scoped manager production scheduling | **NO-GO** (same) |
| Talal employee-app read | **NO-GO** for scheduling mutations; remains **read-only** by design |
| Reminders for real employees | **NO-GO** (`WATHEFNI_SHIFTS_REAL_REMINDERS` off) |
| Broad employee-app rollout | **NO-GO** |
| Production synthetic Wave 3 canary | **NO-GO** (not authorized / not run — staging UX pack only) |
| Staging Wave 3 UX readiness (this pack) | **GO** for UX + gates + freezes |

---

## UX architecture

### Screens
1. **Schedule board** (day/week) — filters: employee, branch, site, team, role  
2. **Create / reschedule / soft-cancel** — audit reason, availability/leave ack, concurrency token  
3. **Swap queue** — approve/reject (scoped)  
4. **Availability queue** — approve/reject  
5. **Reconciliation queue** — acknowledge / audited cancel (never silent)  
6. **Terminal reminder failures** — visibility only  
7. **Assignment history drawer** — versions + events / lineage  

### Design rules applied
- Direct assign without enterprise templates  
- Status chips: scheduled / cancelled / conflicted / reconciliation-required  
- Overnight: visual span across next date **without duplicating authority rows**  
- Split: same-day windows listed as separate rows  
- Stale concurrency surfaced as fail-closed (`stale_state`)  
- Explicit ack for availability/leave warnings  
- Permission-masked actions; manager scope enforced server-side  
- EN/AR + RTL via `useEmployees360Locale` + `dir`/`lang`  
- Loading / empty / error / denied / partial honesty banner states  

### Screenshots
- Desktop board: `screenshots/shifts-wave3-desktop-board.png`  
- Mobile RTL: `screenshots/shifts-wave3-mobile-rtl.png`  

---

## Permission and scope matrix

| Actor | Create / reschedule / cancel | Swap / availability decide | Reconciliation | History | Self-decision |
|---|---|---|---|---|---|
| HR allowlisted (`WATHEFNI_SHIFTS_HR_ALLOWLIST`) | yes (real + synthetic) | yes | yes | yes | n/a |
| Manager allowlisted + in scope | in-scope only | in-scope only | in-scope only | in-scope only | **denied** |
| Not allowlisted + real subject | **denied** when gate on | **denied** | **denied** | read if entitled | denied |
| Synthetic subject (Wave 1/2 markers) | allowed under existing synthetic gates | allowed | allowed | yes | denied |
| Talal employee app | read-only (Wave 3) | no | no | own read only if separately qualified | no |
| Broad employee app | **off** | **off** | **off** | **off** | **off** |

Server entitlements remain `shifts.read` / `shifts.manage` + manager scope keys.

---

## Real-operation allowlist model

| Env | Role |
|---|---|
| `WATHEFNI_SHIFTS_WAVE3` | UX enrich / controlled helpers (default on outside production) |
| `WATHEFNI_SHIFTS_WAVE3_COMPANIES` | default `WATHEFNI` |
| `WATHEFNI_SHIFTS_REAL_MUTATION_GATE` | real (non-synthetic) mutations require allowlist (prod default on) |
| `WATHEFNI_SHIFTS_HR_ALLOWLIST` | named HR phones (digits) |
| `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST` | named scoped-manager phones |
| `WATHEFNI_SHIFTS_REAL_REMINDERS` | real reminder send (default off) |
| `WATHEFNI_SHIFTS_WAVE3_KILL` | kill switch |

Real mutations additionally require **audit reason ≥ 3 chars** and **`expected_updated_at`** concurrency token on cancel/reschedule.

Honesty payload always: `payroll_money=false`, `leave_balances_mutated=false`, `attendance_authority_mutated=false`, no templates/recurring/rotations/publishing/open shifts/PAM.

---

## API additions (staging-ready; not production-deployed)

- `GET /dashboard/posthire/shifts` — filters + Wave 3 enrich (availability, recon flags, terminal reminders, `wave3` posture)  
- `GET /dashboard/posthire/shifts/{id}/history` — versions + events  
- `POST /dashboard/posthire/shifts/{id}/cancel` — optional reason + concurrency token  
- `POST /dashboard/posthire/shifts/{id}/reschedule` — ack availability + reason  
- `POST /dashboard/posthire/shifts/reconciliation/{flag_id}/resolve`  
- Registry: `approve_availability` / `reject_availability`  

---

## Tests and evidence

| Suite | Result |
|---|---|
| Wave 3 UX smoke (`smoke-test-shifts-wave3-ux.py`) | **34 / 0** |
| Employees 360 freeze | **57 / 0** |
| Onboarding freeze | **54 / 0** |
| Attendance freeze | **26 / 0** |
| Leave freeze | **35 / 0** |
| Dashboard `tsc --noEmit` | **clean** |
| Wave 1 / Wave 2 full DB smokes | **not re-run on staging in this pack** (ambient DB URL conflict on VPS smoke path); prior Wave 2C closure remains **GO** |

Local qualify helper: `ops/qualify-shifts-wave3-staging.sh`

---

## Remaining blockers

1. Production deploy of Wave 3 sources not authorized  
2. Named HR/manager allowlists not populated for live use  
3. Full staging API/UI reconciliation against live staging DB still needed under a clean staging env binding  
4. Operator timers remain disabled (intentional)  
5. Real reminder sending remains off  
6. Templates / recurring / rotations / publishing / open shifts / PAM still out of scope  
7. Playwright visual regression against running staging dashboard not yet automated (mock screenshots captured)

---

## Bottom line

**Staging Wave 3 UX + controlled-readiness model: GO.**  
All production enablement scopes remain **NO-GO** until a separate authorized canary/deploy fills allowlists and proves live staging API/UI end-to-end without ambient DB conflicts.
