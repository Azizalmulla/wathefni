# R5B EN / AR / RTL proof

Bilingual from the start. No new English-only Performance debt.

## HR Web

`PerformanceWorkspace.tsx` ships paired EN/AR copy for:

- workspace title / subtitle
- Overview, Goals, Reviews, Calibration, Development tabs
- empty / error / retry via `ResourceState` (`locale` `en` | `ar`)
- launch / close / submit / create actions
- pre-calibration vs calibrated labels
- Learning-off and Talent-off honesty
- Setup deep-link banner

Unit: `workspace bilingual AR` (`الأداء` present). Dashboard vitest includes `dataState.test.tsx`.

Setup card `Wave4PerformancePoliciesCard` titles and descriptions are EN+AR. Performance-only scope copy: "Talent stays unavailable." / "المواهب تبقى غير متاحة."

## Employee App

`src/i18n/en.json` and `src/i18n/ar.json` `performance.*` including:

- title, goals, reviews, check-ins, development
- progress, current value, submit, rationale, final outcome
- empty states
- `talentOff` (EN: "A high rating is not HiPo…"; AR: "التقييم العالي لا يعني إمكانات عالية…")

Unit: `employee EN copy`, `employee AR copy`.

Mobile layout uses logical primitives (existing employee-mobile RTL contract). Performance screens use the same `ListRow` / `EditorialHeading` / `QuietEmpty` stack.

## Qualification

- EN journey: unit + staging DB + vitest
- AR/RTL journey: copy present in Web + App; RTL layout primitives unchanged
- Errors / empty states go through R4 `ResourceState` / query error paths, not hardcoded English-only empty
