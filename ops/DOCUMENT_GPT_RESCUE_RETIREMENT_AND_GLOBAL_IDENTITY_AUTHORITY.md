# Document GPT Rescue Retirement + Global Identity Authority

**Stamp:** `20260804T034341Z`  
**Host:** `root@76.13.63.68`  
**Assistant / tool-agent GPT:** retained (unrelated)

## Final gate

**PRODUCTION_DOCUMENT_PIPELINE_GPT_FALLBACK_FREE = GO**

| Gate | Staging | Production |
|---|---|---|
| Global identity authority | **GO** | **GO** |
| CV GPT rescue retired | **GO** | **GO** |
| Zero GPT identity calls | **0** | **0** |
| Zero CV GPT rescue calls | hard-off + blocked | hard-off + blocked |
| Tenant isolation (WATHEFNI + ISOID1 + ISOID2) | no leakage | no leakage |

Evidence:

- Staging: `ops/evidence/document-gpt-free-global-identity-20260804/summary.json`
- Production: `ops/evidence/document-gpt-free-global-identity-prod-20260804/summary.json`

## Global identity authority status

**ON for all current and future tenants** (default production contract).

Behavior:

- Mistral is the sole automatic provider for identity classify / verify / extract
- Civil ID, passport, residency, work permit, medical supported
- No GPT fallback, shadow path, or hidden secondary provider
- HR confirmation remains mandatory (`authoritative=false` until HR confirms)
- Failures → durable `needs_review`
- Tenant isolation via envelope `company_code` + per-call subject keys
- Cost / retry / circuit-breaker controls remain active

### Exact flags / config changed

| Flag | Before | After |
|---|---|---|
| `WATHEFNI_IDENTITY_MISTRAL_AUTHORITY` | `canary` (prod) / `on`+allowlist (staging) | **`on`** (global default) |
| `WATHEFNI_IDENTITY_MISTRAL_COMPANIES` | `WATHEFNI` allowlist | **removed as primary gate** (legacy `canary` mode only) |
| `WATHEFNI_IDENTITY_MISTRAL_DISABLE_COMPANIES` | n/a | **``** (optional per-tenant disable) |
| Kill switch | n/a explicit | `AUTHORITY=off\|kill\|disabled` |
| `WATHEFNI_CV_GPT_VISION_RESCUE` | `true` (stale / conflicting) | **`off`** + **code hard-ignores** |
| `WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK` | `off` | `off` (unchanged) |

Live process env (staging + production):

```text
WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=on
WATHEFNI_IDENTITY_MISTRAL_DISABLE_COMPANIES=
WATHEFNI_CV_GPT_VISION_RESCUE=off
WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
```

## CV GPT rescue removal proof

Code:

- `cv_extraction.gpt_vision_rescue_enabled()` → always `False` (flag ignored)
- `extract_candidate_cv_document` passes `vision_rescue=None`
- `extract_image_cv_text_with_vision` retired stub — never calls planner/OpenAI
- `_gpt_vision_rescue_adapter` hard no-op returning `cv_gpt_vision_rescue_retired`
- PDF/image OCR failure paths → `needs_review` / `extraction_failed` only
- Stale CV rescue prompt removed from `app.py`
- `inbound_cv_processing.plan_extraction_providers` always `gpt_vision_rescue_eligible=False`
- Docs + `enable-prod-cv-ocr.sh` updated to `off`

Runtime qualify (both envs):

- `gpt_vision_rescue_enabled=false`
- stale `WATHEFNI_CV_GPT_VISION_RESCUE=true` ignored
- forced entrypoints return `cv_gpt_vision_rescue_retired`
- `blocked_attempts=2` (defense counters only; no provider call)

Preserved: local hybrid PDF authority, pdf-inspector/native extraction, Poppler fallback, Mistral OCR, bounded retries/circuit breaker, durable needs_review, CV V2 structuring/evidence, Ranking, Candidate Knowledge.

## Tenant isolation evidence

Synthetic tenants exercised on the same Civil ID fixture: `WATHEFNI`, `ISOID1`, `ISOID2`.

For each tenant:

- classify / verify / extract succeeded
- `envelope.company_code` matched tenant
- proposal namespaced by tenant
- `authoritative=false`, `hr_confirmation_required=true`
- HR correction example recorded as separate confirmed payload
- `leakage=[]` (no cross-tenant envelope/proposal mix)

Also proved:

- kill switch blocks all tenants
- `DISABLE_COMPANIES=ISOID2` disables only ISOID2
- future tenant `FUTURECO` enabled under global default

## Rollback path

Instant package restore (not a hidden GPT re-enable inside the new code):

- Staging: `/opt/wathefni/backups/staging-pre-doc-gpt-free-20260804T034341Z/ROLLBACK.sh`
- Production: `/opt/wathefni/backups/production-pre-doc-gpt-free-20260804T034341Z/ROLLBACK.sh`

Operational overrides without full rollback:

- Identity kill: set `WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=kill`
- Per-tenant pause: set `WATHEFNI_IDENTITY_MISTRAL_DISABLE_COMPANIES=TENANT`

## Sibling freezes

CV V2 / Ranking / Candidate Knowledge / Migration Wave 1 / payroll / shared foundation route matrix: **unchanged**.  
Assistant/tool-agent GPT infrastructure: **retained**.
