# Auth Wave 2 Phase 3B — Face ID arm fix

**Stamp:** `20260807T030944Z`  
**Verdict:** **partially proven** — unit green; physical Face ID retest pending  
**Phase 4:** not started

## Physical finding on `68f5d59c-…`

Overlay appeared after 40s · no crash / OTP / session loss · **PIN only, no Face ID**.

## Root cause

`UnlockWithBiometricGate` marked `attempted=true` **before** calling `authenticateAsync`. On overlay resume, a transient `AppState !== 'active'` (or cancelled effect) after that flag consumed the single attempt → permanent PIN fallback with no prompt.

Also: effect depended on `t` / callback identity; no AppState retry; preference could be wiped on transient `!usable`.

## Fix (architecture unchanged)

| Change | Detail |
|---|---|
| Rising-edge arm | Reset attempt token when `biometricFeatureOn` false→true (Modal ready) |
| Commit timing | Set `attempted` only when skipping definitively **or** right before `promptBiometricUnlock` |
| AppState retry | Re-schedule once when becoming `active` if not yet prompted |
| Modal | `onShow` + 150ms fallback · `presentationStyle="overFullScreen"` |
| Preference | Clear SecureStore preference only when enrollment clearly dropped |
| Settings diag | Bio feature armed · preference · bio gate reason (`armed` / `prompting` / `success` / `fallback_pin:…`) |

Timeout / navigation / Wave 1 / session SecureStore untouched.

## OTA

| Field | Value |
|---|---|
| Group | `9aa012bf-dec5-4c54-9bf0-db525484eeca` |
| Prior | `68f5d59c-c243-4f50-8361-6f49d7a7c5db` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/9aa012bf-dec5-4c54-9bf0-db525484eeca |
| Env | AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=1 |

## Unit

56/56 PASS

## Retest

1. Force-quit → pull OTA · Settings: Overlay Face ID **yes** · Bio preference **yes**
2. ≥40s → overlay → Bio gate should reach `prompting` → **one Face ID**
3. Success → dismiss · Cancel → PIN · wrong/correct PIN
4. After a lock cycle, Settings Bio gate shows `success` or `fallback_pin:cancel`
5. ×25 no crash · no OTP

Phase 3B remains **partially proven** until this matrix is green. Do not start Phase 4.
