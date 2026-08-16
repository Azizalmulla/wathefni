# pdf-inspector Production Shadow Observation Review

Date: 2026-08-04  
Mode: research / read-only  
Flags/routing/OCR/authoritative text: **unchanged**  
Evidence root: `ops/evidence/pdf-inspector-shadow-observation-review-20260804/`

## Verdict

**NO-GO for a guarded advisor canary.**

Production Wave 1 is correctly armed (`WATHEFNI_PDF_INSPECTOR_SHADOW=1`), but **zero live eligible CV PDFs** have been processed since deploy. Available evidence is the production enable offline smoke (24 PDFs) plus read-only fixture reanalysis. That is enough to confirm Wave 0 patterns and fail-open/overhead, and **not** enough to let inspector influence routing.

| Question | Answer |
|---|---|
| Confirms or contradicts Wave 0? | **Confirms** (Arabic Poppler/inspector disagreement; scanned/mixed agree; broken-encoding still unsafe for routing) |
| Do quality gates catch known broken-encoding failure? | **Partial only** — mojibake detection fires; neither Poppler nor inspector proposes OCR; `has_encoding_issues=false` |
| GO/NO-GO future guarded advisor canary | **NO-GO** |
| Live eligible CV PDFs vs 200 threshold | **0 / 200** |

## Observation window

| Field | Value |
|---|---|
| Production shadow deploy | `2026-08-03T22:24:26Z` |
| Flag now | `WATHEFNI_PDF_INSPECTOR_SHADOW=1` (still on) |
| Timeout | `500` ms fail-open |
| Live `cv_extraction` jobs since deploy | **0** |
| Live `cv_extraction_runs` since deploy | **0** |
| Live `candidate_documents` since deploy | **0** |
| Live `stage=pdf_inspector_shadow` rows | **0** |
| Evidence actually available | production enable smoke + fixture reanalysis (24 PDFs / 29 pages) |

## Counts (available evidence)

| Metric | Value |
|---|---:|
| Eligible CV PDFs observed (live) | **0** |
| Eligible PDFs in production enable smoke | **24** |
| Successful inspector runs (smoke matrix) | **24 / 24** |
| Timeouts/errors in matrix | **0** |
| Injected fail-open timeout proven | **yes** |
| Injected fail-open error proven | **yes** |

### Overhead (≤10 pages)

| Stat | Production smoke | Fixture reanalysis |
|---|---:|---:|
| p50 | 3 ms | 2 ms |
| p95 | **18 ms** | 11.4 ms |
| p99 | 18.2 ms | 13.8 ms |
| max | 21 ms | — |

Acceptance `p95 < 150 ms`: **met** on available samples.

## Inspector vs Poppler OCR-page agreement

Exact agreement: **21 / 24 = 87.5%**

| Class | Count | Files |
|---|---:|---|
| Inspector proposed **fewer** OCR pages | **3** | `cv_ar_digital_01/02/03.pdf` |
| Inspector proposed **more** OCR pages | **0** | — |
| High-risk false-skip candidates | **3** | same Arabic digital trio |
| Full agreement | 21 | all other fixtures |

### Projected Mistral pages/cost if inspector advice had been used

Assumption `$0.004/page`. Fixture set only.

| Policy | OCR pages | Cost |
|---|---:|---:|
| All pages | 29 | $0.116 |
| Poppler | 9 | $0.036 |
| Inspector | 6 | $0.024 |
| Expected truth | 7 | $0.028 |

Projected savings vs Poppler: **3 pages / $0.012**. Not meaningful for production until live volume exists.

## Detections

| Detection | Count |
|---|---:|
| inspector no OCR while Poppler OCR | 3 |
| mojibake | 1 (`cv_broken_encoding_01.pdf`) |
| CID/ToUnicode hint | 1 (`cv_tounicode_proper_01.pdf`, likely over-sensitive) |
| reversed/corrupted Arabic | 0 |
| suspicious printable-but-meaningless | 0 |

## Category breakdown (detectable)

| Category | n | agree | inspector fewer | high-risk |
|---|---:|---:|---:|---:|
| english_digital_cv | 4 | 4 | 0 | 0 |
| arabic_digital_cv | 3 | 0 | 3 | 3 |
| bilingual_cv | 2 | 2 | 0 | 0 |
| multicolumn_cv | 2 | 2 | 0 | 0 |
| scanned_image_only_cv | 3 | 3 | 0 | 0 |
| mixed_digital_scanned | 2 | 2 | 0 | 0 |
| broken_encoding | 1 | 1* | 0 | 0 |
| cid_tounicode | 1 | 1 | 0 | 0 |
| contract | 2 | 2 | 0 | 0 |
| identity_document | 2 | 2 | 0 | 0 |
| table_heavy | 2 | 2 | 0 | 0 |

\*Agreement on OCR pages, but both engines fail to demand OCR for the broken-encoding fixture.

## Manual review — every high-risk false-skip

All three high-risk cases are Arabic digital CVs.

### `cv_ar_digital_01/02/03.pdf`

- Poppler: `needs_ocr`, reason **`too_few_words`** (e.g. 508 chars / 5 “words”, Arabic ratio ~0.06)
- Inspector: `text_based`, confidence 1.0, OCR pages `[]`, Markdown length ~230–244, no mojibake
- Classification: **not a scanned-content false skip**. Poppler’s word tokenizer under-counts Arabic; inspector recovers usable Arabic text.
- Routing implication: if inspector were allowed to veto Poppler OCR here, it would likely **reduce unnecessary OCR**, but this is still a disagreement class that must be proven on real customer Arabic CVs before any influence.
- Wave 0: **confirmed**.

### Representative other disagreements / signals

1. **Broken encoding** (`cv_broken_encoding_01.pdf`)  
   Poppler accepts local; inspector proposes no OCR; `has_encoding_issues=false`; **mojibake_hits=4**.  
   Quality gates catch the failure as a **detection signal**, not as an OCR-page proposal.  
   Wave 0 concern remains: broken encoding is **not safely forced into OCR** by either engine.

2. **Scanned** (`cv_scanned_en_01.pdf`) — both agree page 1 needs OCR (`image_only_page` / `scanned`).

3. **Mixed** (`cv_mixed_01.pdf`) — both agree only page 2 needs OCR.

4. **Multi-column / bilingual** — agreement; no high-risk.

5. **CID/ToUnicode proper** — OCR agreement, but CID hint detection fires (noisy heuristic).

## Wave 0 confirmation

| Wave 0 finding | Production observation evidence |
|---|---|
| Arabic digital: inspector better / Poppler over-OCR | **Confirmed** (3/3) |
| Scanned/mixed page routing strong | **Confirmed** |
| Broken-encoding unsafe for primary routing | **Confirmed** (still no OCR proposal; encoding flag false) |
| Overhead tiny vs 150 ms budget | **Confirmed** (p95 18 ms) |
| Fail-open required | **Confirmed** by injected tests |
| Ready to influence OCR | **Still no** |

## Minimum evidence threshold before routing influence

Keep the recommended bar; none of the live thresholds are met yet:

1. ≥ **200 real eligible CV PDFs** with persisted shadow rows  
2. **Zero confirmed false OCR skips** on pages that truly need OCR (scanned/image/corrupt), after human review  
3. **100% capture** of known broken-encoding / high-risk cases as OCR or hard veto signals (not merely mojibake counters)  
4. Fail-open success on **all** inspector errors/timeouts in live traffic  
5. Live p95 overhead **< 150 ms** on ≤10-page CVs  
6. No Arabic/bilingual regression vs Poppler+Wathefni gates on real CVs  

Current live score: **0/200**, broken-encoding capture **partial**, Arabic disagreement class **open**.

## Recommendation

- Leave shadow observation **on** (already enabled); do **not** promote.
- Do **not** start a guarded advisor canary.
- Wait for real CV PDF traffic to accumulate durable `pdf_inspector_shadow` evidence.
- Before any future canary design, fix or specially handle:
  - Arabic `too_few_words` Poppler/inspector disagreement taxonomy (savings candidate vs true risk)
  - broken-encoding elevation from mojibake signal → OCR/veto requirement

No deploy, flag change, or routing promotion was performed in this review.
