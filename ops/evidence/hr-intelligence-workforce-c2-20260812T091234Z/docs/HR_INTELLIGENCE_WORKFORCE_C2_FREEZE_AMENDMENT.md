# Wave 5 C2 — Freeze Amendment (Workforce Intelligence)

**Stamp:** `HR_INTELLIGENCE_WORKFORCE_FULL_PASS`  
**Charter:** `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md`  
**Date:** 2026-08-12  

## What freezes with C2

- Workforce population resolver + headcount/future-starters/hires/exits/turnover/retention/tenure/span formula handlers  
- Employment-period projection + org assignment history for as-of intelligence (projection, not alternate employee SoT)  
- C1 `register_formula_handler` extensibility (shared evaluator remains authority)  

## What does **not** change

1. C1 Registry stamp remains frozen  
2. Waves 1–4 remain frozen  
3. FTE remains blocked  
4. Commercial key remains `analytics`  

## Rollback

`WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2=off` + clear company allowlist; C1/evaluations/periods retained.
