# Wathefni Unified Document Processing Foundation — Production Authority Wave 1

Date: 2026-08-04  
Evidence: `ops/evidence/document-processing-foundation-wave1-20260804/`  
Production backup: `/opt/wathefni/backups/production-pre-doc-foundation-wave1-20260803T232714Z/`

## Verdict

| Scope | Result |
|---|---|
| Pre-authority qualify (9 fixtures) | **PASS** (hybrid accepted **9/9**) |
| Automatic Poppler fallback | **Proven** (stop-file + rollback) |
| GPT as automatic OCR fallback | **Disabled** (0 invocations) |
| Production CV PDF reading authority | **GO — ENABLED** (`production_authority`) |
| Hybrid materializes V2/Ranking/CK as current? | **No** (unchanged V2 after reading) |
| Non-CV forced through CV V2? | **No** |
| Generated/spreadsheet OCR | **Forbidden in route matrix** |
| Later secondary local OCR engine | **Not added** — baseline first |

## Shared foundation deployment status

**Deployed** to production + staging orchestrator modules:

| Module | Role |
|---|---|
| `document_processing_foundation.py` | Envelope helpers, route matrix, caps, worker contract, cloud-portable |
| `cv_pdf_reading_authority.py` | Hybrid primary → Poppler fallback for CV PDFs |
| `local_hybrid_pdf_engine.py` | Native-first page OCR reader |
| `cv_extraction.py` | Authority hook + GPT auto-fallback forbidden |
| `local_hybrid_pdf_engine_canary.py` | Shadow/canary only (`staging_canary` / `production_shadow`) |

Flag:

```text
WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=production_authority
WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
WATHEFNI_DOC_FOUNDATION_DAILY_OCR_COST_CAP_USD=2.0
WATHEFNI_DOC_FOUNDATION_DAILY_DOC_AI_COST_CAP_USD=5.0
WATHEFNI_DOC_FOUNDATION_MAX_SAMPLED_PDFS=50
```

Rollback:

```bash
bash /opt/wathefni/backups/production-pre-doc-foundation-wave1-20260803T232714Z/ROLLBACK.sh
```

(Proven in this wave, then re-enabled.)

## CV PDF authority behavior

1. Try local hybrid (`document_envelope@1` required, page provenance required, quality gate)
2. On timeout / exception / low quality / incomplete envelope / emergency stop → **unchanged Poppler/Mistral path**
3. Feed extracted text into **unchanged** CV Extraction V2 (Document AI), evidence, Ranking, Candidate Knowledge
4. GPT vision is **not** automatic OCR fallback

## Qualify gates (before enable)

| Gate | Result |
|---|---|
| 9 fixtures ran | PASS |
| Zero false OCR skips | PASS |
| Zero structured / Ranking evidence regression | PASS |
| V2 completion same or better | PASS |
| Poppler fallback proven | PASS |
| GPT auto fallback off | PASS |
| DOCX → same V2 | PASS |
| Image CV → Mistral → same V2, no GPT | PASS |
| Hybrid authority accepted majority | PASS (**9/9**) |

## Route matrix (complete)

| Class | Files | Reading | Structuring | OCR | Authority this wave |
|---|---|---|---|---|---|
| CV | PDF | local hybrid + Poppler fallback | CV V2 | Mistral page-level when needed | **Hybrid authoritative** |
| CV | DOCX | native + selective image OCR | CV V2 | embedded text-candidate images only | Existing DOCX |
| CV | JPG/PNG/TIFF | Mistral OCR | CV V2 | full image | Mistral; needs_review on failure |
| generic PDF | PDF | hybrid native-first | document-specific | scanned/corrupt only | Shared reading / legacy structuring |
| identity | image/PDF | shared envelope intake | identity processor | not CV V2 | **Legacy GPT vision** (audit only) |
| contract/compliance | PDF | shared hybrid reading | contract/compliance processors | when needed | Shared reading / legacy structuring |
| spreadsheet | CSV/XLSX | structured parser | schema validation | **never** | Structured import |
| generated offer | PDF | `generated` | none | **never** | Generated |
| payslip | PDF/JSON | generated or mirror | none | **never** | Mirror/generated |
| payroll mirror | JSON/CSV | `mirror_only` | none | **never** | Mirror only |

## Confirmation: CV inputs reach the same unchanged V2 layer

| Input | Reading | Reaches `run_v2_extraction` | Proof |
|---|---|---|---|
| CV PDF | hybrid (or Poppler fallback) | Yes | 9/9 fixtures |
| CV DOCX | `cv_docx.extract_docx_document` | Yes | synthetic DOCX qualify |
| CV image | Mistral OCR | Yes | rendered scanned page; no GPT |

Non-CV classes are **not** routed through CV V2.

## Identity GPT dependency + replacement plan

**Current:** `app.extract_compliance_document_metadata` for `civil_id`, `passport`, `medical`, `residency`, `work_permit` via planner/GPT vision JSON. Does **not** use CV V2 or hybrid.

**Smallest replacement qualification before changing identity authority:**

1. Put identity under shared envelope + intake foundation (no CV schema)
2. Qualify Mistral OCR or a dedicated identity reader on a labeled Civil ID/passport set
3. Match or beat current GPT field accuracy with HR confirmation still required
4. Explicit owner GO to swap reading authority
5. Do **not** use GPT as automatic OCR fallback for CV paths

## Legacy extraction authority (still)

- Identity (GPT vision)
- Contract/compliance structuring processors
- Payslip / generated / mirror (never OCR)
- Spreadsheet imports (never OCR)
- DOCX/image CV reading engines (existing), with V2 unchanged after reading

## Observed failures that could justify a future secondary local OCR

- None in the 9-fixture authority run (0 false skips; hybrid 9/9)
- Image path now ends in `needs_review` / `extraction_failed` when Mistral fails and GPT is off — track live rate before adding PaddleOCR/Surya/etc.
- Document AI dual-call non-determinism remains a provider variance (not a reading-layer false skip)

**Do not add** PaddleOCR, Surya, or GPT fallback in this wave.

## Cloud-portability proof

- Foundation modules have **no** AWS/GCP SDKs
- `document_envelope@1` + `WorkerJobContract` are container-ready async shapes
- Domain routing/authority labels survive a move to AWS or Google Cloud without redesigning module integrations

## GO/NO-GO summary

| Decision | Result |
|---|---|
| Production CV PDF hybrid authority (this wave) | **GO — enabled** |
| Shared foundation as production contract | **GO — deployed** |
| Force all docs through CV V2 | **NO-GO** (correctly refused) |
| GPT automatic OCR fallback | **NO-GO** (disabled) |
| New self-hosted OCR model now | **NO-GO** |
| Identity authority swap | **NO-GO until replacement qualified** |
