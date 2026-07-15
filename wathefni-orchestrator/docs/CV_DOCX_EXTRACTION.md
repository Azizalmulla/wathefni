# DOCX CV extraction (local-first v2)

## Status

Implemented on **staging only**. Production still uses legacy `docx-stdlib` until owner approval.

## Behavior

```text
DOCX
→ local zip/XML extract (paragraphs, tables, headers/footers, text boxes, hyperlinks, RTL/bidi flags)
→ classify embedded images (skip logo/icon/photo; keep text_candidate)
→ mistral-ocr-4-0 ONLY for text_candidate images when local text cannot recover that content
→ quality gates may set needs_review
→ same cache / runs / lease foundation as PDF path
```

Ordinary recoverable DOCX text never calls Mistral.

## Pins

- OCR model (images only): `mistral-ocr-4-0`
- Preprocess: `cv_docx_preprocess_v2`

## Rollback

Leave production untouched, or on staging revert `cv_docx.py` / restore prior `extract_candidate_cv_document` DOCX branch.
