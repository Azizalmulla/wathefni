# Document Extraction Foundation + pdf-inspector Evaluation — Phase 0

**Mode:** research / prototype only  
**Date:** 2026-08-04  
**Evidence:** `ops/evidence/document-extraction-phase0-20260804/`  
**Constraints honored:** no Migration Wave 1-B resume · no production deploy · no paid OCR at scale · **no job deletion** · freezes intact · Poppler remains authoritative

---

## Verdict (one sentence)

The **349** `other_ats_export` extract jobs are **orphaned leftovers from the failed Wave 1-B canary** (0 linked docs/apps); pdf-inspector is a **promising CV-only shadow router** (≈82% OCR-page agreement on a synthetic matrix) but shows **dangerous false-skip on broken encoding** — **NO-GO to change routing** until a richer Arabic/real-scan matrix and Wave 1-B queue safety fixes land.

| Scope | Verdict |
|---|---|
| Orphan provenance | **Confirmed orphans** — safe to cancel after owner approval |
| Shared document-envelope design | **GO to adopt as contract** (implement later) |
| pdf-inspector replace Poppler now | **NO-GO** |
| pdf-inspector shadow role | **Conditional GO** (CV pre-router advisor only) |
| Resume Migration Wave 1-B | **NO-GO** until §7 blockers cleared |

---

## 1. Orphan-job provenance report

**Database:** `wathefni` (production, read-only)  
**Filter:** `company_code=WATHEFNI` · `job_type=cv_extraction` · `payload.source_channel=other_ats_export` · status ∈ pending/retrying

| Field | Value |
|---|---|
| Active count | **349** (334 pending · 15 retrying) |
| Created window | **2026-08-03 21:33:10Z → 21:33:19Z** (~9 seconds) |
| Hour bucket | 100% in `2026-08-03T21` |
| Migration ACK | `8cdd3387-…` at **21:33:01Z**, wave `migration_wave1_foundation_cv_chunked`, marker **MIGW1B** |
| `migration_batches` now | **0** |
| Payload keys | `app_key`, `candidate_document_id`, `source_channel` only — **no `migration_batch_id`** |
| App key pattern | `imp-wathefni-…-WATHEFNI-IMPORT` (bulk import surrogates) |
| Linked `candidate_documents` | **0 exist / 349 missing** |
| Linked `applications` | **0 exist / 349 missing** |
| Valid current CVs | **0** |
| Attempts | 334 × attempts=0 · 15 × attempts=1 |
| Last errors | 15 × `candidate_document_missing` · 334 × empty (never claimed) |
| Verdict | **`ORPHANED_LEFTOVERS_FROM_FAILED_WAVE1B_LIKELY`** |

**Proof they are not live CVs:** every subject document UUID and every `app_key` is gone; retrying jobs already soft-fail with `candidate_document_missing`. The live email channel is separate (`email_inbound`).

**Operational harm now:** `wathefni-inbound-intake-worker` is reclaiming orphans (15 retrying), competing with live CV extraction at `TENANT_CONCURRENCY=1`.

Artifact: `ops/evidence/document-extraction-phase0-20260804/orphan/orphan_provenance.json`

### Exact safe cleanup plan (DO NOT RUN until owner approval)

1. **Preflight snapshot** (read-only): count by status; sample 20 job_ids; confirm still `doc_missing`/`app_missing` = 100%.  
2. **Dry-run SQL** listing job_ids to cancel (no write).  
3. **Cancel only** matching rows:

```sql
-- DRY RUN
SELECT job_id, status, attempts, created_at, payload->>'app_key' AS app_key,
       payload->>'candidate_document_id' AS doc_id
FROM intake_processing_jobs
WHERE company_code = 'WATHEFNI'
  AND job_type = 'cv_extraction'
  AND coalesce(payload->>'source_channel','') = 'other_ats_export'
  AND status IN ('pending','retrying','running','waiting_quota','waiting_budget')
  AND created_at >= '2026-08-03 21:33:00+00'
  AND created_at <  '2026-08-03 21:34:00+00'
  AND NOT EXISTS (
    SELECT 1 FROM candidate_documents d
    WHERE d.document_id::text = coalesce(payload->>'candidate_document_id', subject_id)
  );

-- EXECUTE (owner-approved only)
UPDATE intake_processing_jobs
SET status = 'cancelled',
    last_error_code = 'orphan_wave1b_cancelled',
    last_error_detail = 'phase0_owner_approved_cleanup',
    updated_at = now(),
    leased_by = NULL,
    lease_expires_at = NULL
WHERE company_code = 'WATHEFNI'
  AND job_type = 'cv_extraction'
  AND coalesce(payload->>'source_channel','') = 'other_ats_export'
  AND status IN ('pending','retrying','running','waiting_quota','waiting_budget')
  AND created_at >= '2026-08-03 21:33:00+00'
  AND created_at <  '2026-08-03 21:34:00+00'
  AND NOT EXISTS (
    SELECT 1 FROM candidate_documents d
    WHERE d.document_id::text = coalesce(payload->>'candidate_document_id', subject_id)
  );
```

4. **Post-check:** active `other_ats_export` = 0; `email_inbound` pending unchanged; no application rows deleted.  
5. **Do not** hard-DELETE rows in Phase 0 (retain audit); cancel is enough to stop worker drain.  
6. **Do not** flip OCR/migration flags as part of cleanup.

**Cleanup status:** **NOT EXECUTED** (awaiting owner approval).

---

## 2. Long-term shared document-processing foundation

### 2.1 Principles

- **One envelope, many processors** — shared isolation, provenance, authority, jobs, cost, cancel/rollback/audit.
- **Never force** identity docs, contracts, payslips, or CSV imports through CV parsing or Mistral OCR.
- Specialized processors stay separate: CV spine · identity GPT/HR · contracts/storage · generated payslips/offers · structured imports.

### 2.2 Canonical document envelope (`document_envelope@1`)

```json
{
  "contract": "document_envelope@1",
  "company_code": "WATHEFNI",
  "subject_type": "application|employee|offer|payroll_payslip|import_row|other",
  "subject_key": "string",
  "file_id": "uuid|null",
  "content_sha256": "hex",
  "source_channel": "email_inbound|whatsapp|bulk_import|migration_wave1|hr_upload|ess_upload|generated|mirror",
  "migration_batch_id": "uuid|null",
  "document_class": "cv|identity|contract|payslip|offer|other",
  "authority_label": "held|machine_extracted|human_corrected|human_verified|mirror_only|generated|needs_review",
  "processing": {
    "route": "none|local_text|poppler|pdf_inspector_shadow|mistral_ocr|gpt_vision|generated|mirror",
    "provider": "local|mistral|openai|none",
    "model": "string|null",
    "request_id": "string|null",
    "pages_local": [1],
    "pages_ocr": [2],
    "quality_ok": true,
    "confidence": 0.0,
    "estimated_cost_usd": 0.0,
    "billable_pages": 0,
    "job_id": "uuid|null",
    "shadow": { "pdf_inspector": { "pdf_type": "mixed", "pages_needing_ocr": [2], "agreement": true } }
  },
  "text_ref": "pointer",
  "structured_ref": "pointer",
  "retention_class": "inbound_cv|employee_doc|payroll|ephemeral_synthetic"
}
```

### 2.3 Shared platform services (cross-processor)

| Service | Requirement |
|---|---|
| Tenant isolation | `company_code` on every job + envelope; allowlists for synthetic waves |
| Job tracking | Prefer `intake_processing_jobs` **or** sibling table with same lease/retry/DLQ semantics |
| Retries / DLQ | max attempts, exp backoff, dead_letter, replay |
| Cost / page caps | per-job + daily billable page budget (today quotas are 0/unbounded — must become real) |
| Cancellation | delete/rollback of subject **must** cancel jobs by `job_id` / subject / `migration_batch_id` |
| Rollback | module rollback + job cancel + residual includes queues |
| Audit | append-only events with envelope snapshot |
| Provenance | route, model, pages, cost, authority — one schema |
| Priority lanes | `live_cv` vs `migration_bulk` vs `backfill` so synthetic floods cannot starve email |

### 2.4 Processor map (stay separate)

| Processor | Input | OCR? | Authority |
|---|---|---|---|
| CV spine | PDF/DOCX/image/text | Poppler → optional Mistral → V2 | held / machine / human |
| Identity | Civil ID, passport, residence, work permit, medical | GPT vision (WA) or HR-entered | proposal never gov-verified |
| Contracts / offers | uploads or generated PDF | none by default | checklist / generated |
| Payslips | structured mirror/native | **never OCR** | mirror_only / native display |
| Structured imports | CSV/XLSX | none | dry-run/commit rules |

Target routing for PDFs that **do** need text:

```text
PDF → (shadow: pdf-inspector) → Poppler authoritative today
    → good native pages locally
    → scanned/broken pages → Mistral
    → quality validation
    → specialized module extractor (CV vs identity vs …)
```

---

## 3. pdf-inspector shadow benchmark results

**Script:** `wathefni-orchestrator/scripts/phase0-pdf-inspector-shadow-bench.py`  
**Artifact:** `ops/evidence/document-extraction-phase0-20260804/bench/shadow_benchmark.json`  
**Paid OCR called:** **false**  
**Authoritative router:** Poppler `assess_pdf_pages`

### Matrix (11 fixtures)

| ID | Category | Poppler OCR pages | Inspector type | Inspector OCR pages | Agree? |
|---|---|---|---|---|---|
| cv_en_digital | English CV digital | [] | text_based | [] | yes |
| cv_ar_digital_translit | Arabic proxy (transliteration) | [] | text_based | [] | yes |
| cv_bilingual_digital | Bilingual | [] | text_based | [] | yes |
| cv_multicolumn_digital | Multi-column | [] | text_based | [] | yes |
| cv_scanned_image_only | Scanned | [1] | scanned | [1] | yes |
| cv_mixed_digital_plus_scan | Mixed | [2] | image_based | [1,2] | **no** (extra OCR) |
| cv_broken_encoding | CID/broken | [1] | text_based | [] | **no** (**false skip**) |
| contract_table_heavy | Tables | [] | text_based | [] | yes |
| identity_civil_id_proxy | Identity digital | [] | text_based | [] | yes |
| contract_offer_en_real | Real offer EN | [1] | text_based | [1] | yes |
| contract_offer_ar_real | Real offer AR | [1] | text_based | [1] | yes |

### Summary metrics

| Metric | Value |
|---|---|
| Agreement rate (OCR page sets) | **9/11 = 81.8%** |
| False OCR skips vs Poppler | **1** (broken encoding) |
| Extra OCR vs Poppler | **1** (mixed → over-OCR) |
| Projected OCR pages (Poppler) | 5 |
| Projected OCR pages (inspector) | 5 |
| Projected $ @ $0.004/page | **$0.020** either way on this tiny matrix |
| Speed | Both sub-second locally on this matrix; inspector detect typically tens of ms |

### Qualitative comparison (honest limits)

| Dimension | Finding |
|---|---|
| Extracted-text quality | Digital EN: both fine. Inspector Markdown useful when present. |
| Arabic/RTL integrity | **Not proven** — true Arabic glyph PDFs with embedded fonts were not in matrix (Helvetica limitation). Offer AR real PDF agreed on needing OCR page 1. |
| Reading order / columns | Multi-column synthetic: both accepted local; inspector flagged no columns on this toy fixture. |
| Tables/sections | Table-heavy digital: both local; inspector did not mark tables on toy PDF. |
| Page classification | Strong on pure digital vs pure scanned; **mixed** classified `image_based` aggressively. |
| False OCR skips | **Critical:** broken-encoding marked `text_based` with **empty** `pages_needing_ocr` while Poppler correctly wants OCR. |
| Downstream field accuracy | **Not measured** (would need OCR/LLM — out of Phase 0 cap). |
| Cost/throughput savings | **No savings on this matrix**; potential savings exist on large digital CV corpora if false-skip risk is solved. |

### Expected OCR cost/throughput savings (projection, not measured at scale)

| Scenario | Projection |
|---|---|
| Digital CV bulk (mostly text_based) | High savings if inspector + Poppler **agree** local — avoid Mistral entirely |
| Scanned bulk | No savings (both send pages to OCR) |
| Mixed | Inspector may **increase** cost if it over-OCR digital pages |
| Broken encoding / Arabic CID | Inspector may **under-OCR** → quality regressions unless Poppler veto remains |
| Migration Wave 1 `.txt` | **$0 OCR** already; savings irrelevant — queue enqueue is the real cost |

**Recommendation:** keep **Poppler veto**: inspector may only *add* OCR pages or advise; it must not suppress Poppler `needs_ocr` until false-skip rate is ~0 on a Kuwait bilingual + real-scan matrix.

---

## 4. pdf-inspector GO / NO-GO and recommended role

| Decision | Verdict |
|---|---|
| Replace Poppler as authoritative router | **NO-GO** |
| Change production routing | **NO-GO** |
| Shared pre-OCR layer for all modules now | **NO-GO** |
| CV-only **shadow** advisor (log disagreement) | **Conditional GO** |
| Required before Migration Wave 1-B | **NO** |

**Recommended role:** optional **CV PDF pre-processing/router advisor** in shadow mode inside `cv_extraction.extract_cv_document`, emitting envelope `processing.shadow.pdf_inspector` while Poppler remains SoR. MIT license — low legal risk. Packaging native wheels on prod VPS is an ops risk for a later wave.

---

## 5. Smallest implementation wave (after orphan cleanup approval)

**Document Extraction Wave 0-A — Envelope + shadow logger (staging)**

1. Owner-approved orphan cancel (prod) — separate change-control.  
2. Staging-only: write `document_envelope@1` from CV extract path.  
3. Staging-only: pdf-inspector shadow compare vs Poppler; metrics only.  
4. Expand matrix: real Arabic-font CVs, camera scans, Civil ID samples (synthetic/sanitized).  
5. **No** routing change; **no** Wave 1-B; **no** employee-doc forced OCR.

---

## 6. Fixes required before Migration Wave 1-B resumes

| # | Fix | Why |
|---|---|---|
| 1 | **Owner-approved cancel** of Wave 1-B orphan extract jobs | Stop live queue pollution |
| 2 | Tag extract jobs with **`migration_batch_id`** in payload | Isolation + residual + cancel scope |
| 3 | **Skip or defer** `ensure_application_cv_extraction_job` for large synthetic qualification (`.txt` / flag) | Prove migration without OCR/queue flood |
| 4 | **Rollback cancels** associated `intake_processing_jobs` | Prevent repeat orphan class |
| 5 | **Residual 0 includes queue jobs** | Honest GO gate |
| 6 | **Separate priority / lane** for migration vs live CV | Protect email intake (`tenant_concurrency=1`) |
| 7 | **Deadlock hardening** on chunk commit / import_items | Prior 1k canary failure |
| 8 | Re-qualify only after 1–7 | Then Lane A (pipeline) ± capped Lane B OCR |

Until then: **Migration Wave 1-B = NO-GO**.

---

## 7. What this phase did / did not do

| Did | Did not |
|---|---|
| Read-only orphan provenance | Delete/cancel jobs |
| Designed envelope + foundation | Deploy to production |
| Local shadow benchmark vs Poppler | Call Mistral / paid OCR |
| Documented Wave 1-B blockers | Resume Wave 1-B |
| Saved evidence under `ops/evidence/document-extraction-phase0-20260804/` | Change production flags |

---

## 8. Source anchors

- Orphan query evidence: `ops/evidence/document-extraction-phase0-20260804/orphan/orphan_provenance.json`  
- Bench: `…/bench/shadow_benchmark.json`  
- Script: `wathefni-orchestrator/scripts/phase0-pdf-inspector-shadow-bench.py`  
- Prior audit: `ops/SHARED_DOCUMENT_EXTRACTION_PIPELINE_AUDIT.md`  
- External: [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector) (MIT)
