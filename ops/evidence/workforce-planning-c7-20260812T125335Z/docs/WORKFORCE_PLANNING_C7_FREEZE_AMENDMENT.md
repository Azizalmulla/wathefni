# Wave 6 C7 — Freeze Amendment (Workforce Planning)

**Stamp:** `WORKFORCE_PLANNING_FULL_PASS`  
**Evidence:** `ops/evidence/workforce-planning-c7-20260812T125335Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C7

- Plans, baselines (+ rows), scenarios, assumptions, demand items, gaps, approvals  
- Execution handoffs (`employment_mutated_by_wfp=false`, `hire_created=false`, draft-req only)  
- Setup Wave 6 Workforce Planning module card + company policy knobs  
- Typed Wave 5 fact outbox with explicit `truth_plane` (plan/scenario/approved_execution)  
- Flags: `WATHEFNI_WORKFORCE_PLANNING_C7` + `WATHEFNI_WORKFORCE_PLANNING_COMPANIES`  

## Binding boundaries (frozen)

1. Actual workforce ≠ workforce plan ≠ scenario ≠ approved execution  
2. Planned headcount never enters actual Wave 5 / C2 headcount metrics  
3. JA remains the only job/grade catalog authority  
4. Recruiting / Comp / Talent remain OPTIONAL  
5. Approved demand creates linked **draft** requisition only (explicit action); no auto-post/hire  

## What does **not** change

1. Waves 1–5 remain frozen  
2. C1–C6 Wave 6 remain frozen  
3. No C8 product-acceptance slice yet  
4. Global flags remain off / company-gated; FULL_PASS ≠ broad rollout  

## Rollback

`WATHEFNI_WORKFORCE_PLANNING_C7=off` + clear company allowlist; plan/scenario/handoff history retained.
