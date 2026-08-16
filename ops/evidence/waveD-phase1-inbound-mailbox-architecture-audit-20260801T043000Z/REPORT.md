# Wave D Phase 1 — Inbound hiring mailbox architecture audit

**Stamp:** `20260801T043000Z` (evidence pack)  
**Mode:** Architecture audit only. **No production enablement. No config or code changes in this phase.**  
**Wave D Phase 2+:** not started.

**Interactive summary:** [waveD-phase1-inbound-mailbox-architecture.canvas.tsx](/Users/azizalmulla/.cursor/projects/Users-azizalmulla-Desktop-claw/canvases/waveD-phase1-inbound-mailbox-architecture.canvas.tsx)

---

## Verdict

| Question | Result |
|---|---|
| Phase 1 audit complete / architecture choosable? | **PASS** |
| Best long-term architecture clear? | **PASS** — **Option B: company forwards to Wathefni-generated address** |
| Ready to enable inbound for all companies / change production now? | **FAIL** |

---

## Recommendation (long-term)

**Primary product path:** each company keeps `careers@company.com` (or job-specific aliases) and **forwards** to a **Wathefni-generated** address on `inbound.wathefni.ai` (or Postmark hash recipient). Delivery edge = **Postmark inbound webhook**. Processing = **durable email ingress** (quarantine → malware → CV identity → held Talent Pool → explicit job admit).

| Option | Decision |
|---|---|
| A · Company connects own Microsoft/Google mailbox | **Premium / later** — Gmail foundation exists; live sync blocked; M365/IMAP not implemented |
| B · Forward to Wathefni-generated address | **Best long-term core** — matches code + owner target architecture |
| C · Wathefni hosts a full dedicated recruitment inbox | **Avoid as primary** — highest ops/security/MX cost; Postmark+alias already provides the hosted edge |

Avoid temporary shortcuts: do not revive sync-first mailbox ingestion as the main product, and do not run customer mailboxes as a Wathefni mail host.

---

## Current-state audit

### What already exists

- **Wathefni-controlled inbound (default path):** `intake_addresses`, `resolve_intake_address`, `POST /webhook/postmark/inbound`, `durable_email_ingress`, worker + ops monitor.
- **Kill switches:** `WATHEFNI_INBOUND_EMAIL` (default off), Postmark inbound secret required, `WATHEFNI_MAILBOX_SYNC` (default off).
- **Unified CV layers:** `inbound_cv_authority`, `inbound_cv_intake`, processing/adapters/wave4 cutover, retention policy.
- **Shared import core:** `register_imported_cv` → held applications (`needs_role` / `import_review`) excluded from live Candidates/Ranking until admit.
- **Optional mailbox connector:** Gmail OAuth helpers; M365/IMAP declared but not live; `run_mailbox_sync` fails live with `durable_scan_and_identity_authority_required`.
- **Microsoft Graph mail today:** primarily **outbound** send, not CV ingest.

### Why gated / not general GA

- Default-off until durability, malware, identity, and kill-switch were proven.
- Continuous freeze (2026-07-26): **WATHEFNI-only** automation; no external tenants; no Gmail sync; no sender ack.
- Staging/prod Postmark routing isolation remains an ops hazard for broad enablement.
- Intake Operations UI removed from HR product (backend ops retained).

### Read-only production observation (2026-08-01)

- `WATHEFNI_INBOUND_EMAIL=on` on orchestrator service.
- `wathefni-inbound-intake-worker.timer` and `wathefni-inbound-ops-monitor.timer` **active**.
- `intake_addresses` count: **1 active** (WATHEFNI continuous recipient).
- This is **not** multi-tenant GA.

### Tenant and job matching

- **Tenant:** only from recipient → `intake_addresses` (never sender/subject/body).
- **Job:** optional `position_code` on the address; otherwise held `needs_role`; admit via existing `intake_admit`.

### Candidate / application creation

```text
Postmark webhook → durable receive → scan → CV identity → register_imported_cv
  → held Talent Pool → HR admit → open Job pipeline
```

Sender email is provenance only; weak identity matches open HR identity review (fail-closed).

### CV / attachments

Quarantine store → MIME/preflight → ClamAV → OCR/extraction. Allowlist oriented to PDF/DOCX/images; size/count limits in `IngressConfig` (webhook default ~24 MiB; attachment caps).

### Duplicate / idempotency

`(provider, provider_message_id)`, stable submission/document ids, job idempotency keys, company-scoped content SHA.

### Spam / malware / unsupported / limits

Spam headers + threshold (~5.0) → quarantine; malware fail-closed; unsupported MIME rejected; archive/PDF/image safety caps.

### Retries / dead letters / audit / manual review

Pre-durability non-2xx for Postmark retry; leased jobs + dead_letter + replay; ops summary/monitor; identity-review tables; no HR Intake Ops UI.

### Provider compatibility

| Provider | Inbound CV |
|---|---|
| Postmark | Primary, continuous WATHEFNI proven |
| Google | Optional connector; off / live blocked |
| Microsoft 365 inbound | Not implemented |
| Graph mail | Outbound, not intake |
| IMAP | Declared unsupported |

### Security / privacy / cost / setup

Recipient-only tenant isolation; Fernet mailbox secrets; encrypted quarantine preference; no auto applicant ack in freeze; Postmark+VPS+ClamAV cheaper than hosting customer mailboxes; forward setup is lowest customer effort.

---

## Gaps (before GA)

1. Self-serve intake-address create/rotate/disable + EN/AR setup checklist  
2. Job/department alias product policy + UI  
3. Multi-tenant Postmark routing isolation + commercial quotas  
4. Rebuild Gmail/M365 connectors onto durable pipeline only  
5. Sender acknowledgment / privacy notice productization  
6. Person-registry maturity for intake subjects  

---

## Implementation phases (suggested)

| Phase | Intent |
|---|---|
| **D1** | Architecture audit — **this pack** |
| **D2** | Productize forwarding behind flags (no broad enable) |
| **D3** | Multi-tenant harden (routing, quotas, retention) |
| **D4** | Alias + admit UX without Intake Ops clutter |
| **D5** | Optional Gmail → M365 via durable path |
| **D6** | GA beyond WATHEFNI after matrix + kill-switch drills |

---

## Risks

- Broad enable while Postmark still shares one process/route → cross-env leakage  
- Sync-first mailbox rewrite undoing durable/security work  
- ClamAV outage → intentional `scan_pending` backlog  
- Agency shared senders without CV identity → person collision (mitigated if identity authority stays authoritative)

---

## Key sources

- `wathefni-orchestrator/app.py` — `inbound_email_enabled`, `webhook_postmark_inbound`, `resolve_intake_address`, mailbox sync  
- `wathefni-orchestrator/durable_email_ingress.py`  
- `wathefni-orchestrator/inbound_cv_authority.py`  
- `ops/PREHIRING_HIGH_VOLUME_EMAIL_INTAKE_TARGET_ARCHITECTURE.md`  
- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_ARCHITECTURE_REVIEW.md`  
- `ops/PREHIRING_INBOUND_CV_CONTINUOUS_WATHEFNI_RELEASE_AND_FREEZE.md`  
- `ops/INTAKE_OPERATIONS_UI_REMOVAL_FINALIZATION.md`

---

## Final

**Phase 1 audit: PASS**  
**Production enablement / changes: FAIL (do not proceed in this phase)**  
**Recommended architecture: Option B — forward to Wathefni-generated address → Postmark → durable ingress**
