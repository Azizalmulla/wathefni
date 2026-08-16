# Setup Console — Persistent Operator Auth

**Status:** PASS  
**Evidence:** `ops/evidence/setup-console-operator-auth-20260808T040741Z` (17/0)  
**Scope:** Internal Wathefni operator login only. Does not create a new account system. Does not reopen Setup Console Phases 1–5.

## Verdict

Operators authenticate once with the existing allowlisted operator token + phone. The backend issues opaque **access + refresh** session tokens (same pattern as employee/dashboard sessions). The browser persists them in `localStorage` and auto-opens `/setup-console` while the session is valid.

## Token TTL / refresh behavior

| Token | TTL | Behavior |
|---|---|---|
| **Access** | **8 hours** | Authorizes Setup Console APIs (`Authorization: Bearer`) |
| **Refresh** | **30 days** | Silent rotate via `POST …/auth/refresh`; rotates both tokens |
| **Logout** | — | Revokes session server-side; clears browser storage |
| **Expired/revoked** | — | UI returns to operator login screen |

Silent refresh: API `401` → one in-flight refresh → retry. Failure clears local session.

Legacy operator-token Bearer auth remains for smoke/tooling only; the browser no longer stores the long-lived operator secret.

## Endpoints

- `POST /dashboard/superadmin/setup/auth/login`
- `POST /dashboard/superadmin/setup/auth/refresh`
- `POST /dashboard/superadmin/setup/auth/logout`
- `GET /dashboard/superadmin/setup/auth/session`

## Key files

- `wathefni-orchestrator/setup_console_operator_auth.py`
- `wathefni-orchestrator/app.py` (`superadmin_context` + auth routes)
- `apps/wathefni-dashboard/src/setup-console/session.ts`
- `apps/wathefni-dashboard/src/setup-console/api.ts`
- `apps/wathefni-dashboard/src/setup-console/SetupConsoleApp.tsx`
- Smoke: `wathefni-orchestrator/smoke-test-setup-console-operator-auth.py`

## Storage keys (browser)

- `wathefni_setup_access_token`
- `wathefni_setup_refresh_token`
- `wathefni_setup_operator_phone`
- `wathefni_setup_access_expires_at`

Legacy `sessionStorage` operator-token keys are cleared on load.
