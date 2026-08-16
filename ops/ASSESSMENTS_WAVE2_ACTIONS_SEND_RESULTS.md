# Assessments Wave 2 — Actions, Send Results & Idempotency

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T023832Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Authority:** `assessment_presentation_v1` + `outbound_send_result_v1`  
**Not in this wave:** page redesign, report presentation, admin/authoring moves

---

## Final verdict

**PASS — Wave 2**

Assessment actions now use backend authority, expired attempts route through the correct replacement flow, and every send produces one shared backend-authoritative result envelope. The Hamad resend gap is fixed: a replacement attempt is created, old expired history is preserved, and the send result is explicit (**partially_sent** — email sent, WhatsApp failed) with per-channel detail and human-readable error. Resend is idempotent and completed attempts are protected.

---

## Hamad resend root cause and fix

**Before:** resend on an expired attempt called `deliver_assessment_invitation` on the dead attempt, which returned `attempt_expired` with **no replacement attempt, no send, and no clear result**.

**Fix:** `resend_assessment` now:
- rejects completed attempts (`already_sent`);
- routes **expired** attempts through `send_assessment` → `create_or_resume_assessment_attempt` (creates/resumes a replacement, then delivers);
- attaches a canonical `send_result` to every delivery.

Delivery status is normalized to the canonical invitation set (`sent` / `failed` / `intentionally_skipped`).

**Live Hamad result (`96597485758-WATHEFNI-ACCOUNTING_EXCEL`):**
- Replacement attempt created (`pending`), old `expired` attempt preserved.
- `send_result.state = partially_sent`
- Email: **sent** (postmark), WhatsApp: **failed** — “WhatsApp conversation is not active.”
- Recipient: Hamad Almulla / `h.almulla@almulla-media.com` / `96597485758`
- Second resend stays at **1 open attempt** (idempotent).

---

## Shared outbound send-result contract

`outbound_send_result_v1` fields:

- `state`: `sent` / `queued` / `partially_sent` / `failed`
- `ok`, `message`, `human_error`, `suggested_next_action`
- `recipient { name, email, phone }`
- `channels[]` per-channel: `channel`, `label`, `state`, `ok`, `provider`, `message_id`, `sent_at`, `error`
- `channels_attempted`, `timestamp`

Request accepted is not delivered. Multi-channel sends show Email and WhatsApp separately. Raw provider codes are humanized (e.g. `invalid_grant` → “Email needs reconnecting.”, `conversation_closed` → “WhatsApp conversation is not active.”).

Frontend: one shared `SendResultPanel` component renders the backend result (state badge, recipient, per-channel rows, human error, suggested next action, timestamp) — no page-specific implementations.

---

## Action authority

- Send / Resend / Retry / Cancel / Review come from backend `allowed_actions` in `assessment_presentation_v1`.
- No frontend status guessing for action visibility.
- Mutations remain audited and tenant/permission safe (`assessment.manage`, company-scoped).

---

## Proof (`20260728T023832Z`)

| Assertion | Result |
|---|---|
| Successful send | `sent` (synthetic + email channel live) |
| Queued send | `queued` |
| Partial success | `partially_sent` (Hamad: email sent, WhatsApp failed) |
| Failed send | `failed` (humanized) |
| Expired attempt replacement | **PASS** (new pending attempt, old expired preserved) |
| Resend idempotency | **PASS** (1 open attempt after repeat) |
| Duplicate prevention | **PASS** (no app with >1 active attempt) |
| Completed-attempt protection | **PASS** (`already_sent`) |
| Recipient/channel/provider evidence | **PASS** (email/postmark sent; WhatsApp failed) |
| EN/AR + RTL result messages | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `/opt/wathefni/production-evidence/assessments-wave2-actions-send-results/20260728T023832Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore (+ `outbound_send_result.py`) | Health **200** |
| Dashboard restore | Health **200**; asset `dashboard-DClPrDhC.js` |

---

## Remaining limitations

- The shared send-result contract is wired for assessments; interview invitations, offers, and document requests should adopt the same envelope in their waves.
- WhatsApp delivery for Hamad requires an active conversation; email remains the reliable channel here.
- Retry currently resends through the same idempotent path; a dedicated per-channel retry button is a UX follow-up.
- The result panel appears after a send action; it is not yet embedded per-row.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Actions from backend allowed_actions only | **PASS** |
| Expired → replacement flow | **PASS** |
| No duplicate active attempts/invitations | **PASS** |
| Resend idempotency | **PASS** |
| Completed-attempt protection | **PASS** |
| Shared send-result contract (4 states) | **PASS** |
| Multi-channel separated + humanized errors | **PASS** |
| Audited + tenant/permission safe | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 2.**
