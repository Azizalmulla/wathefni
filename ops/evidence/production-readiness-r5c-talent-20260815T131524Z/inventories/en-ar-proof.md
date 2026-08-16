# R5C EN / AR / RTL proof

Bilingual from the start. No new English-only Talent surface.

## HR Web

`TalentWorkspace` `copy(isAr)` covers:

- Title / IA tabs (Overview, People, Reviews, Succession, Mobility, 9-box)
- Empty / forbidden / unavailable / no-score copy
- Performance-optional and Recruiting-optional honesty
- Actions: profile, evidence, potential, HiPo, review, succession, readiness

Arabic examples: `المواهب`, `مراجعات المواهب`, `التعاقب`, `التنقل الداخلي`, `شبكة التسعة (عرض مشتق)`.

`ResourceState` is locale-aware via existing dashboard primitives.

## Employee App

`en.json` / `ar.json` `talent.*`:

- EN: Talent title, career interests, hidden-judgments hint
- AR: `الاهتمامات المهنية` and matching RTL strings
- Hub uses `readingEdgeAlign(isRTL)`

Unit contract: `employee EN copy` + `employee AR copy` in `smoke-test-r5c-talent-surface.py`.

## Domain labels

C6 `STATUS_LABELS` already ship EN+AR for review / HiPo / readiness states (`ready_now`, `designated`, etc.). HTTP does not invent a second label table.
