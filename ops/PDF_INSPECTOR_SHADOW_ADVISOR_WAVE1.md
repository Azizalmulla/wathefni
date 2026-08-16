# pdf-inspector Shadow Advisor Wave 1

Date: 2026-08-04  
Scope: CV PDFs only · observation only · Poppler authoritative  
Migration Wave 1-B: not resumed  
Identity / contracts / payroll routing: unchanged

## Verdict

**GO for production shadow observation only.**  
Inspector does **not** influence OCR routing, authoritative text, Mistral calls, or downstream CV results.

| Gate | Result |
|---|---|
| Staging qualify | **GO** (p95 shadow wall **14 ms**) |
| Production shadow observation | **GO** (p95 shadow wall **18 ms**) |
| Behavioral invariance | **PASS** |
| Fail-open timeout/error | **PASS** |
| OCR routing influence | **None** |

## What shipped

- Feature flag: `WATHEFNI_PDF_INSPECTOR_SHADOW`
- Timeout: `WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS` (default/hard fail-open 500 ms; min clamp 50 ms)
- Module: `wathefni-orchestrator/pdf_inspector_shadow.py`
- Hook: after Poppler `assess_pdf_pages` in `cv_extraction.extract_cv_document` (PDF branch only)
- Dependency: `pdf-inspector==0.2.6` in `requirements.txt`

### Stored shadow fields

- PDF type, confidence, OCR-page proposal (`pages_needing_ocr_1idx`)
- Encoding flag (`has_encoding_issues`)
- Processing time / wall time
- Markdown quality metrics (len, sha256, alpha ratio, mojibake, Arabic corruption, suspicious printable)
- Comparison vs Poppler pages + Wathefni quality-gate reasons
- Focused detections:
  - mojibake
  - CID/ToUnicode hints
  - reversed/corrupted Arabic
  - suspicious printable-but-meaningless text
  - inspector says no OCR while Poppler says OCR
  - high-risk false-skip candidate

Shadow blob is attached to `ExtractionResult.metadata.pdf_inspector_shadow` and optionally recorded as `cv_extraction_runs.stage=pdf_inspector_shadow`.

## Acceptance proof

| Check | Staging | Production observation |
|---|---|---|
| No text/method/disposition change with flag on vs off | PASS | PASS |
| Fail-open on timeout | PASS | PASS |
| Fail-open on inspector exception | PASS | PASS |
| p95 shadow overhead ≤ 150 ms (≤10 pages) | 14 ms | 18 ms |
| `influences_ocr_routing=false` | PASS | PASS |
| CAPTURE_INGEST remains off | PASS | PASS |

Evidence:

- Staging: `ops/evidence/pdf-inspector-shadow-wave1-20260803T222300Z/`
- Production: `ops/evidence/pdf-inspector-shadow-wave1-prod-20260803T222426Z/`
- Scripts: `ops/qualify-pdf-inspector-shadow-wave1-staging.sh`, `ops/enable-pdf-inspector-shadow-wave1-prod.sh`

## Rollback

Production:

```bash
bash /opt/wathefni/backups/production-pre-pdf-inspector-shadow-wave1-20260803T222426Z/ROLLBACK.sh
```

Or remove drop-in `zzzz-pdf-inspector-shadow-wave1.conf` and unset `WATHEFNI_PDF_INSPECTOR_SHADOW`, then restart orchestrator.

Staging: remove `zzzz-pdf-inspector-shadow-wave1.conf` under staging systemd drop-ins and restart staging.

## Explicit non-goals (still NO-GO)

- Inspector as native text authority
- Inspector as OCR decision maker
- Primary routing with Poppler veto that can skip OCR alone
- Migration Wave 1-B resume
- Identity/contract/payroll extraction changes
