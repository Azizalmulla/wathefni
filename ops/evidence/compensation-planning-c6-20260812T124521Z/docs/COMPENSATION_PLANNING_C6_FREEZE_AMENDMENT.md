# Wave 6 C6 — Freeze Amendment (Compensation Planning)

**Stamp:** `COMPENSATION_PLANNING_FULL_PASS`  
**Evidence:** `ops/evidence/compensation-planning-c6-20260812T124521Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C6

- Compensation cycles, eligibility snapshots, salary bands (JA-referenced), budgets  
- Recommendations (original / calibrated / approved layers), approvals, final decisions  
- Explicit apply/handoff packages (`employment_mutated_by_comp=false`, `payroll_paid=false`)  
- Setup Wave 6 Compensation Planning module card + company policy knobs  
- Typed Wave 5 fact outbox (eligible population / approved adjustments)  
- Flags: `WATHEFNI_COMP_PLANNING_C6` + `WATHEFNI_COMP_PLANNING_COMPANIES`  

## Binding boundaries (frozen)

1. Comp Planning is **not** Payroll  
2. Plan approved ≠ salary changed ≠ payroll applied  
3. JA remains the only grade/job hierarchy authority  
4. Performance / Talent remain OPTIONAL inputs only  
5. Employment-change / payroll (or external) remain execution truth via explicit handoff  

## What does **not** change

1. Waves 1–5 remain frozen  
2. C1–C5 Wave 6 remain frozen  
3. No Workforce Planning (C7) product slice yet  
4. Global flags remain off / company-gated; FULL_PASS ≠ broad rollout  

## Rollback

`WATHEFNI_COMP_PLANNING_C6=off` + clear company allowlist; cycle/band/decision history retained.
