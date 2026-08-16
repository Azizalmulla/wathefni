# Wathefni Calendar — C4 Implementation

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp (product C4):** `20260729T151545Z`  
**Stamp (communication correction):** `20260729T1530Z` (same host; files synced + smokes re-run)  
**Evidence (product):** `/opt/wathefni/production-evidence/wathefni-calendar-c4/20260729T151545Z/`  
**Authority:** C0 (+ A1), C1–C3, `ops/WATHEFNI_COMMUNICATION_CHANNEL_AUDIT.md`  
**Scope:** Internal RSVP · guest invite/token RSVP · reschedule · reminders · **canonical communication handoff**  
**Preserves:** Waves 1–6, Calendar C1–C3, Google operator coexistence  
**Tenants with `calendar` enabled:** **0**

---

## Verdict

**PASS** (product C4 + communication-model correction).

Event truth, RSVP, tokens, reminders, and outbox durability remain as C4. Communication correction narrows Calendar to a **domain intent queue** and routes all Calendar sends through `wathefni_communication` (shared WhatsApp/email adapters). C5+ **not started**.

| Suite | Result |
|---|---|
| `smoke-test-wathefni-communication.py` | **30 PASS / 0 FAIL** |
| `smoke-test-calendar-c4.py` | **38 PASS / 0 FAIL** |
| C3 / C2 / C1 | **41 / 37 / 53** PASS |
| Health after restart | **200** |

---

## C4 PASS/FAIL matrix

| # | Requirement | Result |
|---|---|---|
| 1 | Internal RSVP states + OCC (`rsvp_version`) | **PASS** |
| 2 | Attendee cannot RSVP for another without organizer+manage | **PASS** |
| 3 | Removed attendees cannot RSVP | **PASS** |
| 4 | External guest invite via delivery outbox (routed handoff) | **PASS** |
| 5 | Hashed opaque guest tokens with expiry/revoke | **PASS** |
| 6 | Public EN/AR mobile guest page | **PASS** |
| 7 | Guest accept/decline/tentative replay-safe | **PASS** |
| 8 | Reschedule request does not change event time | **PASS** |
| 9 | Duplicate pending reschedule blocked/idempotent | **PASS** |
| 10 | Interview-linked: Calendar does not independently reschedule | **PASS** |
| 11 | Reminders notify-only (no duplicate blocks) | **PASS** |
| 12 | Reminder claim/lease + cancel on event cancel | **PASS** |
| 13 | Delivery states + idempotent enqueue + audit | **PASS** |
| 14 | Failed delivery does not mark guest invited successfully | **PASS** |
| 15 | Personal/operational notify via canonical router (not parallel providers) | **PASS** |
| 16 | Token cannot cross event/guest/company | **PASS** |
| 17 | Cross-tenant disposable smoke isolation | **PASS** |
| 18 | C1–C3 regression | **PASS** |
| 19 | Google operator unchanged | **PASS** |
| 20 | No broad production enablement | **PASS** (0) |
| 21 | Calendar does not select provider credentials | **PASS** |
| 22 | Company pre-hire / post-hire / hr_ops policy routing | **PASS** |
| 23 | Unqualified channels never selected; fallback stops after success | **PASS** |

---

## Communication-model correction (locked)

### Exact routing model

Calendar emits intents only. Canonical router decides channels from **company `communication_policy`** by recipient lifecycle (`pre_hire` / `external_guest` / `post_hire` / `hr_ops`). Live adapters: `whatsapp`, `email` (+ `wathefni_push` only when flagged). Registry holds future keys (`wathefni_in_app`, Teams, Telegram, SMS) but they are **not selectable** until qualified.

### Company policy schema

`company_settings.settings.communication_policy` — see audit doc. Defaults in `wathefni_communication.DEFAULT_COMMUNICATION_POLICY`. Key is operator-managed (`OPERATOR_MANAGED_SETTING_KEYS`).

### Channel readiness (honest)

| Channel | Selectable now? |
|---|---|
| WhatsApp session | Yes |
| Email (Postmark/Gmail) | Yes |
| Expo push | Only if `WATHEFNI_PUSH_NOTIFICATIONS` on |
| Wathefni in-app inbox | **No** (planned) |
| HSM / Teams / Telegram / SMS | **No** |

### Calendar handoff boundary

`calendar_delivery_outbox.channel = routed`. Payload carries purpose, recipient_type, lifecycle, recipient refs, preferred hint. `process_delivery_item` → `deliver_intent` only — no Octopus/email calls in Calendar.

---

## Exact files changed (product C4 + correction)

| File | Change |
|---|---|
| `wathefni-orchestrator/wathefni_communication.py` | **New** — registry, policy, route, adapters, stop-on-success |
| `wathefni-orchestrator/calendar_participation.py` | Outbox handoff; no direct providers; notify via router |
| `wathefni-orchestrator/calendar_schema.py` | Allow outbox channel `routed` |
| `wathefni-orchestrator/calendar_store.py` | Enqueue `routed` attendee invites; remove dual immediate WhatsApp notify |
| `wathefni-orchestrator/app.py` | `communication_policy` operator-managed key |
| `wathefni-orchestrator/smoke-test-wathefni-communication.py` | **New** |
| `wathefni-orchestrator/smoke-test-calendar-c4.py` | Handoff / routed proofs |
| `ops/WATHEFNI_COMMUNICATION_CHANNEL_AUDIT.md` | Updated post-correction |
| `ops/WATHEFNI_CALENDAR_C4_IMPLEMENTATION.md` | This document |
| (prior C4) schema/UI/worker/reminders | Unchanged in purpose |

---

## Schema / migration

Additive / idempotent:

| Object | Purpose |
|---|---|
| `calendar_delivery_outbox.channel` includes `routed` | Domain handoff (constraint refreshed on ensure) |
| Prior C4 tables | Unchanged |

---

## Workers / timers

| Unit | Interval | Role |
|---|---|---|
| `wathefni-calendar-reminders.timer` | 1m | Reminder claim + delivery sweep → canonical router |
| `wathefni-calendar-outbox.timer` | 1m (C2) | Interview→Calendar ensure (unchanged) |

Prod: `CALENDAR_DELIVERY_DRY_RUN=true` on reminder service until live Calendar sends are explicitly enabled. Dry-run still exercises shared handoff adapters safely.

---

## Delivery states (locked)

`not_queued` · `queued` · `processing` · `delivered` · `failed` · `dead` · `cancelled`

---

## Remaining C5+ items (do not start)

- Google v2 company sync / Outlook / Microsoft
- Two-way external Calendar sync conflict UI
- Recurrence editor / expansion
- Resources / room finder
- Qualifying real Wathefni in-app inbox as a selectable channel
- Migrating non-Calendar notify paths onto the same authority (optional follow-on)

**Stop after C4 communication correction. Do not begin external Calendar synchronization.**
