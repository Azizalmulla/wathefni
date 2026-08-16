# Pre-hiring Unified Inbound CV Pipeline — Wave 3 Implementation

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260726T235921Z`  
Scope: real staging dual-write enablement + additive Manual / WhatsApp adapters  
Production mutations: **none**  
Production dual-write: **OFF** (verified)  
Wave 4 started: **no**  
Channel cutover: **no** (live email/WhatsApp/manual outcome paths remain authoritative)

Prerequisites accepted:

- Wave 0 / Phase 0 contract freeze
- Wave 1 implementation (accepted)
- Wave 2 implementation (accepted, 83/83)

## Four major waves (status)

| Wave | Scope | Status |
|---|---|---|
| **0 / freeze** | Contract freeze | Accepted |
| **Wave 1** | Envelope + email dual-write + defect fixes | Accepted |
| **Wave 2** | Shared processing + `cv_version_id` dual-write | Accepted |
| **Wave 3** | Staging dual-write + Manual/WhatsApp adapters | **This report** |
| **Wave 4** | Person Registry / Talent Pool authority / CK person refs / Job binding / universal gate | Not started |

## Executive verdict

| Gate | Result |
|---|---|
| Real staging dual-write flags enabled (staging service only) | **PASS** |
| Envelope event/item/document parity + checksum | **PASS** (17/17 staging qualify) |
| `cv_version` dual-write parity | **PASS** |
| Zero duplicate candidates / apps / OCR / classification / CK | **PASS** |
| Health 200, retries, dead letters, kill switch, rollback | **PASS** |
| Additive Manual + unsolicited WA + job WA adapters | **PASS** (local + staged hooks) |
| Unsolicited WA → durable HR-visible non-actionable Talent Pool intake | **PASS** (contract) |
| No Job application without exact Job confirmation | **PASS** |
| Manual imports held by default | **PASS** |
| Live email authoritative; no production deploy/cutover | **PASS** |
| Local suites | **97/97 PASS** |

### GO / NO-GO for Wave 4

| Decision | Result |
|---|---|
| **Wave 4 Person Registry / Talent Pool authority / CK person-subject / exact Job binding design** | **GO — with blockers below** |
| Production dual-write enablement | **NO-GO** |
| Cutting over WhatsApp/manual live paths to envelope-only authority | **NO-GO** |
| Treating adapter dual-write as Job application create authority | **NO-GO** |
| Enabling unified auto-admit by default | **NO-GO** (fail-closed) |

## Real staging parity results

Host: `root@76.13.63.68`  
Service: `wathefni-orchestrator-staging.service` (`127.0.0.1:8011`)  
DB: `wathefni_staging` via `WATHEFNI_DATABASE_URL`  
Evidence: `/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave3/20260726T235903Z`  
Local copy: `ops/screenshots/unified-inbound-cv-wave3/qualification.json`

### Staging flags (drop-in `unified-inbound-cv.conf`)

```text
WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER=on
WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS=on
WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING=on
```

Production unit: **no** `unified-inbound-cv.conf`; envelope dual-write **off**.

### Qualify matrix (17/17 PASS)

| Check | Result | Detail |
|---|---|---|
| `health_200` | PASS | 200 |
| `staging_env` | PASS | staging |
| `modules_importable` | PASS | |
| `staging_db_connect` | PASS | wathefni_staging |
| `envelope_idempotent` | PASS | one stable event id on replay |
| `one_envelope_event` | PASS | 1 |
| `document_checksum_parity` | PASS | 1 link with matching SHA |
| `cv_version_dual_write_parity` | PASS | stable `cv_version_id` |
| `whatsapp_unsolicited_adapter` | PASS | |
| `zero_duplicate_authority_writes` | PASS | candidates 97→97, apps 86→86, OCR 41→41, classification 0→0, CK jobs 6467→6467 |
| `retry_helper` | PASS | retrying |
| `dead_letter_helper` | PASS | dead_letter |
| `malware_kill_switch` | PASS | |
| `rollback_flag_off_skips` | PASS | dual_write_disabled |
| `job_gate_fail_closed` | PASS | |
| `staging_commit` | PASS | |
| `production_dual_write_untouched` | PASS | |

Deploy notes:

- Full `app.py` replace was **rejected** (missing staging-only modules such as `talent_pool_auto_email_classification`).
- Successful path: module install + **surgical** `ops/patch-staging-app-unified-inbound-cv-wave3.py` + staging-only systemd drop-in.
- Automatic rollback restored health after the failed full-replace attempt before the surgical path.

## Architecture and modules

```text
Manual Import Center ─┐
Unsolicited WhatsApp ─┼─► inbound_cv_adapters (flagged)
Job WhatsApp attach  ─┘         │
                                ▼
                     inbound_cv_intake dual-write
                                │
                                ▼
              inbound_cv_processing observe/plan/cv_version
                                │
Live authorities unchanged ─────┘
  register_imported_cv / hold_candidate_pending_media /
  convert_job_context_to_application / register_candidate_cv_file /
  durable email path
```

| Module | Role |
|---|---|
| `inbound_cv_intake.py` | `dual_write_channel_receipt`, `dual_write_manual_receipt`, `dual_write_whatsapp_receipt` |
| `inbound_cv_processing.py` | Shared stages, OCR plan, `cv_versions`, kill/retry |
| `inbound_cv_adapters.py` | Manual / unsolicited WA / job WA adapters + Job gate |
| Staging patcher | `ops/patch-staging-app-unified-inbound-cv-wave3.py` |
| Staging qualify | `ops/unified-inbound-cv-wave3-staging-qualify.py` |
| Staging deploy | `ops/deploy-unified-inbound-cv-wave3-staging.sh` |

## Adapter behavior

### 1. Manual dashboard CV uploads

- Hook after successful `register_imported_cv` in `_import_process_one_file` (non-email sources).
- Dual-writes envelope event keyed by `batch_id:content_sha256`.
- `held_by_default=True`; auto-admit still requires explicit company policy (Wave 1 fail-closed) + explicit role.
- Observes shared stages when adapter shared-processing flag is on.
- Does **not** replace Import Center / `register_imported_cv`.

### 2. Unsolicited WhatsApp CVs

- Hook after `hold_candidate_pending_media` INSERT (same TX, savepoint-guarded).
- Dual-writes envelope with `hr_visible=true`, `actionable=false`, Talent Pool intake metadata.
- Provider-message replay protection via unique `(company, channel, provider, account, external_event_id)`.
- **No Job application** created by the adapter (`creates_job_application=False`).
- Shared provider plan: local → Mistral OCR → GPT rescue for image/scanned cases.

### 3. Job-specific WhatsApp CVs

- Hook after successful `register_candidate_cv_file` when source is WhatsApp.
- Dual-writes envelope linked to existing `app_key` / `apply_code`.
- Adapter never creates the application; Stage B / live attach remains authoritative.
- Job gate requires exact selection + confirmation for any future create path.

## Dashboard / HR visibility

| Path | Visibility |
|---|---|
| Manual held imports | Existing Import Center / held statuses (`needs_role` / `import_review`) |
| Unsolicited WhatsApp | Durable envelope item with `talent_pool_intake=true`, non-actionable; pending media still holds temporary bytes |
| Job WhatsApp | Existing application + CV attach; envelope mirrors receipt |
| Ranking / lifecycle | Unchanged exclusions for held/unsolicited; no adapter Job mutation |

Wave 4 should promote envelope Talent Pool intake into first-class HR list UI bound to Person Registry — not done here.

## Tests

### Local

```bash
cd wathefni-orchestrator
.venv/bin/python -m unittest \
  test_unified_inbound_cv_wave3 \
  test_unified_inbound_cv_wave2 \
  test_unified_inbound_cv_wave1 \
  test_unified_inbound_cv_phase0_contracts
```

**97/97 PASS** @ `20260726T235921Z`

Wave 3 scenarios covered offline:

- CV only (unsolicited)
- CV then apply / apply then CV (job adapter)
- Role name with CV (manual held)
- Multiple / replacement CVs
- Image / scanned PDF / DOCX provider plans
- Corrupt / password / unsupported
- Concurrent/replayed provider message id
- Cross-tenant isolation
- Zero downstream Job mutations (adapters do not INSERT applications/candidates)

### Staging

**17/17 PASS** @ evidence `20260726T235903Z` (see above).

## Retries, dead letters, kill switch, rollback

| Control | Proof |
|---|---|
| Retry / DLQ helpers | Staging qualify |
| Malware stage kill switch | Staging qualify |
| Flag-off rollback skip | Staging qualify (`dual_write_disabled`) |
| Deploy rollback | Failed full `app.py` replace auto-rolled back; health restored to 200 |
| Staging drop-in removal | Documented: delete `unified-inbound-cv.conf`, daemon-reload, restart staging |

## Production posture

- No production deploy.
- No production dual-write flags.
- Live email remains authoritative for user-visible email outcomes.
- WhatsApp replies and manual import outcomes still owned by existing live functions.

## Wave 4 entry blockers

1. Accept this Wave 3 report.
2. Design Person Registry / Talent Pool projection for envelope subjects without rewriting source history.
3. Exact Job binding service before any Link-to-Job / Stage B authority merge.
4. Keep production dual-write OFF until a separate production-dark then canary authorization.
5. Do not cut over channel live paths until Talent Pool HR UI + identity review are qualified.

## Artifacts

- `wathefni-orchestrator/inbound_cv_adapters.py`
- Extended `inbound_cv_intake.py` (manual/WhatsApp dual-write)
- Local hooks in `app.py` (+ surgical staging patch)
- `ops/deploy-unified-inbound-cv-wave3-staging.sh`
- `ops/patch-staging-app-unified-inbound-cv-wave3.py`
- `ops/unified-inbound-cv-wave3-staging-qualify.py`
- `ops/screenshots/unified-inbound-cv-wave3/qualification.json`
- This report: `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_WAVE_3_IMPLEMENTATION.md`

## Module fingerprints (local Wave 3)

| Module | SHA-256 |
|---|---|
| `inbound_cv_adapters.py` | `3d7c7e8934e62ede8f54cc664fc3ace29cfe0e16a39793e57f4b118d88c10c5e` |
| `inbound_cv_intake.py` | `d4bad0838c7757431d267ebb27b4941c85acdf7c7173b546bfca33b2fa0ccdb9` |
| `inbound_cv_processing.py` | `ffee7b7e6ab500061628d7760259bcff5b65c8b435607bacbc4f84791774aa97` |
| `durable_email_ingress.py` | `908381b92aef24dc64743c921b92cd9b3e54a0193f1932636ec95e6bcf9df1e7` |
| `test_unified_inbound_cv_wave3.py` | `8a12cdca7aaa7c8400942ef61274dc1da600fab2580eca060c12fa5b7d86241b` |
