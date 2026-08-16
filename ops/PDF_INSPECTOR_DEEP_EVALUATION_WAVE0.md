# pdf-inspector Deep Evaluation Wave 0

Date: 2026-08-04  
Mode: staging/local shadow-only  
Evidence: `ops/evidence/pdf-inspector-deep-eval-wave0-20260804/`  
Constraints honored: no production routing change · Poppler authoritative · no Migration Wave 1-B · no paid OCR/Mistral · real PDFs only

## Fixture confirmation (locked before run)

All 24 fixtures are structurally valid PDFs (ReportLab/TrueType, image-embedded scanned pages, or a real public legal PDF). No `.txt` CVs and no trivial Latin placeholders for Arabic.

| Category | Count | Notes |
|---|---:|---|
| English digital CV | 4 | includes 1 multipage |
| Arabic digital CV | 3 | Noto Kufi embedded + reshape/bidi |
| Bilingual AR/EN CV | 2 | dual-font stacked |
| Multi-column CV | 2 | two-column frames |
| Scanned / image-only CV | 3 | rendered PNG embedded as image page |
| Mixed digital + scanned | 2 | page1 text + page2 image |
| CID/ToUnicode | 1 | proper Unicode TrueType |
| Broken encoding | 1 | deliberate mojibake stress |
| Contracts | 2 | generated employment + real MOJ Labor Law (3 pages) |
| Identity-document style | 2 | Civil ID digital + passport scanned |
| Table-heavy | 2 | compensation + experience matrix |
| **Total** | **24** | **29 pages** |

## Package / binding identity

| Field | Value |
|---|---|
| Package | `pdf-inspector` |
| PyPI version | **0.2.6** |
| Binding | **Python via PyO3** (`pdf_inspector.abi3.so`) |
| License | MIT |
| Local extension SHA-256 | `696e3bde5c1114fea03f9edd4c4276b27df4104eebdc7f034761b457ab27f53e` |
| PyPI macOS arm64 wheel SHA-256 | `d2b2aaa95b242da38630bbd0644ffe9a929466f9c4e6406d6f1957b59b413d08` |
| Upstream commit | **Not pinned.** GitHub tags at evaluation time included `v0.2.0`–`v0.2.3` then `v0.3.x`…`v0.7.0`; no `v0.2.6` tag. Report package version + wheel digest, not an invented commit. |

### APIs used (full path, not classification alone)

1. `process_pdf(path)` — detect + extract + Markdown (**primary Wave 0 path**)
2. `detect_pdf(path)` — detection-only comparison
3. `classify_pdf(path)` — lightweight type / OCR pages (0-indexed)
4. `extract_pages_markdown(path)` — per-page Markdown, `needs_ocr`, tables/columns
5. `extract_text(path)` — plain text companion

Collected from `process_pdf`: `pdf_type`, `markdown`, `page_count`, `processing_time_ms`, `pages_needing_ocr`, `confidence`, `is_complex_layout`, `pages_with_tables`, `pages_with_columns`, `has_encoding_issues`.

### Scan strategy / Full

Python `process_pdf(path, pages=None)` does **not** expose `ScanStrategy`.  
Documented Rust strategies: `EarlyExit` (default), `Full`, `Sample(n)`, `Pages(vec)`.  
`Full` is available through Rust `process_pdf_with_options` only.  
Wave 0 therefore exercised the Python default full processing path plus `extract_pages_markdown`, and records that **Full cannot be forced from the current Python binding**.

## Headline results

| Metric | Value |
|---|---|
| Inspector exact OCR-page match vs expected | **95.8%** (23/24) |
| Poppler exact OCR-page match vs expected | 83.3% |
| Inspector ↔ Poppler agreement | 87.5% |
| Inspector false OCR skips | **1** (`cv_broken_encoding_01`) |
| Inspector unnecessary OCR pages | **0** |
| Digital needle hit (inspector Markdown) | **0.935** |
| Digital needle hit (Poppler text) | 0.780 |
| Arabic integrity (all applicable, incl. scanned) | 0.688 |
| Arabic integrity (digital only) | **0.786** |
| Field accuracy (inspector Markdown heuristics) | 0.756 |
| Field accuracy (Poppler heuristics) | 0.668 |
| Avg process time inspector | **~1.1 ms** |
| Avg Poppler assess time | ~58.6 ms |

### Projected Mistral page/cost savings (no OCR called)

Assumption: `$0.004 / page` (`MISTRAL_OCR_COST_USD_PER_PAGE`).

| Policy | OCR pages / 29 | Cost |
|---|---:|---:|
| OCR all pages | 29 | $0.116 |
| Poppler advisory | 9 | $0.036 |
| pdf-inspector advisory | 6 | $0.024 |
| Expected truth | 7 | $0.028 |

On this matrix, inspector would save **~$0.012 vs Poppler** and **~$0.092 vs all-pages**. This is a projection only.

## Failure examples

### 1) Dangerous false OCR skip — broken encoding

`cv_broken_encoding_01`  
Expected OCR: page 1.  
Inspector: `pdf_type=text_based`, `confidence=1.0`, `has_encoding_issues=False`, `pages_needing_ocr=[]`.  
It extracted mojibake as if trustworthy. **This blocks primary routing and keeps advisor behind Poppler veto.**

### 2) Real-world Arabic legal PDF — native text unusable for needles

`contract_kuwait_labor_law_real_01` (real MOJ Law 6/2010, first 3 pages)  
Inspector returned substantial Markdown, but character order/encoding is corrupted relative to verified needles `قانون` / `العمل` (0/2 hits).  
Not safe as a stand-alone Arabic legal text extractor without quality gates.

### 3) Synthetic Arabic CVs — inspector better than Poppler

For `cv_ar_digital_0{1,2,3}`, inspector recovered Arabic needles at 100% and did **not** request OCR.  
Poppler `assess_pdf_pages` marked page 1 `needs_ocr` on all three.  
Shadow disagreement is useful, but production must not let inspector alone skip OCR until broken-encoding false-skips are solved.

### 4) Multi-column preservation — success

`cv_multicolumn_01/02` Markdown preserved columns as a Markdown table. Strong layout signal.

### 5) Scanned pages — success

Image-only CVs and passport scan: empty Markdown, OCR pages correct, no native field leakage.

## GO / NO-GO

| Role | Verdict | Why |
|---|---|---|
| 1. Native PDF text extraction | **NO-GO** | Real Arabic legal PDF fails needle integrity; bilingual name miss; not ready to replace Poppler text. |
| 2. OCR-page advising | **CONDITIONAL-GO** | 95.8% exact match and 0 unnecessary OCR, but **1 false skip** on broken encoding. Shadow-only advisor only. |
| 3. Primary routing with Poppler veto | **NO-GO** | Must not skip OCR on inspector alone while false-skips exist; Python cannot force `ScanStrategy::Full`. |

## Smallest safe implementation wave

**Name:** `pdf_inspector_shadow_advisor_wave1`

- Flag: `WATHEFNI_PDF_INSPECTOR_SHADOW=1`
- Scope: CV PDF intake only
- Behavior: call `process_pdf` beside Poppler `assess_pdf_pages`; record shadow signals; **never** change Mistral/Poppler routing
- Authoritative router: Poppler
- Observability: store shadow blob on extraction runs; metrics for disagreement, false-skip candidates, encoding-issue rate
- Rollback: unset flag; no routing dependency
- Accept before any advisor canary that can influence OCR:
  - false OCR skips on known need-OCR set = 0
  - broken-encoding flagged or OCR’d = 100%
  - digital Arabic needle integrity ≥ 0.90
  - digital needle hit ≥ 0.90
  - shadow overhead p95 ≤ 150 ms on ≤10-page CVs

Out of scope: replace Poppler, skip/call Mistral from inspector alone, identity/contract/payroll routing, Migration Wave 1-B resume.

## Decision implication for Migration Wave 1-B

Do **not** block or gate Migration Wave 1-B on pdf-inspector integration.  
Wave 1-B should resume later with the already-proven extraction safety remediations (defer extraction, batch tags, rollback cancel, residual queue checks).  
pdf-inspector should proceed, if at all, as a separate shadow-only wave.

## Artifacts

- Harness: `wathefni-orchestrator/scripts/wave0-pdf-inspector-deep-eval.py`
- Manifest: `ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures/MANIFEST.json`
- Matrix: `ops/evidence/pdf-inspector-deep-eval-wave0-20260804/results/matrix.json`
- Table: `ops/evidence/pdf-inspector-deep-eval-wave0-20260804/results/matrix.md`
- Per-doc Markdown/text: `ops/evidence/pdf-inspector-deep-eval-wave0-20260804/artifacts/`
