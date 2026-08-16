# Pre-Hiring Durable Email Ingress — Isolated Staging Address Activation

**Status:** ADDRESS/CONFIG QUALIFIED — **NO-GO for sending mail**  
**Date:** 2026-07-25  
**Host:** `srv1419988` (`76.13.63.68`)  
**Backend:** `wathefni-orchestrator-staging.service` · `127.0.0.1:8011`  
**Database:** `wathefni_staging`  
**Evidence:** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-isolated-address/20260725T124039Z`  
**Production app/DB/Postmark hook:** untouched  

## Verdict

**GO** for keeping this single synthetic staging intake address active with staging inbound **receipt** enabled, workers stopped, sender acknowledgment off, and no mail sent.

**NO-GO** for sending even one synthetic CV email while the shared Postmark inbound webhook still targets production.

This phase activated exactly one company-wide held-intake address on the isolated staging tenant, armed staging receipt gates, and proved resolve/reject/disable behavior with configuration and direct internal checks only. No email was sent. No intake worker was started. No application code was deployed. Production was not changed.

---

## 1. Address identity (sensitive values redacted)

| Field | Value |
|---|---|
| `intake_id` | `25bdf532-fdc4-40b4-b200-02e6c36d1fc1` |
| Full address | `stg-cv-ingress-dark@inbound.wathefni.ai` |
| `local_part` | `stg-cv-ingress-dark` |
| `domain` | `inbound.wathefni.ai` |
| Synthetic | yes |
| Customer careers address | no |
| Status | `active` |
| Create audit `result_id` | `7a2874fd-26e9-4ecd-957b-e6d04364fcaa` |
| Activate audit `result_id` | `3e107bbc-7fe9-44c2-8b34-02968f689652` |

Immutable metadata provenance recorded on the row:

- `environment=staging`
- `destination_type=company_wide_general_intake`
- `default_destination_behavior=held_intake`
- `job_binding=null`
- `role_profile_binding=null`
- `immutable_route_provenance=true`
- `customer_careers_address=false`

Active staging intake addresses before: **0**. After: **1**. No other active staging intake address exists.

---

## 2. Tenant mapping

| Item | Value |
|---|---|
| `company_code` | `WATHEFNI` |
| Destination type | company-wide / general intake |
| `position_code` | `NULL` |
| `position_title` | `NULL` |
| Job / Role Profile binding | absent |
| Default destination behavior | held intake |

Recipient resolution uses staging `intake_addresses` only. Proven:

- `stg-cv-ingress-dark@inbound.wathefni.ai` → `WATHEFNI`
- unknown recipient → no row
- another staging tenant cannot insert/reuse the same `(local_part, domain)` (`UniqueViolation` against `ASSTJOBRANKUX`)

---

## 3. Postmark staging configuration

### What was configured

Staging-only Postmark route artifact:

- `/root/.openclaw/secrets/wathefni-postmark-inbound-route.staging.json`
- Evidence copy: `postmark_staging_route_config.json`

Intended staging webhook shape (redacted):

```text
http://127.0.0.1:8011/webhook/postmark/inbound?token=***REDACTED***
```

| Check | Result |
|---|---|
| Staging inbound auth secret loaded | Pass (`sha256` prefix recorded in evidence) |
| Staging vs production inbound secrets distinct | Pass |
| Staging env references production URLs/streams | Pass — none |
| Sender acknowledgment | `off` |
| Mail sent | **No** |
| Shared Postmark `InboundHookUrl` mutated | **No** |

### Shared Postmark server (unchanged)

Read-only check before and after:

| Field | Value |
|---|---|
| Server | `My First Server` |
| `InboundDomain` | `wathefni.ai` |
| `InboundHookUrl` | `https://***:***@api.wathefni.ai/webhook/postmark/inbound` |
| Targets staging `:8011` | **No** |

### Why the cloud route was not applied to the shared server

The account has one inbound stream on the shared production Postmark server. That stream already serves production inbound (including the existing production careers hash address). Pointing `InboundHookUrl` at staging would divert production inbound. No Postmark Account token is available on this host to create a dedicated staging server/stream in this phase.

Therefore:

- Wathefni-side staging address + receipt gates are armed;
- Postmark cloud inbound still points only at production;
- **sending mail to the synthetic address would not reach staging.**

---

## 4. Route type and held-intake semantics

| Requirement | Proof |
|---|---|
| Company-wide / general | `position_code` / `position_title` null; metadata `destination_type=company_wide_general_intake` |
| Not bound to Job / Role Profile | binding fields null in row + metadata |
| Default held intake | metadata `default_destination_behavior=held_intake`; no auto job admit path from this address alone |
| Durable route snapshot source | intake row `position_code` remains null for this address |

No candidate, application, OCR, embedding, or classification work was invoked.

---

## 5. Feature-flag scope

Staging EnvironmentFile `/root/.openclaw/secrets/wathefni-intake.staging.env`:

| Flag | Before | After |
|---|---|---|
| `WATHEFNI_INBOUND_EMAIL` | `off` | `on` |
| `WATHEFNI_SENDER_ACKNOWLEDGMENT` | `off` | `off` |

Scope:

- Applies only to `wathefni-orchestrator-staging.service` via its intake EnvironmentFile drop-in.
- Does **not** globally enable unrestricted processing: workers remain disabled/stopped, so no processing job executes.
- Does **not** enable sender acknowledgment.
- Production `postgres.env` inbound settings were not modified by this phase.

Staging orchestrator restarted to load the flag. Health remained `200` with `application_environment=staging` / `database_environment=staging` match.

---

## 6. Worker stopped / disabled proof

| Unit | Active | Enabled |
|---|---|---|
| `wathefni-intake-worker-staging.service` | `inactive` | `disabled` |
| `wathefni-intake-worker-staging.timer` | `inactive` | `disabled` |

No intake worker was started. No malware scan / OCR / structuring / embeddings / classification job runner was enabled.

---

## 7. Zero queue / candidate / application / extraction proof

At end of phase (before any email):

```text
jobs=0 submissions=0 documents=0 inbound_messages=0
```

Additional checks:

- no recent WATHEFNI applications with intake/email/postmark-like `data_source` in the last 2 hours;
- no Postmark delivery to `stg-cv-ingress-dark@inbound.wathefni.ai` in recent inbound message listing (0 hits / 10 checked).

---

## 8. Unknown-recipient and cross-tenant proof

| Check | Result |
|---|---|
| Correct recipient → `WATHEFNI` | Pass |
| Unknown recipient rejected | Pass |
| Cross-tenant reuse of same local+domain blocked | Pass (`UniqueViolation`) |
| Resolved company remains only `WATHEFNI` | Pass |
| Job binding absent | Pass |

Evidence: `safety_proofs.json`, `cross_tenant_proof.json`.

---

## 9. Disable / re-enable rollback proof

Performed on the same address without deleting configuration:

1. `status=active` → resolve succeeds.
2. `status=disabled` → resolve returns none; row retained.
3. Audit `intake_address_disabled` written.
4. `status=active` restored → resolve succeeds again.
5. Audit `intake_address_activated` written for re-enable.

Inbound can be immediately disabled at either layer without deleting config:

- address `status=disabled`, and/or
- staging `WATHEFNI_INBOUND_EMAIL=off` + staging service restart.

---

## 10. Webhook acceptance proof (internal only; not a synthetic email)

Direct localhost checks against staging `:8011` only (not the public webhook as a fake email substitute):

| Probe | HTTP | Meaning |
|---|---|---|
| Bad token | `401 unauthorized` | auth required |
| Staging secret + empty `{}` | `400 provider_message_id_required` | auth accepted; inbound **not** disabled (`503 inbound_disabled` absent); payload rejected before durability |

No public webhook invocation with a synthetic email payload. No Postmark “Send Test” / live delivery.

---

## 11. Audit evidence

`action_results` rows for actor `ops_isolated_address_activation` / company `WATHEFNI`:

| Action | Count |
|---|---|
| `intake_address_created` | 1 |
| `intake_address_activated` | 2 (initial + re-enable) |
| `intake_address_disabled` | 1 |

---

## 12. ClamAV and quarantine health

| Check | Result |
|---|---|
| `wathefni-staging-clamav` | Up / healthy |
| Quarantine mount `/opt/wathefni/staging/quarantine/email-intake` | mounted |
| Malware scanning executed this phase | **No** (workers stopped; no mail) |

---

## 13. Zero-mail confirmation

- No email sent by this phase.
- No Postmark inbound delivery observed for the synthetic address.
- Shared Postmark inbound hook left on production URL.
- Queue/submission/document counters remain zero.

---

## 14. Unresolved risks

1. **Shared Postmark inbound hook** still targets production. Staging cannot receive provider-delivered mail until a dedicated staging Postmark server/stream (or otherwise non-diverting hook) is attached to `127.0.0.1:8011` / an approved staging-only public path.
2. Staging webhook remains localhost-bound (`127.0.0.1:8011`). Owner decision default was localhost + tunnel; no public staging Postmark path was exposed in this phase.
3. Staging `WATHEFNI_INBOUND_EMAIL=on` arms receipt for the staging process. With workers stopped this cannot process, but a future misrouted authenticated POST to staging could durable-ledger if it reached `:8011` with a resolvable recipient.
4. Synthetic address uses domain `inbound.wathefni.ai` (staging-only local-part). Until Postmark staging isolation exists, that alias must not be used for live mail.
5. No Postmark Account token on host → cannot create an isolated staging server from this phase alone.

---

## 15. GO / NO-GO for sending exactly one synthetic CV email (workers remain stopped)

| Gate | Status |
|---|---|
| One synthetic staging address active | Pass |
| Maps to exactly one `company_code` (`WATHEFNI`) | Pass |
| Company-wide / no job bind / held intake | Pass |
| Staging inbound receipt flag on | Pass |
| Sender ack off | Pass |
| Workers disabled + stopped | Pass |
| Queue depth zero | Pass |
| Unknown / cross-tenant rejection proven | Pass |
| Disable without delete proven | Pass |
| Audit evidence present | Pass |
| ClamAV + quarantine healthy | Pass |
| Production unchanged | Pass |
| Postmark webhook points **only** to staging | **Fail** (still production) |

### Verdict

**NO-GO** for sending exactly one synthetic CV email while workers remain stopped.

Unblock condition for a later send phase (still with workers stopped): attach inbound delivery to staging-only webhook credentials/URL without diverting production inbound (dedicated Postmark staging server/stream, or an explicitly approved non-production hook), then re-prove provider path → staging `:8011` before any mail.

---

## 16. Explicit non-actions

This phase did **not**:

- send any email;
- start or enable any intake worker;
- create candidates or applications;
- run malware scanning, OCR, structuring, embeddings, or classification;
- enable sender acknowledgment;
- activate any other intake address;
- deploy new application code;
- change production app, DB, secrets, or Postmark `InboundHookUrl`.
