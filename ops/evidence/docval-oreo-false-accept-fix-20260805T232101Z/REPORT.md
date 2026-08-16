# Document Validation Parity — Oreo false-accept fix

**Stamp:** `20260805T232101Z`  
**Evidence:** `ops/evidence/docval-oreo-false-accept-fix-20260805T232101Z/`  
**Scope:** Aziz/Talal soft canary only (`HARD=off`; allowlist unchanged)

## Root cause

Soft-gate treated **unknown / 0 confidence / no document fields** as “blurry document needing HR review” (`allow_uncertain` ← `needs_review`).  
The Oreo lifestyle photo was therefore **stored** and sent to HR instead of blocked.

## Fix

In `onboarding_doc_validation_parity.py`:

- `has_credible_document_evidence` — document label, match, or extracted fields required for uncertain path
- `is_obvious_non_document` — unknown/empty/selfie/product/screenshot with no document evidence → **block**
- `validator_unavailable` when verify returns None/errors — **block + retry**, do not store arbitrary bytes
- Soft `allow_uncertain` only when credible document evidence exists but readability/confidence is poor

Hard-gate not expanded. Soft allowlist remains Aziz + Talal only.

## Proof

| Fixture | Expected | Result |
|---|---|---|
| selfie | block | PASS |
| person holding product | block | PASS |
| food/product photo | block | PASS |
| game screenshot | block | PASS |
| blurry Civil ID | soft uncertain | PASS |
| cropped/partial Civil ID | soft uncertain | PASS |
| clear Civil ID | allow | PASS |
| Oreo live re-eval (sha `67221e96…`) | block `not_a_document` | PASS |

Prod smoke: see `tests/prod-smoke.out`.

## Canary reset

`civil_id_canary_test` reset to **pending** / upload enabled.  
Real `civil_id` untouched (`accepted`, sha `fe98f7d9…`).

## Retest steps (Aziz mobile)

1. Open disposable item **CANARY ONLY — Civil ID upload test**.
2. Upload a clear non-document (selfie / product / food) → must **block** with correction; item stays pending.
3. Optionally upload a blurry/partial Civil ID → soft submit + HR review alert.
4. Upload a clear Civil ID → accept/processing.
5. After any successful/uncertain submit:  
   `WATHEFNI_ENV=production .venv/bin/python ops-aziz-docval-canary-item.py reset`

## Deploy

- Host: `/opt/wathefni/orchestrator/onboarding_doc_validation_parity.py`
- Restart: `wathefni-orchestrator` healthy after deploy
- Flags unchanged: `SOFT=on` `HARD=off` companies=WATHEFNI allowlist=Aziz,Talal
