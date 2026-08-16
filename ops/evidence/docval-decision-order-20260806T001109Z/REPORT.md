# Decision-order fix — non-doc message + blurry OCR override

**Stamp:** `20260806T001109Z`  
**Evidence:** `ops/evidence/docval-decision-order-20260806T001109Z/`  
**Scope:** Soft canary Aziz + Talal only (`HARD=off`)

## Live retest audit (exact uploads)

### A) Random non-document — `2026-08-06T00:03:42Z`

| Field | Value |
|---|---|
| Event | `a4ff43d3-8dde-4b3f-92db-9ff85e904925` |
| HTTP | **422** |
| Bytes | 192836 (bytes not stored — rejection) |
| Rejection code | `glare_or_shadow` ← **wrong message** |
| Document-likeness | **Not evaluated** (capture gate short-circuited before Mistral) |
| Capture | Local glare reject fired first |
| Final rule (buggy) | capture-reject → glare copy |
| Correct rule | obvious non-document → wrong-document message |

### B) Blurry Civil ID — `2026-08-06T00:03:58Z`

| Field | Value |
|---|---|
| HTTP | **200** |
| SHA | `afa47900d614…0c4f` (same as prior allow `ed6cae26-…` / `23:51:31Z`) |
| New version? | **No** — idempotent same-SHA replay |
| Borderline? | **No** — capture assess = **reject** `too_blurry` |
| Metrics | laplacian **3.366** (< reject max **6.0**); glare 0.0; crop_hot_sides **3** |
| Stored Mistral (23:51) | `civil_id` · conf **0.97** · `matches=true` · `extracted` · `unreadable_reason=null` |
| Decision at 23:51 | `allow` (pre–capture-layer / OCR-ok path) |
| Live re-eval now | **block** `too_blurry` even with Mistral conf **0.96** |
| Why 00:03:58 submitted | After reset-to-pending, Wave 2A idempotent pending version with same SHA returned **200 before validation** |

**Not** “borderline + high OCR → allow”. It was **idempotent bypass** of the capture gate on a prior-allowed SHA.

## Enforced order (deployed)

1. Obvious non-document → block with wrong-document message  
2. Credible document + clearly bad capture → block with retake guidance  
3. Credible document + borderline capture → HR (`allow_uncertain`)  
4. Clean → continue normally  

High OCR confidence **cannot** convert capture-reject into allow.  
Same-SHA idempotent short-circuit only while item is already `submitted`/`processing` (not after reset-to-pending).

## Fixtures

- `fixtures/blurry_civil_id_afa47900.jpg` — exact live blurry Civil ID  
- `fixtures/random_nondoc_glare_like.jpg` — glare-heavy non-doc regression (bytes of the live 422 were not stored)

## Proof

Prod smokes PASS. Prove JSON: `audit/prove.json`

| Case | Result |
|---|---|
| Exact blurry + OCR 0.97 mock | block `too_blurry` |
| Exact blurry + live Mistral | block `too_blurry` (conf 0.96) |
| Glare nondoc + lifestyle mock | block `looks_like_photo_not_document` (not glare) |
| Glare nondoc + live Mistral | block `not_a_document` (not glare) |

## Canary

`civil_id_canary_test` reset → **pending** / upload enabled. Real Civil ID untouched.
