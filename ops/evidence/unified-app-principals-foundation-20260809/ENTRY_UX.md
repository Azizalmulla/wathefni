# Unified entry UX (no startup principal chooser)

**Stamp:** `unified-entry-no-chooser-20260809`  
**Verdict:** **PASS**  
**Delivery:** OTA canary · runtime `0.3.0` · group `99b969d9-4089-49cb-80f3-2e05c203ffba`

## Auth-path audit (why this shape)

| Approach | Verdict |
| --- | --- |
| Probe email/phone against employee + operator tables | Rejected — identity linking / enumeration |
| Guess method from input shape | Rejected — ambiguous + wrong API risk |
| Startup “Continue as Employee/HR” | Rejected — exposes internal two-principal model |
| **One Wathefni screen · user picks sign-in method** | **Accepted** — phone OTP vs work email/password; sessions stay isolated |

## Resulting login / routing flow

1. **No sessions** → Wathefni sign-in with **Phone** | **Work email** methods (not principal labels).
2. **Phone** → existing employee OTP activate → Employee workspace (+ PIN/Face ID as today).
3. **Work email** → `/dashboard/mobile/auth/login` only → HR workspace.
4. **Employee session only** → Employee shell (automatic).
5. **HR session only** → HR shell (automatic).
6. **Both** → last preference, else silent Employee default; switch via Settings (post-auth).
7. **Returning signed-in** → unlock (Employee) then straight into resolved workspace — no chooser.

## Gates

- `verify-unified-principals.py` 23/23 PASS
- `tsc --noEmit` PASS
- capability foundation GREEN
- push-register-storm GREEN
