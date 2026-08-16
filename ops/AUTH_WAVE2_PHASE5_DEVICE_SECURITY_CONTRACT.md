# Auth Wave 2 — Phase 5: Basic device security (canonical contract)

**Status:** FROZEN — **fully proven** (2026-08-07)  
**Frozen base:** `ops/AUTH_WAVE1_FROZEN_CONTRACT.md` (do not weaken)  
**Rule:** One active employee device at a time. Server session is the authority. Local PIN / Face ID never revive a revoked session.

---

## 1. Product rule (preserved)

```text
Activation code → Create PIN → Face ID (optional)
Activating a new phone revokes the previous device session automatically
Employee does not manually revoke the old phone first
```

| Moment | Behavior |
|---|---|
| New phone activates | Prior sessions revoked (`reactivated_via_invite`); new session minted |
| Old phone opens | Tokens fail → return to activation (after local unlock if PIN still present) |
| Employee signs out this device | `POST /app/auth/logout` + local clear |
| HR revoke (lost/compromised) | All active sessions + push tokens revoked; employee needs a new invite |
| Temporary offline / 5xx | Must **not** revoke or wipe the local session |

---

## 2. Employee UX

### Settings → Device security

Show only calm facts (no fingerprints, session IDs, tokens, or internal reasons):

| Field | Source |
|---|---|
| Current device | Fixed label |
| Device type / platform | `ios` / `android` / unknown → localized label |
| Activated date | Session `created_at` |
| Last active | Session `last_seen_at` |
| Status | Active (this device only reaches this screen while authenticated) |
| Action | **Sign out this device** → confirm → logout + local clear |

### New-device notice (once)

When activate response includes `replaced_previous_device: true`, after the employee finishes local setup and reaches the signed-in app, show **once**:

> Wathefni was activated on this device. Your previous device was signed out.

Do not show on first-ever activation (no prior session).

---

## 3. HR UX (compact)

On the employee profile, one **App access** area:

| Field | Meaning |
|---|---|
| Access | Active / Not active |
| Device | Platform label when active |
| Last active | When active |
| **Revoke access** | Permission-gated, reason + audit, idempotent |
| Re-invite | Delivered via invitation/delivery contract (no normal code handoff); see `ops/EMPLOYEE_APP_INVITATION_DELIVERY_CONTRACT.md` |

No multi-device console, naming, trust scores, or remote wipe.

---

## 4. API contract

### Employee

| Route | Role |
|---|---|
| `POST /app/auth/activate` | Optional `platform` (`ios`/`android`); response may include `replaced_previous_device` |
| `GET /app/device-security` | Current-device summary only (no ids/tokens) |
| `POST /app/auth/logout` | Sign out **this** device (frozen) |

### HR (dashboard)

| Route | Permission | Role |
|---|---|---|
| `GET /dashboard/posthire/employees/{employee_key}/app-access` | `employees.manage` | Active? platform? last active? |
| `POST .../app-access/revoke` | `employees.manage` | Body: `reason`, `idempotency_key` → revoke all app sessions + push |

Revoke reasons use server vocabulary (`hr_revoked`, `reactivated_via_invite`, `logout`, `offboarded`, `ess_session_epoch_*`). Clients never show those strings.

Employee-facing revoke UX (not for offline/5xx):

| Server error | Employee copy |
|---|---|
| `app_access_revoked` (`hr_revoked`, `reactivated_via_invite`) | **Your app access was reset** · Sign in again with a new activation code. |
| `app_auth_failed` after failed refresh (natural expiry / ambiguous) | Existing session-expired copy |

---

## 5. Security rules

1. **Server session authority** — access + refresh hashes; status `active` required.
2. **Revocation invalidates access and refresh** — set `status=revoked`, clear `refresh_hash`, stamp `revoked_at` / `revoked_reason`.
3. **Authoritative kill switches remain:** `session_epoch`, logout, offboarding, new-device activate, HR revoke.
4. **PIN / Face ID are local** — they only unseal SecureStore; they cannot mint tokens or bypass revoke.
5. **Soft failures do not revoke** — offline / 5xx keep local session (Wave 1/2 classifier).
6. **HR revoke** — permission-gated, audited (`employee_app_access_revoked`), idempotent on `idempotency_key`.
7. **Tenant isolation** — company scoped; manager scope via existing employee visibility helpers.

---

## 6. Explicit non-goals (Phase 5)

Multiple trusted devices · device naming · trust scores · remembered-device lists · per-device permissions · remote wipe · activation delivery channels · Phase 6 rollout.

---

## 7. Qualification matrix

| Proof | Expectation |
|---|---|
| Current device details | Platform, activated, last active, Active |
| Employee sign-out | Local session cleared; needs activation to return |
| HR revoke | Active device session dead |
| Old PIN / Face ID | Cannot restore revoked access |
| New-phone activate | Old phone revoked; returns to activation |
| New phone | Completes PIN + Face ID; notice once |
| Offline / 5xx | No revoke |
| Permissions / tenant | Cross-tenant and unauthorized deny |
| Bank ESS / onboarding / payroll / nav | Unchanged |
| EN / AR / RTL | Clean |

**Verdict labels:** fully proven · partially proven · blocked · failed  
**Do not begin Phase 6 automatically.**
