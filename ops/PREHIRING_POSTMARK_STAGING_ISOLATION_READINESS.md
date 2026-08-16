# Pre-Hiring — Postmark Staging Isolation Readiness

**Status:** STAGING ISOLATION READY — **GO for one synthetic PDF (workers stopped)**  
**Date:** 2026-07-25  
**Host:** `srv1419988` (`76.13.63.68`)  
**Staging backend:** `wathefni-orchestrator-staging.service` · `127.0.0.1:8011`  
**Evidence (edge setup):** `/opt/wathefni/staging/staging-evidence/postmark-staging-isolation/20260725T124635Z`  
**Evidence (address remap):** `/opt/wathefni/staging/staging-evidence/postmark-staging-isolation/20260725T125548Z-address-remap`  
**Production Postmark server:** byte-for-byte unchanged  

## Verdict

**GO** for sending **exactly one** synthetic PDF CV to the dedicated staging Postmark inbound address while intake workers remain **disabled and stopped**, sender acknowledgment remains **off**, and production Postmark stays untouched.

**NO-GO** for starting workers, enabling sender ack, sending a second mail, or using the old `inbound.wathefni.ai` alias.

This update remapped staging `intake_addresses` to the dedicated Postmark hash alias after the owner created staging Postmark server `20067520` and saved the staging-only webhook URL. No email was sent in this phase. No workers were started. Production intake configuration was not changed.

---

## 1. Staging Postmark server / stream identity

| Item | Value |
|---|---|
| Staging Postmark server ID | `20067520` (owner-created in Postmark UI) |
| Inbound hash | `965f89c46a9dfbca61a0831f8ba1f631` |
| Inbound address | `965f89c46a9dfbca61a0831f8ba1f631@inbound.postmarkapp.com` |
| Inbound webhook URL | `https://wathefni:***REDACTED***@api.wathefni.ai/webhook/postmark-staging/inbound` |
| Targets | staging edge → `:8011` only |
| Production server ID (forbidden) | `19430066` — unchanged |

Production remains on server `19430066` / `InboundDomain=wathefni.ai` / `/webhook/postmark/inbound` → `:8010`.

---

## 2. Inbound domain / alias (remapped)

### Active staging recipient (exclusive)

| Field | Value |
|---|---|
| `intake_id` | `25bdf532-fdc4-40b4-b200-02e6c36d1fc1` (same row; remapped in place) |
| Full address | `965f89c46a9dfbca61a0831f8ba1f631@inbound.postmarkapp.com` |
| `local_part` | `965f89c46a9dfbca61a0831f8ba1f631` |
| `domain` | `inbound.postmarkapp.com` |
| `company_code` | `WATHEFNI` |
| Job binding | none |
| Route type | company-wide / general intake |
| Default behavior | held intake |
| Status | `active` |
| Remap audit `result_id` | `bd61a381-9ea5-4476-b7d1-5e6c5ec0a368` |

### Previous synthetic alias

| Alias | Status |
|---|---|
| `stg-cv-ingress-dark@inbound.wathefni.ai` | **Not active** — replaced on the same row; not retained as an active historical alias |

Proven: old alias no longer resolves for staging intake.

---

## 3. Staging webhook destination

Caddy on `api.wathefni.ai`:

```text
/webhook/postmark-staging*  →  rewrite to /webhook/postmark*  →  127.0.0.1:8011
/webhook/postmark*          →  127.0.0.1:8010   (production; unchanged)
```

Auth gate re-checked after remap: staging path + staging secret → `400 provider_message_id_required` (auth accepted; inbound not disabled). No synthetic email payload used as a stand-in for a real CV.

---

## 4. Secret separation

| Secret | Scope |
|---|---|
| Staging inbound webhook secret | `wathefni-intake.staging.env` only |
| Production inbound webhook secret | `postgres.env` only; distinct |
| Production Postmark server token | `postgres.env` only |
| Sender acknowledgment | `off` |

---

## 5. Production unchanged proof

Production Postmark server JSON compared before and after remap:

- byte-identical
- server ID still `19430066`
- production `intake_addresses` still only the careers hash `92d69b51…@inbound.postmarkapp.com` (not the staging hash)

No production Postmark mutation. No production intake-address mutation.

---

## 6. Wathefni tenant mapping proofs (18/18)

| Check | Result |
|---|---|
| New Postmark alias → exactly `WATHEFNI` | Pass |
| Hash recipient resolution → `WATHEFNI` | Pass |
| Old synthetic alias no longer accepts | Pass |
| Unknown recipient fail-closed | Pass |
| Cross-tenant reuse blocked (`UniqueViolation`) | Pass |
| Cross-tenant resolution stays `WATHEFNI` | Pass |
| No job binding | Pass |
| Exactly one staging address row / active | Pass |

Evidence: `…/20260725T125548Z-address-remap/remap_proofs.json`

---

## 7. Worker stopped proof

| Unit | Active | Enabled |
|---|---|---|
| `wathefni-intake-worker-staging.service` | `inactive` | `disabled` |
| `wathefni-intake-worker-staging.timer` | `inactive` | `disabled` |

---

## 8. Zero-data / zero-mail proof

```text
jobs=0 submissions=0 documents=0 inbound_messages=0
```

- No recent WATHEFNI intake/email/postmark-like applications
- No mail sent by this phase
- Recent production inbound listing shows no hits for the staging hash / old alias

---

## 9. Retry, retention, and payload settings

Unchanged from prior readiness:

- Postmark inbound retries: up to 10 attempts on non-200; stops on `403`
- Wathefni staging body cap 24 MiB; attachments 12; file 8 MiB; total 12 MiB; PDF pages 40 — compatible with a single modest synthetic PDF
- Sender ack off; workers stopped ⇒ receipt may durable-ledger/queue, but **no processing job will execute**

---

## 10. Rollback / disable (staging only)

Without touching production Postmark:

1. `UPDATE intake_addresses SET status='disabled' …` for the staging hash row, and/or  
2. `WATHEFNI_INBOUND_EMAIL=off` + restart staging orchestrator, and/or  
3. Clear staging Postmark server webhook URL in Postmark UI (server `20067520` only)

Never edit production server `19430066`.

---

## 11. Unresolved risks

1. First real mail will create durable receipt artifacts while workers stay stopped (expected for receipt qualification; not processing).
2. Staging edge path is publicly reachable under `/webhook/postmark-staging` but secret-gated.
3. Keep the staging inbound hash unpublished outside this test.
4. Do not send a second email until receipt/queue behavior from the first is reviewed.

---

## 12. GO / NO-GO for sending exactly one synthetic PDF CV (workers stopped)

| Gate | Status |
|---|---|
| Dedicated staging Postmark server/stream | Pass (`20067520`) |
| Staging-only exclusive inbound alias | Pass (hash `@inbound.postmarkapp.com`) |
| Webhook points only to staging | Pass |
| Staging secret; production secret unused by staging | Pass |
| Production Postmark unchanged | Pass |
| Production intake addresses unchanged | Pass |
| Maps to exactly `WATHEFNI`; no job bind; held intake | Pass |
| Old alias no longer accepts | Pass |
| Unknown / cross-tenant fail-closed | Pass |
| Sender ack off | Pass |
| Workers disabled + stopped | Pass |
| Queue / submissions / documents / inbound = 0 | Pass |
| No email sent yet | Pass |

### Verdict

**GO** — send **exactly one** synthetic PDF CV to:

```text
965f89c46a9dfbca61a0831f8ba1f631@inbound.postmarkapp.com
```

Keep workers stopped. Do not enable sender acknowledgment. Do not send a second message until receipt is reviewed. Do not use `stg-cv-ingress-dark@inbound.wathefni.ai`.

---

## 13. Explicit non-actions (this remap phase)

- No email sent  
- No intake worker started or enabled  
- No production Postmark or production intake-address change  
- No application code deploy  
