# Wave 5 C4 — Freeze Amendment (Time / Leave / Payroll Intelligence)

**Stamp:** `HR_INTELLIGENCE_TIME_PAY_FULL_PASS`  
**Charter:** `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md`  
**Date:** 2026-08-12  

## What freezes with C4

- Time/Leave/Shifts/OT/Payroll formula handlers on C1 shared evaluator  
- Attendance / leave / shift / OT / sealed-payroll projections (not alternate SoT)  
- Money KPIs fail-closed without sealed `money_authority=wathefni`  
- Settlement finalized ≠ paid; payment acknowledged ≠ paid  

## What does **not** change

1. C1–C3 stamps remain frozen  
2. Waves 1–4 domain authorities remain SoT  
3. Commercial key remains `analytics`  
4. No dashboard redesign  

## Rollback

`WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4=off` + clear company allowlist; prior history retained.
