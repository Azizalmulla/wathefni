# Identity Document Processing Wave 2 — GPT Retirement and Mistral Authority

**Stamp:** staging `20260804T032734Z` · production canary `20260804T033032Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Civil ID front/back, passport, residency, work permit, medical certificate  
**HR authority:** machine fields remain non-authoritative until HR confirms

## Verdict

| Gate | Result |
|---|---|
| Staging cutover (Mistral authority, GPT retired) | **GO** |
| Production WATHEFNI canary | **GO** |
| Expand identity authority beyond WATHEFNI | **NO-GO** |
| CV / Ranking / Candidate Knowledge / Migration Wave 1 / payroll / shared foundation | **unchanged** |

Mistral Document AI is now the sole automatic path for identity classify / verify / extract. GPT is not a fallback, shadow authority, or hidden secondary path. Instant rollback is restore of the previous code package only.

## Phase A — staging cutover

**Backup / rollback:** `/opt/wathefni/backups/staging-pre-identity-wave2-20260804T032734Z/ROLLBACK.sh`

**Deployed:**

- `identity_document_extraction.py` (authority APIs)
- `app.py` (three identity callers delegated to Mistral)
- systemd drop-in `identity-mistral-authority.conf`:
  - `WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=on`
  - `WATHEFNI_IDENTITY_MISTRAL_COMPANIES=WATHEFNI`

**Qualify evidence:** `ops/evidence/identity-wave2-authority-20260804/summary.json`

| Check | Result |
|---|---|
| Classify OK | 12/12 |
| Verify OK | 12/12 |
| Extract OK | 12/12 |
| GPT-free | 12/12 |
| `authoritative=false` + HR confirmation required | 12/12 |
| Circuit → durable `needs_review` | PASS |
| Non-canary company disabled under prod canary gate | PASS |
| Runtime `gpt_identity_calls` | **0** |
| Runtime provider | `mistral` only |

Also exercised: front/back Civil IDs, duplicate keys (content hash + identifier), date/expiry validation, HR correction example (machine stays non-authoritative), retries/circuit breaker, no GPT re-enable flag.

## Phase B — production WATHEFNI canary

**Backup / rollback:** `/opt/wathefni/backups/production-pre-identity-wave2-20260804T033032Z/ROLLBACK.sh`

**Live env (MainPID):**

```text
WATHEFNI_ENV=production
WATHEFNI_IDENTITY_MISTRAL_AUTHORITY=canary
WATHEFNI_IDENTITY_MISTRAL_COMPANIES=WATHEFNI
WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK=off
```

**Health:** `{"status":"ok",...,"application_environment":"production"}`

**Qualify evidence:** `ops/evidence/identity-wave2-prod-canary-20260804/summary.json`

| Check | Result |
|---|---|
| Classify / verify / extract | 12/12 each |
| GPT-free | 12/12 |
| `gpt_identity_calls` | **0** |
| OTHERCO authority | disabled |
| WATHEFNI authority | enabled |

Non-WATHEFNI companies: Mistral authority off → durable `needs_review` / unverified — **no GPT**.

## Exact GPT identity call sites removed or disabled

| Former GPT site | Wave 2 behavior |
|---|---|
| `extract_compliance_document_metadata` | Delegates to `identity_document_extraction.extract_compliance_via_mistral` only |
| GPT body inside `verify_onboarding_media_item` | Removed; delegates to `verify_onboarding_media` |
| GPT body inside `classify_onboarding_media_upload` | Removed; delegates to `classify_onboarding_media` |
| Invalid `temperature: 0` Terra vision payloads for identity | Removed with the GPT bodies |
| Identity-specific GPT prompts / retries / fallback | Removed (no stale prompt strings remain in `app.py`) |

Source proof on staging + production: each of the three functions contains `identity_document_extraction` and does **not** contain `planner_provider_config`, `temperature`, or vision `input_image` payloads.

## Runtime zero-call proof

| Environment | `gpt_identity_calls` | `mistral_calls` (qualify) | `last_provider` |
|---|---:|---:|---|
| Staging qualify | 0 | 37 | mistral |
| Prod WATHEFNI canary qualify | 0 | 37 | mistral |

Stale identity GPT prompt search on production `app.py`: **0 hits**.

No `WATHEFNI_IDENTITY_GPT*` flag exists. No hidden GPT fallback helper in the identity module (`gpt_auto_fallback_forbidden() -> True`).

## Remaining GPT usage elsewhere in Wathefni (intentionally retained)

Shared planner / tool-agent infrastructure remains for unrelated features (counts in production `app.py`):

| Symbol / marker | Approx count | Notes |
|---|---:|---|
| `planner_provider_config(` | 16 | Pre-Hiring Assistant / toolcall / non-identity |
| `openai-responses` | 16 | Same shared provider paths |
| `WATHEFNI_TOOL_AGENT*` | 9 | Assistant config |
| `gpt-5.6-terra` default | 1 | Default tool-agent model pin |

Also present and **out of scope** (not identity):

- `WATHEFNI_CV_GPT_VISION_RESCUE=true` — CV path only; unchanged this wave
- Document foundation GPT auto OCR fallback remains **off**

## Flow (live)

```text
upload (original file preserved)
  → document_envelope@1
  → Mistral Document AI classify / verify / extract
  → strict schema + field confidence/provenance
  → deterministic validation
  → authoritative=false until HR confirms
  → needs_review on outage / circuit / unusable
  → no GPT calls
```

## Expand beyond WATHEFNI

**NO-GO** until owner approval after soak on WATHEFNI canary. Next wave would only widen `WATHEFNI_IDENTITY_MISTRAL_COMPANIES` (or flip authority `on` in production) — still without restoring GPT.

## Rollback

Restore previous package:

- Staging: `/opt/wathefni/backups/staging-pre-identity-wave2-20260804T032734Z/ROLLBACK.sh`
- Production: `/opt/wathefni/backups/production-pre-identity-wave2-20260804T033032Z/ROLLBACK.sh`

Rollback restores prior code + removes the identity authority drop-in. It does **not** re-enable a live hidden GPT identity path inside the Wave 2 package.
