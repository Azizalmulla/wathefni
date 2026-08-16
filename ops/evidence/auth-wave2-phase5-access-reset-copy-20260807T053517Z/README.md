# Auth Wave 2 Phase 5 — Basic device security (final stamp)

**Stamp:** `20260807T0535Z` (access-reset copy close)  
**Evidence:** `ops/evidence/auth-wave2-phase5-access-reset-copy-20260807T053517Z` / prior `auth-wave2-phase5-device-security-20260807T045603Z`  
**Verdict:** **fully proven**  
**Do not begin Phase 6.**

## Auth reason confirmation

Physical HR revoke showed “Session expired” because:

1. Session row was `status=revoked`, `revoked_reason=hr_revoked`
2. `/app/*` resolved historical token → generic `app_auth_failed`
3. Client classifier wiped → `accessState=session_expired`

That path was caused by HR revocation (not network/5xx).

## Copy fix

| Case | Server code | Employee UI |
|---|---|---|
| HR revoke / new-device replacement | `app_access_revoked` | **Your app access was reset** / Sign in again with a new activation code. |
| Natural expiry / ambiguous dead session | `app_auth_failed` after refresh fail | Existing session-expired copy |
| Offline / 5xx | soft / transient | Unchanged — no wipe, no reset copy |

Security unchanged: token clear, PIN/Face ID local reset on wipe, `session_epoch`, refresh invalidation.

## Live re-prove (revoke → activation → re-invite)

```
historical = revoked / hr_revoked
me_after_error = app_access_revoked
refresh_dead_ok
reinvite_activate_ok
```

## Canary OTA

`7f1731ad-d482-4b7a-a2fc-502fa1a987c8`

## Activation (Aziz, after re-prove)

Phone `99338566` · code issued in live log (one-time; may already be consumed by the automated activate step).

## Unit

Phase 5 unit **38/38**
