# Wave D Phase 2 — Productize forwarded inbound CV email (tenant-flagged)

**Stamp:** `20260801T045345Z`  
**Mode:** Local implementation only. **No deploy. No Wave D3. No external-tenant enablement. No Gmail/M365 mailbox sync.**

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Architecture matches approved Option B (forward → Wathefni intake → Postmark → durable ingress) | **PASS** |
| Create / rotate / disable / inspect tenant intake addresses | **PASS** |
| Tenant resolved only from recipient (`intake_addresses`) | **PASS** |
| Optional job alias vs `needs_role` hold | **PASS** |
| Quarantine / malware / duplicate / identity / explicit admit path preserved | **PASS** (unchanged durable pipeline; D2 gates before route) |
| EN/AR forwarding setup instructions | **PASS** |
| Status + last-received health without Intake Operations UI | **PASS** |
| Tenant flags + quotas (fail-closed allowlist) | **PASS** |
| Enablement limited to WATHEFNI / test tenants | **PASS** |
| External tenants / mailbox sync not enabled | **PASS** |
| Local security + E2E evidence | **PASS** (19/19 product smoke + 3/3 dashboard vitest) |

---

## Architecture changes

**Product path (unchanged edge, productized control plane):**

```
company careers@ / recruitment mailbox
  → customer forwarding rule
  → tenant Wathefni intake address (inbound.wathefni.ai)
  → Postmark inbound webhook
  → durable_email_ingress (quarantine → malware → identity → held pool → explicit HR admit)
```

**New control plane (`inbound_intake_product.py` + Settings APIs):**

1. **Global kill-switch** `WATHEFNI_INBOUND_EMAIL` (existing).
2. **Allowlist** `WATHEFNI_INBOUND_ALLOWED_COMPANIES` (default: `WATHEFNI` + obvious test tenants such as `INBOUND*` / `*TEST*`). External companies fail closed.
3. **Tenant flag** `company_settings.inbound_forwarding_enabled` (default on when allowlisted; explicit `false` blocks resolve).
4. **Tenant quotas** `company_settings.inbound_quotas` stored + surfaced; applied as overrides into `IngressConfig` when non-zero (commercial still defaults to 0 / off).
5. **Soft-disable + rotate** — active addresses uniquely own `local_part@domain`; disable frees the name without hard-delete; rotate disables old and creates a new active recipient.
6. **Recipient-only tenancy** — `resolve_intake_address` still maps envelope recipient → `intake_addresses`, then rejects if tenant gate fails (treated as `unknown_recipient`).

**Explicitly out of scope (unchanged / not built):** Gmail or Microsoft mailbox sync; external GA enablement; Wave D3 commercial quota enforcement.

---

## UX flow

**Settings → Communications → Email & document intake** (no Intake Operations clutter restored):

1. See enablement badge + company last-received health (`last_received_at`, 7-day count).
2. Create an intake address (optional label). Default hold = **needs role** until HR assigns.
3. Optional job-specific alias (`position_code` / title) → **role_bound**.
4. Copy address → configure company forwarding (EN/AR checklist: Outlook / M365 / Gmail).
5. Rotate (disable old + mint new) or Disable when the address must stop accepting mail.
6. Inspect via list/detail APIs with per-address health.

---

## API / data changes

| Endpoint | Behavior |
|---|---|
| `GET /dashboard/prehire/integrations/intake` | List + feature (enabled/allowlisted/quotas/health) + EN/AR setup steps |
| `GET /dashboard/prehire/integrations/intake/{id}` | Inspect one address (tenant-scoped) |
| `POST /dashboard/prehire/integrations/intake` | Create (auto local_part if omitted); require tenant gate |
| `POST .../intake/{id}/disable` | Soft-disable |
| `POST .../intake/{id}/rotate` | Disable + create replacement preserving role/label |
| `DELETE .../intake/{id}` | Aliases soft-disable (no hard delete of active routing) |
| `GET/PUT /dashboard/prehire/integrations/email` | Intake block enriched with feature, steps, health; PUT can set `inbound_forwarding_enabled` / `inbound_quotas` for allowlisted tenants only |

**Schema:** partial unique index `idx_intake_addresses_local_active` (`WHERE status='active'`); drops legacy global unique index so disabled rows do not block rotate.

**Dashboard:** `types.ts` / `api.ts` clients; `EmailDocumentIntakeCard` create/copy/rotate/disable + setup steps.

---

## Security and tenant-isolation tests

Smoke: `wathefni-orchestrator/smoke-test-inbound-intake-product.py` → **19 passed, 0 failed**

Covered:

- Allowlist includes WATHEFNI/test; external `ACMECORP` blocked on create
- Cross-tenant inspect/disable → **404**
- Resolve tenant only from recipient
- Durable receive for allowlisted active address
- Disable → subsequent mail `unknown_recipient`
- Rotate → old recipient rejected; new active
- Tenant flag `inbound_forwarding_enabled=false` fails closed on resolve
- Forged active address for non-allowlisted company never resolves
- Quotas stored and surfaced
- Job alias `role_bound` vs general `needs_role`
- EN/AR setup steps present; no Intake Operations keys

Dashboard: `SettingsEmailSending.test.tsx` → **3 passed** (product language; no Intake Operations).

**Note:** Full legacy `smoke-test-inbound-email.py` path through `accepted_intake_preparation` still needs Mistral OCR locally (`ocr_required_mistral_disabled`). That is a pre-existing extraction dependency, not introduced by D2. D2 smoke covers durable receipt + gating without requiring OCR.

---

## Local end-to-end evidence

| Artifact | Path |
|---|---|
| Product smoke log | `ops/evidence/waveD-phase2-inbound-forwarding-productize-20260801T045345Z/verify/smoke-inbound-intake-product.log` |
| Dashboard vitest log | `.../verify/settings-email-sending-vitest.log` |
| Key file SHAs | `.../verify/key-files.sha256` |

**DB:** `wathefni_local_boundary` via `/tmp/waveC-local-env/postgres.test.env`  
**Env marker:** `wathefni-local-boundary-remediation-v1`

---

## Enablement posture (local)

- Global inbound can be ON for local proof.
- Tenant enablement remains fail-closed to **WATHEFNI + test allowlist**.
- External tenants are **not** enabled.
- Mailbox sync remains **off**.
- Production deploy / D3 **not started**.

---

## Follow-ups (Wave D3+, not this phase)

- Commercial quota defaults and billing-backed caps
- Postmark multi-env routing isolation for broad GA
- Optional premium Option A (customer mailbox sync) later
