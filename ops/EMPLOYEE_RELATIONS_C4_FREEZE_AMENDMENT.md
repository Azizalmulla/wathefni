# Wave 6 C4 — Freeze Amendment (Employee Relations)

**Stamp:** `EMPLOYEE_RELATIONS_FULL_PASS`  
**Evidence:** `ops/evidence/employee-relations-c4-20260812T113855Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C4

- ER case types/versions, sealed cases, parties, allegations, access grants  
- Investigation notes/findings (lockable), evidence refs, safe employee messages  
- Outcomes + optional employment-change handoffs (no ER employment mutation)  
- Setup Wave 6 Employee Relations module card + company policy knobs  
- Typed Wave 5 fact outbox (safe aggregates only)  
- Flags: `WATHEFNI_EMPLOYEE_RELATIONS_C4` + `WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES`  

## What does **not** change

1. Waves 1–5 remain frozen  
2. C1–C3 Wave 6 remain frozen  
3. Wave 3 employment-change/termination remains sole employment mutation authority  
4. Ordinary HR / manager permissions do not imply ER access  
5. No Engagement / Comp / WFP product slices yet  
6. Global flags remain off / company-gated; FULL_PASS ≠ broad rollout  

## Rollback

`WATHEFNI_EMPLOYEE_RELATIONS_C4=off` + clear company allowlist; case history retained; no employment rewrite.
