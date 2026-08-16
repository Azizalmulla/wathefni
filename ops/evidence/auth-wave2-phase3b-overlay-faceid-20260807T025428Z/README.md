# Auth Wave 2 Phase 3B — Face ID on proven auto-lock overlay

**Stamp:** `20260807T025428Z`  
**Verdict:** **partially proven** — unit green; awaiting physical Face ID matrix  
**Phase 4:** not started

## Architecture (unchanged)

- `LocalUnlockShell` timeout-only → `needsLocalUnlock`
- Full-screen `Modal` overlay (above native-stack)
- AuthGate / navigation / Wave 1 session / SecureStore unchanged
- No device-lock detector
- No `setStatus('locked')` from AppState

## Phase 3B change

Reuse cold-start `UnlockWithBiometricGate` inside the overlay:

1. Modal mounts → PIN UI visible
2. `onShow` → arm Face ID (`EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC=1` + biometric canary)
3. Gate waits for stable `AppState.active` (450ms + 250ms) — one prompt max
4. Face ID success → dismiss overlay only (still `signedIn`)
5. Cancel / fail / unavailable → PIN stays in the same overlay

## OTA

| Field | Value |
|---|---|
| Group | `68f5d59c-c243-4f50-8361-6f49d7a7c5db` |
| Runtime | `0.1.0` |
| Branch | `canary` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/68f5d59c-c243-4f50-8361-6f49d7a7c5db |
| Env | PIN=1 · BIOMETRIC=1 · AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=1 |
| Prior PIN-only | `f6364b3b-5b9f-4ec9-8c97-3ec22f560a89` |

## Unit

48/48 PASS (`smoke-test-auth-wave2-phase3-autolock-unit.py`)

## Physical matrix

1. Force-quit → pull OTA · Settings: enabled yes · Overlay Face ID yes · timeout 30000
2. &lt;30s away → no overlay
3. ≥40s → overlay → Face ID
4. Face ID success → overlay gone · still signed in
5. Cancel → PIN · wrong PIN calm error · correct PIN dismisses
6. Control Center → no lock
7. Rapid ×25 → no crash
8. No OTP / logout / nav reset · Bank ESS / onboarding unchanged · EN/AR RTL OK

## Rollback

`./ROLLBACK.sh` republishes `AUTO_LOCK_BIOMETRIC=0` (PIN-only overlay) or full `AUTO_LOCK=0`.
