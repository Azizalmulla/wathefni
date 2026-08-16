# Wave 5 C6 — Freeze Amendment (HR Intelligence Surfaces)

**Stamp:** `HR_INTELLIGENCE_SURFACES_FULL_PASS`  
**Charter:** `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md`  
**Date:** 2026-08-12  

## What freezes with C6

- Product-layer Intelligence workspace (Overview / explore / drill / about / saved views / export)  
- Thin HTTP routes under `/dashboard/posthire/intelligence/*` wrapping `c1.evaluate_kpi` only  
- Saved views + export job persistence (presentation layer — not KPI truth)  
- Scheduled delivery remains **safe debt** (same evaluator pipeline later)  

## What does **not** change

1. C1–C5 Registry/evaluator/domain KPI stamps remain frozen  
2. No new KPI math / fact engine / Talent inference  
3. Ops Attention (`inbox`) remains separate from Intelligence  
4. Commercial key remains `analytics`  

## Rollback

`WATHEFNI_HR_INTELLIGENCE_SURFACES_C6=off` + clear company allowlist; UI falls back to legacy Wave1 analytics patterns; C1–C5 retained.
