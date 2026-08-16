# Oreo false-accept — decision trace

**Stamp:** `20260805T232101Z`
**Employee:** `WATHEFNI-96599338566`
**Checklist item (API):** `civil_id_canary_test`
**Validated as:** `civil_id` via `CANARY_VALIDATION_ALIASES`
**File:** `F7CB3770-DD6B-4EFB-995F-A8D83633A7C5.jpg`
**SHA256:** `67221e9686f312c7ca1fdb2d2e28072f7d219ae484ca8bb6198ad3c5c4ef360f`
**Version:** `81d08408-31ac-499b-a1d6-99f1b77a3a4a` / file_id `a9bdb930-fb30-42f4-abaf-f2e441e09219`
**Submitted at:** `2026-08-05T23:15:32Z`

## Expected item / document type

| Field | Value |
|---|---|
| API item_id | `civil_id_canary_test` |
| document_type (stored) | `civil_id_canary_test` |
| Soft-gate expected | `civil_id` (alias) |
| Route document_class | identity |

## Classify / verify (original upload)

| Field | Value |
|---|---|
| provider | mistral |
| detected_item | unknown |
| matches_expected_item | false |
| confidence | 0.0 |
| extraction_status | needs_review |
| reason | needs_review |
| delegated_to | identity_document_extraction |
| gpt_used | false |
| authoritative | false |

## Quality

No separate quality hard-fail (size/format OK). Image was a clear lifestyle photo (person holding Oreo oatmeal), not blurry.

## Identity / Mistral

| Field | Value |
|---|---|
| extraction_status | needs_review |
| extraction_error | shared_extract_unavailable |
| confidence | 0.0 |
| fields (name/number/dates) | all null |
| gpt_used | false |
| timeout / circuit-open | **no** — Mistral ran; result was unusable/unknown |
| fallback to GPT | **no** (forbidden) |

## Final gate (original — bug)

| Field | Value |
|---|---|
| gate | soft |
| decision | **allow_uncertain** |
| reason | **needs_review** |
| rule | soft path: `extraction_status==needs_review` AND `confidence < 0.65` → `_uncertain("needs_review")` without requiring document evidence |
| hr_review_recommended | true |
| stored | yes (processing / awaiting hr_review) |

## Stored flags / audit

- `onboarding_items.lifecycle_meta.doc_validation` = soft / allow_uncertain / needs_review
- `employee_documents.metadata.extraction.doc_validation` = same
- `employee_ess_document_versions.review_status` = `pending_hr_review`
- `ocr_proposal` all null / needs_review
- No dedicated rejection row (upload was accepted)

## Fix proof (same bytes, new gate)

| Check | Result |
|---|---|
| Replay Oreo verify shape | block / `not_a_document` |
| Live re-eval stored file | block / `not_a_document` |
| credible_document_evidence | false |
| obvious_non_document | true |

Live verification snapshot:
{
  "matches_expected_item": false,
  "detected_item": "unknown",
  "confidence": 0.0,
  "reason": "needs_review",
  "provider": "mistral",
  "gpt_used": false,
  "extraction_status": "needs_review",
  "delegated_to": "identity_document_extraction",
  "channel": "whatsapp_onboarding",
  "document_type": "civil_id",
  "canonical_document_type": "civil_id",
  "authoritative": false,
  "hr_confirmation_required": true
}

Replay:
{
  "decision": "block",
  "reason": "not_a_document",
  "gate": "soft",
  "should_block": true,
  "message_en": "This doesn't look like the document we asked for. Please upload a clear photo or scan of the requested document."
}
