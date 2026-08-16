# Employee Mobile — Internal Build & Refinement Wave 1

**Stamp:** `20260805T021500Z`  
**App:** `apps/wathefni-employee-mobile`  
**Scope:** Talal canary · production API · no store submit · no allowlist expansion  
**Evidence:** `ops/evidence/employee-mobile-wave1-20260805T021500Z/`

## Fixes completed (client)

1. **Pull-to-refresh** on Home, Onboarding, Documents, Leave, Shifts, Attendance, Notifications — content stays mounted; full-screen loading only when no cached data.
2. **Foreground refetch** via `ForegroundQueryRefresh` (`refetchQueries({ type: 'active' })`) plus existing `/app/me` refresh.
3. **Logout / session clear** clears React Query (`queryClient.clear()`) and employee `me`/`profile` state.
4. **Duplicate-submit guards** on leave request (`submitLock`) and onboarding upload (`uploadLock`).
5. **Leave date picker** (`@react-native-community/datetimepicker`) with range validation; removed manual `YYYY-MM-DD` text entry.
6. **Onboarding due dates** shown when `due_date` is present on items.
7. **Rejected-state copy removed** from Home attention + onboarding guidance (unsupported vs compliance reject path).
8. **Home CTA de-dupe** — removed leave mini-action and duplicate onboarding/attendance quick actions; quick row keeps request-leave + documents only.
9. **EAS production profile** set to `distribution: "internal"`, Android `apk`, env → `https://api.wathefni.ai`, push off.
10. **Brand assets added** under `assets/` (icon, adaptive-icon, splash, notification-icon) — cream/ink design-system mark; wired in `app.json`.
11. Bundle ID preserved: `ai.wathefni.employee`.

## Owner actions still required (exact stop)

**Stopped at Expo authentication.** Signed builds were not produced.

Aziz must run locally (Wathefni Expo owner account — do not create a separate project):

```bash
cd apps/wathefni-employee-mobile
npx eas-cli login
# or: export EXPO_TOKEN=<owner token>
npx eas-cli whoami
npx eas-cli init   # links existing Wathefni project; replaces REPLACE_WITH_EAS_PROJECT_ID
```

Then continue:

```bash
npx eas-cli device:create          # register Talal test iPhones for internal iOS
npx eas-cli build --profile production --platform ios --non-interactive
npx eas-cli build --profile production --platform android --non-interactive
```

If prompted next:
- **Apple credentials / team** owning `ai.wathefni.employee`
- **Android keystore** (EAS-managed OK)
- Confirm generated cream/ink **icon/splash** match the approved brand kit (or replace PNGs in `assets/` before build)

Do **not** work around with a new Expo project or change the allowlist.

## Build status

| Platform | Identifier / status |
|---|---|
| **iOS** | **NOT BUILT** — blocked on `eas login` / `EXPO_TOKEN` |
| **Android** | **NOT BUILT** — same blocker |

Attempt evidence: `verify/eas-build-attempt.out` → `An Expo user account is required to proceed.`

## Tests

| Check | Result |
|---|---|
| `npm run typecheck` | **PASS** |
| `scripts/verify-capability-foundation.py` | **GREEN** |
| Talal API smoke (prior stamp) | **TALAL_EMPLOYEE_APP_CANARY_OK** (`20260805T014204Z`) — backend/allowlist unchanged this wave |
| Signed-build check | **FAIL** at Expo auth (expected until owner login) |

## Onboarding sync (unchanged authority)

Shared tables: `onboarding_items` + assignments. Wave 1 client refresh/PTR improves visibility of HR updates after foreground/pull. Uploads still write the same rows the web console reads. No shadow records; no cross-employee client keys.

## Remaining blockers

1. Owner Expo login + real `projectId` via `eas init` on existing Wathefni project  
2. Apple device registration / signing for internal iOS  
3. Physical install of production-profile builds  
4. Optional: replace provisional assets if marketing has a different approved pack  

## Rollback

Revert client files under `apps/wathefni-employee-mobile/` (Wave 1 diffs). Remove `assets/` if unwanted. Restore prior `eas.json` / `app.json` if needed. No backend/orchestrator deploy in this wave.

## GO / NO-GO

| Decision | Result |
|---|---|
| Live physical-device UI/UX review | **NO-GO** until installable iOS + Android production-internal builds exist |
| Continue Talal API canary | **GO** |
| Store submission | **NO-GO** |
| Allowlist / payroll / hiring expansion | **NO-GO** |
