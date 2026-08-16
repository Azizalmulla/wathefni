# Wathefni Communication Channel Audit

**Date:** 2026-07-29 (Asia/Kuwait)  
**Updated:** 2026-07-29 — C4 communication-model correction  
**Mode:** Living audit after narrow Calendar handoff correction (C5 not started)  
**Scope:** Communication / delivery channels + canonical routing authority  
**Primary trees:** `wathefni-orchestrator/wathefni_communication.py`, `outbound_delivery.py`, `app.py`, Calendar C4 (`calendar_participation.py`)

---

## Verdict (post-correction)

Wathefni now has a **canonical communication authority** for Calendar intents:

- **Router:** `wathefni_communication.deliver_intent` / `resolve_route`
- **Company policy:** `company_settings.settings.communication_policy` (operator-managed)
- **Calendar outbox:** `calendar_delivery_outbox` is a **domain handoff queue** (`channel=routed`) — it does **not** select providers or credentials

**Still true (legacy spines coexist outside Calendar):**

1. Candidate/HR direct callers in `app.py` (`notify_candidate`, `send_email`, `notify_hr_admins`) remain for non-Calendar flows until those paths are migrated.
2. Employee outbound ladder (`outbound_delivery` → `employee_messages`) remains for employee HR workflows.

**Calendar C4 no longer calls Octopus/email directly.** Live adapters: WhatsApp session + email via shared senders with `company_code` + `account_id`.

---

## Exact routing model

```text
Module (Calendar) emits intent
  purpose · recipient_type · lifecycle · recipient ref · event ref · urgency · locale · privacy-safe payload
        │
        ▼
calendar_delivery_outbox (durable handoff, idempotent, retry)
  channel = routed   (never provider credentials)
        │
        ▼
wathefni_communication.deliver_intent
  1. classify lifecycle (pre_hire | external_guest | post_hire | hr_ops) from recipient identity
  2. load company communication_policy (defaults if unset)
  3. apply purpose_overrides
  4. build ladder: hint (if enabled) → preferred → fallback
  5. drop unqualified / disabled channels
  6. consent / quiet_hours gates
  7. try adapters in order — STOP after first confirmed success
        │
        ▼
Adapters (only if selectable)
  whatsapp → send_octopus_whatsapp(account_id, company_code, audience=…)
  email    → send_outbound_email(company_code=…)
  wathefni_push → send_outbound_push (only when flag enables)
```

**No global WhatsApp-first. No office/frontline stereotype.** Company policy chooses order.

### Lifecycle → policy slice

| Recipient identity | Lifecycle | Default foundation |
|---|---|---|
| Candidate (`guest_kind=candidate` / `app_key` / `person_key`) | `pre_hire` | Link-based; default preferred `email`, fallback `whatsapp` (overridable) |
| External non-candidate guest | `external_guest` | Same shape as pre_hire defaults (overridable) |
| Employee attendee | `post_hire` | Preferred `wathefni_in_app`, `wathefni_push` (not selectable until qualified); company must enable live extras |
| HR / organizer operational | `hr_ops` | Same foundation; company enables live alert channels |

Classification uses **recipient identity**, not event type.

---

## Company policy schema

Stored at `company_settings.settings.communication_policy` (key in `OPERATOR_MANAGED_SETTING_KEYS`).

```json
{
  "pre_hire": {
    "preferred_channels": ["email"],
    "fallback_channels": ["whatsapp"],
    "enabled_channels": ["email", "whatsapp"],
    "allowed_purposes": ["calendar_invitation", "calendar_reminder", "..."],
    "require_consent": false,
    "connected_account": null,
    "quiet_hours": {}
  },
  "external_guest": { "...same shape..." },
  "post_hire": {
    "preferred_channels": ["wathefni_in_app", "wathefni_push"],
    "fallback_channels": [],
    "enabled_channels": ["wathefni_in_app", "wathefni_push"],
    "allowed_purposes": ["..."],
    "require_consent": false,
    "connected_account": null,
    "quiet_hours": {}
  },
  "hr_ops": { "...same shape as post_hire defaults..." },
  "purpose_overrides": {
    "calendar_reminder": {
      "preferred_channels": ["email"],
      "fallback_channels": ["whatsapp"],
      "enabled_channels": ["email", "whatsapp"]
    }
  }
}
```

Defaults live in `wathefni_communication.DEFAULT_COMMUNICATION_POLICY`. Companies override per lifecycle; purpose overrides merge on top.

---

## Channel readiness matrix (audit truth)

| Channel | Registry key | Exists | Real sending | Company account | Production-ready / selectable | Used by Calendar C4 (via router) |
|---|---|---|---|---|---|---|
| WhatsApp session | `whatsapp` | Yes | Yes (when not dry-run) | Dark (flag); shared default | **Yes** | Yes, when policy enables |
| Email Postmark/Gmail | `email` | Yes | Yes | Platform from-address | **Yes** | Yes, when policy enables |
| WhatsApp HSM | `whatsapp_hsm` | Yes | Partial | Partial | **No (dark)** | No (not in adapters) |
| Expo push | `wathefni_push` | Yes | When flag on | Device tokens | **Dark** (selectable only if `WATHEFNI_PUSH_NOTIFICATIONS` on) | Only if selectable + enabled |
| Wathefni in-app inbox | `wathefni_in_app` | Planned | No qualified sender | N/A | **No (planned)** | Never selected until qualified |
| Google Calendar invite | legacy `gog` | Yes | Yes | Shared GOG | **Legacy** | No |
| Microsoft Teams | `microsoft_teams` | Registry only | No | — | **Absent** | Never |
| Telegram | `telegram` | Registry only | No | — | **Absent** | Never |
| SMS | `sms` | Vocabulary | No | — | **Absent** | Never |

---

## Calendar handoff boundary

| Owns (`calendar_delivery_outbox`) | Does **not** own |
|---|---|
| Durable intent + purpose | Provider credentials |
| Recipient / event references | Company channel account resolution |
| Idempotency key | Consent / quiet hours policy |
| Retry / lease / handoff status | Channel registry / readiness |
| Intent payload for router | Direct Octopus / Postmark calls |

Worker: `process_delivery_item` → `wathefni_communication.deliver_intent` only.

---

## Canonical authorities (updated)

| Concern | Authority |
|---|---|
| Channel registry + readiness | `wathefni_communication.CHANNEL_REGISTRY` |
| Company communication policy | `company_settings.communication_policy` |
| Routing + fallback + stop-on-success | `wathefni_communication.deliver_intent` |
| Calendar domain queue | `calendar_delivery_outbox` (`routed`) |
| Live WhatsApp / email senders | `app.send_octopus_whatsapp`, `app.send_outbound_email` |
| Employee workflow ladder (non-Calendar) | `outbound_delivery` / `employee_messages` (unchanged) |
| Delivery audit events | `outbound_delivery_events` (via shared senders) |

---

## Proofs (2026-07-29 correction)

| Proof | Result |
|---|---|
| Candidate routing → pre_hire policy | PASS (`smoke-test-wathefni-communication.py`) |
| Employee routing → post_hire policy | PASS |
| HR → hr_ops policy | PASS |
| No global WhatsApp-first | PASS (default email-first; company can set WA-first) |
| No office/frontline assumption | PASS |
| Calendar does not select provider credentials | PASS (no `send_octopus_whatsapp` in Calendar) |
| Unqualified channels not selected | PASS |
| Live WhatsApp/email handoff | PASS (adapters + dry-run Calendar path) |
| Fallback stops after success | PASS |
| company_code threaded (no cross-tenant invent) | PASS |
| C1 / C2 / C3 / C4 | **53 / 37 / 41 / 38** PASS, 0 FAIL |
| Communication smoke | **30** PASS, 0 FAIL |
| Health after orchestrator restart | **200** |

---

## Remaining gaps (not this correction)

- Migrate non-Calendar `notify_hr_admins` / `candidate_communication_router` onto the same authority
- Qualify real `wathefni_in_app` inbox sender
- Quiet hours TZ-aware enforcement
- Company-owned WhatsApp accounts default ON
- C5+ external calendar sync — **not started**

**Stop line:** Communication-model correction complete. C5 not started.
