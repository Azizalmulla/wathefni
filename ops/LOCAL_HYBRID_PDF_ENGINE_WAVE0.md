# Wathefni Local Hybrid PDF Engine — Wave 0

Date: 2026-08-04  
Mode: staging / offline implementation + qualification  
Evidence: `ops/evidence/local-hybrid-pdf-engine-wave0-20260804/`  
Constraints honored: no Firecrawl hosted API · no production routing change · no Migration Wave 1-B · no silent pdf-inspector upgrade · no document-type parsing inside the engine

## Verdict

| Scope | Result |
|---|---|
| Upstream pin | **Keep Python `pdf-inspector==0.2.6`** |
| Experimental engine implemented | **Yes** (`local_hybrid_pdf_engine.py`) |
| Corpus gates (560, OCR simulated) | **PASS** |
| Real Mistral proof (≤30 pages) | **PASS** (12 billable pages, $0.048) |
| CV-only **staging** canary | **CONDITIONAL GO** (flagged alternate path; owner approval required) |
| Production influence / default cutover | **NO-GO** |

## 1. Upstream truth and pin

| Item | Value |
|---|---|
| Safest integration | **Current Python PyO3 binding** |
| Pin | `pdf-inspector==0.2.6` |
| PyPI macOS arm64 wheel SHA-256 | `d2b2aaa95b242da38630bbd0644ffe9a929466f9c4e6406d6f1957b59b413d08` |
| Local extension SHA-256 | `696e3bde5c1114fea03f9edd4c4276b27df4104eebdc7f034761b457ab27f53e` |
| PyPI sdist SHA-256 | `5bb387f39bf7a93b02b49188b670b9798f8ccc7e58f68eee5883a512aa05ceb2` |
| GitHub tags observed | up to `v0.7.0` (semver **diverges** from PyPI) |
| npm `@firecrawl/pdf-inspector` | `1.12.0` (separate version line) |
| crates.io / main Cargo.toml | reports `0.1.7` — **not** used as pin |
| Production upgrade this wave | **Forbidden** |

Why not Node/Rust CLI/service: Wathefni orchestrator is Python; 0.2.6 is already on the production venv for shadow Wave 1; page API `extract_pages_markdown` is sufficient; npm/GitHub numbering is inconsistent with PyPI.

Artifact: `upstream/PIN.json`

## 2. Architecture

```text
PDF bytes
  → limits (max pages/bytes/timeout/retries/projected-cost)
  → pdf-inspector extract_pages_markdown (native Markdown + needs_ocr)
  → per-page decision:
        inspector needs_ocr → OCR
        OR native fails quality gate (mojibake / empty / corrupt) → OCR
        OR usable native (Arabic-aware) → keep local
  → Mistral OCR only selected pages (or simulate)
  → merge pages in order with provenance
  → cache(content_sha256, inspector_version, ocr_model, engine_version)
  → document_envelope@1
```

**Not inside this engine:** CV field parsing, identity, contracts, compliance. Downstream processors consume the envelope.

### Implementation

| Piece | Path |
|---|---|
| Engine | `wathefni-orchestrator/local_hybrid_pdf_engine.py` |
| Corpus qualify (OCR off) | `scripts/wave0-local-hybrid-pdf-engine-qualify.py` |
| Real OCR proof | `scripts/wave0-local-hybrid-pdf-engine-real-ocr.py` |
| Wired into `extract_cv_document`? | **No** |
| Production flag? | **None added** |

### Caps / safety

- max pages (default 10; corpus qualify used 15)
- max bytes 20–25 MiB
- timeout / retries on OCR
- projected-cost cap
- one failed OCR page does not discard successful native/OCR pages
- paid OCR default **off** (`allow_paid_ocr=False` → `[OCR_SIMULATED …]` markers)

### Envelope

Outputs `contract: document_envelope@1` with `processing.page_methods[]`, `pages_local`, `pages_ocr`, costs, inspector metadata, and optional merged Markdown.

## 3. Corpus qualification (paid OCR disabled)

Corpus: Wave 2 **560** PDFs.

| Gate | Result |
|---|---|
| Zero false OCR skips | **PASS** (0 docs) |
| All broken-encoding → OCR | **PASS** (21/21) |
| Wave 0 Arabic trio kept local when usable | **PASS** (3/3, Arabic chars ≥40) |
| Scanned + mixed page routing | **PASS** |
| `document_envelope@1` on all | **PASS** |

| Metric | Value |
|---|---:|
| OCR-set agreement vs Poppler | 99.29% |
| Hybrid OCR pages (simulated) | 147 |
| Poppler OCR pages | 149 |
| Quality-forced OCR pages | 21 (broken-encoding) |
| Projected cost if executed | $0.588 |
| Overhead p95 | 2 ms |

Disagreement classes vs Poppler (not false skips):

1. **broken_encoding (21)** — hybrid forces OCR via mojibake gate; Poppler usually agrees (`corrupt_or_unusable_text`), except Wave 0 fixture where Poppler accepts local.
2. **arabic_digital Wave 0 (3)** — Poppler `too_few_words` → OCR; hybrid keeps usable native Arabic Markdown.

## 4. Real Mistral proof (capped)

Ran on VPS evidence workspace only (not production routing). Model **`mistral-ocr-4-0`**.

| Metric | Value |
|---|---:|
| Documents | 12 |
| Hybrid billable pages | **12** (cap 30) |
| Hybrid estimated cost | **$0.048** |
| Poppler-compare OCR pages (extra evidence) | 11 / $0.044 |
| Field-marker parity (email/phone/experience/skills) | **12/12 (100%)** |
| Failures | **0** |

Coverage: EN scanned, AR scanned, mixed, rotated, low-res, broken-encoding, Wave 0 scan/mixed/broken.

Merged outputs preserved page order and method provenance in envelopes under `real_ocr/*.envelope.json`.

## 5. Comparison vs current Poppler → Mistral path

| Dimension | Hybrid Wave 0 | Poppler production path |
|---|---|---|
| False OCR skips (corpus true-need) | **0** | N/A baseline |
| Broken encoding | Forces OCR (fixes Wave 0/2 inspector false-skip class) | Usually OCR via quality gate; Wave 0 fixture can accept local |
| Arabic digital usable text | Keeps native (saves OCR vs Poppler over-OCR) | Often `too_few_words` → OCR |
| Scanned / mixed | Page-accurate | Page-accurate |
| Layout | Inspector native Markdown + table/column meta | pdftotext layout |
| Latency (routing) | p95 ~2 ms inspector | Poppler assess higher |
| Cost (corpus projected) | 147 pages / $0.588 | 149 / $0.596 |
| Real proof field markers | Parity with Poppler+Mistral on 12 docs | Same OCR model |

## 6. Failures / examples

No corpus false skips. Representative examples:

- `syn_broken_encoding_000.pdf` — native mojibake → `quality_forced_ocr` / real OCR billable
- `wave0_cv_ar_digital_01.pdf` — native Arabic preserved; Poppler would OCR
- `syn_mixed_digital_scanned_000.pdf` — page1 native + page2 OCR (real proof merged both)

## 7. GO/NO-GO

### CV-only staging canary — **CONDITIONAL GO**

Allowed only with explicit owner approval, and only if:

1. New flag e.g. `WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary` (default off)
2. CV PDFs only; envelope consumers only; **no** identity/contract/payroll
3. Prefer **shadow or alternate path** first: write envelope + compare to Poppler result; do **not** replace authoritative text until a second GO
4. Paid OCR still subject to existing Mistral enablement + cost caps
5. Keep `pdf-inspector==0.2.6` pin
6. Rollback = unset flag (Poppler path unchanged)

### Production default / shared foundation cutover — **NO-GO**

Needs live traffic evidence, more real-OCR volume, and owner GO after staging canary.

## 8. Later plan — shared PDF foundation across modules

1. **Staging canary (CV-only)** — flag-gated alternate/shadow path emitting `document_envelope@1`.
2. **Promote envelope** as the shared contract; CV / identity / contract processors remain separate consumers.
3. **Hard rules in shared layer:** never OCR payslips; identity stays GPT/HR vision unless explicitly opted in; contracts default no OCR.
4. **Advisor policy:** hybrid may keep native Arabic when usable; must never skip OCR on `corrupt_or_unusable_text` / mojibake / image-only.
5. **Only then** consider making hybrid the default PDF text foundation behind Poppler retirement — separate wave, separate GO.

## 9. What was not done

- No production deploy of the engine into `extract_cv_document`
- No Firecrawl hosted API
- No Migration Wave 1-B resume
- No silent upgrade past pdf-inspector 0.2.6
- No full-corpus paid OCR
