# EN / AR / RTL proof

## Backend labels

| Key | EN | AR |
|---|---|---|
| okr_cycle | OKR cycle | دورة النتائج الرئيسية |
| review_cycle | Review cycle | دورة المراجعة |
| confidence | Confidence | الثقة |
| claimed | Claimed (not verified) | مُدّعى (غير موثّق) |
| AI-SYNTHESIZED | AI-synthesized (explanation only) | توليد الذكاء (شرح فقط) |
| active | Active | نشط |

Proved in `tests/pt1-unit.out` and staging DB bilingual checks.

## HR Web

`PerformanceWorkspace.tsx` and `TalentWorkspace.tsx` ship paired EN/AR copy for cycle, alignment, update, confidence, and evidence index.

## Employee App

`src/i18n/en.json` + `ar.json` include `okrCycle`, `noOkrCycle`, `addUpdate`, `confidenceNotProgress`, `alignmentHint`, `checkInNotProgress`, `historyReady`.

## Setup

`Wave4PerformanceTalentPoliciesCard.tsx` bilingual toggles for confidence and OKR Talent evidence consume contract.
