# Lightweight capture-quality layer — Document Validation Parity

**Stamp:** `20260806T000158Z`  
**Evidence:** `ops/evidence/docval-capture-quality-layer-20260806T000158Z/`  
**Scope:** Soft canary Aziz + Talal only (`HARD=off`)

## Layer

`onboarding_capture_quality.py` (PIL + NumPy only):

| Check | Reject | Borderline → HR |
|---|---|---|
| Resolution | short &lt; 360 or long &lt; 480 | short &lt; 520 |
| Blur (Laplacian var) | &lt; 6 | &lt; 40 |
| Glare / overexposure | white frac ≥ 0.28 | ≥ 0.18 |
| Heavy crop / cut-off | ≥ 3 hot border sides | ≥ 2 |

- Clearly bad → **block** + retake copy  
- Borderline → continue Mistral/identity, then **allow_uncertain** (`capture_quality_borderline`)  
- Clean → continue normally  

Mistral extraction + identity matching unchanged. No GPT / OpenCV / KYC SDK.

## Proof

| Case | Outcome |
|---|---|
| Clear synthetic ID | allow |
| Mild blur | allow_uncertain (HR) |
| Severe blur | block `too_blurry` |
| Glare | block `glare_or_shadow` |
| Heavy crop | block `document_not_fully_visible` |
| Prior “blurry but OCR-ok” canary (sha afa479…) | **reject** `too_blurry` (laplacian 3.37) — closes OCR-override gap |
| Low false rejection | clear synthetic allow; smoke PASS |

## Canary

`civil_id_canary_test` reset to **pending** / upload enabled.
