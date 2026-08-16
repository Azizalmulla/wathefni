# Auth Wave 2 Phase 3 — PIN overlay activation fix + canary diagnostics

**Stamp:** `20260807T024253Z`  
**Verdict:** not proven — awaiting physical device retest  
**Phase 4:** not started · overlay Face ID still off

## Why b9c90b4f failed the physical PIN test

Owner report: &lt;30s away OK · ≥30s away also returned with **no PIN overlay**.

Likely causes (not mutually exclusive):

1. **Native-stack z-order** — `LocalUnlockOverlay` was an absolute `View` sibling of `AuthGate`. On iOS, native-stack screens can paint **above** sibling Views, so `needsLocalUnlock` could flip true while the PIN UI stayed invisible.
2. **Console diagnostics stripped** — production babel `transform-remove-console` removed all `[autolock-overlay]` logs, so device could not show OTA/flag/elapsed/decision.
3. **Possible stale OTA / master / timeout / key** — without a Settings panel, those could not be confirmed on device.

## Fix in this OTA

| Change | Detail |
|---|---|
| Overlay host | `Modal` fullScreen (above native-stack) — PIN-only, no Face ID |
| Settings canary panel | Update ID · build marker · enabled · timeout · last away · last elapsed · last decision · overlay active |
| Build marker | `al-overlay-v3:${EXPO_PUBLIC_LOCAL_AUTO_LOCK}` → expect `al-overlay-v3:1` |
| Master | `EXPO_PUBLIC_LOCAL_AUTO_LOCK=1` · `EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC=0` |
| Employee key | `me.employee.employee_key \|\| me.employee_key \|\| profile.employee_key` |

## OTA

| Field | Value |
|---|---|
| Group | `f6364b3b-5b9f-4ec9-8c97-3ec22f560a89` |
| Runtime | `0.1.0` |
| Branch | `canary` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/f6364b3b-5b9f-4ec9-8c97-3ec22f560a89 |
| Prior prove OTA | `b9c90b4f-83c7-42fe-8145-d2c991324417` |
| Disable OTA | `3c51b707-15c4-4793-8cf5-f933a62f236f` |

## Unit

39/39 PASS (`smoke-test-auth-wave2-phase3-autolock-unit.py`)

## Physical retest (required)

1. Force-quit → reopen → pull OTA.
2. **Settings → Auto-lock canary** must show:
   - Build marker `al-overlay-v3:1`
   - Update ID matching this group (prefix ok)
   - Auto-lock enabled: **yes**
   - Timeout: **30000 ms** (set 30 seconds if not)
3. Away **5–15s** → decision `none` · no overlay.
4. Away **≥40s** → decision `timeout` · **PIN Modal visible** · unlock with PIN · session/nav unchanged.
5. Control Center only → decision `none` / no lock.
6. Rapid background/resume **×25** → no crash.
7. No OTP / session wipe.

If Settings shows `enabled: no (master=0 …)` → OTA env wrong; stop.  
If decision=`timeout` but no Modal → still a mount bug; stop.  
If ×25 crashes → mark failed; do **not** enable Face ID.
