# Aziz Employee App invite delivery trace

Stamp: `20260808T080340Z`  
Employee: `WATHEFNI-96599338566` (Aziz Mobile QA)  
No resend performed during this investigation.

## Verdict

**ROOT CAUSE:** Invitation + activation code were created and marked delivered, but delivery targeted a non-receivable QA email (`aziz+mobile-qa@wathefni.internal`). WhatsApp could not deliver either (`no_usable_conversation_id`). Aziz never saw a code because no channel reached a real inbox/device conversation.

**Postmark quota:** NOT the issue (API accepts sends; today’s server stats show sends with `SMTPApiErrors: 0`).

**Runtime `app_access_enabled`:** Related only as the *trigger* (Enable & invite auto-delivery). Not a regression that blocked invite creation.

## Trace

| Step | Result |
|---|---|
| HR action | Enable app access / auto-invite (`trigger_source=app_access_enabled`, idempotency `access_enabled:WATHEFNI-96599338566…`) at `2026-08-08 07:54:51Z` |
| Invite created | Yes — `invite_id=0a5d2f40-2a73-457a-857a-40f0461013fa`, `status=pending`, `code_hash` present |
| Code generated | Yes — stored in outbound message variables; invite expires `2026-08-09 07:54:51Z`; not redeemed |
| Channel selection | Ladder: WhatsApp session → template → **email fallback** |
| WhatsApp | Failed: `no_usable_conversation_id` (many stale/smoke conversation IDs on phone `96599338566`) |
| Template WhatsApp | Skipped: `template_disabled` |
| Email | Selected fallback to `aziz+mobile-qa@wathefni.internal` |
| Postmark call (local record) | `ok=true`, `provider=postmark`, `provider_accept_status=accepted_by_provider`, `dry_run=false`, MessageID `7534a3d4-ff9f-4d3a-a796-da221944d246` |
| Postmark API follow-up | That MessageID returns Error 701 “not found”; no outbound to this recipient dated today. Prior sends to the same `.internal` address exist and later bounce |
| Historical Postmark bounces for recipient | Transient / `smtp;550 4.4.7 QUEUE.Expired; message expired` — undeliverable mailbox/domain |
| Final invite state | `delivery_status=delivered`, `delivery_channel=email`, `last_delivery_error=null` (HR UI success; employee never received) |
| App access | `app_access_enabled=true`, eligible; `app_access_active=false` (no session) |

## What is / is not broken

- Invitation architecture behaved as designed for Enable→auto-invite.
- Defect for the user experience is **contact data + WhatsApp conversation usability**, not invite minting and not Postmark monthly quota.
- Secondary concern: local “accepted_by_provider” MessageID for today’s send is not visible in Postmark message search (investigate separately if needed; does not change the undeliverable-recipient root cause proven by bounce history).

## Safest fix (no architecture change)

1. Set Aziz’s employee `email` to a real address he can open (not `*.wathefni.internal` / `*.invalid`).
2. Optionally clean/repair WhatsApp conversation mapping for `96599338566` if phone delivery is desired.
3. Then **one** Resend from HR (or Show activation code only if status is needs_attention / exception path).
4. Do not repeatedly resend while email remains `.internal`.

Evidence files in this directory: `db-trace.txt`, `deep-trace.txt`, `postmark-*.txt`.
