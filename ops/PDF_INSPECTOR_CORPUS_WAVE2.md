# CV PDF Corpus Acquisition and Shadow Evaluation Wave 2

Date: 2026-08-04  
Mode: research / staging / offline only  
Evidence: `ops/evidence/pdf-inspector-corpus-wave2-20260804/`  
Constraints honored: no LinkedIn/Google/personal-site scraping · no production intake · no real candidate records · no paid OCR/Mistral · Poppler still authoritative · inspector shadow-only

## Verdict

Corpus target **met** (**560** valid PDFs). Offline shadow eval is strong on scanned/mixed/layout agreement and overhead, and **still blocks any routing influence**.

| Gate | Result |
|---|---|
| ≥500 legally usable PDFs | **PASS** (560) |
| Paid OCR invoked | **No** |
| Production / full-corpus staging intake | **Not done** |
| Inspector may influence routing | **NO** |
| Guarded advisor canary | **NO-GO pending owner approval of plan below** |

Critical offline finding: on **20/21** synthetic broken-encoding CVs, Poppler correctly demands OCR (`corrupt_or_unusable_text`) while inspector proposes **no OCR** (mojibake detected, `has_encoding_issues=false`). That is a **confirmed high-risk false-skip class** if inspector advice were used.

## Source / licence ledger

| Source | Licence / terms | Real PII? | Internal eval OK? | Included? |
|---|---|---|---|---|
| Wathefni Wave 2 synthetic corpus | Generated in-repo; fake `@synthetic-eval.example` | No | Yes | **Yes (535)** |
| Wave 0 fixtures | Synthetic internal reuse | No | Yes | **Yes (24)** |
| Kuwait MOJ Labor Law excerpt (3p) | Public government legal PDF | No | Yes (layout only) | **Yes (1)** |
| DocLayNet | CDLA-Permissive-1.0 | Possible in source docs | Yes | **No** — multi-GB deferred; layout edges synthesized |
| PubLayNet | CDLA-Permissive-1.0 / PMC OA | No | Yes (non-CV) | **No** — deferred |
| EraMatch CV Parsing Benchmark | Stated CC0 + synthetic | No | Likely yes | **No** — avoided third-party retention; local synthetic used |
| opensporks/resumes (LiveCareer scrape) | Labeled CC0 but scraped examples | Yes | **No** | **Excluded** |
| LinkedIn / Google / personal sites | Unlicensed scraping | Yes | **No** | **Excluded** |

Full ledger: `manifests/licence_ledger.json`  
Manifest: `manifests/corpus_manifest.json` / `.csv`

## Category counts (560)

| Category | n |
|---|---:|
| english_digital_cv | 124 |
| arabic_digital_cv | 83 |
| bilingual_cv | 52 |
| scanned_image_only_cv | 44 |
| mixed_digital_scanned | 32 |
| multicolumn_cv | 32 |
| english_digital_multipage | 25 |
| design_heavy_cv | 25 |
| table_heavy_cv | 25 |
| broken_encoding | 21 |
| unusual_font_icon_cv | 20 |
| lowres_compressed_scan_cv | 20 |
| cid_tounicode_missing_font | 20 |
| scanned_arabic_cv | 15 |
| rotated_scan_cv | 15 |
| cid_tounicode (wave0) | 1 |
| contract_or_legal | 3 |
| other wave0 reuse buckets | 3 |

All target stress classes are present: English/Arabic/bilingual, multi-column/design-heavy, scanned/image-only, mixed, tables/icons/unusual fonts, CID/missing-font proxies, mojibake/broken encoding, rotated/low-res/compressed scans.

## Offline shadow evaluation (no paid OCR)

| Metric | Value |
|---|---:|
| PDFs evaluated | 560 |
| Successful inspector runs | **560 / 560** |
| Timeouts / errors / fail-open | **0 / 0 / 0** |
| Exact OCR-page agreement | **537 / 560 = 95.89%** |
| Inspector fewer OCR pages (docs) | **23** |
| Inspector more OCR pages (docs) | **0** |
| High-risk false-skip docs | **23** |
| Overhead p50 / p95 / p99 | **2 / 2 / 3 ms** (max 12) |

### Disagreement matrix (non-zero disagreement only)

| Category | n | agree | disagree | inspector fewer | inspector more | high-risk |
|---|---:|---:|---:|---:|---:|---:|
| broken_encoding | 21 | 1 | **20** | 20 | 0 | 20 |
| arabic_digital_cv | 83 | 80 | **3** | 3 | 0 | 3 |

All other categories: **100% OCR-page agreement** in this corpus (including scanned, mixed, bilingual, multicolumn, design-heavy, tables, rotated/low-res scans, CID proxies).

### Detections

| Detection | Docs |
|---|---:|
| inspector_no_ocr_while_poppler_ocr | 23 |
| mojibake | 21 |
| cid_tounicode_failures (hint) | 21 |
| reversed/corrupted Arabic | 0 |
| suspicious printable-but-meaningless | 0 |

### Arabic / RTL slice (n=150: Arabic digital + scanned Arabic + bilingual)

- Agree: **147 / 150**
- High-risk / inspector-fewer: **3** (all Wave 0 Arabic digital fixtures; Poppler `too_few_words`)
- New synthetic Arabic digital (80): **full agreement** (both accept local text)
- Reversed/corrupted Arabic detections: **0**

### Broken-encoding slice (n=42 including CID proxies)

- Mojibake on synthetic broken_encoding: **21 / 21**
- Inspector `has_encoding_issues`: **0**
- Inspector proposes OCR: **0**
- Poppler proposes OCR on synthetic broken_encoding: **20 / 21** (`corrupt_or_unusable_text`)
- Wave 0 broken fixture: both **accept local** (signal-only mojibake; no OCR proposal)

**Quality gates catch many broken-encoding cases via Poppler**, and shadow **mojibake detection** fires — but inspector OCR advice does **not** capture them. Using inspector to skip Poppler OCR here would be a false skip.

### Projected Mistral pages/cost if inspector advice used

Assumption `$0.004/page`. Offline corpus only; **not** a production savings claim.

| Policy | OCR pages | Cost |
|---|---:|---:|
| Poppler | 149 | $0.596 |
| Inspector | 126 | $0.504 |
| Delta | −23 pages | −$0.092 |

Those 23 “saved” pages are exactly the disagreement set (20 broken-encoding + 3 Arabic Wave 0) — **not safe savings**.

## Manual review — every high-risk class

### A. Broken encoding (20 docs) — **confirmed dangerous if inspector influenced OCR**

Example: `syn_broken_encoding_000.pdf`

- Poppler: `needs_ocr` / `corrupt_or_unusable_text`
- Inspector: `text_based`, OCR `[]`, `has_encoding_issues=false`, mojibake_hits=6
- Verdict: **true high-risk false-skip candidate**. Inspector must not veto Poppler OCR here.

Wave 0 `cv_broken_encoding_01`: both accept local; mojibake still detected — gates incomplete as OCR proposers.

### B. Arabic digital Wave 0 trio (3 docs) — **disagreement, likely Poppler over-OCR**

Examples: `wave0_cv_ar_digital_01/02/03.pdf`

- Poppler: `needs_ocr` / `too_few_words` (few whitespace words, usable Arabic chars)
- Inspector: recovers Arabic Markdown (~150 Arabic chars), no OCR
- Verdict: **not a scanned false skip**; taxonomy = Arabic tokenization mismatch. Still must not auto-promote inspector veto without live customer proof.

### C. Representative agreement classes (sampled)

- Scanned / rotated / low-res: both need OCR (`image_only_page` / `scanned`)
- Mixed: both OCR page 2 only
- Bilingual / multicolumn / tables: both accept digital
- CID/missing-font proxy: OCR agreement; CID hint noisy but non-routing

Artifacts: `artifacts/manual_high_risk_review.json`, `artifacts/representative_failures.json`, `results/false_skip_candidates.json`

## Staging subset (approved for *future* intake testing only)

Path: `staging_subset/` (**26** synthetic PDFs)

- Synthetic only; fake emails
- Mix of English/Arabic/bilingual/scan/mixed/broken/CID/design
- **Owner approval required before any staging intake**
- Must not create production candidates
- Must not bulk-load the 560 corpus

Manifest: `staging_subset/staging_subset_manifest.json`

---

## Exact plan for owner approval

### Staging plan (optional next step — requires explicit GO)

1. Keep production shadow flag as-is; **no routing change**.
2. On **staging only**, run an intake harness against the **26-doc subset** (not the full 560).
3. Assert:
   - Poppler remains authoritative for OCR pages
   - Inspector shadow rows persist (`stage=pdf_inspector_shadow` or equivalent)
   - No Mistral calls for pages Poppler accepts
   - Behavioral invariance vs shadow-off for final CV text/fields on digital accepts
   - Fail-open still holds under injected timeout
4. Separately, offline-keep the full 560 corpus for regression; do **not** insert into DB.
5. Exit criteria for staging subset: 26/26 processed, 0 routing influence, 0 paid OCR surprises, shadow metrics match offline.

### Production canary plan (later — blocked until thresholds met)

**Hard NO-GO today.** Do not start a guarded advisor canary until:

1. ≥ **200 live** eligible production CV PDFs with shadow rows (Wave 1 observation still at 0 live)
2. **Zero confirmed false OCR skips** on pages that truly need OCR after human review  
   - Wave 2 offline already shows **20 confirmed broken-encoding false-skip candidates** if inspector vetoed Poppler → must be fixed or hard-excluded before any influence
3. **100% capture** of broken-encoding/high-risk as OCR **or hard veto** (not mojibake counters alone; `has_encoding_issues` unreliable today)
4. Fail-open on all live inspector errors/timeouts
5. Live p95 overhead **< 150 ms**
6. No Arabic/bilingual regression on real CVs
7. Explicit owner GO for a **narrow** canary design, e.g.:
   - Advisor may only **add** OCR pages, never remove Poppler OCR pages; **or**
   - Advisor limited to `scanned`/`image_only` confirmation; broken-encoding and Arabic disagreements excluded

### Minimum evidence threshold before inspector may influence routing

Unchanged from observation review, plus Wave 2 addendum:

- ≥200 real eligible CV PDFs in production shadow
- Zero confirmed false OCR skips
- 100% broken-encoding/high-risk capture as OCR or hard veto
- Fail-open success on all inspector errors/timeouts
- p95 < 150 ms
- No Arabic/bilingual regression
- **New:** offline/staging proof that inspector cannot suppress Poppler `corrupt_or_unusable_text` / quality-gate OCR pages

## Recommendation

1. Accept Wave 2 corpus + offline eval as the legal evaluation foundation.
2. **Do not** promote inspector; **do not** start production canary.
3. Optionally approve staging intake of the **26-doc subset** only.
4. Before any future advisor design, treat “inspector fewer OCR pages than Poppler on `corrupt_or_unusable_text`” as a **blocking defect**.

No deploy, flag change, or routing promotion was performed in this wave.
