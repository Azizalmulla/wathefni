# 20260806T222232Z — Auth Wave 2 Phase 1: locale restart must not wipe session

## Verdict

**partially proven** — defect fixed and on canary OTA; re-prove physical EN↔AR / AR↔EN on Aziz after restore

## Activation code (Aziz restore)

**`692269`** for +965 99338566 (pending invite; ~24h). After activate → Create PIN again (prior PIN was wiped by the bug).

## Root cause

On language restart the boot path set `skip_unlock_once`, then called `/app/me`.

If that call (or refresh) failed for any reason, it ran:

`blockForError(session_expired)` → **`clearLocalAuthMaterial()`** → cleared SecureStore tokens **and** PIN → “Session expired” → activation OTP.

So the restart was **treated as logout**. Tokens were not required to be missing first; a failed `/me` after reload was enough to wipe everything.

## Fix

1. Dual-write **locale_restart_preserve** marker (AsyncStorage + SecureStore) before reload.
2. While that marker is set, `blockForError` **must not** clear session/PIN.
3. After restart: try seamless `/me` resume; on failure → **PIN unlock** with sealed tokens (acceptable). Never OTP.
4. Clear preserve marker only after successful `signedIn` / unlock.
5. Short settle delay before `Updates.reloadAsync()`.

## Prove (automated)

| Check | Result |
|---|---|
| Unit | **37/37 PASS** |
| Capability / typecheck | GREEN / PASS |
| Wave 1 + Bank + onboarding live | **30/30 PASS** (Aziz 9548 · Talal 403) |

## OTA

Group `9dc373a9-b9ce-4a7a-9877-5023454ecdc3` · canary · `EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1`  
Prior: `173506a4-…`

## Physical re-test (Aziz)

1. Force-quit → load OTA  
2. Activate with **692269** → Create PIN  
3. Settings → العربية → confirm restart → remain signed in **or** PIN unlock (not OTP)  
4. Settings → English → same  
5. Refresh / Bank / onboarding / logout still OK  

## Explicit non-actions

No biometrics / Phase 2.
