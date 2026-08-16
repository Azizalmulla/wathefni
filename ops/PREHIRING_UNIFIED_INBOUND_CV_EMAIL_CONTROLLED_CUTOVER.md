# Pre-hiring Unified Inbound CV — Email Controlled Cutover

Date: 2026-07-27 (Asia/Kuwait) / deploy stamp `20260727T011622Z`  
Canary payload stamp: `20260727T011801Z`  
Prerequisites accepted: production-dark; legacy binding backfill; forward dual-write; WhatsApp + manual controlled cutover  
Host: `root@76.13.63.68`  
Database: `wathefni` (production)  
Tenant: **WATHEFNI** only  

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-email-cutover/20260727T011622Z/`
- Local: `ops/screenshots/unified-inbound-cv-email-cutover/20260727T011622Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-email-cutover-20260727T011622Z/`

Artifacts:
- Authority module: `wathefni-orchestrator/inbound_cv_channel_cutover.py` (`accept_email_inbound`, `after_email_extraction`)
- Durable ingress comment boundary: `wathefni-orchestrator/durable_email_ingress.py`
- Surgical patcher: `ops/patch-production-app-unified-inbound-cv-email-cutover.py`
- Canary: `ops/unified-inbound-cv-email-cutover-canary.py`
- Deploy: `ops/deploy-unified-inbound-cv-email-cutover.sh`

---

## Verdict

| Gate | Result |
|---|---|
| Cut over accepted inbound email CV processing (WATHEFNI) | **PASS** |
| Postmark webhook / tenant routing / ACK / ClamAV / retries / DLs unchanged | **PASS** |
| Existing email IDs + provenance preserved | **PASS** |
| Live canary (41/41) | **PASS** |
| Verified-job-binding ENFORCE OFF | **PASS** |
| Job-specific WhatsApp Stage B unchanged | **PASS** |
| External tenants / Role Profiles OFF | **PASS** |
| Kill switch + rollback + health 200 | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| Controlled WATHEFNI inbound-email authority cutover (this task) | **GO / PASS** |
| Full unified intake freeze for WATHEFNI (WA unsolicited + manual + email) | **GO** under existing kill switch + rollback |
| Enable `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` | **NO-GO** |
| Change Job-specific WhatsApp Stage B application authority | **NO-GO** |
| External tenants / Role Profiles | **NO-GO** |

---

## What was cut over

| Channel | Authority now | Flag |
|---|---|---|
| Inbound email (accepted CV processing) | Unified intake cutover | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on` |
| Unsolicited WhatsApp CV | Unified intake (prior) | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on` |
| Manual dashboard CV | Unified intake (prior) | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on` |
| Tenant allowlist | WATHEFNI only | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI` |
| Job WhatsApp Stage B | **unchanged** (`convert_job_context_to_application`) | not modified as authority |
| Verified job binding ENFORCE | **OFF** | not set |

Unchanged by design:
- Postmark webhook entry (`process_postmark_inbound` → `durably_receive_postmark`)
- Tenant routing via `intake_addresses`
- Acknowledgment boundary
- Provider MessageID idempotency
- ClamAV `file_safety_scan`
- Retry / dead-letter helpers (`replay_dead_letter`)

Cutover adds:
- Stage observe on durable email jobs
- After clean scan → `accept_email_inbound` (sender provenance only)
- After extraction completion → `dual_write_cv_version` + `after_email_extraction`

---

## Required proofs — canary `20260727T011801Z`

No-Job recipient: `92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`  
MessageID: `email-cutover-20260727T011801Z-1804d965cc`  
Inbound: `c993b8a3-3610-50a9-ba3f-08df8c4da80c`  
Submission: `94c956fc-39fe-5ee2-a5af-6b63f91d188a`  
Subject: `c83e2179-23ff-5253-b56c-63ad52a2c173`

| Requirement | Proof |
|---|---|
| One source event / item / document per attachment | event `67bd376e-…`; 2 items; 2 docs; 2 envelope doc links |
| Replay idempotency | same MessageID → `duplicate=true`, same inbound; accept replay → still 1 event |
| Scan before extraction | both docs `clean,clean` after validation/scan drain; `malware_scan` stage completed |
| Local → Mistral OCR → GPT rescue plan | PNG stages include `local_extraction`, `mistral_ocr`, `gpt_vision_rescue` |
| Person / identity-review outcome | person `05230465-…` from extracted phone `+96555572001` |
| Talent Pool for no-Job email CVs | entry `8ce5e588-…`, `actionable=false`, subject-linked |
| Reusable `cv_version` | per-doc versions e.g. `1c4cfeef-…`, `2ffa52b3-…`; replay stable |
| Candidate Knowledge indexing | CK jobs reason `email_inbound_cutover` for `person:05230465-…` |
| No duplicate candidate/person/application/CV | 0 canary apps; 1 person; accept replay no dup event; CV count stable on replay |
| Sender is provenance only | `sender_email_provenance_only=true`; sender not stored as candidate contact |
| Multi-attachment | 2 accepted attachments (PDF + PNG) |
| Retry / dead-letter / restart durability | `replay_dead_letter` → pending then cancelled; quarantine keys stored |
| Rollback | `ROLLBACK.sh` → `ROLLBACK_OK`; re-apply cutover posture |
| Health 200 / zero unrelated mutations | health 200 pre/post; applications `20→20` |

Surgical patch actions: `observe`, `extraction` (+ `ingress_already` from copied module).  
After-scan SQL corrected to use `intake_submissions.provider_message_id` / `sender_address` (`after-scan-sql-fix.txt`).

---

## Kill switch / rollback

| Control | Evidence |
|---|---|
| Kill switch | Rename flags file → email authority absent; `email_authority_enabled=False` | `kill-switch-proof.txt`, `kill-switch-skip.json` |
| Restore | Flags restored; health 200 | `post-kill-restore-health.txt` |
| Rollback script | Restores pre-email `app.py`, `durable_email_ingress.py`, prior cutover module, flags | `rollback-run.txt` → `ROLLBACK_OK` |
| Re-apply | Email cutover module + patch + flags restored | `rollback-proof.txt`, `final-health.txt`, `final-flags-live.txt` |

---

## Final posture (left enabled)

```text
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
# WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE  — NOT SET
```

---

## Final GO / NO-GO for freeze and later enforcement

| Item | Decision |
|---|---|
| Keep WATHEFNI email authority cutover | **GO** |
| Full unified intake freeze (WA + manual + email) for WATHEFNI | **GO** under kill switch + rollback |
| Later enable verified-binding ENFORCE | **NO-GO** (separate authorization; shadow-only remains) |
| Change Job Stage B WhatsApp application authority | **NO-GO** |
| External tenants / Role Profiles | **NO-GO** |

Stop condition honored: report only — ENFORCE not enabled; Stage B Job authority unchanged; external tenants remain OFF.
