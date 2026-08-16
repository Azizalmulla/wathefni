# Wave 5 C1 — Freeze Amendment (KPI Registry / Intelligence Spine)

**Stamp:** `HR_INTELLIGENCE_REGISTRY_FULL_PASS`  
**Charter:** `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md` (`WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C1

- KPI Registry + fact/query spine authority in `hr_intelligence_registry_c1.py`  
- Commercial entitlement key remains **`analytics`** (no second commercial module)  
- Binding cohort / headcount / FTE / demographic policy constants from charter §0.7–§0.8  
- Global flags remain fail-closed (`WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1`, company allowlist, `WATHEFNI_ANALYTICS_KILL`)  

## What does **not** change

1. Waves 1–4 remain frozen — C1 consumes nothing that mutates domain SoT  
2. Attention remains Ops Attention (not Intelligence)  
3. FTE remains blocked until authoritative inputs (C2+)  
4. No Intelligence UI until later slices  

## Rollback

`WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1=off` + clear company allowlist; optional `WATHEFNI_ANALYTICS_KILL=on`.  
Registry definitions and evaluation history are retained.
