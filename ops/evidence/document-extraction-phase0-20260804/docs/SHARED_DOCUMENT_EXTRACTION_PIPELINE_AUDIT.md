# Wathefni Shared Document Extraction Pipeline Audit

**Mode:** research + implementation truth only  
**Date:** 2026-08-04  
**Constraints honored:** no deploy · no extraction behavior change · no paid OCR calls · no queue cleanup · no Migration Wave 1-B resume · all module freezes intact

---

## Verdict (one sentence)

Wathefni has a **real shared CV extraction spine** (durable `intake_processing_jobs` → Poppler/DOCX local → optional Mistral OCR → V2 Document AI), but **employee/compliance/payroll/offer documents do not use it** — they are either GPT-vision metadata (WhatsApp onboarding only), human-entered, or structured generation/mirrors — so the platform is **not yet one shared document-extraction OS**.

| Question | Answer |
|---|---|
| One shared extraction spine? | **Partial YES for CVs only**; **NO** across modules |
| Where is Mistral OCR called? | CV path only (`cv_extraction` / `cv_docx` selective images / `cv_extraction_v2`) |
| pdf-inspector adopt now? | **NO-GO as replacement**; **conditional GO as optional pre-router prototype** after CV-only proof |
| Resume Migration Wave 1-B? | **NO-GO** until blockers in §12 are fixed |

---

## 1. Architecture map (current truth)

```text
                         ┌─────────────────────────────────────────┐
                         │         CHANNEL INGRESS                   │
                         │  WA CV · Bulk/Import · Email · Migration  │
                         │  WA onboarding · HR hub · ESS · Renew      │
                         │  Offers (generated) · Payslips (mirror)    │
                         └───────────────┬───────────────────────────┘
                                         │
          ┌──────────────────────────────┼──────────────────────────────┐
          │                              │                              │
          ▼                              ▼                              ▼
   CV FAMILY                      EMPLOYEE/COMPLIANCE              STRUCTURED DOCS
   (shared spine)                 (separate path)                  (no OCR)
          │                              │                              │
          ▼                              ▼                              ▼
 storage (file_registry /         store_onboarding_document       offer PDF generate
 candidate_documents)             file_registry +                 payroll_payslip_documents
          │                       employee_documents +
          ▼                       compliance_documents +
 enqueue intake_processing_jobs   governed_document_versions
 job_type=cv_extraction                  │
          │                              ├─ WhatsApp: GPT vision metadata
          ▼                              └─ HR/ESS/renew: no extract
 wathefni-inbound-intake-worker
          │
          ├─ .txt/.md/.csv → local text
          ├─ .docx → cv_docx (local XML; selective image OCR)
          ├─ PDF → assess_pdf_pages (Poppler)
          │     digital pages → pdftotext
          │     needs_ocr pages → Mistral OCR (if flag on)
          │     OCR fail → GPT vision rescue (V2: force-only)
          ├─ image CV → Mistral OCR (if flag on)
          │
          ├─ contacts/dates (AR/EN deterministic)
          ├─ profile / evidence / facts
          ├─ CV Extraction V2 (Mistral Document AI annotation)
          └─ optional CK / talent-pool / embeddings (CV-only)
```

**Workers (production, read-only observed):**

| Unit | Role |
|---|---|
| `wathefni-orchestrator` | API; enqueues jobs; **does not** drain CV queue in-process |
| `wathefni-inbound-intake-worker` (+ timer) | Drains `intake_processing_jobs` (limit=1 bursts observed) |
| `wathefni-ck-index` | Candidate Knowledge index (PRODUCTION-DARK) |
| `wathefni-talent-pool-auto-email-classification` | Post-extraction classification (bounded) |
| `wathefni-document-storage-reconcile` | Employee-app **storage** finalize only (currently failed unit; not OCR) |
| Legacy `wathefni-prehire-cv-process` | Must stay **off** (direct `candidate_documents` poll) |

---

## 2. Path-by-path implementation truth

### 2.1 CV family (shared spine)

| Path | Intake → storage → queue → extract → module |
|---|---|
| **Bulk CV / Import Center** | Upload → `process_bulk_cv_import` / `register_imported_cv` → `candidate_documents` (`pending_extraction`) → `ensure_application_cv_extraction_job` → worker → held application |
| **Migration Wave 1 chunked CV** | Staged files → `_import_process_one_file` → **same** `register_imported_cv` → **same** enqueue (`source_channel=other_ats_export`) → held apps |
| **Email / ATS inbound** | Postmark → durable validation → ClamAV → identity → prep/held → enqueue `cv_extraction` (`email_inbound`) |
| **WhatsApp candidate CV** | Media → `register_candidate_cv_file` → enqueue `cv_extraction` |

**File-type routing (CV spine):**

| Type | Local | Mistral OCR | GPT rescue | V2 Document AI |
|---|---|---|---|---|
| `.txt` / `.md` / `.csv` | read bytes | **no** | no | internal/annotation if bytes allow |
| `.docx` | XML/structure (`cv_docx`) | **embedded text-candidate images only** | no | yes (whole doc) |
| Digital PDF | Poppler `pdftotext` | **no** if all pages `accepted_local` | no | yes |
| Scanned / mixed PDF | keep good pages | **failed pages only** | failed OCR pages* | yes |
| Image CV | — | full image if OCR on | after fail* | yes |

\*With `WATHEFNI_CV_EXTRACTION_V2=true` (prod), GPT rescue is **force-gated** in code even if `WATHEFNI_CV_GPT_VISION_RESCUE=true`.

### 2.2 Employee / compliance / onboarding documents

| Path | Extraction | Engine | Authoritative? |
|---|---|---|---|
| WhatsApp onboarding (Civil ID, passport, medical, residence, work permit…) | Sync GPT vision classify + metadata JSON | **GPT vision, not Mistral** | OCR proposal `authoritative: false` until HR confirms |
| HR Document Hub upload | **Skipped** (`extraction={}`) | none | HR enters / reviews |
| ESS onboarding / renew upload | **Skipped** | none | same |
| Compliance Findings Wave 1 | Read projection over stored rows | none | guidance-only; never government verified |
| Employment contract / offer_letter uploads | Store only | none | checklist / journey |
| Arabic contract link | Upload-only link to snapshot | none | not OCR |

Types dual-written to compliance when upload-synced: `civil_id`, `passport`, `medical`, `education_cert`, `residence`, `work_permit`. Contracts/offers/photos are not compliance-synced the same way.

### 2.3 Structured / generated documents (no OCR)

| Path | Truth |
|---|---|
| **Pre-hire offers** | Generated PDF from terms; served; no extraction |
| **Payroll payslips** | Materialized JSON + lines (`payroll_payslip_document@1`); download is text/JSON render; **explicitly no OCR** |
| **Attendance / employee CSV import** | Spreadsheet parse only; no PDF/OCR |

### 2.4 Search / indexing

| After extract | Scope |
|---|---|
| Voyage / semantic / Candidate Knowledge | **CV / pre-hire only** |
| Employee hub | `file_registry` list/download — **no embedding rebuild** |
| Payslips / offers | Structured DB — no semantic OCR index |

### 2.5 Privacy / retention

| Mechanism | Scope |
|---|---|
| Inbound quarantine + `inbound_retention_policy` | **Email/CV intake** objects; cleanup flags currently **off** on prod |
| Employee documents | Ordinary storage + audit; **not** inbound retention |
| Mistral OCR transport | Base64-first (no Files API retention by default); Files delete helper exists for rare uploads |
| Human authority | `preserve_human_fields` — machine never overwrites human_verified/corrected |

---

## 3. Is there one spine or several?

| Layer | Reality |
|---|---|
| **CV durable queue + extract** | **One spine** (good) |
| **Employee identity docs** | **Second spine** (GPT vision + HR) |
| **Payroll / offers / CSV** | **No extraction spine** |
| **Adapters / dual-write** | Additive observation (`inbound_cv_adapters`, unified intake) — not a second live OCR engine |
| **Legacy CV poller** | Separate path that must stay disabled |

**Duplication / inconsistency findings:**

1. **Two “OCR” brands in product language** — Mistral for CVs; GPT vision “OCR proposals” for Civil ID/passport — different engines, different queues, different authority.
2. **WhatsApp extracts; HR/app/renew do not** — intentional for LLM-free endpoints, but creates asymmetric quality.
3. **V1 cost estimate $0.004/page vs V2 success-path $0.005/page** — accounting inconsistency.
4. **Doc says prod OCR default OFF**; production currently has `WATHEFNI_CV_MISTRAL_OCR=true`.
5. **`WATHEFNI_CV_GPT_VISION_RESCUE=true` on prod** but V2 force-gates rescue — flag honesty drift.
6. **Migration rollback does not cancel `intake_processing_jobs`** — apps can be deleted while extraction jobs remain pending (confirmed).
7. **No shared canonical document envelope** across CV evidence, employee_documents extraction columns, and payroll payloads.
8. **Quotas set to 0** (`DAILY_PROCESSING_JOB_QUOTA=0` etc.) — treated as unlimited / not bounding cost today.

---

## 4. Every Mistral call site (implementation)

| Site | Endpoint | Role |
|---|---|---|
| `cv_extraction.py` `mistral_ocr_process` | `POST /v1/ocr` | Page/image OCR (`mistral-ocr-4-0`) |
| `cv_extraction.py` Files DELETE helper | `DELETE /v1/files/{id}` | Rare cleanup |
| `cv_docx.py` via image OCR helper | `/v1/ocr` | Selective DOCX embedded images |
| `cv_extraction_v2.py` `mistral_ocr_with_annotation` | `POST /v1/ocr` | OCR + document annotation |
| `cv_extraction_v2.py` chat fallback | `POST /v1/chat/completions` | Optional; **OFF** on prod (`CHAT_FALLBACK=false`) |

**Not called for:** Civil ID, passport, residence, work permit, medical, contracts, payslips, offers, attendance/employee CSV.

Pinned model: **`mistral-ocr-4-0`** (never `mistral-ocr-latest`).

---

## 5. Queues, workers, isolation, cleanup

### 5.1 Queue

| Item | Truth |
|---|---|
| Table | `intake_processing_jobs` |
| CV job type | `cv_extraction` |
| Claim | `FOR UPDATE SKIP LOCKED` + tenant fairness |
| Lease | `WATHEFNI_INTAKE_JOB_LEASE_SECONDS=180` |
| Max attempts | 5 → retry with exp backoff (5s→900s) → **dead_letter** |
| Tenant concurrency | **`WATHEFNI_INTAKE_TENANT_CONCURRENCY=1`** on prod |
| Idempotency | `candidate-document:{document_id}:extract` |
| Revive | Re-enqueue **revives** `cancelled` / `dead_letter` |

Isolation axes today: **`company_code`** + **`job_type`** + payload `source_channel` / `app_key` / `candidate_document_id`.  
**Missing:** migration_batch_id on jobs; module tag; hard priority lane for live email vs migration bulk.

### 5.2 Current orphan / backlog risk (read-only, 2026-08-04)

| Metric | Value |
|---|---|
| `cv_extraction` **pending** | **344** |
| of which `source_channel=other_ats_export` | **344** |
| `cv_extraction` retrying (`other_ats_export`) | 5 |
| `cv_extraction` completed (all channels) | 24 |
| `cv_extraction` dead_letter | 4 (email_inbound) |
| Migration marker apps / batches | 0 (apps cleaned; **jobs left**) |

**Interpretation:** Interrupted Migration Wave 1-B synthetic canary enqueued extraction for held imports, then rolled back applications without cancelling jobs. Those pending jobs still sit on the **same** WATHEFNI intake queue the live email path uses (`tenant_concurrency=1`). Worker is actively starting (`activating`).

**This audit did not cancel or clean these jobs** (owner rule).

### 5.3 Cost exposure (read-only)

| Window | Billable pages | Est. cost | Runs |
|---|---|---|---|
| Last 30 days (`cv_extraction_runs`, WATHEFNI) | **9** | **~$0.036** | 141 |

Most runs are local/cache; Mistral page volume is currently small.  
**Risk is queue contention and future bulk OCR**, not present monthly spend.

If Wave 1-B ran **10k scanned PDFs** with OCR on: order-of-magnitude **~$40** at $0.004/page (1 page/doc) plus hours of shared-queue drain — **not** the current `.txt` fixture cost (≈$0 OCR) but still enqueue flood.

### 5.4 Caps / timeouts

| Control | Value |
|---|---|
| Max PDF pages at intake | **40** (`WATHEFNI_INTAKE_MAX_PDF_PAGES`) |
| Max file bytes (intake) | 8 MiB |
| OCR HTTP timeout | 120s (V1) / 180s (V2 annotation) |
| V2 retries | 2 |
| Extraction single-flight lease | 180s (`cv_extraction_leases`) |
| Daily/monthly job quotas | **0 (= unbounded)** |

### 5.5 Arabic / EN / RTL / multi-column

| Capability | Current |
|---|---|
| Arabic alone forces OCR? | **No** (by design) |
| Digit / bidi normalize | Yes (contacts/dates) |
| Bilingual headings / Kuwait phones | Deterministic extractors |
| DOCX RTL / bidi flags | Preserved in local structure |
| Multi-column PDF reading order | Poppler-dependent; **not** a dedicated layout model |
| Broken encoding → OCR | Via quality gates / image-dominant heuristics — not Firecrawl `has_encoding_issues` |

### 5.6 Confidence, quality, rescue

| Gate | Behavior |
|---|---|
| `cv_text_quality_ok` / `page_text_usable` | Length, words, printable ratio, mojibake |
| Page dispositions | `accepted_local` · `needs_ocr` · `empty` |
| Soft-complete (no infinite retry) | `low_quality_text`, `ocr_required_mistral_disabled`, `no_text_extracted`, `file_not_found`, … |
| Rescue | GPT vision after OCR fail; **V2 force-only** |
| Cache | `cv_extraction_cache` keyed by content+pages+model+options |

### 5.7 Provenance

Stored across: `EngineCallMeta`, `cv_extraction_runs`, `cv_extraction_cache`, `application_cv_evidence_materializations.provenance`, `application_cv_fact_snapshots`, `application_cv_extraction_v2`, DOCX block provenance, `FieldProvenance` (machine vs human).

**Gap:** employee GPT-vision metadata and payroll payloads do **not** share this provenance model.

---

## 6. Canonical document-envelope recommendation

**Do not invent a second OCR stack.** Introduce a thin **Document Envelope** that all modules can attach to `file_registry` subjects:

```text
document_envelope@1
  company_code
  subject_type / subject_key          # application | employee | payroll_run | offer …
  file_id / content_sha256
  source_channel                     # email_inbound | whatsapp | bulk_import | migration_wave1 | hr_upload …
  migration_batch_id?                # optional
  document_class                     # cv | identity | contract | payslip | other
  processing:
    route                            # local_text | poppler | mistral_ocr | gpt_vision | none | generated
    model / provider / request_id
    pages_local[] / pages_ocr[]
    quality_ok / confidence
    estimated_cost_usd
    job_id?                          # intake_processing_jobs when used
  authority:
    machine_extracted | human_corrected | human_verified | mirror_only | generated
  text_ref / structured_ref          # pointers, not duplicated blobs
```

**Adoption order:** (1) CV spine emits envelope, (2) migration jobs carry `migration_batch_id`, (3) employee GPT path writes the same shape without joining the CV worker, (4) payroll/offers mark `route=generated|mirror`.

---

## 7. pdf-inspector evaluation (Firecrawl, MIT)

Library: [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector) (MIT) — Rust classifier + optional Markdown extract; `text_based` / `scanned` / `image_based` / `mixed`; `pages_needing_ocr`; confidence; encoding-issue flag; RTL/column hints claimed.

### Compared to current Poppler `assess_pdf_pages`

| Concern | Current Poppler spine | pdf-inspector |
|---|---|---|
| Digital vs scanned | Per-page text usability + image dominance | Fast stream classification (~10–50ms) |
| Mixed PDF page routing | **Already exists** | Also page-level `pages_needing_ocr` |
| Broken native text → OCR | Quality gates | `has_encoding_issues` signal |
| Arabic/RTL | Explicit product rules (Arabic ≠ OCR) | RTL support claimed — **must prove on Kuwait bilingual PDFs** |
| Multi-column | Weak / Poppler order | Claims column-aware extract |
| Mistral compatibility | Feeds page subset to `/v1/ocr` | Can feed the **same** page list |
| Licensing | Poppler system dep | **MIT** — low legal friction |
| Ops | Already proven in prod path | New native wheel/ABI surface on VPS |

### Integration point (if ever)

**Only** inside `cv_extraction.extract_cv_document` **before** or **instead of** Poppler disposition — still emitting the same page list into existing Mistral/rescue. **Not** in employee GPT path, payroll, or Migration Center UI.

### Expected benefits

Faster reject of pure scans; better encoding-broken detection; optional Markdown for V2; less Poppler variance on some PDFs.

### Risks

Arabic/RTL false “text_based” with garbage CID fonts; wheel/glibc packaging on prod; dual classifiers until Poppler retired; over-confidence skipping needed OCR.

### pdf-inspector GO / NO-GO

| Decision | Verdict |
|---|---|
| Replace current spine now | **NO-GO** |
| Shared pre-OCR router for all modules now | **NO-GO** |
| Optional CV-only classifier prototype (shadow vs Poppler) | **Conditional GO** — only after §12 blockers and a tiny synthetic matrix |
| Required for Migration Wave 1-B | **NO** |

**Recommended role:** *optional pre-OCR router / advisor on the CV spine*, never the system of record for authority, never employee-identity OCR, never a reason to reopen frozen modules.

---

## 8. Smallest justified prototype wave (only if owner wants)

**Name:** Document Extraction Wave 0 — CV Pre-OCR Router Shadow  
**Size:** staging + synthetic only; **≤20** PDFs (digital / scanned / mixed / Arabic-bilingual / broken encoding)  
**Does:** run pdf-inspector **shadow** beside Poppler; log agreement/disagreement; **no** change to live routing; **no** paid OCR beyond existing staging samples already used for CV OCR proof  
**Does not:** touch employee docs, payroll, Migration Wave 1-B, freezes, prod flags  

If disagreement rate is high on Arabic/Kuwait samples → **stop**. If high agreement → consider Wave 0-B to let pdf-inspector **propose** `pages_needing_ocr` with Poppler veto.

**Not justified as a blocker** for Migration Wave 1-B. Wave 1-B blockers are operational (below), not pdf-inspector.

---

## 9. Current Mistral usage summary

| Item | Prod truth |
|---|---|
| OCR flag | **ON** (`WATHEFNI_CV_MISTRAL_OCR=true`) |
| V2 | ON; chat fallback OFF |
| 30-day billable pages | **9** (~$0.04) |
| Primary cost risk | Bulk enqueue of extract jobs + future scanned PDFs, not today’s burn |
| Migration `.txt` fixtures | Local text — **$0 OCR**, but **still enqueue** `cv_extraction` |

---

## 10. Migration Wave 1-B — blockers before resume

Owner must approve fixes; this audit does **not** implement them.

1. **Cancel/isolate orphan backlog** — ~344 pending `other_ats_export` `cv_extraction` jobs (and 5 retrying) left after failed canary; they share the live WATHEFNI intake queue. *Cleanup requires explicit owner approval.*
2. **Migration path must not flood live extraction** — add skip-enqueue **or** cancel-on-rollback **or** deferred/low-priority lane tagged `migration_batch_id` for Wave 1 synthetic commits.
3. **Hard residual definition** — residual 0 must include `intake_processing_jobs` for canary markers, not only applications/migration_batches.
4. **Deadlock hardening** — 1k canary failed with Postgres deadlock on `import_items` / lifecycle cleanup; reduce worker burst / shorten transactions / serialize chunk commits before re-running 1k/10k.
5. **Decide OCR scope for Wave 1-B** — recommended: Lane A = migration pipeline on `.txt` with **no live OCR queue pressure**; Lane B = ≤10 real OCR docs / ≤20 pages separate.
6. **Flag honesty** — document OCR-on-prod vs docs; clarify GPT rescue force-gate under V2.
7. **Do not** enable real-customer migration, millions claim, Migration Center UI, or Wave 2.

Until 1–5 are addressed and owner re-approves, **Migration Wave 1-B production synthetic qualification remains NO-GO**.

---

## 11. Freezes / out of scope

Unchanged and not reopened: Employees 360 · Onboarding · Attendance · Leave · Shifts · Payroll · Compliance · Analytics · Action Inbox · Platform Assistant · Module-Aware Shell · Setup Console · Migration Wave 1 freeze (staging only; prod synthetic not frozen GO).

This audit: **research only**. No deploy, no OCR API spend, no queue mutation, no Wave 1-B resume.

---

## 12. Source anchors

- `wathefni-orchestrator/cv_extraction.py` — Poppler assess, Mistral OCR, quality, cache, leases  
- `wathefni-orchestrator/cv_extraction_v2.py` / `_internal.py` / `_schema.py` — Document AI path  
- `wathefni-orchestrator/cv_docx.py` — DOCX local-first  
- `wathefni-orchestrator/durable_email_ingress.py` — job queue, lease, retry, DLQ  
- `wathefni-orchestrator/app.py` — `ensure_application_cv_extraction_job`, `register_imported_cv`, `process_candidate_cv_document`, WhatsApp CV  
- `wathefni-orchestrator/migration_wave1_cv_foundation.py` — chunked CV → import core (enqueues extract via register)  
- `wathefni-orchestrator/kuwait_pilot_document_journey.py` — employee doc journey  
- `wathefni-orchestrator/inbound_retention_policy.py` / `intake_quarantine_storage.py`  
- `wathefni-orchestrator/payroll_payslip_wave3.py` — no OCR  
- `wathefni-orchestrator/docs/CV_OCR_MISTRAL.md`, `docs/CV_DOCX_EXTRACTION.md`  
- External: [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector) (MIT)

---

## 13. GO / NO-GO table

| Scope | Verdict |
|---|---|
| Research / this audit | **GO** |
| Claim “one shared extraction OS across all modules” | **NO-GO** (CV-only today) |
| pdf-inspector replace Poppler now | **NO-GO** |
| pdf-inspector CV shadow prototype | **Conditional GO** (owner-approved, staging, tiny) |
| Clean 344 orphan jobs | **NO-GO until owner approval** |
| Resume Migration Wave 1-B | **NO-GO** until §10 blockers cleared |
| Call paid OCR / change extraction flags in this wave | **NO-GO** |
