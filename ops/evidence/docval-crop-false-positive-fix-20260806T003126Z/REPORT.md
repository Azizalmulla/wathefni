# Crop false-positive fix — weak crop signal + rejection metrics

**Stamp:** `20260806T003126Z`  
**Evidence:** `ops/evidence/docval-crop-false-positive-fix-20260806T003126Z/`  
**Scope:** Soft canary Aziz + Talal only (`HARD=off`)

## Server change

- `crop_hot_sides` is **no longer** a standalone hard reject / borderline
- Recorded as weak `crop_signal` in metrics
- `document_not_fully_visible` only when crop concern is **supported** by:
  low-confidence / non-match extraction, missing side/page, explicit partial/crop OCR text, missing required fields, or reliable document geometry
- Clear high-confidence complete docs **allow** even when frame-filling
- Blur / glare / resolution hard rejects unchanged (high OCR cannot override)
- Rejection audit + HTTP detail now persist `capture_quality` metrics

## Proof

| Case | Expected | Result |
|---|---|---|
| Clear inset | allow | PASS |
| Clear frame-filling | allow | PASS |
| Edge-touching valid | allow | PASS |
| Genuinely cut-off (partial OCR) | block `document_not_fully_visible` | PASS |
| Missing side | block `missing_side` | PASS |

## Mobile prep (not built)

- `apps/wathefni-employee-mobile/src/lib/documentScanner.ts` stub  
- `docs/NATIVE_DOCUMENT_SCANNER_PREP.md` — VisionKit / ML Kit / edge / auto-crop / perspective / retake / multi-page  

## Canary

`civil_id_canary_test` reset → pending / upload enabled.
