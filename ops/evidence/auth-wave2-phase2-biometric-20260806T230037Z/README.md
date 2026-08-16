# 20260806T230037Z — Auth Wave 2 Phase 2: Face ID / Touch ID

## Verdict

**partially proven**

Native biometric capability is present and configured. JS wrapper + canary OTA are shipped. Automated contract/preserve checks PASS. Physical Face ID / Touch ID matrix on Aziz + Talal devices is still required to close as **fully proven**.

**Do not begin Phase 3.**

## Architecture

```
OTP (Wave 1) → Create PIN (Phase 1) → optional Face ID / Touch ID opt-in (Phase 2)
                                    ↓
Normal reopen → locked (tokens sealed)
             → if preference on + hardware enrolled → OS biometric prompt once
             → success → unseal session (same as PIN unlock; no backend auth)
             → cancel / fail / unavailable → PIN screen immediately
```

- Biometrics never call the backend.
- Preference + enrolled security level live in SecureStore (`wathefni.biometric.*`).
- PIN verifier remains canonical local fallback.
- Session wipe still only via Phase 1 `classifyAuthFailure` (definitive refresh reject / stale epoch / inactive / logout).
- Canary only: Aziz + Talal · master flag `EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=1` · requires PIN flag on.

## Native configuration

| Item | Status |
|---|---|
| `expo-local-authentication` ~14.0.1 | in binary |
| Plugin + `NSFaceIDUsageDescription` | configured |
| Android `USE_BIOMETRIC` / `USE_FINGERPRINT` | configured |
| Baked env PIN=1 BIOMETRIC=1 | production profile |

**No missing native capability** — do not JS-workaround around Face ID.

## Build IDs + install

| Platform | Build ID | Version | Artifact |
|---|---|---|---|
| iOS | `24c71b0a-6b09-4bb3-8d0d-c1e5dcbdc076` | 0.1.0 (10) | [IPA](https://expo.dev/artifacts/eas/DDTQ09q5JLEHb-vJQbIt3Ofu1Sv8hsDURql_BCvEYa4.ipa) · [dashboard](https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/24c71b0a-6b09-4bb3-8d0d-c1e5dcbdc076) |
| Android | `e7eefb47-abfb-4b0e-8387-bf02b75805cc` | 0.1.0 (3) | [APK](https://expo.dev/artifacts/eas/xPRMOdQJS0NI9InNttye4b7Yhrqy1Dfuk91fhi0JHqc.apk) · [dashboard](https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/e7eefb47-abfb-4b0e-8387-bf02b75805cc) |

**Install method:** install the internal native build → open app (pulls canary OTA) → activate with OTP if needed → create PIN → optional Face ID.

### Canary OTA (JS on runtime 0.1.0)

| Field | Value |
|---|---|
| Group | `02919c30-f663-4471-a8a6-058dbdf37054` |
| Channel | canary |
| Flags | PIN=1 · BIOMETRIC=1 |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/02919c30-f663-4471-a8a6-058dbdf37054 |

Old binaries **without** `expo-local-authentication` must not be used for Phase 2 — install the builds above.

## Files changed (Phase 2 surface)

- `src/auth/biometricPolicy.ts`
- `src/auth/biometricStorage.ts`
- `src/auth/biometricAuth.ts` (lazy native require; `disableDeviceFallback`)
- `src/auth/AuthProvider.tsx` (`needsBiometricOptIn`, unlock/opt-in/settings APIs)
- `src/features/pin/BiometricOptInView.tsx`
- `src/features/pin/UnlockWithBiometricGate.tsx`
- `app/_layout.tsx` · `app/settings.tsx`
- `src/features/remaining/RemainingViews.tsx`
- `src/i18n/en.json` · `ar.json`
- `app.json` · `eas.json` · `package.json`
- `wathefni-orchestrator/smoke-test-auth-wave2-phase2-biometric-unit.py`

Session-hardening (`authFailure.ts`) remains in force from Phase 1.

## Tests

| Gate | Result |
|---|---|
| Phase 2 biometric unit | **34/34 PASS** |
| Phase 1 PIN unit | **38/38 PASS** |
| Phase 1 session-hardening unit | **28/28 PASS** |
| Live preserve (Aziz+Talal `/me`, refresh, bank, onboarding, logout) | **10/10 PASS** (no new-device revoke in this stamp) |

## Live qualification (owner / canary devices)

After native install + OTA:

1. OTP → Create PIN → optional **Use Face ID?**  
2. Force-quit → Face ID auto → success opens app  
3. Cancel Face ID → PIN immediately  
4. Fail Face ID → PIN immediately  
5. Settings disable biometrics → PIN only  
6. Settings re-enable → works  
7. Remove/change device biometrics → graceful PIN  
8. Change PIN · logout · refresh  
9. EN↔AR / RTL  
10. Aziz Bank ESS · Talal bank 403 · onboarding unchanged  

### Aziz activation (for reinstall)

Phone `99338566` · code **`321898`** (one-time; supersedes prior unused codes)

## Rollback

1. OTA with `EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=0` → PIN-only (same native binary)  
2. Or republish prior hardening group `41239180-9b5a-4cc1-88f7-7a2f8d2ad7f8`  
3. Native rollback only if binary itself is bad (reinstall prior internal build)

## Remaining risks

- Physical Face ID / Touch ID not yet owner-stamped on Aziz/Talal devices  
- Native builds were compiled before final JS polish; OTA supplies current JS (runtime 0.1.0 match)  
- Face ID system permission string in the binary is the slightly older wording (harmless)

## Explicit non-actions

- Phase 3 idle/background lock — **not started**  
- No new backend auth routes  
- No OTP delivery changes  
