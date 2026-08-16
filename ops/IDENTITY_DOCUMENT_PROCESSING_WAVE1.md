# Identity Document Processing Wave 1 — Shared Foundation Qualification

**Stamp:** `20260804`  
**Host:** staging qualify on `root@76.13.63.68` (`/opt/wathefni/staging/claw-mirror`)  
**Production deploy this wave:** **NO-GO** (explicit)  
**Staging authority (module ready / shadow-canary eligible):** **GO**

## Verdict

Mistral Document AI identity extraction via `document_envelope@1` is qualified to replace the legacy GPT-vision path for Civil ID, passport, residency, work permit, and medical certificates on **staging authority next**, with HR remaining final authority. This wave does **not** cut over production and does **not** mutate the shared foundation route matrix.

Evidence:

- Corpus: `ops/evidence/identity-wave1-corpus-20260804/`
- Bench: `ops/evidence/identity-wave1-qualify-20260804/summary.json`
- Module: `wathefni-orchestrator/identity_document_extraction.py`
- Scripts: `scripts/build-identity-wave1-synthetic-corpus.py`, `scripts/wave1-identity-document-processing-qualify.py`

## Exact current GPT dependency map

| Call site | File | Role | Gate |
|---|---|---|---|
| `extract_compliance_document_metadata` | `app.py` ~30121–30220 | Primary identity/compliance field extraction via vision | `confidence >= 0.55` → extracted; type mismatch if `>= 0.75` and wrong type |
| `verify_onboarding_media_item` | `app.py` ~29955+ | Verify uploaded onboarding media matches expected item | `confidence >= 0.65` |
| `classify_onboarding_media_upload` | `app.py` ~30034+ | Classify which onboarding item an upload is | `confidence >= 0.75` |
| Provider | `planner_provider_config()` | Default model `gpt-5.6-terra` via `openai-sse` / Responses API | — |
| Input | `media_data_uri(media)` | Base64 data-URI image/PDF ≤ 8MB | — |

**Legacy GPT schema fields:** `document_type`, `document_number`, `issued_date`, `expiry_date`, `nationality`, `full_name`, `date_of_birth`, `confidence`, `reason`.

**Persistence / authority today:** proposals land in `employee_documents` / `compliance_documents` / `governed_document_versions` with OCR proposal `authoritative=false` until HR confirms.

**Foundation route (unchanged this wave):**

```text
document_class=identity
structuring=identity_processor_current_gpt_vision
ocr_policy=do_not_use_cv_v2
authority_in_this_wave=legacy_gpt_vision_until_replacement_qualified
```

**Known production GPT breakage discovered during bench:**  
`extract_compliance_document_metadata` sends `temperature: 0`. `gpt-5.6-terra` on the Responses API rejects temperature. Wave 1 scored GPT with temperature omitted so the *intended* path is comparable; the live `temperature=0` call is currently fail-closed unless another code path bypasses it.

## Required flow (implemented candidate)

```text
upload
  → document_envelope@1 (shared foundation helper)
  → Mistral OCR / Document AI annotation (strict identity schema) when needed
  → per-field confidence + provenance (authoritative=false)
  → deterministic validation only (dates, expiry≥issue, id format, front/back, duplicates)
  → needs_review when unusable / circuit open
  → HR review and confirmation (still final authority)
```

Hard constraints honored:

- No CV Extraction V2 for identity
- No GPT as automatic extraction or fallback
- No invented values (null stays null); missing fields remain missing
- No changes to CV extraction, Ranking, Candidate Knowledge, Migration Wave 1, or foundation route matrix authority

## New identity schema (Mistral Document AI)

`document_type`, `side`, `document_relationship`, `full_name_ar`, `full_name_en`, `document_number`, `nationality`, `date_of_birth`, `issue_date`, `expiry_date`, `employer_or_sponsor`, `field_confidence`, `overall_confidence`.

Each materialized field carries:

```json
{
  "value": "... or null",
  "confidence": 0.0,
  "provenance": {
    "source": "mistral_document_ai",
    "extractor": "identity_mistral_document_ai",
    "contract": "identity-document-extraction-v1",
    "authoritative": false,
    "hr_confirmed": false
  }
}
```

Retry + circuit breaker: env `WATHEFNI_IDENTITY_MISTRAL_RETRIES` (default 2), `WATHEFNI_IDENTITY_MISTRAL_CIRCUIT_FAILURES` (default 3), `WATHEFNI_IDENTITY_MISTRAL_CIRCUIT_COOLDOWN_S` (default 60). Open circuit → durable `needs_review` (no GPT fallback).

## Labeled synthetic / anonymized qualification set

12 fixtures covering:

| Coverage | Fixtures |
|---|---|
| Types | civil_id (front/back), passport, residency, work_permit, medical |
| Languages | Arabic, English, bilingual |
| Capture | scan, mobile photo, rotated, low resolution |

All synthetic/anonymized — no real customer PII.

## Labeled benchmark results (Mistral vs GPT)

| Metric | Mistral path | GPT path (temp omitted) |
|---|---:|---:|
| Mean field accuracy | **96.3%** | 91.1% |
| Arabic integrity rate | 87.5% | 87.5% |
| Invented fields | **0** | 2 |
| Missing fields | 0 | 0 |
| Incorrect fields | 4 | 8 |
| Mean latency | 4479 ms | 2529 ms |
| Total cost (12 docs) | **$0.048** | $0.053 |
| Cost ratio (M/G) | 0.90× | — |
| HR review burden proxy | **4** | 10 |
| `needs_review` | 0 | 0 |

Accuracy delta (Mistral − GPT): **+5.2 pp**.  
Hardest fixture for both: `work_permit_ar_lowres_01` (Mistral 56%, GPT 40%).

## Failure classes

**Mistral**

- `mistral_incorrect:document_number` (1) — low-res Arabic work permit
- `mistral_incorrect:date_of_birth` (1)
- `mistral_incorrect:employer_or_sponsor` (1)
- `mistral_arabic_corrupt:full_name_ar` (1)

**GPT**

- `gpt_incorrect:document_number` (2)
- `gpt_invented:full_name_en` (2) — silent invention on Arabic-only docs
- plus incorrect nationality / DOB / expiry / employer / Arabic corrupt (1 each)

## GO / NO-GO

| Gate | Result |
|---|---|
| Staging authority (module qualify / next shadow flip) | **GO** |
| Production deploy / live cutover this wave | **NO-GO** |
| CV / Ranking / Candidate Knowledge / Migration Wave 1 / foundation matrix mutation | **unchanged** |

Staging GO criteria met: Mistral mean accuracy ≥ 70%, not materially worse than GPT, zero invented fields, provenance present, no GPT fallback, circuit behavior available, durable `needs_review` path present.

## Smallest production cutover wave

**Identity Document Processing Wave 2 — Staging Authority → Production Shadow → Canary**

1. Staging: wire `identity_document_extraction.extract_identity_document` behind a shadow flag for onboarding extract (HR confirmation gate unchanged).
2. Staging authority canary for **civil_id + passport** only.
3. Production **shadow** (write non-authoritative proposals; GPT may remain live) for ~1 week dual-run.
4. Production canary company `WATHEFNI`, then expand residency / work_permit / medical.
5. Remove GPT extract/verify/classify identity calls after dual-run parity; update foundation route matrix `structuring` to `identity_processor_mistral_document_ai`.
6. Fix or delete the Terra `temperature=0` call site as part of GPT retirement (do not keep a broken fallback).

## What this wave did / did not do

**Did**

- Added identity module + synthetic corpus + staging Mistral-vs-GPT qualify evidence
- Synced module/scripts to staging qualify tree only

**Did not**

- Deploy to production
- Change `app.py` onboarding extract/verify/classify callers
- Change CV V2, Ranking, Candidate Knowledge, Migration Wave 1
- Change `document_processing_foundation.ROUTE_MATRIX` authority labels
