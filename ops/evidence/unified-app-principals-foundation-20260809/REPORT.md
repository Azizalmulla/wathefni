# Unified Wathefni app — dual-principal foundation

**Stamp:** `unified-app-principals-foundation-20260809`  
**Verdict:** **PASS** (foundation + native canary built)  
**App version:** `0.3.0` · buildNumber `23` · channel `canary`  
**Bundle:** `ai.wathefni.employee` only  
**Runtime:** new (`runtimeVersion` policy = `appVersion` → `0.3.0`)

## iOS canary install

https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/fa70005b-6eb4-4481-860f-9c4013d92a93

Install on the provisioned iPhone, then open Wathefni (same icon).

### Open HR shell

1. Cold start with no sessions → **Continue as HR**
2. Company code: `WATHEFNIQA`
3. Email: `qa@wathefni.invalid`
4. Password: `WathefniQA2026!`

Or: Employee activate first → Settings → **Switch to HR** → sign in with the QA operator (or your WATHEFNI owner).

## SDK alignment decision

**Keep Employee on Expo SDK 54. Backport HR UI into that binary.**

Why: lowest regression risk to the frozen Employee App (PIN/Face ID, push, OTA,
qualified canary). HR was Expo 57 but never shipped; upgrading Employee → 57
would blast every Employee surface. HR screens were ported as `src/hr` onto SDK 54.

## Integration changes

1. Freeze amended: `docs/ADMIN_MOBILE_SCOPE_FREEZE.md` → one public binary / two principals
2. Dual SecureStore: `wathefni.session.*` (employee) · `wathefni.hr.*` (operator, THIS_DEVICE_ONLY)
3. Mode router: employee-only / HR-only / both→switcher / neither→entry
4. HR workspace at `/hr/*` (no collision with Employee routes)
5. HR API remain allowlisted `/dashboard/mobile/*` — not on `/app/me`
6. No auto-link by email/phone
7. HR push **not** on `/app/push`
8. `ai.wathefni.hr` ship-retired (`SHIP_RETIRED.md`)
9. Flag: `EXPO_PUBLIC_HR_WORKSPACE_ENABLED=1` on production canary profile

## Dual sessions

| Principal | Auth | Authority | Push |
| --- | --- | --- | --- |
| Employee | `/app/auth/*` + PIN/biometric | `/app/me` | `/app/push/*` |
| HR | `/dashboard/mobile/auth/*` | `/dashboard/mobile/me` | none (phase 1) |

Preference `wathefni.principal.mode` is AsyncStorage UX only — never authority.

## Employee regression

| Gate | Result |
| --- | --- |
| `tsc --noEmit` | PASS |
| `verify-capability-foundation.py` | GREEN |
| `verify-push-register-storm.py` | GREEN |
| `verify-unified-principals.py` | 18/18 PASS |
| EAS iOS production canary | finished (`fa70005b-…`) |

## Rollback

1. Rebuild/OTA with `EXPO_PUBLIC_HR_WORKSPACE_ENABLED=0` → Employee-only shell
2. Or reinstall prior `0.2.0` canary IPA
3. Clear HR keys independently without wiping employee session

## Stop line

Owner can install this IPA and physically open the HR shell inside the same
Wathefni app. No HR redesign in this wave.
