# HR-1 — Wathefni HR Operator Mobile Authentication and Capability Contract

**Status:** Backend implementation (staging proof required)  
**Date:** 2026-07-14  
**Scope:** Backend-only. No Wathefni HR frontend. No Employee App changes. No production enablement.

---

## 1. Authentication architecture

Wathefni HR uses a **dedicated operator-mobile channel**, separate from:

| Surface | Identity | Sessions | Routes |
| --- | --- | --- | --- |
| Employee App | `employees` | `employee_sessions` | `/app/auth/*`, `/app/*` |
| Browser dashboard | `dashboard_users` | `dashboard_user_sessions` (access only) | `/dashboard/auth/*` |
| **Wathefni HR mobile** | `dashboard_users` | `dashboard_operator_mobile_sessions` | `/dashboard/mobile/*` |
| Setup Console | platform env | N/A | internal / setup |

### Sign-in model

- Credentials: email + password + company_code (required under one-account-per-company).
- Backend resolves user ID, company, role, permissions, modules, manager scope, workspace capabilities.
- Client never supplies role, permissions, modules, or authoritative company claims.
- Generic `invalid_credentials` for unknown email/company/password combinations.
- Explicit codes for `operator_disabled`, `company_disabled`, `company_archived`, `rate_limited`.
- Rate limit: 8 failures / 15 minutes → 15-minute lock (`rate_limited`).
- MFA: extension stub returned (`mfa.enforced=false`); HR-1 does not weaken login to add MFA later.

### Authority

Every authenticated mobile request stamps:

```text
permission_authority = backend_current
permission_subject_user_id = authenticated user
permission_subject_company = session-bound company
```

Permissions and scope are recomputed on every `/dashboard/mobile/me` (and any future mobile endpoint) from live grants, role defaults, modules, lifecycle, and manager scopes.

---

## 2. Endpoint contract

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/dashboard/mobile/auth/login` | none | Issue access + refresh; return `me` bootstrap |
| `POST` | `/dashboard/mobile/auth/refresh` | refresh body | Rotate tokens; return new `me` |
| `POST` | `/dashboard/mobile/auth/logout` | access and/or refresh | Revoke presented tokens |
| `POST` | `/dashboard/mobile/auth/logout-all` | access | Revoke all mobile sessions for user |
| `GET` | `/dashboard/mobile/me` | access | Canonical capability bootstrap |

### Login request

```json
{ "email": "...", "password": "...", "company_code": "ACME" }
```

### Login / refresh response (shape)

```json
{
  "ok": true,
  "access_token": "<opaque>",
  "refresh_token": "<opaque>",
  "token_type": "bearer",
  "expires_at": "...",
  "refresh_expires_at": "...",
  "company_code": "ACME",
  "channel": "operator_mobile",
  "mfa": { "required": false, "enforced": false, "challenge_ready": false },
  "secure_store": { "...": "client contract" },
  "me": { "...": "same as GET /me" }
}
```

### Error shape

```json
{
  "detail": {
    "error": "<stable_code>",
    "message": "Access needs to be verified.",
    "channel": "operator_mobile"
  }
}
```

Stable codes: `invalid_credentials`, `session_expired`, `session_revoked`, `operator_disabled`, `company_disabled`, `company_archived`, `permission_authority_unavailable`, `module_disabled` (feature reason), `manager_scope_missing` / `manager_scope_conflict` (feature reasons), `feature_disabled`, `action_forbidden`, `rate_limited`, `employee_token_rejected`, `browser_session_rejected`, `legacy_authority_rejected`.

---

## 3. Session schema and lifecycle

Table: `dashboard_operator_mobile_sessions`

- Opaque access (45m) + refresh (30d)
- Only SHA-256 hashes stored
- Refresh rotation marks prior row `rotated`; reuse → `session_revoked`
- Logout / logout-all / operator disable / company disable|archive revoke sessions
- Session bound to exactly one `company_code`; `X-Company-Code` mismatch → `action_forbidden`
- Channel tag: `operator_mobile`

Login attempts: `dashboard_operator_mobile_login_attempts` (hashed company|email key).

### SecureStore client contract (documented only)

Keys: `wathefni.hr.access_token`, `wathefni.hr.refresh_token`, `wathefni.hr.company_code`, `wathefni.hr.access_expires_at`.

Rules: store opaque tokens only; never cache permissions as authority; cold-start always call `/me`; clear store on `session_expired` / `session_revoked`; never log tokens.

---

## 4. `/dashboard/mobile/me` typed response

```json
{
  "ok": true,
  "principal": {
    "user_id": "...",
    "company_code": "...",
    "display_name": "...",
    "email": "...",
    "role": "...",
    "role_label": "..."
  },
  "permission_authority": "backend_current",
  "account_state": "active",
  "company_state": "active",
  "workspaces": {
    "hr": { "enabled": true, "features": { "...": { "enabled": true, "actions": ["read"] } } },
    "recruiting": { "enabled": true, "features": { "...": {} } },
    "owner": { "enabled": false, "features": {}, "reason": "feature_disabled" }
  },
  "scope": {
    "restricted": true,
    "binding": "dashboard_user_id",
    "configured": true,
    "configuration_error": null
  },
  "mfa": {},
  "secure_store": {},
  "session": { "channel": "operator_mobile", "company_bound": true, "mobile_session_id": "..." }
}
```

No Setup Console capabilities. No employee ID lists in scope metadata.

---

## 5–7. Capability matrices

See `ops/HR1_CAPABILITY_MATRIX.md`.

---

## 8. Manager-scope integration

HR-0A precedence unchanged:

1. `dashboard_user_id` exclusive when present  
2. phone-only transitional when user-ID absent  
3. conflict → fail closed  
4. never merge sets  
5. `manager` never implies company-wide access  

`/me` returns safe metadata only. Record-level enforcement remains on data endpoints.

---

## 9. Mobile API compatibility

See `ops/HR1_MOBILE_API_COMPATIBILITY.md`.

---

## 10. Verification

- Local: `python3 smoke-test-hr1-operator-mobile.py`
- Staging: `ops/hr1-staging-verify.py` against `:8011`
- Rollback: `ops/HR1_SAFE_ROLLBACK.md`

---

## Boundaries (still in force)

No Wathefni HR frontend, no unified app, no employee auth reuse, no legacy `ai-recruiter/`, no Setup Console exposure, no production company config changes, no Brian canary, no EAS/TestFlight.
