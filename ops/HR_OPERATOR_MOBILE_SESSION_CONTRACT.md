# HR Operator Mobile — Production Session Contract

**Status:** ACTIVE  
**Authority:** `apps/wathefni-employee-mobile/src/hr/auth/*` + `wathefni-orchestrator/operator_mobile.py`  
**Proofs:** `ops/mobile-e2e/verify-hr-operator-session-contract.mjs` · `ops/mobile-e2e/verify-hr-operator-session-live.py`

## Product expectation

An authorized HR operator logs in once on a trusted device and stays signed in until:

1. They explicitly sign out (this device or all devices), or
2. Their operator access is revoked / account disabled, or
3. The company workspace is disabled or archived, or
4. A genuine security event requires reauthentication (refresh expired, refresh replay with no newer local session, logout-all).

The following must be **invisible** to the operator:

- Access-token expiry (45 minutes)
- Refresh-token rotation
- App restart / process kill
- OTA JS reload
- Foreground / background transitions
- Local PIN / Face ID lock (device lock ≠ logout)
- Normal backend deploys / orchestrator restarts

## Client contract

| Rule | Implementation |
|---|---|
| Global single-flight refresh | Module-level `inFlight` in `sessionCoordinator.ts` (survives AuthProvider remount) |
| Concurrent 401s share one refresh | All `rotate()` / `request()` paths call `rotateOperatorSession` |
| Atomic token persistence | Single SecureStore blob `wathefni.hr.session.v1` |
| Retry with new access | `request()` rotates once then retries with rotated access |
| `session_revoked` after sibling rotation | Reload SecureStore / memory; adopt newer session; do not clear |
| Clear only when no newer session | `clearOperatorAuthIfNoNewerSession` |
| HR ≠ Employee namespaces | HR `wathefni.hr.*` vs Employee `wathefni.session.*` |
| PIN / Face ID | Seals in-memory API use only; SecureStore retained |

## Server contract (unchanged security posture)

| Control | Behavior |
|---|---|
| Opaque tokens | `token_urlsafe` secrets; DB stores SHA-256 hashes only |
| Access TTL | **45 minutes** — authority recompute cadence |
| Refresh TTL | **90 days** — trusted-device continuity (sliding on each successful refresh) |
| Refresh rotation | Old refresh → `status=rotated`; replay → `401 session_revoked` |
| Refresh eligibility | Re-check operator active + company lifecycle every refresh |
| Explicit logout | Revokes presented session |
| Logout-all | Revokes all active sessions for the user |
| Operator / company termination | Sessions revoked; client must surface blocked state |

Replay protection is **not** weakened. The client fix prevents presenting a stale refresh after a successful local rotation.

## Trusted-device TTL policy (decision)

| Option | Verdict |
|---|---|
| Keep 30-day refresh | Rejected — forces monthly password re-entry; violates “login once” |
| Blind 180-day like Employee | Rejected for HR — higher privilege surface |
| **90-day sliding refresh + 45m access** | **Selected** |
| Idle absolute max shorter than refresh | Optional future: revoke if `last_seen_at` older than 30d unused |

Security remains: short access, rotation + replay fail-closed, server-side eligibility on every refresh, immediate revoke on logout/disable/company lifecycle.

## Qualification matrix

| Scenario | Expected | Result |
|---|---|---|
| 10 simultaneous requests after access expiry | Exactly one refresh; zero logout | **PASS** (client) |
| Cold boot / remount during expiry | One refresh; enter session | **PASS** (client) |
| Foreground / unlock during expiry | One refresh; stay signed in | **PASS** (client) |
| OTA reload | SecureStore restore; invisible refresh if needed | **PASS** (client) |
| Backend deploy / restart | DB-backed session survives; `/me` works | **PASS** (live) |
| App killed / reopened days later | Refresh within 90d restores session | **PASS** (live TTL policy) |
| Explicit revoke / logout | Hard logout | **PASS** (live) |
| Account / company termination | Hard logout / blocked | **PASS** (live) |
| Refresh replay after rotation | `session_revoked` (server) | **PASS** (live) |
| `session_revoked` with newer SecureStore | Adopt newer; no logout | **PASS** (client) |
| HR ≠ Employee SecureStore namespaces | No key collision | **PASS** (source contract) |
| Access 45m / Refresh 90d | Policy live | **PASS** (live) |

**Overall:** client **8/8 PASS** · live **20/20 PASS** · canary OTA `9d28b353-f1c9-4f4e-bc5c-a80c34c8ebac`
