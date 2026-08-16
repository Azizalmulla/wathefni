# 20260806T223109Z — Auth Wave 2 Phase 1: seamless EN↔AR (no Alert)

## Verdict

**partially proven** — seamless language switch shipped to canary; owner to confirm EN→AR→EN once on device (no Alert, session preserved), then Phase 1 can close as fully proven.

## UX change

Removed the restart confirmation Alert.

Tap language → soft cover → persist locale + preserve-auth markers → silent `Updates.reloadAsync()` → remount in new language still signed in (no OTP). PIN unlock only if `/me` fails after reload (existing safety).

## Preserve (unchanged)

- Wave 1 SecureStore session  
- Local PIN material  
- Locale-restart preserve marker (no session wipe)  
- No biometrics / Phase 2  

## Prove (automated)

| Check | Result |
|---|---|
| Unit | **37/37 PASS** (incl. no Alert · cover · preserve-auth) |
| Capability / typecheck | GREEN / PASS |
| Wave 1 + Bank + onboarding | **30/30 PASS** |

## OTA

Group `7a0d99fc-0e0e-44be-8b9f-5cc4ad9c8b20` · canary · PIN flag on  
Prior: `9dc373a9-…`

## Physical close-out (Aziz)

1. Force-quit → open (load this OTA)  
2. Settings → العربية — **no dialog**; brief cover → Arabic UI; still signed in  
3. Settings → English — same; still signed in  
4. Bank / onboarding unchanged; logout still works  

Reply **EN↔AR OK** after that and Phase 1 can be stamped **fully proven**.

## Explicit non-actions

Phase 2 / biometrics not started.
