# Document Validation — capture-quality decision contract

**Stamp:** `20260805T232735Z`  
**Evidence:** `ops/evidence/docval-capture-quality-contract-20260805T232735Z/`

## Decision contract

| Case | Outcome |
|---|---|
| Obvious non-document | **block** |
| Blurry / cut off / glare / unreadable / missing side or page | **block** + calm EN/AR retake guidance |
| Credible correct document with genuine semantic/field uncertainty | **allow_uncertain** → HR |
| Clear valid document | **allow** |

HR review is **not** the default for fixable capture-quality issues.

## Soft/hard scope

- `SOFT=on` `HARD=off`
- Companies: `WATHEFNI`
- Allowlist: Aziz + Talal only (unchanged)
- Hard gate not expanded

## New / refined retake reasons (EN+AR)

- `too_blurry`
- `document_not_fully_visible`
- `glare_or_shadow`
- `missing_side`
- `missing_page`

Semantic HR copy for `needs_review` / `identity_unverified` reserved for non-fixable uncertainty.

## Proof (prod smoke)

| Fixture | Expected | Result |
|---|---|---|
| selfie / product / food / game screenshot | block | PASS |
| blurry Civil ID | block `too_blurry` | PASS |
| cropped/partial Civil ID | block `document_not_fully_visible` | PASS |
| glare/shadow Civil ID | block `glare_or_shadow` | PASS |
| Civil ID back-only | block `missing_side` | PASS |
| clear Civil ID | allow | PASS |
| semantic identity_unverified on clear match | allow_uncertain (HR) | PASS |
| Oreo-style unknown/0 | block `not_a_document` | PASS |

## Low false rejection note

Fixture clear Civil ID **allows**.  
Live re-eval of Aziz’s currently stored `civil_id` (sha `fe98f7d9…`, status accepted) classifies as `instruction_screenshot` via Mistral — that file is a WhatsApp onboarding UI screenshot, not a Civil ID photo. Blocking it is correct under this contract; it does not indicate false rejection of a genuine ID.

## Canary

`civil_id_canary_test` remains **pending** / upload enabled for live device retest.

## Retest

1. Non-document → block  
2. Blurry / cropped / glare Civil ID → block with retake message (not HR)  
3. Clear Civil ID → accept  
4. (Optional) ambiguous name on a clear ID → HR review alert after submit  
