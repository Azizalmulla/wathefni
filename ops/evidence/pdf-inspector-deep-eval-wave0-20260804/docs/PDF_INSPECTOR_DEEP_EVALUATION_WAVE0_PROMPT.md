# pdf-inspector Deep Evaluation Wave 0 prompt

Start pdf-inspector Deep Evaluation Wave 0, staging and shadow-only.

Do not change production routing, replace Poppler, deploy a routing change, or resume Migration Wave 1-B. Do not call paid OCR beyond a tightly capped sample that receives separate owner approval.

Confirm and report:

- exact `pdf-inspector` package version and upstream commit;
- Python, Rust, or Node binding used;
- every API invoked, explicitly distinguishing `process_pdf` from classification-only calls;
- exact scan strategy, including `Full`;
- whether native text, extracted Markdown, `pages_needing_ocr`, confidence, encoding signals, and layout signals are collected;
- dependency, licensing, platform, and operational constraints.

Build a curated, versioned benchmark set covering:

- Arabic, English, and bilingual CVs;
- single- and multi-column CVs;
- digital, scanned, image-based, and mixed PDFs;
- CID/ToUnicode and deliberately broken-encoding PDFs;
- contracts;
- identity-document PDFs;
- table-heavy documents.

For every document, define verified expected text and expected downstream fields before scoring. Compare:

1. current authoritative Poppler output and page routing;
2. `pdf-inspector` extracted Markdown and routing signals;
3. Mistral OCR reference output only where needed and separately approved;
4. verified expected text;
5. downstream CV/document field extraction results.

Measure:

- Arabic character integrity and RTL order;
- bilingual ordering;
- reading order and multi-column integrity;
- section, list, and table preservation;
- false OCR skips;
- unnecessary OCR pages;
- per-page routing agreement and disagreement;
- extraction latency and throughput;
- projected Mistral page reduction and cost savings;
- downstream field precision, recall, and critical-field accuracy.

Use `pdf-inspector` only as a recorded shadow signal. Poppler remains authoritative and no shadow result may alter extraction or OCR routing.

Return:

- benchmark manifest and reproducible harness;
- document-by-document result matrix;
- representative failure examples with extracted artifacts;
- projected page and cost savings with assumptions;
- GO/NO-GO separately for:
  - local text extractor;
  - OCR-page advisor;
  - primary router with Poppler veto;
- exact smallest safe implementation wave, feature flag, observability, rollback, and acceptance thresholds.

Evaluating only classifier agreement is insufficient. The repository claims native text extraction, Markdown conversion, page-level OCR routing, confidence, and layout-aware extraction, so all of those capabilities must be exercised and measured.

