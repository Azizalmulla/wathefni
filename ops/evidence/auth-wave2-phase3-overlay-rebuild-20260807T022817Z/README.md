# Auth Wave 2 Phase 3 — overlay rebuild (PIN-only)

## Verdict

**failed** (prior AppState→`setStatus('locked')` implementations crashed).  
**Replacement:** timeout-only **local unlock overlay** — PIN-only first. Face ID on overlay **not enabled**. Phase 4 not started.

## Rollback / disable

- Disabled auto-lock OTA: `3c51b707-15c4-4793-8cf5-f933a62f236f` (`EXPO_PUBLIC_LOCAL_AUTO_LOCK=0`)
- Production `eas.json` default: `EXPO_PUBLIC_LOCAL_AUTO_LOCK=0`

## New architecture

- Authenticated app / navigation / SecureStore / Wave 1 stay mounted
- `needsLocalUnlock` flag only (never `setStatus('locked'|'signedOut')` from AppState)
- Full-screen `LocalUnlockOverlay` above the app
- Privacy cover during inactive/background (not an auth lock)
- Timeout only: Immediate / 30s default / 1m / 5m / Never
- Device screen-lock detector **removed** from this phase
- Overlay PIN verify never wipes session / never OTP

## PIN-only prove OTA

- Group: `b9c90b4f-83c7-42fe-8145-d2c991324417`
- Dashboard: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/b9c90b4f-83c7-42fe-8145-d2c991324417
- `AUTO_LOCK=1` · `AUTO_LOCK_BIOMETRIC=0`

## Required physical matrix (PIN-only)

1. Force-quit → reopen → load this OTA; Settings Auto-lock = **30 seconds**
2. 5–15s away → no overlay
3. ≥40s away → **one PIN overlay** (no Face ID)
4. Control Center → no lock
5. Rapid background/resume **×25** → **no crash**
6. No OTP / session loss / nav reset / Bank / onboarding change

**If ×25 is not crash-free: stop, mark failed, do not enable Face ID.**

Only after PIN-only is green: enable overlay Face ID in a separate OTA.
