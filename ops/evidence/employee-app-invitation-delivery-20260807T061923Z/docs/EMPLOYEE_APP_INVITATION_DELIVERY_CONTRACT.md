# Employee App — Invitation + Delivery (canonical contract)

**Status:** ACTIVE — canary (WATHEFNI)  
**Scope:** Invitation issuance + outbound delivery to the employee  
**Out of scope:** Auth Wave 2 (activate / PIN / Face ID / sessions / revoke / session_epoch) — frozen; **do not start Phase 6**  
**SMS:** Never used for activation codes

---

## 1. Product rule

```text
Employee eligible → auto invitation → deliver (email / WhatsApp) → employee activates → PIN → Face ID
HR does NOT normally copy or hand codes
```

| Moment | Behavior |
|---|---|
| Employee created (eligible + module on) | Auto-issue one pending invite + deliver (flag-gated) |
| Onboarding starts (`in_progress`) | Auto-issue if none pending (idempotent) |
| Delivery succeeds | HR sees **sent** / **delivered** + channel |
| Delivery fails / needs HR | HR sees **failed** / **needs_attention**; exception path may show code |
| Resend / Re-invite | Fresh invite supersedes prior pending; deliver again; **no code in HR response** |
| New invite | Invalidates previous pending invite |
| Expiry | Pending past `expires_at` → **expired**; activate rejects expired |
| Employee request-code | Only if prior invite exists; cooldown; re-issue + deliver (generic ACK) |
| Activate | Auth Wave 2 unchanged |

---

## 2. Authority split

| Concern | Owner |
|---|---|
| Invite row, expiry, one pending, supersede | `employee_app_invites` + `create_employee_app_invite` |
| Auto trigger, delivery status, HR snapshot, resend/reinvite | `employee_app_invitation.py` |
| Outbound ladder (WhatsApp → email; no SMS) | `deliver_app_activation_code` → `deliver_employee_notification` |
| Activate / sessions / revoke / device security | Auth Wave 2 (unchanged) |

Plaintext codes exist only for: outbound delivery payload, and the **exception** HR handoff (`hr_task_only`) when delivery needs attention.

---

## 3. HR statuses

| Status | Meaning |
|---|---|
| `none` | No invite yet |
| `pending` | Invite exists, not yet sent |
| `sent` | Handed to a channel |
| `delivered` | Outbound reported delivered / accepted |
| `activated` | Invite redeemed |
| `expired` | Pending past expiry |
| `failed` | Delivery failed |
| `needs_attention` | Ladder could not reach employee; HR may use code exception |

---

## 4. Feature flags

| Env | Role |
|---|---|
| `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE` | `on` / `off` — master auto-invite |
| `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES` | Optional allowlist (e.g. `WATHEFNI`) |

When auto-invite is off, HR Resend / Re-invite and request-code delivery still work.

---

## 5. API (dashboard)

| Route | Role |
|---|---|
| `GET .../app-invitation` | Snapshot (status, channel, sent_at, expires, actions). **Never returns code.** |
| `POST .../app-invitation/resend` | Force new invite + deliver; audit; no code |
| `POST .../app-invitation/reinvite` | Same after revoke/expiry; audit; no code |
| `GET/POST .../app-access` (+ revoke) | Auth Wave 2 Phase 5 — unchanged |
| `POST .../app-invite` (`hr_task_only`) | **Exception only** — returns one-time code |

---

## 6. HR UX

On employee profile **App access**:

1. Access / Device / Last active (Phase 5)
2. Invitation status + channel + last sent
3. **Resend invitation** / **Re-invite** (deliver to employee)
4. **Revoke access** when active
5. **Show activation code** only when status is `needs_attention` (or explicit exception)

Header “Activation handoff” is demoted to the exception path.

---

## 7. Non-goals

- SMS activation
- Multi-device invite fan-out
- Changing Auth Wave 2 activate / PIN / Face ID
- Phase 6
- Returning codes on normal Resend / Re-invite / auto-invite
