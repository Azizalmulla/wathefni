# 20260806T232633Z — Auth Wave 2 Phase 3: Smart Auto-Lock

## Verdict

**partially proven**

Timeout-based auto-lock + settings + EN/AR are shipped to canary OTA. Unit/contract matrix PASS.
Device-lock path is in new native binaries (`expo-screen-detector`, Expo 51–compatible vendored module).
iOS + Android native builds FINISHED. Physical device matrix (Aziz/Talal) is still open — do **not** begin Phase 4.

## Architecture

```
signedIn + AppState inactive/background
  → record awayStartedAt
  → probe isDeviceScreenLocked() (native when present; else false)

AppState active
  → if deviceWasLocked → seal session → status=locked (Face ID/PIN)
  → else if elapsedMs >= timeoutMs → seal session → status=locked
  → else stay unlocked + soft refreshMe()

timeoutMs options: 0 | 30000 (default) | 60000 | 300000 | null (Never)
Never: time-based lock off; device-lock still locks when native probe works.
Auto-lock never clears SecureStore session / PIN / Wave 1 tokens.
Unlock reuses Phase 1–2 biometric/PIN gate only — no OTP unless Wave 1 session truly invalid.
```

Canary only: Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`  
Master flag: `EXPO_PUBLIC_LOCAL_AUTO_LOCK` (inherits PIN master when unset; production eas env = `1`)  
Company may hide Never via `EXPO_PUBLIC_LOCAL_AUTO_LOCK_ALLOW_NEVER=0`

## Timeout implementation

- Policy: `src/auth/autoLockPolicy.ts` (`shouldAutoLockOnResume`)
- Persist: SecureStore `wathefni.autolock.timeout_ms` (`autoLockStorage.ts`)
- Device probe: `src/auth/deviceLock.ts` → lazy `require('expo-screen-detector')`
- Wiring: `AuthProvider` AppState listener seals `sessionRef` → `sealedSessionRef`, `setStatus('locked')`
- Settings: `SettingsView` list (Immediate / 30s / 1m / 5m / Never)

## Files changed

- `src/auth/autoLockPolicy.ts` (new)
- `src/auth/autoLockStorage.ts` (new)
- `src/auth/deviceLock.ts` (new)
- `src/auth/AuthProvider.tsx`
- `app/settings.tsx`
- `src/features/remaining/RemainingViews.tsx`
- `src/i18n/en.json` · `ar.json`
- `eas.json` (`EXPO_PUBLIC_LOCAL_AUTO_LOCK=1`)
- `package.json` + `modules/wathefni-screen-detector/` (Expo 51 gradle fix)
- `wathefni-orchestrator/smoke-test-auth-wave2-phase3-autolock-unit.py`

## Tests

`python3 wathefni-orchestrator/smoke-test-auth-wave2-phase3-autolock-unit.py` → **39 passed, 0 failed**  
(`prove/unit.txt`)

Behavioral: bg &lt;30s stay · ≥30s lock · immediate · 1m/5m · never · device-lock overrides.

## Live qualification (owner / canary device)

On OTA `fda08e77-…` (timeout path works on existing biometric binary):

1. Background &lt;30s → no unlock prompt
2. Background ≥30s → Face ID/PIN
3. Face ID cancel → PIN
4. Face ID success → app opens
5. Settings change timeout; EN/AR + RTL
6. No OTP / no session loss / Bank ESS + onboarding still load

On **new native** build (screen detector):

7. Lock phone → unlock phone → Face ID/PIN even if away &lt; timeout

## Evidence

- OTA group: `fda08e77-f7a1-464c-8596-00cc4e4c6461`
- Dashboard: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/fda08e77-f7a1-464c-8596-00cc4e4c6461
- iOS native: `7b3dc831-287d-4b0a-8676-eed08838ac6c` (build 11)  
  IPA: https://expo.dev/artifacts/eas/YmqXdIRKc80wPUP75yAbM3FNxIFrRfietpp6NAdacp4.ipa
- Android native: `92869701-685b-4975-823b-52c1bc4109d9` (versionCode 5)  
  APK: https://expo.dev/artifacts/eas/P-_S_7SzFKJ2-2O9c85mYTIdrI2Uecv9NDT4Pyy1gnE.apk  
  (prior failed `b3c3ba7e-…` — Expo 52 gradle on Expo 51; fixed via vendored module)

## Rollback

`ROLLBACK.sh` — republish prior group `3d4d10ca-1852-473b-b912-a32de97d5245`  
Prior biometric natives remain installable if needed.

## Remaining risks

- Physical matrix not owner-closed
- Existing biometric-only binary: device-lock probe returns false (timeout-only) until install of build 11 / vc 5
- iOS `isProtectedDataAvailable` / Android `KeyguardManager` semantics under brief Control Center / notification shade should be watched on device

## Out of scope (stopped)

Phase 4 recovery · device trust · new backend auth · OTP changes · bank step-up
