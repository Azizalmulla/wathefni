# CV OCR upgrade (Mistral OCR 4)

## Status

Implemented behind `WATHEFNI_CV_MISTRAL_OCR` (**default OFF**).

Do **not** enable on production until:

1. Staging proof with synthetic/sanitized samples is green
2. Owner approves privacy / retention configuration
3. Explicit production flag flip

## Pins

| Item | Value |
| --- | --- |
| OCR model | `mistral-ocr-4-0` (never `mistral-ocr-latest`) |
| Python SDK | `mistralai==2.6.0` |
| API | `POST https://api.mistral.ai/v1/ocr` (`v1`) |
| Preprocessing version | `cv_ocr_preprocess_v1` |
| Cost assumption | `$4 / 1,000 pages` → `$0.004 / page` |

HTTP adapter is used for OCR (urllib) so runtime does not depend on SDK imports at request time. The SDK pin is still installed and recorded for compatibility/tooling.

## Flow

```text
Digital PDF with good embedded text
→ Poppler pdftotext (local)
→ no OCR

Scanned / image-only / corrupt page
→ Mistral OCR 4 for those pages only

OCR still fails quality gates
→ GPT-5.4 vision rescue for failed pages only

Accepted text
→ deterministic contacts/dates (AR/EN)
→ structured profile (existing gpt-5.4 parser)
→ Voyage embedding
→ candidate analysis (unchanged)
```

Arabic alone does **not** trigger OCR.

## Feature flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `WATHEFNI_CV_MISTRAL_OCR` | OFF | Enable Mistral OCR path |
| `WATHEFNI_CV_GPT_VISION_RESCUE` | **retired / ignored** | CV GPT vision rescue is hard-disabled; flag cannot re-enable |
| `MISTRAL_API_KEY` or `WATHEFNI_MISTRAL_ENV` | unset | Required for live OCR |

Secrets file convention: `/root/.openclaw/secrets/mistral.env` containing `MISTRAL_API_KEY=...`.

## Caching contract

Company-scoped unique key:

```text
SHA256(
  content SHA-256
  + page hashes
  + preprocessing version
  + provider
  + exact OCR model
  + API version
  + extraction options
)
```

Table: `cv_extraction_cache`.

Same successful OCR request is not billed twice for the same company + cache key.

## Worker leasing / single-flight

Table: `cv_extraction_leases`.

Lease key: `cv:{company_code}:{document_id}:cv_extract`.

TTL: 180s. Concurrent workers cannot process the same CV stage twice.

## Telemetry / metadata

Replaces misleading `gpt-5.4-vision` with:

- `stage`
- `tier`
- `provider`
- `actual_request_model`
- `provider_response_model`

Plus: request id, latency, billable pages, estimated cost, cache hit.

Runs stored in `cv_extraction_runs`.

## Privacy / retention

Mistral may retain uploaded Files API objects for up to ~30 days unless deleted earlier.

Our implementation:

1. Prefers **direct base64** `document_url` / `image_url` (no Files API object created)
2. Retention label recorded as `base64_direct_no_files_api`
3. If a temporary upload path is ever used, `mistral_delete_file()` deletes it immediately after OCR
4. CV body text / PII are never written to general application logs
5. Existing production CVs are **not** sent while the flag is OFF

## Migration / rollback

**Migration:** `ensure_schema()` creates:

- `cv_extraction_cache`
- `cv_extraction_leases`
- `cv_extraction_runs`

**Rollback:**

1. Set `WATHEFNI_CV_MISTRAL_OCR=false` (instant behavioral rollback)
2. Redeploy previous orchestrator artifact if code rollback needed
3. Tables are additive; safe to leave in place

## Staging proof checklist

Use **synthetic** scanned PDF + image CV only. Do not use production candidate CVs.

1. Install `mistral.env` on staging
2. Enable `WATHEFNI_CV_MISTRAL_OCR=true` only on staging service
3. Run `smoke-test-cv-extraction-ocr.py`
4. Run staging proof script against fixtures
5. Record latency, billable pages, cost, rescue rate
6. Stop for owner approval before production

## Controlled production rollout recommendation

1. Keep production flag OFF
2. After staging proof + privacy approval:
   - enable for one pilot company only (env or future company setting)
   - monitor `cv_extraction_runs` for cost, latency, rescue rate, failures
3. Expand company by company
4. Do not backfill old CVs in the first rollout
