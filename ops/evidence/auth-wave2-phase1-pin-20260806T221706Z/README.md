# 20260806T221706Z — Auth Wave 2 Phase 1 restamp: calm RTL language restart

## Verdict

**partially proven** (RTL “crash” fixed and on canary OTA; confirm once on device that the restart Alert appears and session resumes)

## Root cause

**Intentional process restart**, not a random crash or session wipe.

`setLocale` called `I18nManager.forceRTL` then **silent** `DevSettings.reload()` whenever EN↔AR flipped layout direction. On device that looked like the app closed/exited with no explanation.

## Fix

1. Confirm with Alert **before** applying RTL + reload (Cancel keeps current language).
2. Prefer `Updates.reloadAsync()`; fall back to `DevSettings.reload()`; else manual close/open copy.
3. While signed in, set one-shot `skip_unlock_once` so after restart: SecureStore session + PIN remain, **no OTP**, **no PIN re-prompt** for that intentional restart.
4. Copy clarifies you stay signed in.

## Prove

| Check | Result |
|---|---|
| Unit (PIN + RTL contract) | **34/34 PASS** |
| Typecheck / capability | **PASS / GREEN** |
| Wave 1 live Aziz+Talal | **30/30 PASS** |
| Aziz Bank ESS | last4 **9548** unchanged |
| Talal Bank ESS | **403** unchanged |
| Onboarding | unchanged |
| Physical EN↔AR Alert + resume | **owner confirm** after OTA |

## OTA

- Group `173506a4-e2ea-4a66-9d1e-d5b2860c426c`
- Branch `canary` · runtime `0.1.0`
- `EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1`
- Prior PIN group `b41cdbcf-9338-4073-a0be-af8ea9773c71`

## Rollback

Republish prior group `b41cdbcf-…` (or earlier) via `ROLLBACK.sh`.

## Physical check (Aziz)

1. Force-quit → open (load this OTA) → unlock if needed  
2. Settings → العربية → read Alert → Restart app  
3. App reopens signed in (no OTP, no PIN for this restart) · UI Arabic/RTL  
4. Settings → English → same · back to LTR  
5. Bank still verified · onboarding still complete  

## Explicit non-actions

No biometrics / Phase 2.
