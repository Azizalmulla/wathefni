# Pre-hiring Unified Inbound CV Pipeline — Wave 2 Implementation

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260726T234826Z`  
Scope: shared security and CV-processing authority after accepted Wave 1  
Production mutations: **none**  
Production dual-write enablement: **none**  
Wave 3 started: **no**  
WhatsApp / manual cutover: **no**

Prerequisites accepted:

- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_ARCHITECTURE_REVIEW.md`
- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_PHASE_0_CONTRACT_FREEZE.md`
- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_WAVE_1_IMPLEMENTATION.md`

## Four major waves (status)

| Wave | Scope | Status |
|---|---|---|
| **0 / freeze** | Contract freeze | Accepted |
| **Wave 1** | Intake envelope + email dual-write + three defect fixes | Accepted |
| **Wave 2** | Shared security / CV-processing authority + `cv_version_id` dual-write | **This report** |
| **Wave 3** | Manual + unsolicited WhatsApp adapters | Not started |
| **Wave 4** | Person Registry / Talent Pool / CK person refs / Job binding / universal gate | Deferred |

## Executive verdict

| Gate | Result |
|---|---|
| Live email pipeline remains authoritative and behavior-compatible | **PASS** |
| Shared stage catalog generalized (accept → validate → scan → extract → OCR → rescue → facts → cv_version → classify → CK) | **PASS** |
| Stages idempotent, retryable, versioned, observable; DLQ + kill switches | **PASS** |
| `cv_version_id` dual-write first; no `app_key` reader cutover | **PASS** |
| Staging-style envelope dual-write parity + zero-duplicate proof | **PASS** (local staging simulation) |
| Image / scanned PDF / Arabic / English / bilingual / DOCX / corrupt / password / unsupported / malware cases | **PASS** |
| WhatsApp + manual remain on current paths | **PASS** |
| Production deploy / production dual-write | **NO** (correct) |

### GO / NO-GO for Wave 3

| Decision | Result |
|---|---|
| **Wave 3 manual + WhatsApp adapters (local additive design)** | **GO — with blockers below** |
| Enabling envelope or `cv_version` dual-write in production without authorized staging parity on a real staging DB | **NO-GO** |
| Cutting over WhatsApp or manual before Wave 2 acceptance + Wave 3 design freeze | **NO-GO** |
| Treating `cv_versions` as the sole reader authority | **NO-GO** (dual-write only; `app_key` readers stay live) |
| Big-bang replacement of email job handlers | **NO-GO** |

## Architecture and modules

```text
Postmark / durable_email_ingress (authoritative wrappers)
  → shared stage observation (optional ledger)
  → validate / scan / identity / accepted prepare / extract (existing handlers)
  → cv_extraction: local → Mistral OCR → GPT rescue
  → evidence + facts (app_key keyed)
  → talent_pool_auto_email_classification (canary)
  → additive cv_versions dual-write (flagged)
  → CK index workers (separate; still app: refs)

inbound_cv_intake (Wave 1 envelope; staging dual-write)
inbound_cv_processing (Wave 2 shared authority)
```

### New module

`wathefni-orchestrator/inbound_cv_processing.py`

| Concern | Implementation |
|---|---|
| Stage catalog | `STAGES` + `STAGE_VERSIONS` (`unified-inbound-cv-processing-v1:<stage>:1`) |
| Email job mapping | `EMAIL_JOB_STAGE` maps live `job_type` → shared stage |
| `cv_versions` table | Stable UUID5 `cv_version_id` from company + content SHA + legacy document id |
| Stage ledger | `cv_processing_stage_runs` with unique idempotency key |
| Bridges | nullable `cv_version_id` on `candidate_cv_text_versions`, evidence, facts |
| Provider plan | `plan_extraction_providers` (local → Mistral → GPT rescue; no network) |
| Parity proof | `parity_zero_duplicate_proof` |

### Wired (behavior-compatible)

| File | Change |
|---|---|
| `app.py` | Schema bootstrap; savepoint-guarded `dual_write_cv_version` after extraction; `process_durable_email_ingress_job` observes stages when ledger enabled |
| `durable_email_ingress.py` | Co-ensure processing schema with email/envelope schema |
| Live handlers | Still call `validate_submission`, `scan_document`, identity/prepare, `process_candidate_cv_document` |

### Flags (all default OFF for production-dark)

| Flag | Role |
|---|---|
| `WATHEFNI_UNIFIED_CV_PROCESSING` | Master shared-authority / enables stage ledger |
| `WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER` | Stage run observability without master |
| `WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE` | Additive `cv_versions` dual-write |
| `WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE` | Wave 1 envelope dual-write (staging only) |
| `WATHEFNI_UNIFIED_STAGE_KILL_*` | Explicit fail-closed kills for malware / local extract / facts / cv_version |
| `WATHEFNI_CV_MISTRAL_OCR` | Existing OCR master |
| `WATHEFNI_CV_GPT_VISION_RESCUE` | Existing rescue gate |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS` | Classification worker kill |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS` | CK index worker kill |

## Shared stages

| Stage | Live email authority today | Wave 2 shared surface |
|---|---|---|
| `document_acceptance` | `intake_validation` / `accepted_intake_preparation` | Mapped + ledger |
| `mime_content_validation` | `inspect_document_safety` during scan + identity path | Mapped; safety matrix tested |
| `malware_scan` | `scan_document` + ClamAV + `inbound_cv_authority` | Mapped; fail-closed contracts pinned |
| `local_extraction` | `cv_extraction` Poppler / DOCX XML / plaintext | Provider plan + email `cv_extraction` job |
| `mistral_ocr` | `cv_extraction` when pages/images need OCR | Provider plan; kill via OCR flag |
| `gpt_vision_rescue` | Only after OCR fail / image legacy rescue | Provider plan; kill via rescue flag |
| `structured_facts` | `candidate_cv_facts.materialize_facts` inside CV worker | Reserved job maps; live path unchanged |
| `immutable_cv_version` | Closest: `candidate_cv_text_versions.version_id` | New `cv_versions` dual-write |
| `classification` | Auto-email canary enqueue | Kill via workers flag; no new enqueue |
| `candidate_knowledge_indexing` | Separate CK workers on text versions | Kill via index workers flag; still `app:` |

## Extraction / OCR provider behavior

Deterministic plan (no provider calls in Wave 2 qualification):

1. **DOCX with local text** → local XML only; OCR not primary.
2. **Digital PDF / text accepted locally** → Poppler/local only; Arabic/English/bilingual do **not** force OCR when local quality is OK.
3. **Scanned PDF / image needing OCR** → Mistral OCR eligible when `WATHEFNI_CV_MISTRAL_OCR=on`; GPT vision rescue eligible on OCR fail when rescue enabled (defaults with OCR).
4. **OCR kill switch OFF** → scanned path records `mistral_ocr_disabled`; no silent full-page GPT unless image legacy rescue path applies.

Live implementation remains in `cv_extraction.py` / `cv_docx.py` / `app.extract_candidate_cv_document`. Wave 2 does not replace those engines; it versions and observes them and dual-writes `cv_version_id`.

## Retries, dead letters, kill switches, zero-duplicate proof

| Control | Proof |
|---|---|
| Email job retry → dead letter | Existing `fail_job` / `RetryableJobError` / max attempts (unchanged) |
| Shared stage retry/DLQ helper | `mark_stage_retry_or_dead_letter` unit tested |
| Stage idempotency | Unique `(company_code, idempotency_key)` + stable run id |
| `cv_version` idempotency | Unique `(company, content_sha256, legacy_document_id)` + UUID5 |
| Envelope dual-write idempotency | One event / one document link on replay |
| Kill switches | Independent stage kills + existing OCR/classification/CK flags |
| Zero duplicate candidate/app/OCR/class/CK from dual-write | `parity_zero_duplicate_proof` + envelope module has no create/enqueue authority |

## Staging-only email envelope dual-write parity

Remote staging DB was **not** mutated in this task. Parity was qualified as a **local staging simulation** with `WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=1` inside offline tests:

| Check | Result |
|---|---|
| One envelope event per live-style submission | PASS |
| Document link count matches live documents | PASS |
| Checksum / provenance carried on document link | PASS |
| Replay does not create a second event | PASS |
| Candidate / application creates from dual-write | 0 |
| Extra OCR / classification / CK writes from dual-write | 0 |

Production dual-write remains **OFF**. Real staging DB enablement requires separate authorization after this report is accepted.

## Case matrix

| Case | How proven |
|---|---|
| Image CV | PNG safety clean + image OCR provider plan |
| Scanned PDF | `needs_ocr=True` → Mistral + rescue plan |
| Arabic / English / bilingual | Local-OK PDF does not force OCR |
| DOCX | Local XML primary plan |
| Corrupt PDF | `invalid_corrupt` / `pdf_eof_missing` |
| Password-protected PDF | `password_protected` / `pdf_encrypted` |
| Unsupported | `.doc` → `unsupported_type` |
| Malware / scanner fail-closed | Source pins on quarantine states + authority scan ledger |

## Local test results

```bash
cd wathefni-orchestrator
.venv/bin/python -m unittest \
  test_unified_inbound_cv_wave2 \
  test_unified_inbound_cv_wave1 \
  test_unified_inbound_cv_phase0_contracts
```

| Suite | Count | Result |
|---|---|---|
| Wave 2 | 26 | **PASS** |
| Wave 1 | 15 | **PASS** |
| Phase 0 | 42 | **PASS** |
| **Total** | **83** | **PASS** @ `20260726T234826Z` |

Artifact: `wathefni-orchestrator/test_unified_inbound_cv_wave2.py`

## Module fingerprints (Wave 2 local)

| Module | SHA-256 |
|---|---|
| `inbound_cv_processing.py` | `ffee7b7e6ab500061628d7760259bcff5b65c8b435607bacbc4f84791774aa97` |
| `durable_email_ingress.py` | `908381b92aef24dc64743c921b92cd9b3e54a0193f1932636ec95e6bcf9df1e7` |
| `app.py` | `ce3d0e0c30fd45a7b04a527b0f40fb083d8dc6ed2e27a6753b7f6e037c9889d4` |
| `test_unified_inbound_cv_wave2.py` | `d0d7dfd9fa316991b9c820fea7a59c3a07355c242edf2328a4f6af9a909da766` |

## Production posture

- No production deploy.
- No production enablement of envelope dual-write, processing master, stage ledger, or `cv_version` dual-write.
- Live email path remains the user-visible authority for retries, DLQ, scan, extract, classify, and candidate/application creation.
- `app_key` readers unchanged; `cv_version_id` is additive bridge only.

## Explicit non-goals (preserved)

- No WhatsApp adapter / pending-media replacement.
- No manual upload quarantine cutover.
- No CK `person:` / `subject:` refs.
- No Ranking reader cutover to `cv_versions`.
- No Wave 3 implementation in this task.

## Wave 3 entry blockers

1. Accept this Wave 2 report.
2. Authorized **real staging** enablement of envelope dual-write with live parity counters (events, checksums, zero extra candidate/app/OCR/class/CK rows).
3. Keep auto-admit fail-closed for any unified manual path (Wave 1 remediation).
4. Do not route WhatsApp/manual through shared processing until adapters are designed behind flags with rollback.
5. Keep email wrappers authoritative while adapters call shared stages.

## Artifacts

- `wathefni-orchestrator/inbound_cv_processing.py`
- `wathefni-orchestrator/test_unified_inbound_cv_wave2.py`
- Updates: `app.py`, `durable_email_ingress.py`
- This report: `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_WAVE_2_IMPLEMENTATION.md`
