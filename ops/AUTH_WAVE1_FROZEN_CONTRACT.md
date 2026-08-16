# Auth Wave 1 — Frozen employee login contract

**Status:** FROZEN (Auth Wave 2 Phase 0)  
**Stamp:** `ops/evidence/auth-wave1-freeze-20260806T214259Z/`  
**Authority:** this document + live routes in `wathefni-orchestrator/app.py` + mobile `src/auth/*`  
**Rule:** Phase 1+ may **gate** local access to an existing session. They must **not** replace, duplicate, or weaken this contract.

---

## 1. Single canonical flow

```text
HR invite (OTP) → employee enters phone + code
  → POST /app/auth/activate
  → opaque access + refresh tokens
  → mobile stores tokens in SecureStore (WHEN_UNLOCKED)
  → all /app/* calls use Bearer access token
  → on 401, mobile POST /app/auth/refresh then retry
  → logout: POST /app/auth/logout + clear SecureStore
```

Identity for every `/app/*` request comes **only** from the server session resolved from the bearer token. Clients never supply `employee_key` as auth.

### Backend routes (frozen)

| Route | Role |
|---|---|
| `POST /app/auth/activate` | Redeem pending invite → mint session; revoke prior active sessions (`reactivated_via_invite`) |
| `POST /app/auth/request-code` | Re-issue only if a prior invite exists; always generic OK; 60s cooldown |
| `POST /app/auth/refresh` | Rotate access+refresh hashes in place; re-check company/employee eligibility |
| `POST /app/auth/logout` | Revoke presented access token (`revoked_reason=logout`) |
| `GET /app/me` | Session identity + capabilities (post-auth) |

### Mobile (frozen)

| Piece | Path | Behavior |
|---|---|---|
| SecureStore session | `src/auth/session.ts` | Keys `wathefni.session.token` / `wathefni.session.refresh` · `WHEN_UNLOCKED` only |
| Auth authority | `src/auth/AuthProvider.tsx` | activate / requestCode / signOut / refresh-on-401 / clear on inactive |
| No PIN / biometrics | — | Phase 1 may wrap SecureStore access with a **local** PIN gate only (see `ops/evidence/auth-wave2-phase1-pin-20260806T215837Z/`). Biometrics remain Phase 2. |

---

## 2. Recorded constants (do not change casually)

| Constant | Value | Meaning |
|---|---|---|
| `_EMPLOYEE_APP_INVITE_TTL_HOURS` | **24** | Pending OTP invite lifetime |
| `_EMPLOYEE_APP_MAX_CODE_ATTEMPTS` | **5** | Wrong codes → invite `locked` → HTTP **429** `too_many_attempts` |
| `_EMPLOYEE_APP_CODE_RESEND_COOLDOWN_SECONDS` | **60** | `request-code` silent no-op inside window |
| `_EMPLOYEE_APP_SESSION_TTL_DAYS` | **7** | Access token expiry |
| `_EMPLOYEE_APP_REFRESH_TTL_DAYS` | **180** | Refresh token expiry |

Tokens are opaque `token_urlsafe` secrets. Server stores **SHA-256 hashes only** (`token_hash` / `refresh_hash`). OTP codes are hashed with company+phone+code; plaintext code is never persisted.

---

## 3. Failure, retry, revocation matrix

| Case | HTTP | Error / reason | Client expectation |
|---|---|---|---|
| Wrong/missing OTP, unknown phone, ineligible | **401** | `app_activation_failed` (generic) | Calm “ask HR for a new code” |
| ≥5 wrong OTP attempts | **429** | `too_many_attempts` | Ask HR for new invite |
| Bad/expired access; bad refresh | **401** | `app_auth_failed` | Sign in again (activate) |
| ESS identity epoch mismatch | **401** | `stale_session_epoch` | Sign in again |
| Company disabled / module off / inactive employment | **403** | `company_*` / `employee_app_not_enabled_for_company` / `account_inactive` | Blocked state |
| App globally disabled | **503** | `employee_app_disabled` | Unavailable |
| `request-code` any outcome | **200** | generic OK message | Never discloses registration |
| Logout (even unknown token) | **200** | `{ok: true}` | Local clear is authoritative |
| New-device / re-activate | — | prior sessions `reactivated_via_invite` | Old device tokens die |
| Offboard / employment inactive | — | `revoke_employee_app_access` | All sessions + push dead |

Refresh rotates **both** secrets; the previous access token must not resolve after rotation.

---

## 4. Kuwait phone aliases (frozen)

`employee_phone_alias_list` treats local **8-digit** and **965XXXXXXXX** as one identity. Activate matches pending invites with `phone = ANY(aliases)`. Code hash uses the **invite’s stored phone**, not the raw request form.

---

## 5. `session_epoch` (frozen kill switch)

On session create, stamp `employee_sessions.ess_session_epoch` from active `employee_ess_identity_bindings.session_epoch` when present. On `/app/*` auth, if stamped epoch ≠ current binding epoch → revoke with `ess_session_epoch_stale` and deny. This is the **server** hard kill for ESS identity changes. Local PIN/biometrics never replace it.

---

## 6. Phase 1+ PIN rule (binding)

**PIN unlocks the existing local SecureStore session only.**

- PIN is **not** a server credential and is never sent to `/app/auth/*`.
- PIN must not mint, extend, or replace access/refresh tokens.
- Lost PIN / wiped install → Wave 1 OTP activate again (no local recovery of tokens).
- Biometrics (later) wrap the same local gate; OTP remains the only first-login server auth.

---

## 7. UX rules for future phases (do not implement in Phase 0)

| Moment | UX |
|---|---|
| First login | OTP once → create PIN |
| Normal return | Open app → PIN → app opens |
| Later (Phase 2+) | Face ID first, PIN fallback |
| Always | No repeated setup screens, technical copy, unnecessary choices, or extra auth prompts |

---

## 8. Explicit Phase 0 non-actions

Do **not** add: PIN, biometrics, idle lock, recovery redesign, device trust, `expo-local-authentication`, or new server auth routes.
