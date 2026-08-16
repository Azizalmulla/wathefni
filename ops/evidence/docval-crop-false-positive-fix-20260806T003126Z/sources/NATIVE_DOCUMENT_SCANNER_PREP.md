# Native document scanner — preparation (not built)

**Status:** prep only · **not** wired into upload UI · **no** native SDK dependency yet  
**Date:** 2026-08-06  
**Related:** soft doc-validation canary (Aziz/Talal); server crop false-positive fix

## Goal

Replace plain camera / library picks for onboarding documents with a free native
document scanner so employees capture inset, perspective-corrected pages with
retake and multi-page support — reducing server-side crop false positives.

## Target stack

| Platform | SDK | Notes |
|---|---|---|
| iOS | **VisionKit** `VNDocumentCameraViewController` | System UI; edge detect, crop, perspective |
| Android | **ML Kit Document Scanner** | Google Play services; similar UX |

Do **not** add paid KYC SDKs for this path.

## Required capabilities (later wave)

1. Edge detection  
2. Auto crop  
3. Perspective correction  
4. Retake  
5. Multi-page support  

## Repo prep (this change)

- `src/lib/documentScanner.ts` — typed API + `isNativeDocumentScannerAvailable()` → `false`  
- Current path remains `src/lib/uploadDocument.ts` (expo-image-picker / DocumentPicker)

## Later implementation checklist

1. Expo config plugin / native module for VisionKit + ML Kit Document Scanner  
2. New native build (permissions if needed)  
3. Wire Onboarding upload CTAs: prefer `scanDocument()`, fallback to picker  
4. Pass optional `corners` / geometry into upload metadata for server support  
5. EN+AR copy for scanner retake / multi-page  
6. Canary Aziz/Talal only until qualified  

## Out of scope now

- Installing VisionKit / ML Kit packages  
- Native build or OTA that claims scanner support  
- Changing server thresholds beyond the crop weak-signal fix  
