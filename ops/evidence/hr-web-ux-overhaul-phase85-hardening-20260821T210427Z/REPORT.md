# HR Web UX overhaul — production hardening pass

**Stamp:** `20260821T210427Z`  
**Base source:** `1af9d5e7aa1ac85f8b317d0c35f58827810341a8` (Phase 8.5) plus uncommitted frontend hardening  
**Host:** `https://app.octo-hr.com/dashboard/`  
**Scope:** Minimum HR Web static bundle. Orchestrator was not restarted. Setup Console configuration, entitlements, allowlists, production data, and operator credentials were not changed. Palette/visual-system phase was not started.

---

## 1. Shifts auth-wall fix

**Cause:** `accessIssueFromError()` treated resource-level `permission_denied` as a session failure. Every workspace that called `onAccessIssue(accessIssueFromError(err))` unmounted the shell to Sign in.

Confirmed production path for the E2E owner (`shifts.read` granted, no `employees.read`):

`GET /dashboard/posthire/shifts` → 200  
`GET /dashboard/posthire/employee-org/units` → 403 `permission_denied`

That 403 used to drop `?page=shifts` to Sign in (“Your role does not include access to this workspace”).

**Fix:** only genuine session failures open the global auth wall:

- HTTP 401
- `dashboard_auth_failed`
- `dashboard_user_identity_required`
- `dashboard_company_required`
- `hr_user_not_allowed`
- `account_inactive`

`permission_denied`, `module_disabled`, and `action_forbidden` stay in-page. Permissions were not broadened.

**After deploy, same E2E identity:** Shifts workspace remains mounted. Org-units 403 renders the existing ResourceState (“Could not load this data” / Retry) inside Shifts. `authWall=false`, `orgErr=true`. Evidence: `screenshots/e2e-shifts/shifts-en-settled.png`.

---

## 2. Other incorrect global-auth classifications

The only code that mapped a **resource** 403 onto the Sign in surface was `permission_denied` in `apps/wathefni-dashboard/src/lib/access.ts`. That helper is the shared classifier for App bootstrap/summary errors and every `onAccessIssue` call site (Shifts, Employees, Leave, Payroll, Preboarding, Probation, Requisitions, Activity, and others).

No other session-ending mappings were found that should have been in-page. `module_disabled` / `action_forbidden` already returned `null`. Fail-closed composition is unchanged: missing grants still hide nav and still 403 the API.

---

## 3. Qualification of previously unreviewed surfaces

Authorized identity: WATHEFNI owner with canonical `employees.read` / `employees.manage` (112 bootstrap permissions). E2E owner was **not** used to fabricate Employees/360/Organization PASS.

| Surface | Identity | Deep link | Refresh | EN | AR/RTL | Result |
|---|---|---|---|---|---|---|
| Employees | owner | `?page=employees` stays | kept | directory 100/116 | `الموظفون`, RTL | **PASS** |
| Employee 360 | owner | `?page=employees&employee=WATHEFNI-96550252254` (Talal) | kept | profile + Next/Employment tabs | — | **PASS** |
| Organization | owner | `?page=workforce` stays | kept | unit hierarchy | `الهيكل التنظيمي` | **PASS** |
| Shifts after fix | owner | `?page=shifts` stays | kept | schedule + All teams | `الورديات` RTL | **PASS** |
| Shifts after fix | E2E (no `employees.read`) | stays in workspace | kept | in-page org-units error, roster still shown | — | **PASS** (fail-closed) |
| Preboarding | owner | URL `page=preboarding`, chrome remaps to Overview | Overview | not in nav | not in nav | **UNVERIFIED** |
| Probation | owner | URL `page=probation`, chrome remaps to Overview | Overview | not in nav | not in nav | **UNVERIFIED** |
| Requisitions | owner | URL `page=requisitions`, chrome remaps to Overview | Overview | not in nav | not in nav | **UNVERIFIED** |

Fail-closed API truth (not broadened):

| API | E2E | Owner |
|---|---|---|
| `/dashboard/posthire/employees` | 403 `permission_denied` | 200 |
| `/dashboard/posthire/employee-org/units` | 403 `permission_denied` | 200 |
| `/dashboard/posthire/shifts` | 200 | 200 |
| `/dashboard/posthire/preboarding` | 404 | 404 |
| `/dashboard/posthire/probation` | 404 | 404 |
| `/dashboard/prehire/requisitions` | 404 | 404 |

WATHEFNI `enabled_modules` does not include `preboarding`, `probation`, or `requisitions`. Production HTTP 404s match missing live routers/modules. Those three pages were not marked PASS.

Screenshots: `screenshots/owner/` and `screenshots/e2e-shifts/`.

---

## 4. Cold-start timings

Path measured on production: `page load → stored-session validation → shell first paint → first useful surface`.

“Loading saved dashboard access…” lasted because:

1. Neutral resolving surface waits on bootstrap (correct; chrome must not mount before session validation).
2. Non-overview pages then waited on **prehire summary + notifications** before mounting destination content (`dashboardLoaded`).
3. The loading chip stayed until Overview became interactive.

Safe changes (session validation unchanged):

- Clear the stored-session loading chip once bootstrap/`moduleState` exists.
- Mount non-overview pages as soon as workspace bootstrap is available.
- Overview still waits for summary + notifications.
- Protected chrome still does not mount before `sessionValidated`.

### `?page=shifts` (E2E identity, 3 cold runs)

| Milestone | Before (median ms) | After (median ms) |
|---|---|---|
| Resolving surface visible | 991 | 1016 |
| Session resolved / resolving gone | 1270 | 1246 |
| Shell first paint | 1280 | 1260 |
| First useful Shifts paint | 2440* | **1447** |
| Settled auth wall | **yes (Sign in)** | **no (Shifts kept)** |

\*Before “useful” was a false-positive: Shifts mounted, then org-units 403 kicked the global wall. Settled title was Sign in.

### `?page=overview` after (2 cold runs)

| Milestone | After (median ms) |
|---|---|
| Resolving visible | 1084 |
| Session resolved | 1302 |
| Shell first paint | 1312 |
| First useful Overview (greeting) | 1915 |
| Auth wall | no |

---

## 5. Tests

Dashboard vitest (targeted):

- `authAccessCopy.test.ts` — `permission_denied` is not a session auth issue
- `ShiftsOrgUnitsFilter.test.tsx` — org-units 403 stays in Shifts, does not call `onAccessIssue`
- `App.test.tsx` — resource `permission_denied` after a valid session does not open Sign in
- `dashboardShellContract.test.ts` — non-overview pages mount after bootstrap
- Phase 8.5 / shell / runtime explorer contracts

**47 passed** in those files. Orchestrator was not restarted; backend tests were not required.

---

## 6. Deployed frontend

| Item | Value |
|---|---|
| Live shell | `/dashboard/assets/dashboard-BJjRNyvW.js` |
| Post-hire chunk | `/dashboard/assets/PostHire-Ba0XUnap.js` |
| Access classifier chunk | `/dashboard/assets/access-tvKsLMTA.js` |
| CSS | `/dashboard/assets/reportClientError-TmM_Ste8.css` |
| Previous live shell | `dashboard-6-joZZvC.js` |
| Orchestrator | `MainPID=1872262`, `NRestarts=0`, `/health` 200, `/ready` 200 |

SHA-256 (live):

- `index.html` `b1c0ad01644b75c7db9a054a8bf0357a3383bf583e136d74cea42a59d9986aa3`
- `dashboard-BJjRNyvW.js` `3b5e38f9e51a996779467b88297960d607fa4dd72ba06b0b1aea4bd79b4cf4c2`
- `PostHire-Ba0XUnap.js` `d6884d05fca54b5c087d3937e150351c53047c1e25640e974d97088069ac315c`

Vite still emits `setup-console.html` hashed assets so the static graph stays consistent. No Setup product/config change.

### Rollback (frontend only, does not restart orchestrator)

```bash
ssh root@76.13.63.68 /opt/wathefni/backups/production-pre-hr-web-ux-phase85-hardening-20260821T210427Z/ROLLBACK.sh
```

Restores `dashboard-6-joZZvC.js`. Local copy: `rollback/ROLLBACK.sh`.

---

## 7. Remaining blockers before the final visual-system phase

1. **Preboarding, Probation, and Requisitions are not live on WATHEFNI production** — modules off, APIs 404, deep links fail-closed to Overview. Do not mark them PASS and do not enable modules/routers from this pass.
2. Hardening source is **uncommitted** on top of `1af9d5e7`.
3. Palette / visual-system phase has not started (intentional).
4. Unrelated pre-existing polish (not blockers for this pass): mixed English onboarding-status pills on the Arabic Employees table.

Stop here. Do not start the palette until the owner directs it.
