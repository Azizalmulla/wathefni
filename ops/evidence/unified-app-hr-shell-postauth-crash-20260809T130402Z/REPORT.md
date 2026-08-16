# HR shell post-auth crash fix

**Stamp:** unified-app-hr-shell-postauth-crash-20260809T130402Z
**Prior OTA:** e046b071-f3ea-45a8-a515-f5499d1c156f
**Runtime:** 0.3.0 / channel canary

## Crash cause

After Work-email auth, `ModeRedirect` swapped `UnsignedEntry` → root Stack while URL was still `/`.
Expo Router focused Employee `app/(tabs)/_layout.tsx`, which calls `useAuth()`.
Employee `AuthProvider` is only under `EmployeeShell` — not mounted in HR mode.
HR providers live under `app/hr/_layout.tsx` and never reached.

**First failing module:** `app/(tabs)/_layout.tsx` → `useAuth must be used within AuthProvider`

Not a `/dashboard/mobile/me` payload issue (QA me has principal+scope; Home data smoke PASS).
Not an Expo 57→54 API incompatibility on the Home path.

## Fix

1. Guard HR mode: `Redirect` to `/hr` + splash until `segments[0]==='hr'`, then `<Slot />`
2. Work-email success calls `router.replace('/hr')` before `selectMode('hr')`
3. Removed unsafe `HrShellHost` Stack that registered Employee routes without providers

## OTA

| Field | Value |
| --- | --- |
| Update group | `e6ef7513-4a84-456d-8ab3-ba13cf133b8e` |
| iOS update | `019fe69f-5908-793e-824c-8feb842b657c` |
| Runtime / channel | `0.3.0` / `canary` |

## Gates

- verify-hr-shell-postauth-crash.py PASS
- verify-unified-principals.py 28/28
- verify-capability-foundation.py GREEN
- verify-push-register-storm.py GREEN
- Home data smoke (WATHEFNIQA /me + priorities) PASS

## Verdict

**PASS** (root cause + fix + OTA). Physical cold-start Work-email → Home eyeball after force-quit/reopen.

