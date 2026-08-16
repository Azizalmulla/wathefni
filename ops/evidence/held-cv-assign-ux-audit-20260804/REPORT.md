# Held CVs waiting for a job — audit + UX correction

**Date:** 2026-08-04  
**Scope:** Candidates → Held CVs card (`HeldIntakeReviewCard`). Backend admit/assign authority unchanged.

## Root cause — the two live held CVs (WATHEFNI)

| | CV 1 | CV 2 |
|---|---|---|
| App | `imp-wathefni-3673b2f6eeab34c8-WATHEFNI-IMPORT` | `imp-wathefni-4115005c9dcdfc37-WATHEFNI-IMPORT` |
| File | `k.pdf` (“kill”) | `cv.pdf` (“d6requal”) |
| Status | `needs_role` | `needs_role` |
| `position_code` | empty | empty |
| `role_suggestion` | **null** | **null** |
| Intake address | `wathefni-cv-362cae@inbound.wathefni.ai` | same |
| Source | `email_inbound` | `email_inbound` |
| Extraction | **failed** (`ocr_required_mistral_disabled`) | **failed** (same) |
| Validation | rejected (quality) | rejected (quality) |

**Why held:** arrived on a **general** intake address with **no job alias / application source**, so no `position_code` was stamped → `needs_role`. This is **not** “system scored relevance and was unsure” — there is **no** `role_suggestion` at all.

**Extraction:** attempted (`pdftotext`); soft/OCR path required Mistral OCR which is disabled → `extraction_status=failed`. Hold reason is still missing job link, not extraction failure alone.

## Implementation truth (before fix)

- Suggestions today = metadata/folder/`applied_role` fuzzy only (`resolve_import_role`), **not** CV↔job ranking.
- Product already: explicit alias may auto-admit only if company setting ON; suggestions never auto-admit.
- **Bug:** `targetKeys` used `picked.length ? picked : group.app_keys` → with **zero** checkboxes, Assign & admit acted on the **entire group**. Shared group-level job select amplified the risk.

## UX after fix

- Default per row: **Assign job** → row-scoped selector → **Assign and admit** (disabled until job chosen) for **that** `app_key` only.
- Checkboxes = explicit bulk only; bulk toolbar appears **only after** selection; copy states N and “same job”.
- Confirm disabled until job selected (row + bulk).
- Preview, permissions, bulk API, audit, eligibility, intake authority preserved.

## Tests

`apps/wathefni-dashboard/src/components/candidates/HeldIntakeReviewCard.test.tsx` — 6 passed, including POST body proofs that sibling rows are never included.
