# Wave D Phase 5 — Optional customer mailbox connectors (durable pipeline)

**Stamp:** `20260801T154944Z`  
**Mode:** Local implementation only. **No deploy. No GA. No Wave D6.**  
**External tenants:** remain disabled.  
**Default product:** forwarding (D2) — mailbox connectors are **optional / premium**.

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Audit: Gmail/M365 vs durable ingress gaps | **PASS** |
| Architecture: single durable pipeline (no second ingest) | **PASS** |
| Gmail readonly scopes documented + reused | **PASS** |
| M365 Mail.Read scopes documented + provider stub | **PASS** |
| Live sync → durable ingress (not legacy import) | **PASS** |
| Idempotent sync (duplicate provider message) | **PASS** |
| Dry-run / pause (flag off) / reconnect semantics | **PASS** |
| Tenant-scoped secrets + least-privilege scopes | **PASS** |
| Settings UX: connect / status / last sync / reconnect / pause / disconnect | **PASS** |
| EN/AR + RTL screenshots | **PASS** |
| Forwarding remains default; connectors flag default off | **PASS** |
| External tenants disabled; GA/D6 not started | **PASS** |
| Local smoke 18/18 + Settings vitest 4/4 | **PASS** |

---

## Architecture

```
Default (core):  careers@company → forward → intake_addresses → Postmark → durable ingress
Premium (D5):    Gmail / M365 OAuth (read-only folder)
                    → fetch_new_messages (provider adapter)
                    → Postmark-shaped envelope (provider:gmail|m365 + message id)
                    → process_postmark_inbound / durable pipeline
                    → quarantine → malware → OCR/identity → held → explicit admit
```

**Reuse (unchanged behavior):** durable receive tables, quarantine store, ClamAV, identity authority, dedupe `(provider, provider_message_id)` + `content_sha256`, quotas/kill-switch (D3), held intake + admit (D4), replay/audit workers.

**Removed from live path:** legacy `import_batches` / `register_imported_cv` from mailbox sync.

**Routing:** company from `mailbox_connections.company_code`; durable `intake_id` from an active company intake address (created as needs_role connector route if none exists).

```mermaid
flowchart LR
  subgraph default [Default core]
    F[Company forward] --> P[Postmark webhook]
  end
  subgraph premium [Optional premium D5]
    G[Gmail readonly] --> S[run_mailbox_sync live]
    M[M365 Mail.Read stub] --> S
  end
  P --> D[durable_email_ingress]
  S --> D
  D --> Q[quarantine / malware / OCR / identity]
  Q --> H[held intake + explicit admit]
```

---

## Provider scopes (security review)

| Provider | Scopes | Notes |
|---|---|---|
| **Gmail** | `gmail.readonly` only | Existing OAuth app; Fernet-encrypted refresh tokens in `mailbox_credentials` |
| **Microsoft 365** | `Mail.Read`, `User.Read`, `offline_access` | **Dedicated** mailbox OAuth app (`WATHEFNI_M365_MAILBOX_*`) — **not** calendar SP, **not** Mail.Send outbound SP |
| Explicitly excluded | `Mail.Send`, `Mail.ReadWrite`, modify/delete | Read-only recruitment folders/labels |

**Token lifecycle:** refresh at rest (encrypted); short-lived access minted in-process; auth/network failures → `needs_reconnect` (calm HR copy); pause = `sync_enabled=false`; disconnect deletes connection + credentials.

**Tenant isolation:** all mailbox CRUD filtered by `company_code`; inbound allowlist still applies to durable receive; external tenants remain fail-closed.

**Kill switch:** `WATHEFNI_MAILBOX_SYNC` default **off** (GA not enabled).

---

## UX (Settings → Communications)

| Surface | Role |
|---|---|
| Email & document intake | **Default** forwarding create/rotate/disable (D2/D4) |
| Recruitment mailbox connector (optional) | Premium connect / status / last sync / folder / Sync now / Pause / Reconnect / Disconnect |

EN/AR + RTL. Hidden unless flag + encryption + OAuth ready (fail-closed). Copy states forwarding remains default and messages use the durable pipeline.

Screenshots: `screenshots/connector-{en,ar}-{desktop,mobile}.png`

---

## Files

| File | Role |
|---|---|
| `wathefni-orchestrator/inbound_mailbox_connectors.py` | **New** — scopes, envelope map, durable sync, M365 stub, EN/AR status |
| `wathefni-orchestrator/app.py` | Live `run_mailbox_sync` → durable; M365 provider; feature payload |
| `wathefni-orchestrator/inbound_intake_product.py` | Forwarding default + premium marker |
| `wathefni-orchestrator/smoke-test-inbound-mailbox-connectors-d5.py` | Local E2E smoke |
| `apps/wathefni-dashboard/.../SettingsPage.tsx` | `MailboxConnectorCard` EN/AR |
| `apps/wathefni-dashboard/.../types.ts` | Feature type extended |

---

## Tests & evidence

| Artifact | Path |
|---|---|
| Smoke log / JSON (18/18) | `verify/smoke-d5.log`, `verify/smoke-d5.json` |
| Vitest Settings (4/4) | `verify/vitest-settings.log` |
| Key SHAs | `verify/key-files.sha256` |
| Screenshots | `screenshots/` |
| This report | `REPORT.md` |

Key smoke proofs:
- Live sync `mode=live_durable` with durable counts
- Replay → `duplicate=1` (idempotent)
- Dry-run reports `pipeline=durable_email_ingress`
- Flag off → `mailbox_sync_disabled`
- No `batch_id` / legacy import items in live result

---

## Enablement posture

- Forwarding = default core product  
- `WATHEFNI_MAILBOX_SYNC=off` (connectors dark)  
- External tenants disabled  
- M365 live Graph fetch not GA (stub until `WATHEFNI_M365_MAILBOX_*` configured)  
- **No deploy. No D6.**

---

## Final

**PASS** — Wave D Phase 5 local: optional Gmail/M365 connectors designed and wired through the **same** durable D2/D3 pipeline, with forwarding kept as the default product.
