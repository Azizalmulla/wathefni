# 20260806T225101Z — Auth Wave 2 Phase 1 hardening: stop random session loss

## Verdict

**partially proven** — classifier + AuthProvider hardening shipped to canary OTA; Wave 1 live API 30/30 PASS; owner device matrix still required (force-quit / offline / language / PIN) before **fully proven**.

Biometrics (Phase 2) is **not** enabled on this OTA (`EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=0`). Do not treat the in-flight native biometric builds as the install path for this fix.

## Root causes

1. **`blockForError(..., force=true)` wiped on `app_auth_failed`** whenever `/app/me` or refresh surfaced that code — including ambiguous first failures and paths that had not proven refresh was dead.
2. **Incidental API `network_error` called `blockForError`** and flipped the whole app to the access shell (felt like logout even when tokens remained).
3. **`refreshMe` with empty in-memory `sessionRef`** could take the signed-out path instead of reloading SecureStore.
4. **Locale / RTL restart** could still present “Session expired” copy even when preserve markers blocked wipe — encouraging Sign In → real logout.
5. **`stale_session_epoch` was not mapped** as a definitive wipe reason (fell through as unknown).

## Fix

Central classifier: `src/auth/authFailure.ts` → `classifyAuthFailure`.

| Signal | Wipe SecureStore + PIN? | App shell |
|---|---|---|
| Expired access → refresh OK | No | Continue |
| Network / 5xx / ambiguous | No | Soft offline/unknown + Retry (boot/refresh/unlock only) |
| API network blip on a feature call | No | No full-app takeover |
| Refresh rejected (`app_auth_failed` after refresh attempt) | **Yes** | Sign in again |
| `stale_session_epoch` | **Yes** | Sign in again |
| `account_inactive` | **Yes** | Account ended |
| Locale preserve marker | Never wipe | Soft retry / PIN lock |

Logs `[auth] decision …` and `[auth] clearing local session material reason=…` before any wipe.

## OTA (install this first)

| Field | Value |
|---|---|
| Group | `41239180-9b5a-4cc1-88f7-7a2f8d2ad7f8` |
| Channel | canary |
| Runtime | 0.1.0 |
| PIN flag | `1` |
| Biometric flag | `0` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/41239180-9b5a-4cc1-88f7-7a2f8d2ad7f8 |

Force-quit → reopen to pull update.

## Prove (automated)

| Check | Result |
|---|---|
| Hardening unit | **28/28 PASS** |
| Phase 1 PIN unit | **38/38 PASS** |
| Wave 1 live Aziz+Talal | **30/30 PASS** (activate / me / refresh / logout / new-device revoke / Bank+onboarding snapshots) |

## Device matrix (owner — canary Aziz/Talal)

After OTA:

1. Force-quit → open → still in (or PIN unlock) — **not** OTP from a soft failure  
2. Airplane mode → open / pull → offline + Retry; tokens kept  
3. Language EN↔AR → stay signed in  
4. PIN unlock still works  
5. Logout → OTP required  
6. After server revoke / dead refresh → calm “Sign in again” + OTP  

Note: the Wave 1 live prove script rotates/revokes server sessions then mints a **server-side** restored session. Phones that still hold pre-prove tokens may correctly require OTP once after this prove — that is definitive revoke, not a regression.

## Files

- `apps/wathefni-employee-mobile/src/auth/authFailure.ts` (new)
- `apps/wathefni-employee-mobile/src/auth/AuthProvider.tsx`
- `apps/wathefni-employee-mobile/src/capabilities.ts`
- `apps/wathefni-employee-mobile/src/api/errors.ts`
- `apps/wathefni-employee-mobile/src/components/AccessStates.tsx`
- `apps/wathefni-employee-mobile/src/i18n/en.json` · `ar.json`
- `apps/wathefni-employee-mobile/src/auth/biometricAuth.ts` (lazy-require; flag off on this OTA)
- `wathefni-orchestrator/smoke-test-auth-wave2-phase1-session-hardening-unit.py`

## Rollback

Republish prior canary group `7a0d99fc-0e0e-44be-8b9f-5cc4ad9c8b20`, or set wipe behavior back only via OTA revert. No native rebuild required for this hardening.

## Remaining risks

- Owner device matrix not yet stamped on physical phones  
- Live prove may have invalidated on-device tokens (OTP once)  
- Phase 2 native builds exist separately; do not enable biometrics until this hardening is device-confirmed  

## Explicit non-actions

- Do **not** begin Phase 3 (idle lock)  
- Do **not** enable biometrics on canary until Phase 1 hardening is device-OK  
