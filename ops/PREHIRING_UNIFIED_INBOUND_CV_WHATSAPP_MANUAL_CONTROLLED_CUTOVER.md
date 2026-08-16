# Pre-hiring Unified Inbound CV — WhatsApp + Manual Controlled Cutover

Date: 2026-07-27 (Asia/Kuwait) / canary stamp `20260727T010230Z`  
Deploy backup: `20260727T010157Z`  
Prerequisites accepted: production-dark; legacy binding backfill; forward dual-write canary  
Host: `root@76.13.63.68`  
Database: `wathefni` (production)  
Tenant: **WATHEFNI** only  

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-wa-manual-cutover/20260727T010230Z/`
- Local: `ops/screenshots/unified-inbound-cv-wa-manual-cutover/20260727T010230Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-wa-manual-cutover-20260727T010157Z/`

Artifacts:
- Authority module: `wathefni-orchestrator/inbound_cv_channel_cutover.py`
- Messages: `cv_received_talent_pool` in `candidate_messages.py`
- Surgical patcher: `ops/patch-production-app-unified-inbound-cv-wa-manual-cutover.py`
- Canary: `ops/unified-inbound-cv-wa-manual-cutover-canary.py`
- Deploy: `ops/deploy-unified-inbound-cv-wa-manual-cutover.sh`

---

## Verdict

| Gate | Result |
|---|---|
| Cut over unsolicited WhatsApp CV intake (WATHEFNI) | **PASS** |
| Cut over manual dashboard CV intake (WATHEFNI) | **PASS** |
| Inbound email remains authoritative | **PASS** |
| Job-specific WhatsApp Stage B remains authoritative | **PASS** |
| Verified-job-binding ENFORCE OFF | **PASS** |
| Live canary (29/29) | **PASS** |
| Provider/upload replay idempotency | **PASS** |
| Durable storage (not temp-only media) | **PASS** |
| Kill switch + rollback + health 200 | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| Controlled WATHEFNI WhatsApp-unsolicited + manual cutover (this task) | **GO / PASS** |
| Expand WhatsApp/manual rollout inside WATHEFNI under monitoring | **GO** (with kill switch ready) |
| Cut over inbound email | **NO-GO** |
| Enable `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` | **NO-GO** |
| Change Job-specific WhatsApp Stage B application authority | **NO-GO** |
| External tenants | **NO-GO** |

---

## What was cut over

| Channel | Authority now | Flag |
|---|---|---|
| Unsolicited WhatsApp CV (no Job) | Unified intake cutover | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on` |
| Manual dashboard CV upload | Unified intake cutover | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on` |
| Tenant allowlist | WATHEFNI only | `WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI` |
| Inbound email | **unchanged** (durable email path) | email authority flag **not set** |
| Job WhatsApp Stage B | **unchanged** (`convert_job_context_to_application`) | not modified as authority |

Durable root: `/opt/wathefni/var/intake-durable`

---

## Required behavior — proven

### Unsolicited WhatsApp

| Requirement | Proof |
|---|---|
| Durably store + validate | File at `/opt/wathefni/var/intake-durable/whatsapp_unsolicited/WATHEFNI/…pdf` |
| Scan / extract / OCR plan | ClamAV clean; shared stages; image path uses OCR-eligible plan |
| Create/reuse `cv_version` | e.g. `73144853-01c0-575e-b2e8-9a18f43b3d7f` (1 row; replay stable) |
| Person or identity review | person `9a0561df-f5da-5852-8361-d0f15c197365` linked |
| HR-visible non-actionable Talent Pool | entry `9f2c84a4-fd42-5225-88c3-7360e35166b6`, `actionable=false`, `hr_visible=true` |
| CK index (searchable, non-actionable) | `candidate_knowledge_index_jobs` + index meta |
| Honest confirmation | template `cv_received_talent_pool` (EN/AR) — no APPLY required |
| No Job application | `creates_job_application=false`; 0 apps for canary WA phones |

### Manual upload

| Requirement | Proof |
|---|---|
| Shared intake/security/processing | pre-scan + durable store + adapter/wave4 |
| Held by default | `held_by_default=true`, `auto_admit=false` |
| No automatic Job admission | cutover forces `auto_admit=False` |
| Uploader/batch provenance | `provenance.batch_id` + `uploader_user_id` preserved |
| Malware rejection | EICAR → `malware_rejected` before register |

---

## Canary matrix (`20260727T010230Z`)

| Check | Result |
|---|---|
| Health 200 pre/post | PASS |
| ENFORCE off / WA+manual on / email authority absent | PASS |
| WA PDF accept + Talent Pool confirmation | PASS |
| Provider message replay → one `intake_source_events` row | PASS (`4907b88f-…`) |
| Image/scanned OCR plan | PASS |
| DOCX accept | PASS |
| Malware reject (WA + manual) | PASS |
| Empty/invalid reject | PASS |
| Restart durability (intake-durable path) | PASS |
| Manual held accept + provenance | PASS |
| HR-visible non-actionable TP | PASS |
| CK searchable non-actionable | PASS |
| Zero WA Job applications | PASS (0) |
| No duplicate CV version / TP person | PASS |
| Unrelated apps unchanged | PASS (20→20 non-canary) |

Surgical patch actions: `helper`, `hold_cutover`, `resolve_reply`, `no_app_reply`, `manual_prescan`, `manual_cutover`.

---

## Kill switch / rollback

| Control | Evidence |
|---|---|
| Kill switch | Rename flags file → authority flags absent from process; cutover functions skip | `kill-switch-proof.txt`, `kill-switch-skip.json` |
| Restore | Flags restored; health 200 | `post-kill-restore-health.txt` |
| Rollback script | `/opt/wathefni/backups/…010157Z/ROLLBACK.sh` restores pre-cutover `app.py`, messages, flags; removes cutover module | `rollback-run.txt` → `ROLLBACK_OK`, health 200 |
| Re-apply | Cutover module + patch + flags restored after proof | `rollback-proof.txt`, `final-health.txt` |

---

## Final posture (left enabled)

```text
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
# WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE  — NOT SET
# WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL         — NOT SET
```

---

## Final GO / NO-GO for expansion and email

| Item | Decision |
|---|---|
| Keep WATHEFNI WhatsApp-unsolicited + manual cutover | **GO** |
| Expand WhatsApp/manual rollout (more volume / monitoring) | **GO** under existing kill switch + rollback |
| Later cut over inbound email | **NO-GO** (separate authorization required) |
| Enable verified-job-binding ENFORCE | **NO-GO** |
| Change Job Stage B WhatsApp application authority | **NO-GO** |

Stop condition honored: report only — ENFORCE not enabled; email not cut over; Stage B Job authority unchanged.
